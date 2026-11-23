from __future__ import annotations

import ipaddress
import json
import secrets
import socket
import time
from io import BytesIO
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse
from pydantic import BaseModel
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from ..auth import get_current_user, project_editor_scope, project_reviewer_scope, project_scope
from ..config import settings
from ..db import get_db
from ..excel import export_testcases, import_testcases
from ..llm import LLMError, LLMUnavailable, extract_headings, generate_testcases, heading_alignment, local_split_requirements, relevance_coverage, split_requirements
from ..logic import generate_artifact, next_numeric_id, now_label, parse_openapi, uid
from ..case_engine_local import STRATEGY_CN, generate as local_generate
from ..case_runner import TOKENS as case_runner_tokens, probe_sample, run_case as run_api_case
from ..models import Project, Requirement, RequirementFile, User
from ..parsing import SUPPORTED_EXTENSIONS, extract_text, safe_filename
from ..response import ok
from ..schemas import (
    AgentCaseGenerateRequest, ApiDefCreate, ApiSampleRequest, ApiSend, AppRunRequest, CaseRunRequest, ElementCreate, FlowSave, GenerateCasesRequest, GenerateRequest,
    ImportYaml, RecorderStepIn, ReviewDecision, ReviewSubmit, RunRequest, ScriptCreate, ScriptUpdate, SplitConfirm,
    SuiteCreate, TestCaseCreate, TestCaseUpdate,     ToolRun, YamlSave, RequirementCreate, RequirementUpdate,     UiBatchRequest, UiCompileRequest, UiRunOneRequest, UiRunRequest,
)
from .. import ui_media
from ..store import store
from ..trace_models import TraceApi

router = APIRouter()

UPLOAD_ROOT = Path(settings.upload_dir).resolve()


def project(db: Session, pid: str) -> Project:
    item = db.get(Project, pid)
    if not item:
        raise HTTPException(404, "项目不存在")
    return item


def must_doc(collection: str, doc_id: str, pid: str) -> dict[str, Any]:
    item = store.get(collection, doc_id, pid)
    if not item:
        raise HTTPException(404, f"{collection} 不存在: {doc_id}")
    return item


def iso(value: Any) -> str:
    return value.strftime("%Y-%m-%d %H:%M") if value else ""


def new_requirement_id(db: Session) -> str:
    items = db.scalars(select(Requirement.id)).all()
    return f"REQ-{next_numeric_id([{'id': item} for item in items], 'id', 'REQ'):03d}"


def requirement_public(requirement: Requirement, db: Session) -> dict[str, Any]:
    files = db.scalars(
        select(RequirementFile).where(RequirementFile.requirement_id == requirement.id).order_by(RequirementFile.created_at)
    ).all()
    return {
        "id": requirement.id,
        "projectId": requirement.project_id,
        "parentId": requirement.parent_id,
        "kind": requirement.kind,
        "title": requirement.title,
        "priority": requirement.priority,
        "status": requirement.status,
        "owner": requirement.owner_name,
        "version": requirement.version,
        "description": requirement.description,
        "docName": requirement.doc_name,
        "points": requirement.points or [],
        "prototype": requirement.prototype,
        "apiYaml": requirement.api_yaml,
        "generations": requirement.generations or [],
        "splitStatus": requirement.split_status,
        "splitProposal": requirement.split_proposal,
        "createdAt": iso(requirement.created_at),
        "updatedAt": iso(requirement.updated_at),
        "files": [
            {
                "id": file.id,
                "filename": file.filename,
                "size": file.size,
                "parseStatus": file.parse_status,
                "createdAt": iso(file.created_at),
            }
            for file in files
        ],
    }


def requirement_text(requirement: Requirement, db: Session) -> str:
    files = db.scalars(
        select(RequirementFile).where(RequirementFile.requirement_id == requirement.id)
    ).all()
    parts = [requirement.title, requirement.description, *[file.parsed_text for file in files]]
    parts.extend(str(point) for point in (requirement.points or []))
    return "\n\n".join(part for part in parts if part).strip()


# ---------------- requirements ----------------
@router.get("/requirements")
def list_requirements(
    pid: str = Depends(project_scope), db: Session = Depends(get_db)
) -> dict[str, Any]:
    items = db.scalars(
        select(Requirement).where(Requirement.project_id == pid).order_by(Requirement.created_at)
    ).all()
    return ok([requirement_public(item, db) for item in items])


@router.get("/requirements/{requirement_id}")
def get_requirement(
    requirement_id: str, pid: str = Depends(project_scope), db: Session = Depends(get_db)
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    return ok(requirement_public(requirement, db))


@router.post("/requirements")
def create_requirement(
    body: RequirementCreate,
    pid: str = Depends(project_editor_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = Requirement(
        id=new_requirement_id(db),
        project_id=pid,
        kind="main",
        title=body.title,
        priority=body.priority,
        status="待解析",
        owner_name=body.owner or user.name,
        description=body.description,
        doc_name=body.docName,
        points=[],
        generations=[],
    )
    db.add(requirement)
    db.commit()
    return ok(requirement_public(requirement, db))


@router.put("/requirements/{requirement_id}")
def update_requirement(
    requirement_id: str,
    body: RequirementUpdate,
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    if body.title is not None:
        if not body.title.strip():
            raise HTTPException(400, "需求名称不能为空")
        requirement.title = body.title.strip()
    if body.priority is not None:
        requirement.priority = body.priority
    if body.status is not None:
        requirement.status = body.status
    if body.owner is not None:
        requirement.owner_name = body.owner
    if body.description is not None:
        requirement.description = body.description
    db.commit()
    return ok(requirement_public(requirement, db))


@router.post("/requirements/upload")
def upload_requirements(
    files: list[UploadFile] = File(...),
    title: str = Form(""),
    pid: str = Depends(project_editor_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    if not files:
        raise HTTPException(400, "请选择至少一个文件")
    requirement = Requirement(
        id=new_requirement_id(db),
        project_id=pid,
        kind="main",
        title=title.strip() or Path(files[0].filename or "需求").stem,
        priority="P1",
        status="解析中",
        owner_name=user.name,
        description="",
        points=[],
        generations=[],
        split_status="待拆分",
    )
    db.add(requirement)
    db.flush()
    folder = UPLOAD_ROOT / pid / requirement.id
    folder.mkdir(parents=True, exist_ok=True)
    total_bytes = 0
    parsed_parts = []
    for upload in files:
        filename = safe_filename(upload.filename or "document")
        suffix = Path(filename).suffix.lower()
        if suffix not in SUPPORTED_EXTENSIONS:
            raise HTTPException(400, f"不支持的文件类型：{filename}")
        content = upload.file.read()
        total_bytes += len(content)
        if total_bytes > settings.max_upload_mb * 1024 * 1024:
            raise HTTPException(413, f"文件总大小超过 {settings.max_upload_mb}MB")
        stored = folder / f"{secrets.token_hex(8)}{suffix}"
        stored.write_bytes(content)
        try:
            parsed = extract_text(stored, filename)
            status = "已解析"
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from exc
        except Exception as exc:  # noqa: BLE001 - parser failures must be visible
            parsed = ""
            status = "解析失败"
            print(f"[parse] {filename}: {exc}")
        parsed_parts.append(parsed)
        db.add(RequirementFile(
            id=f"RF-{secrets.token_hex(6)}",
            requirement_id=requirement.id,
            filename=filename,
            stored_path=str(stored.relative_to(UPLOAD_ROOT)),
            mime=upload.content_type or "",
            size=len(content),
            parsed_text=parsed,
            parse_status=status,
        ))
    requirement.doc_name = files[0].filename
    requirement.description = "\n\n".join(part for part in parsed_parts if part)[:20000]
    requirement.status = "已解析"
    db.commit()
    return ok(requirement_public(requirement, db))


@router.get("/requirements/{requirement_id}/files/{file_id}")
def download_requirement_file(
    requirement_id: str,
    file_id: str,
    pid: str = Depends(project_scope),
    db: Session = Depends(get_db),
) -> StreamingResponse:
    file = db.scalar(select(RequirementFile).where(
        RequirementFile.id == file_id, RequirementFile.requirement_id == requirement_id
    ))
    if not file:
        raise HTTPException(404, "文件不存在")
    requirement = db.get(Requirement, requirement_id)
    if not requirement or requirement.project_id != pid:
        raise HTTPException(404, "文件不存在")
    path = (UPLOAD_ROOT / file.stored_path).resolve()
    if UPLOAD_ROOT not in path.parents or not path.exists():
        raise HTTPException(404, "文件已丢失")
    return StreamingResponse(
        BytesIO(path.read_bytes()),
        media_type=file.mime or "application/octet-stream",
        headers={"Content-Disposition": f'attachment; filename="{file.filename}"'},
    )


@router.get("/requirements/{requirement_id}/files/{file_id}/text")
def requirement_file_text(
    requirement_id: str,
    file_id: str,
    pid: str = Depends(project_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    file = db.scalar(
        select(RequirementFile).where(RequirementFile.id == file_id, RequirementFile.requirement_id == requirement_id)
    )
    if not requirement or not file:
        raise HTTPException(404, "文件不存在")
    return ok({"filename": file.filename, "text": file.parsed_text[:50000], "parseStatus": file.parse_status})


@router.delete("/requirements/{requirement_id}")
def delete_requirement(
    requirement_id: str,
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    db.delete(requirement)
    db.commit()
    return ok(None)


@router.post("/requirements/{requirement_id}/generate")
def generate_requirement(
    requirement_id: str,
    body: GenerateRequest,
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    current = {
        "id": requirement.id,
        "version": requirement.version,
        "title": requirement.title,
        "prototype": requirement.prototype,
        "apiYaml": requirement.api_yaml,
        "generations": requirement.generations or [],
    }
    result = generate_artifact(current, body.kind)
    requirement.version = current["version"]
    requirement.prototype = current["prototype"]
    requirement.api_yaml = current["apiYaml"]
    requirement.generations = current["generations"]
    db.commit()
    return ok(result)


@router.put("/requirements/{requirement_id}/prototype")
def save_prototype(
    requirement_id: str,
    prototype: dict[str, Any],
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    requirement.prototype = prototype
    db.commit()
    return ok(requirement_public(requirement, db))


@router.put("/requirements/{requirement_id}/yaml")
def save_yaml(
    requirement_id: str,
    body: YamlSave,
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    requirement.api_yaml = body.yaml
    db.commit()
    return ok(requirement_public(requirement, db))


@router.post("/requirements/{requirement_id}/split")
def split_requirement(
    requirement_id: str,
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    requirement = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not requirement:
        raise HTTPException(404, "需求不存在")
    text = requirement_text(requirement, db)
    if len(text) < 40:
        raise HTTPException(400, "需求内容太少，无法拆分")
    local_children = local_split_requirements(requirement.title, text)
    headings = extract_headings(text, requirement.title)
    mode = "local"
    try:
        children = split_requirements(requirement.title, text)
        mode = "ai"
        if local_children and relevance_coverage(children, text) < 0.45:
            children = local_children
            mode = "local"
        elif headings and heading_alignment(children, headings) < max(1, len(children) // 2):
            children = local_children
            mode = "local"
    except (LLMUnavailable, LLMError):
        if not local_children:
            requirement.split_status = "拆分失败"
            db.commit()
            raise HTTPException(502, "模型不可用，且文档没有可提取的章节")
        children = local_children
        mode = "local"
    requirement.split_status = "待确认"
    requirement.split_proposal = {"children": children, "mode": mode}
    db.commit()
    return ok(requirement_public(requirement, db))


@router.post("/requirements/{requirement_id}/split/confirm")
def confirm_split(
    requirement_id: str,
    body: SplitConfirm,
    pid: str = Depends(project_editor_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    parent = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not parent:
        raise HTTPException(404, "需求不存在")
    if not body.children:
        raise HTTPException(400, "没有可创建的子需求")
    existing = db.scalars(
        select(Requirement).where(Requirement.parent_id == requirement_id)
    ).all()
    for item in existing:
        db.delete(item)
    db.flush()
    created = []
    for child in body.children:
        requirement = Requirement(
            id=new_requirement_id(db),
            project_id=pid,
            parent_id=parent.id,
            kind="sub",
            title=child.title,
            priority=child.priority,
            status="待解析",
            owner_name=parent.owner_name,
            description=child.description,
            points=child.points,
            generations=[],
        )
        db.add(requirement)
        db.flush()
        created.append(requirement_public(requirement, db))
    parent.split_status = "已拆分"
    parent.split_proposal = {"children": [child.model_dump() for child in body.children]}
    db.commit()
    return ok(created)


@router.get("/requirements/{requirement_id}/children")
def list_children(
    requirement_id: str,
    pid: str = Depends(project_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    parent = db.scalar(
        select(Requirement).where(Requirement.id == requirement_id, Requirement.project_id == pid)
    )
    if not parent:
        raise HTTPException(404, "需求不存在")
    children = db.scalars(select(Requirement).where(Requirement.parent_id == requirement_id)).all()
    return ok([requirement_public(item, db) for item in children])


# ---------------- testcases ----------------
@router.get("/testcases")
def list_testcases(
    requirementId: str | None = None,
    includeArchived: bool = False,
    pid: str = Depends(project_scope),
) -> dict[str, Any]:
    """用例列表。默认只返回在册用例。

    去重合并把 294 条副本标了 `archived`，它们仍然留在库里（可回滚、可溯源），
    但列表/导出默认不展示——否则人一打开还是 363 条，去重等于白做。
    需要看全量时传 includeArchived=true。
    """
    items = store.all("testCases", pid)
    if not includeArchived:
        items = [item for item in items if not item.get("archived")]
    if requirementId:
        items = [
            item for item in items
            if item.get("requirementId") == requirementId
            or requirementId in (item.get("relatedRequirementIds") or [])
        ]
    return ok(items)


@router.post("/testcases")
def create_testcase(
    body: TestCaseCreate,
    pid: str = Depends(project_editor_scope),
) -> dict[str, Any]:
    items = store.all("testCases", pid)
    case = {
        "id": f"TC-{next_numeric_id(items, 'id', 'TC')}",
        "projectId": pid,
        **body.model_dump(),
        "status": "草稿",
        "version": "v1",
        "updatedAt": now_label(),
    }
    store.put("testCases", case["id"], case)
    return ok(case)


@router.put("/testcases/{case_id}")
def update_testcase(
    case_id: str,
    body: TestCaseUpdate,
    pid: str = Depends(project_reviewer_scope),
) -> dict[str, Any]:
    case = must_doc("testCases", case_id, pid)
    case.update({key: value for key, value in body.model_dump().items() if value is not None})
    case["projectId"] = pid
    case["updatedAt"] = now_label()
    store.put("testCases", case_id, case)
    return ok(case)


@router.delete("/testcases/{case_id}")
def delete_testcase(case_id: str, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    must_doc("testCases", case_id, pid)
    store.delete("testCases", case_id)
    return ok(None)


@router.post("/testcases/{case_id}/run")
def run_testcase(
    case_id: str,
    body: CaseRunRequest,
    pid: str = Depends(project_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """运行用例。API 用例打到真实 shang-pivot 后端执行；功能用例记录人工执行结果。"""
    case = must_doc("testCases", case_id, pid)
    case_type = case.get("caseType") or ("api" if case.get("relatedApi") else "functional")

    def schema_lookup(path: str, method: str) -> dict[str, Any] | None:
        row = db.scalar(
            select(TraceApi).where(
                TraceApi.project_id == pid, TraceApi.path == path, TraceApi.method == method)
        )
        return (row.request_schema or None) if row else None

    if case_type == "functional":
        # 功能测试用例：人工按步骤执行，记录结论
        if not body.manualVerdict:
            return ok({"mode": "manual", "case": case,
                       "message": "功能测试用例需人工按步骤执行，请在执行面板记录结果"})
        case["lastRun"] = {
            "at": now_label(), "mode": "manual", "verdict": body.manualVerdict,
            "note": body.manualNote or "", "executor": user.name,
        }
        store.put("testCases", case_id, case)
        return ok({"mode": "manual", "lastRun": case["lastRun"], "case": case})

    # API 测试用例：真实执行
    report = run_api_case(case, schema_lookup=schema_lookup, force=body.force)
    report["mode"] = "api"
    case["lastRun"] = {
        "at": now_label(), "mode": "api", "verdict": report.get("verdict", ""),
        "detail": report.get("detail", ""),
        "http": (report.get("actual") or {}).get("http"),
    }
    store.put("testCases", case_id, case)
    report["lastRun"] = case["lastRun"]
    return ok(report)


@router.get("/testcases/engines")
def available_engines(_: User = Depends(get_current_user)) -> dict[str, Any]:
    """返回用例生成引擎及可用性，供前端决定默认引擎与提示。"""
    key = settings.llm_api_key or ""
    placeholder = (not key) or len(key) < 20 or "xxx" in key.lower() or key in {"sk-", "your-key", "test-key"}
    return ok({
        "engines": [
            {
                "value": "internal", "label": "系统内部逻辑",
                "available": True,
                "desc": "基于 PRD 业务规则、负面清单与追溯链本地生成，无需外部 API",
            },
            {
                "value": "external", "label": "外部 AI API",
                "available": not placeholder,
                "desc": f"调用外部大模型（{settings.llm_model}）生成" if not placeholder
                        else "未配置有效的 LLM_API_KEY，当前不可用",
            },
            {
                "value": "agent", "label": "测试工程师 AGENT",
                "available": True,
                "desc": "资深测试工程师方法论驱动：等价类/边界值/状态迁移/并发幂等/安全/数据一致性七类设计，基于 PRD 与真实接口契约建模",
            },
        ],
        "externalReady": not placeholder,
        "model": settings.llm_model,
    })


@router.post("/testcases/agent/generate")
def agent_generate_cases(
    body: AgentCaseGenerateRequest,
    pid: str = Depends(project_editor_scope),
) -> dict[str, Any]:
    """测试工程师 AGENT：按方法论生成详细专业用例。

    requirementId 为空时对全部无用例的需求批量生成；dryRun 只预览不落库。
    设计说明见 docs/traceability/测试工程师AGENT-设计说明.md。
    """
    import subprocess
    import sys
    from pathlib import Path

    backend_dir = Path(__file__).resolve().parents[2]
    cmd = [sys.executable, "-m", "agents.case_agent"]
    if body.requirementId:
        cmd += ["--only", body.requirementId]
    if body.dryRun:
        cmd += ["--dry-run"]
    if body.overwrite:
        cmd += ["--overwrite"]
    proc = subprocess.run(cmd, cwd=backend_dir, capture_output=True, text=True, timeout=300)
    if proc.returncode != 0:
        raise HTTPException(500, f"测试工程师 AGENT 运行失败：{proc.stderr[-500:]}")
    generated = len(store.all("testCases", pid))
    return ok({
        "message": "测试工程师 AGENT 已完成用例生成（状态=待评审）" if not body.dryRun else "预览完成（未落库）",
        "output": proc.stdout[-1500:],
        "totalCases": generated,
    })


@router.post("/testcases/generate")
def generate_cases(
    body: GenerateCasesRequest,
    pid: str = Depends(project_editor_scope),
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    context = body.source
    requirement = None
    if body.requirementId:
        requirement = db.scalar(select(Requirement).where(
            Requirement.id == body.requirementId, Requirement.project_id == pid
        ))
        if not requirement:
            raise HTTPException(404, "需求不存在")
        context = requirement_text(requirement, db)

    # 关联需求（含主需求）：既作为生成上下文，也写入用例的关联字段
    related_ids = list(dict.fromkeys(
        ([body.requirementId] if body.requirementId else []) + list(body.relatedRequirementIds)
    ))
    related_titles: dict[str, str] = {}
    if related_ids:
        rows = db.execute(
            select(Requirement.id, Requirement.title).where(Requirement.id.in_(related_ids))
        ).all()
        related_titles = {r[0]: r[1] for r in rows}
        if related_titles:
            context += "\n\n关联需求：\n" + "\n".join(
                f"- {rid}: {title}" for rid, title in related_titles.items())

    # PRD：内部引擎的核心输入；外部引擎也可作为增强上下文
    prd_doc = None
    if body.requirementId:
        row = db.execute(text(
            "SELECT doc FROM requirement_prd WHERE requirement_id=:rid AND project_id=:pid"
        ), {"rid": body.requirementId, "pid": pid}).fetchone()
        if row:
            prd_doc = row[0]

    if body.engine == "internal":
        drafts = local_generate(
            title=requirement.title if requirement else body.source,
            module_hint=related_titles.get(body.requirementId, ""),
            strategies=body.strategies,
            prd_doc=prd_doc,
            context=context,
        )
        engine_label = "内部逻辑"
    else:
        # 外部 AI：把 PRD 的负面清单与业务规则作为增强上下文注入
        if prd_doc and body.rag:
            s = prd_doc.get("sections", {})
            rules = "\n".join(f"- {r.get('text', '')}" for r in s.get("businessRules", []))
            negs = "\n".join(f"- [{n.get('id')}] {n.get('scenario', '')}"
                             for n in s.get("exceptions", []))
            context += f"\n\n业务规则：\n{rules}\n\n已知负面场景：\n{negs}"
        strategies_cn = "、".join(body.strategies)
        try:
            drafts = generate_testcases(
                f"{body.source}（引擎=外部AI，模型={body.model or 'default'}，策略={strategies_cn}）",
                context,
            )
        except LLMUnavailable as exc:
            raise HTTPException(503, f"外部 AI 不可用：{exc}。可切换到「内部逻辑」引擎。") from exc
        except LLMError as exc:
            raise HTTPException(
                502, f"外部 AI 调用失败（{exc}）。请在生成配置中切换到「系统内部逻辑」引擎。"
            ) from exc
        engine_label = f"外部AI·{body.model or '默认'}"

    # 按策略过滤（外部模型可能不严格遵循，这里强制对齐勾选的策略）
    wanted = {STRATEGY_CN.get(s, s) for s in body.strategies}
    drafts = [d for d in drafts if not wanted or d.get("type") in wanted] or drafts

    start = next_numeric_id(store.all("testCases", pid), "id", "TC")
    return ok([
        {
            "id": f"TC-{start + index}",
            "projectId": pid,
            **draft,
            "source": engine_label,
            "requirementId": body.requirementId or "",
            "relatedRequirementIds": related_ids,
            "relatedRequirementTitles": [related_titles.get(r, r) for r in related_ids],
            "owner": user.name,
            "status": "草稿",
            "version": "v1",
            "updatedAt": now_label(),
        }
        for index, draft in enumerate(drafts)
    ])


@router.post("/testcases/review")
def submit_review(
    body: ReviewSubmit,
    pid: str = Depends(project_editor_scope),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    cases = store.all("testCases", pid)
    for draft in body.cases:
        existing = next(
            (case for case in cases if case.get("module") == draft.get("module") and case.get("title") == draft.get("title")),
            None,
        )
        if existing:
            case_id = existing["id"]
            existing.update({key: value for key, value in draft.items() if key != "id"})
            existing["status"] = "待评审"
            existing["projectId"] = pid
            existing["updatedAt"] = now_label()
            store.put("testCases", case_id, existing)
        else:
            case_id = str(draft.get("id") or uid("TC"))
            store.put("testCases", case_id, {
                **draft, "id": case_id, "projectId": pid, "status": "待评审", "updatedAt": now_label(),
            })
        if not store.get("reviews", case_id, pid):
            store.put("reviews", case_id, {
                "caseId": case_id,
                "projectId": pid,
                "title": draft.get("title", ""),
                "status": "待评审",
                "comments": [{
                    "id": uid("C"), "author": user.name, "content": "AI 生成草稿已提交评审",
                    "time": now_label(), "action": "提交评审",
                }],
            })
    return ok(len(body.cases))


@router.get("/testcases/reviews")
def review_queue(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("reviews", pid))


@router.post("/testcases/reviews/{case_id}")
def review_case(
    case_id: str,
    body: ReviewDecision,
    pid: str = Depends(project_reviewer_scope),
    user: User = Depends(get_current_user),
) -> dict[str, Any]:
    review = must_doc("reviews", case_id, pid)
    review["status"] = body.action
    review.setdefault("comments", []).append({
        "id": uid("C"), "author": user.name, "content": body.comment or (
            "同意，覆盖完整" if body.action == "通过" else "请补充异常场景"
        ), "time": now_label(), "action": body.action,
    })
    store.put("reviews", case_id, review)
    case = store.get("testCases", case_id, pid)
    if case:
        case["status"] = body.action
        store.put("testCases", case_id, case)
    return ok(store.all("reviews", pid))


@router.get("/testcases/export.xlsx")
def export_cases(pid: str = Depends(project_scope)) -> StreamingResponse:
    # 导出只给在册用例：把 294 条副本一起导出，评审方分不清哪条是原始用例
    buffer = export_testcases([c for c in store.all("testCases", pid) if not c.get("archived")])
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": 'attachment; filename="testcases.xlsx"'},
    )


@router.post("/testcases/import.xlsx")
async def import_cases(
    file: UploadFile = File(...),
    pid: str = Depends(project_editor_scope),
) -> dict[str, Any]:
    content = await file.read()
    if len(content) > settings.max_upload_mb * 1024 * 1024:
        raise HTTPException(413, f"文件超过 {settings.max_upload_mb}MB")
    try:
        items, errors = import_testcases(content)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    existing = {case["id"]: case for case in store.all("testCases", pid)}
    created = updated = 0
    for item in items:
        case_id = item.get("id")
        if case_id and case_id in existing:
            existing[case_id].update({**item, "projectId": pid, "updatedAt": now_label()})
            existing[case_id]["id"] = case_id
            store.put("testCases", case_id, existing[case_id])
            updated += 1
        else:
            new_id = case_id if case_id and case_id not in existing else f"TC-{next_numeric_id(store.all('testCases', pid), 'id', 'TC')}"
            store.put("testCases", new_id, {
                **item, "id": new_id, "projectId": pid, "source": "Excel 导入",
                "owner": "", "status": item.get("status") or "待评审", "version": "v1",
                "updatedAt": now_label(),
            })
            created += 1
    return ok({"created": created, "updated": updated, "errors": errors})


# ---------------- api testing ----------------
@router.get("/api-defs")
def list_api_defs(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("apiDefs", pid))


@router.post("/api-defs")
def create_api_def(body: ApiDefCreate, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    item = {
        "id": uid("API"), "projectId": pid, "method": body.method, "path": body.path,
        "summary": body.name, "status": "启用", "source": "手工", "module": body.module, "creator": "",
    }
    store.put("apiDefs", item["id"], item)
    return ok(item)


@router.delete("/api-defs/{api_id}")
def delete_api_def(api_id: str, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    must_doc("apiDefs", api_id, pid)
    store.delete("apiDefs", api_id)
    return ok(None)


@router.post("/api-defs/import")
def import_api_defs(body: ImportYaml, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    parsed = parse_openapi(body.yaml)
    if not parsed:
        raise HTTPException(400, "未从 YAML 中解析到接口定义")
    existing = store.all("apiDefs", pid)
    added = []
    for item in parsed:
        if any(def_item.get("method") == item["method"] and def_item.get("path") == item["path"] for def_item in existing):
            continue
        record = {
            "id": uid("API"), "projectId": pid, "method": item["method"], "path": item["path"],
            "summary": item["summary"] or "导入接口", "status": "待调试",
            "source": "OpenAPI 导入", "module": body.module, "creator": "",
        }
        store.put("apiDefs", record["id"], record)
        added.append(record)
    return ok(added)


def json_value(body: str, path: str) -> Any:
    data = json.loads(body)
    current = data
    for part in path.removeprefix("$.").split("."):
        if not part:
            continue
        if isinstance(current, list):
            current = current[int(part)]
        else:
            current = current[part]
    return current


def evaluate_assertions(assertions: list[dict[str, Any]], status: int, body: str, elapsed_ms: int) -> tuple[int, int]:
    passed = 0
    for assertion in assertions:
        kind = str(assertion.get("type", ""))
        expected = str(assertion.get("expected", ""))
        try:
            if kind == "状态码":
                ok_value = str(status) == expected
            elif kind == "JSONPath":
                ok_value = str(json_value(body, str(assertion.get("expression", "")))) == expected
            elif kind == "响应时间":
                limit = int("".join(ch for ch in expected if ch.isdigit()) or "500")
                ok_value = elapsed_ms < limit
            elif kind == "响应体包含":
                ok_value = expected in body
            else:
                ok_value = False
        except Exception:
            ok_value = False
        passed += 1 if ok_value else 0
    return passed, len(assertions)


def validate_target(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise HTTPException(400, "URL 必须是以 http:// 或 https:// 开头的完整地址")
    if "{{" in url:
        raise HTTPException(400, "URL 仍包含 {{变量}}，请填写可访问的真实地址")
    if settings.allow_private_targets:
        return
    try:
        infos = socket.getaddrinfo(parsed.hostname, None)
    except socket.gaierror as exc:
        raise HTTPException(400, "无法解析目标主机") from exc
    for info in infos:
        address = ipaddress.ip_address(info[4][0])
        if address.is_private or address.is_loopback or address.is_link_local:
            raise HTTPException(400, "当前环境不允许访问内网地址")


@router.post("/api-defs/send")
def send_api_request(body: ApiSend, _: str = Depends(project_scope)) -> dict[str, Any]:
    validate_target(body.url)
    started = time.perf_counter()
    headers = dict(body.headers)
    if body.body:
        headers.setdefault("Content-Type", "application/json")
    if body.auth == "admin":
        headers.setdefault("Authorization", f"Bearer {case_runner_tokens.admin()}")
    elif body.auth == "customer":
        headers.setdefault("Authorization", f"Bearer {case_runner_tokens.c()}")
    try:
        with httpx.Client(timeout=settings.api_test_timeout_seconds, follow_redirects=True) as client:
            response = client.request(
                body.method.upper(),
                body.url,
                content=body.body.encode("utf-8") if body.body else None,
                headers=headers,
            )
    except httpx.HTTPError as exc:
        raise HTTPException(502, f"请求失败：{exc}") from exc
    elapsed_ms = max(1, int((time.perf_counter() - started) * 1000))
    text = response.text
    if isinstance(body.assertions, list) and body.assertions:
        passed, total = evaluate_assertions(body.assertions, response.status_code, text, elapsed_ms)
    else:
        default = [
            {"type": "状态码", "expression": "-", "expected": "200"},
            {"type": "JSONPath", "expression": "$.code", "expected": "0"},
            {"type": "响应时间", "expression": "-", "expected": "< 500ms"},
        ]
        passed, total = evaluate_assertions(default, response.status_code, text, elapsed_ms)
    return ok({
        "status": response.status_code,
        "statusText": response.reason_phrase or "",
        "timeMs": elapsed_ms,
        "sizeKb": round(len(response.content) / 1024, 2),
        "body": text,
        "assertionsPassed": passed,
        "assertionsTotal": total,
    })


@router.post("/api-defs/sample")
def sample_api_request(body: ApiSampleRequest, pid: str = Depends(project_scope), db: Session = Depends(get_db)) -> dict[str, Any]:
    """为调试面板探测真实样本：替换路径占位、按契约构造请求体。"""
    template = body.path
    row = db.scalar(select(TraceApi).where(
        TraceApi.project_id == pid, TraceApi.path == template, TraceApi.method == body.method.upper()))
    schema = (row.request_schema or None) if row else None
    sample = probe_sample(body.method.upper(), template, schema)
    sample["known"] = row is not None
    if row:
        sample["summary"] = row.summary
        sample["service"] = row.service
        sample["requestSchema"] = row.request_schema or {}
        sample["responseSchema"] = row.response_schema or {}
    return ok(sample)


@router.get("/api-suites")
def list_suites(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("suites", pid))


@router.post("/api-suites")
def create_suite(body: SuiteCreate, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    suite = {
        "id": uid("S"), "projectId": pid, "name": body.name, "count": body.count,
        "cron": body.cron, "lastResult": "-", "status": "启用",
    }
    store.put("suites", suite["id"], suite)
    return ok(suite)


@router.post("/api-suites/{suite_id}/run")
def run_suite(suite_id: str, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    suite = must_doc("suites", suite_id, pid)
    suite["lastResult"] = "成功"
    store.put("suites", suite_id, suite)
    return ok(suite)


@router.get("/api-reports")
def list_reports(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("reports", pid))


# ---------------- webui ----------------
@router.get("/ui/pages")
def list_ui_pages(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("uiPages", pid))


@router.get("/ui/elements")
def list_ui_elements(pageId: str | None = None, pid: str = Depends(project_scope)) -> dict[str, Any]:
    items = store.all("uiElements", pid)
    if pageId:
        items = [item for item in items if item.get("pageId") == pageId]
    return ok(items)


@router.post("/ui/elements")
def create_ui_element(body: ElementCreate, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    page = must_doc("uiPages", body.pageId, pid)
    element = {
        "id": uid("E"), "projectId": pid, "pageId": page["id"], "pageName": page["name"],
        "name": body.name, "selectorType": body.selectorType, "selectorValue": body.selectorValue,
    }
    store.put("uiElements", element["id"], element)
    return ok(element)


@router.delete("/ui/elements/{element_id}")
def delete_ui_element(element_id: str, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    must_doc("uiElements", element_id, pid)
    store.delete("uiElements", element_id)
    return ok(None)


@router.get("/ui/scripts")
def list_ui_scripts(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("uiScripts", pid))


@router.post("/ui/scripts")
def create_ui_script(body: ScriptCreate, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    script = {
        "id": uid("US"), "projectId": pid, "name": body.name, "framework": body.framework,
        "content": body.content, "updatedAt": now_label(), "status": "启用",
    }
    store.put("uiScripts", script["id"], script)
    return ok(script)


@router.put("/ui/scripts/{script_id}")
def save_ui_script(script_id: str, body: ScriptUpdate, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    script = must_doc("uiScripts", script_id, pid)
    script["content"] = body.content
    script["updatedAt"] = now_label()
    store.put("uiScripts", script_id, script)
    return ok(script)


def _media_payload(run_id: str, media: dict | None) -> dict[str, Any]:
    """把落盘的步骤截图/视频转成可直接访问的签名 URL。"""
    media = media or {}
    shots = []
    for s in media.get("steps") or []:
        name = (s or {}).get("name")
        if name:
            shots.append({"index": s.get("index"), "name": name,
                          "url": ui_media.media_url(run_id, name)})
    video = media.get("video") or ""
    return {
        "steps": shots,
        "video": video,
        "videoUrl": ui_media.media_url(run_id, video) if video else "",
        "bytes": media.get("bytes") or 0,
    }


def _run_item(doc: dict[str, Any]) -> dict[str, Any]:
    """单条执行记录 → 列表项（兼容历史数据：steps 曾是数字、无媒体）。"""
    rid = doc.get("id") or ""
    raw_steps = doc.get("steps")
    steps = raw_steps if isinstance(raw_steps, list) else []
    media = _media_payload(rid, doc.get("media"))
    verdict = doc.get("verdict") or doc.get("result") or ""
    return {
        "id": rid, "kind": "single",
        "title": doc.get("script") or doc.get("caseTitle") or rid,
        "caseId": doc.get("caseId") or "", "browser": doc.get("browser") or "",
        "result": doc.get("result") or verdict, "verdict": verdict,
        "caseCount": 1,
        "passed": 1 if verdict == "通过" else 0,
        "failed": 1 if verdict == "失败" else 0,
        "shots": len(media["steps"]),
        "hasVideo": bool(media["video"]),
        "media": media,
        "mediaPruned": bool(doc.get("mediaPruned")),
        "time": doc.get("time") or "", "duration": doc.get("duration") or "",
        "startedAtMs": int(doc.get("startedAtMs") or 0),
        "steps": steps,
        "finalUrl": doc.get("finalUrl") or "", "pageText": doc.get("pageText") or "",
        "orderNo": doc.get("orderNo") or "",
        "assertions": int(doc.get("assertions") or 0),
        "assertionsPassed": int(doc.get("assertionsPassed") or 0),
    }


def _batch_item(doc: dict[str, Any]) -> dict[str, Any]:
    """批量执行记录 → 列表项（执行记录里只显示一行，点进去看逐条）。"""
    rid = doc.get("id") or ""
    results = doc.get("results") or []
    shots = sum(len((r.get("media") or {}).get("steps") or []) for r in results)
    has_video = any((r.get("media") or {}).get("video") for r in results)
    failed = int(doc.get("failed") or 0)
    executed = int(doc.get("executed") or len(results))
    running = doc.get("status") == "running"
    verdict = "执行中" if running else ("未执行" if executed == 0 else ("失败" if failed else "通过"))
    return {
        "id": rid, "kind": "batch",
        "title": doc.get("title") or f"批量执行 · {len(results)} 条",
        "caseId": "", "browser": doc.get("browser") or "Chromium(批量)",
        "result": verdict, "verdict": verdict,
        "caseCount": int(doc.get("executed") or len(results)),
        "passed": int(doc.get("passed") or 0), "failed": failed,
        "shots": shots, "hasVideo": has_video,
        "media": {"steps": [], "video": "", "videoUrl": "", "bytes": int(doc.get("mediaBytes") or 0)},
        "mediaPruned": bool(doc.get("mediaPruned")),
        "time": doc.get("startedAt") or "", "duration": f"{doc.get('totalSeconds') or 0}s",
        "startedAtMs": int(doc.get("startedAtMs") or 0),
        "status": doc.get("status") or "finished",
        "steps": [], "finalUrl": "", "pageText": "", "orderNo": "",
        "assertions": sum(int(r.get("assertions") or 0) for r in results),
        "assertionsPassed": sum(int(r.get("assertionsPassed") or 0) for r in results),
    }


@router.get("/ui/runs")
def list_ui_runs(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """执行记录：单条 + 批次合并，按开始时间倒序。

    批量执行只出现一条（kind=batch），点进去是 /ui/batches/{id} 的子页面；
    单条记录在本页展开抽屉（含每步截图与视频）。
    """
    singles = [_run_item(d) for d in store.all("uiRuns", pid)]
    batches = [_batch_item(d) for d in store.all("uiBatches", pid)]
    items = singles + batches

    def sort_key(it: dict[str, Any]):
        return (it.get("startedAtMs") or 0, it.get("time") or "")

    items.sort(key=sort_key, reverse=True)
    total = len(items)
    passed = sum(1 for r in items if r.get("verdict") == "通过")
    failed = sum(1 for r in items if r.get("verdict") == "失败")
    seconds = []
    for r in items:
        d = str(r.get("duration") or "")
        if d.endswith("ms"):
            try:
                seconds.append(float(d[:-2]) / 1000)
            except ValueError:
                pass
        elif d.endswith("s"):
            try:
                seconds.append(float(d[:-1]))
            except ValueError:
                pass
    return ok({
        "items": items,
        "stats": {
            "total": total,
            "passed": passed,
            "failed": failed,
            "avgSeconds": round(sum(seconds) / len(seconds), 1) if seconds else 0,
            "batches": len(batches),
            "singles": len(singles),
        },
        "media": ui_media.stats(),
    })


@router.get("/ui/batches/{batch_id}")
def get_ui_batch(batch_id: str, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """批次详情：一条批次记录点进去的子页面数据（逐条用例 + 每步截图/视频）。"""
    doc = store.get("uiBatches", batch_id, pid)
    if not doc:
        raise HTTPException(404, "批次不存在或已被清理")
    cases = []
    for r in doc.get("results") or []:
        run_id = f"{batch_id}__{r.get('caseId', '')}"
        cases.append({
            "caseId": r.get("caseId", ""), "caseTitle": r.get("caseTitle", ""),
            "module": r.get("module", ""), "pageObject": r.get("pageObject", ""),
            "writeFlow": bool(r.get("writeFlow")), "verdict": r.get("verdict", ""),
            "assertions": int(r.get("assertions") or 0),
            "assertionsPassed": int(r.get("assertionsPassed") or 0),
            "finalUrl": r.get("finalUrl", ""), "pageText": r.get("pageText", ""),
            "orderNos": r.get("orderNos") or [],
            "seconds": r.get("seconds") or 0,
            "steps": r.get("steps") or [],
            "media": _media_payload(run_id, r.get("media")),
        })
    return ok({
        "id": doc.get("id"), "title": doc.get("title"), "status": doc.get("status"),
        "startedAt": doc.get("startedAt"), "totalSeconds": doc.get("totalSeconds"),
        "total": doc.get("total"), "executed": doc.get("executed"),
        "passed": doc.get("passed"), "failed": doc.get("failed"),
        "partial": doc.get("partial"), "skippedCount": doc.get("skippedCount"),
        "passRate": doc.get("passRate"), "writeExecuted": doc.get("writeExecuted"),
        "mediaBytes": doc.get("mediaBytes"), "mediaPruned": bool(doc.get("mediaPruned")),
        "byPageObject": doc.get("byPageObject") or {},
        "failures": doc.get("failures") or [],
        "skippedCases": doc.get("skippedCases") or [],
        "cases": cases,
    })


@router.get("/ui/media/{run_id}/{name}")
def get_ui_media(run_id: str, name: str, k: str = "") -> FileResponse:
    """步骤截图 / 执行视频（签名 URL，无需 Header，供 <img>/<video> 直接加载）。"""
    if not ui_media.verify(run_id, name, k):
        raise HTTPException(403, "媒体链接已过期，请刷新执行记录")
    path = ui_media.file_path(run_id, name)
    if not path:
        raise HTTPException(404, "媒体文件不存在（可能已按容量策略清理）")
    media_type = "image/png" if name.lower().endswith(".png") else (
        "video/webm" if name.lower().endswith(".webm") else "application/octet-stream")
    return FileResponse(path, media_type=media_type,
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/ui/media-stats")
def get_media_stats(_: str = Depends(project_scope)) -> dict[str, Any]:
    """媒体库用量（5GiB 预算 + 现有占用），页面底部展示。"""
    return ok(ui_media.stats())


@router.post("/ui/runs")
def run_ui_script(body: RunRequest, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    script = must_doc("uiScripts", body.scriptId, pid)
    run = {
        "id": uid("UR"), "projectId": pid, "script": script["name"], "browser": body.browser,
        "result": "成功", "shots": 3, "video": True, "time": now_label(), "duration": "36s",
    }
    store.put("uiRuns", run["id"], run)
    return ok(run)


@router.get("/ui/recorder")
def list_recorder_steps(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("recorderSteps", pid))


# ---------------- UI 自动化：编译 → 复用脚本 → 共享浏览器池执行 ----------------
def _all_functional_cases(pid: str, include_archived: bool = False) -> list[dict[str, Any]]:
    return [
        c for c in store.all("testCases", pid)
        if (c.get("caseType") or ("api" if c.get("relatedApi") else "functional")) == "functional"
        and (include_archived or not c.get("archived"))
    ]


@router.post("/ui/compile")
def compile_ui_cases(body: UiCompileRequest, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """把功能测试用例编译成关键字 IR 与可复用 Playwright 脚本，落库到 uiScripts。"""
    from ..ui_step_compiler import compile_batch, to_playwright_script
    cases = _all_functional_cases(pid)
    if body.caseIds:
        wanted = set(body.caseIds)
        cases = [c for c in cases if c.get("id") in wanted]
    if not cases:
        raise HTTPException(404, "没有可编译的功能测试用例")

    result = compile_batch(cases)
    existing = {s.get("caseId") for s in store.all("uiScripts", pid) if s.get("caseId")}
    created = 0
    for ir_case in result["compiled"]:
        if ir_case["caseId"] in existing and not body.overwrite:
            continue
        script = to_playwright_script(ir_case)
        doc = {
            "id": f"US-{ir_case['caseId']}", "projectId": pid,
            "caseId": ir_case["caseId"], "caseTitle": ir_case["caseTitle"],
            "name": ir_case["caseTitle"][:80], "framework": "Playwright · 关键字驱动",
            "content": script, "ir": ir_case,
            "status": "启用" if ir_case["summary"]["ready"]
                      else ("部分可执行" if ir_case["summary"]["uiRunnable"] else "待补全"),
            "updatedAt": now_label(),
        }
        store.put("uiScripts", doc["id"], doc)
        created += 1
    return ok({
        "stats": result["stats"], "created": created,
        "skipped": len(result["compiled"]) - created,
        "details": [
            {"caseId": c["caseId"], "title": c["caseTitle"], **c["summary"]}
            for c in result["compiled"]
        ],
    })


@router.get("/ui/compile/{case_id}")
def get_compiled_case(case_id: str, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """查看单条用例的编译结果（IR + 可复用脚本）。"""
    doc = store.get("uiScripts", f"US-{case_id}", pid)
    if not doc:
        raise HTTPException(404, "该用例尚未编译，请先执行编译")
    return ok(doc)


@router.get("/ui/cases")
def ui_case_index(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """单条执行用例索引：编译一遍拿到 PO/可执行性/是否写操作，供页面选选哪条跑。

    编译是纯字符串处理（363 条约 30ms），不必落库，也就不必先点「编译全部」。
    """
    from ..ui_batch_runner import _functional_cases
    from ..ui_step_compiler import compile_batch

    compiled = compile_batch(_functional_cases(pid))["compiled"]
    items = [{
        "caseId": c["caseId"],
        "title": c["caseTitle"],
        "module": c.get("module", ""),
        "pageObject": c["summary"]["pageObject"],
        "ready": c["summary"]["ready"],
        "uiRunnable": c["summary"].get("uiRunnable", False),
        "writeFlow": c["summary"].get("writeFlow", False),
        "totalSteps": c["summary"]["total"],
        "executable": c["summary"]["executable"],
        "assertions": c["summary"].get("assertions", 0),
        # 绑定信息：来源/页面/风险，供列表显示"这条用例到底测哪个页面"
        "binding": c["summary"].get("binding") or {},
    } for c in compiled]
    return ok({
        "total": len(items),
        "ready": sum(1 for x in items if x["ready"]),
        "writeFlows": sum(1 for x in items if x["writeFlow"]),
        "cases": items,
    })


# ---------------------------------------------------------------- 用例去重合并
@router.get("/ui/dedup")
def ui_dedup_preview(limit: int = 200, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """去重体检：363 条里有多少是同一件事被登记多次，合并后会剩多少。

    只读。返回分组明细（哪条当主用例、并掉哪些、为什么选它），供人工抽查后再执行。
    """
    from .. import ui_case_dedup

    cases = _all_functional_cases(pid, include_archived=True)
    p = ui_case_dedup.plan(cases)
    items = p.pop("items")
    return ok({**p, "items": items[:max(1, limit)]})


@router.post("/ui/dedup/apply")
def ui_dedup_apply(body: dict[str, Any] | None = None, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    """执行合并：保留主用例，副本标记 archived+duplicateOf，需求/模块聚合到主用例。

    可只合并选定的组（body={"primaryIds": [...]}），默认合并全部重复组。
    """
    from .. import ui_case_dedup

    body = body or {}
    primary_ids = body.get("primaryIds") or None
    cases = _all_functional_cases(pid, include_archived=True)
    report, touched = ui_case_dedup.apply(cases, pid, ids=primary_ids)
    for doc in touched:
        store.put("testCases", doc["id"], doc)
    return ok(report)


@router.post("/ui/dedup/restore")
def ui_dedup_restore(pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    """回滚去重：清掉归档标记，恢复全部用例为在册状态。"""
    from .. import ui_case_dedup

    cases = _all_functional_cases(pid, include_archived=True)
    report, touched = ui_case_dedup.restore(cases)
    for doc in touched:
        store.put("testCases", doc["id"], doc)
    return ok(report)


@router.get("/ui/dedup/groups/{case_id}")
def ui_dedup_group(case_id: str, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """反查：某条被合并的用例归到了哪条主用例；主用例又吸收了哪些副本。"""
    from .. import ui_case_dedup

    cases = _all_functional_cases(pid, include_archived=True)
    by_id = {c.get("id"): c for c in cases}
    case = by_id.get(case_id)
    if not case:
        raise HTTPException(404, "用例不存在")
    primary_id = case.get("duplicateOf") or case_id
    primary = by_id.get(primary_id) or {}
    members = [c for c in cases
               if c.get("id") == primary_id
               or c.get("duplicateOf") == primary_id
               or (case.get("duplicateOf") is None and ui_case_dedup.normalize(c.get("title") or "")
                   == ui_case_dedup.normalize(case.get("title") or ""))]
    return ok({
        "caseId": case_id,
        "isPrimary": primary_id == case_id,
        "primary": {"caseId": primary_id, "title": primary.get("title", ""),
                    "module": primary.get("module", "")},
        "members": [{"caseId": c.get("id"), "module": c.get("module", ""),
                     "requirementId": c.get("requirementId", ""),
                     "archived": bool(c.get("archived"))} for c in members],
        "requirementIds": primary.get("relatedRequirementIds") or [],
        "modules": primary.get("relatedModules") or [],
    })


# ---------------------------------------------------------------- 用例↔页面绑定
@router.get("/ui/bindings")
def ui_bindings_list(kind: str | None = None, q: str | None = None,
                     onlyNeedsReview: bool = False, limit: int = 500, offset: int = 0,
                     pid: str = Depends(project_scope)) -> dict[str, Any]:
    """用例-页面绑定体检：每条用例当前绑在哪、可不可跑、为什么不可跑。

    与 /ui/cases 的区别：这里给的是"绑定视角"，包含建议、置信度、缺口原因，
    供绑定体检页批量确认；/ui/cases 给的是"执行视角"。
    """
    from .. import ui_bindings
    from ..ui_batch_runner import _functional_cases

    pages = [p for p in ui_bindings.load_pages() if p.get("projectId") == pid] or ui_bindings.load_pages()
    cases = _functional_cases(pid)

    rows: list[dict[str, Any]] = []
    by_kind: dict[str, int] = {}
    confirmed = 0
    for c in cases:
        sug = ui_bindings.suggest(c, pages)
        res = ui_bindings.resolve(c, pages)
        # 已有显式绑定时，以生效绑定为准；否则展示规则建议
        effective = res if res.get("source") == ui_bindings.SOURCE_HUMAN else sug
        k = effective.get("kind", ui_bindings.KIND_UNBOUND)
        by_kind[k] = by_kind.get(k, 0) + 1
        if res.get("source") == ui_bindings.SOURCE_HUMAN:
            confirmed += 1
        rows.append({
            "caseId": c.get("id"), "title": c.get("title", ""), "module": c.get("module", ""),
            "priority": c.get("priority", ""), "status": c.get("status", ""),
            "kind": k, "kindLabel": ui_bindings.KIND_LABEL.get(k, k),
            "pageId": effective.get("pageId", ""), "pageName": effective.get("pageName", ""),
            "pagePath": effective.get("pagePath", ""), "poName": effective.get("poName", ""),
            "source": res.get("source", ui_bindings.SOURCE_NONE),
            "confidence": effective.get("confidence", 0),
            "needsReview": res.get("needsReview", True),
            "reason": effective.get("reason", ""),
            "suggestPageId": sug.get("pageId", ""), "suggestPageName": sug.get("pageName", ""),
            "suggestPoName": sug.get("poName", ""),
            "runnable": k == ui_bindings.KIND_UI_PO and bool(effective.get("poName")),
        })

    if kind:
        rows = [r for r in rows if r["kind"] == kind]
    if onlyNeedsReview:
        rows = [r for r in rows if r["needsReview"]]
    if q:
        needle = q.strip().lower()
        rows = [r for r in rows if needle in (r["title"] + r["caseId"] + r["module"]).lower()]
    total = len(rows)
    bindable = sum(1 for r in rows if r["kind"] in (
        ui_bindings.KIND_UI_PO, ui_bindings.KIND_UI_NO_PO, ui_bindings.KIND_UI_AMBIGUOUS))
    page_rows = [{"pageId": p["id"], "name": p["name"], "path": p["path"],
                  "domain": p.get("domain") or "",
                  "pos": ui_bindings.PAGE_POS.get(p["path"], [])} for p in pages]
    page_rows.sort(key=lambda x: (x["domain"], x["path"]))
    return ok({
        "summary": {
            "total": len(cases), "byKind": by_kind, "confirmed": confirmed,
            "bindable": bindable,
            "needsReview": sum(1 for r in rows if r["needsReview"]),
            "runnable": sum(1 for r in rows if r["runnable"]),
        },
        "total": total, "items": rows[offset:offset + limit], "pages": page_rows,
    })


class UiBindingItem(BaseModel):
    caseId: str
    pageId: str | None = None
    # 一页多流程时由人指定；不传则按标题意图推导
    poName: str | None = None


class UiBindingWrite(BaseModel):
    items: list[UiBindingItem]
    clear: bool = False


@router.get("/ui/bindings/options")
def ui_binding_options(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """绑定选择器用的轻量选项：页面清单 + 页面→PO 映射 + PO 全集。"""
    from .. import ui_bindings
    from ..ui_page_objects import po_names

    pages = [p for p in ui_bindings.load_pages() if p.get("projectId") == pid] or ui_bindings.load_pages()
    rows = [{"pageId": p["id"], "name": p["name"], "path": p["path"],
             "domain": p.get("domain") or "", "pos": ui_bindings.PAGE_POS.get(p["path"], [])}
            for p in pages]
    rows.sort(key=lambda x: (x["domain"], x["path"]))
    return ok({"pages": rows, "poNames": po_names()})


@router.post("/ui/bindings")
def ui_bindings_write(body: UiBindingWrite, pid: str = Depends(project_editor_scope),
                      user: User = Depends(get_current_user)) -> dict[str, Any]:
    """人工确认/修改用例-页面绑定。

    写入的是用例文档本身（pageId + bindingSource=human），因此：
    - 下次编译立刻按新绑定推导 PO，不需要重新"生成脚本"；
    - 走的是普通 PUT 同样的 JSONB 存储，需求/用例导出也带着绑定；
    - 绑定变更记 audit，可回答"谁在什么时候改的"。
    """
    from .. import ui_bindings

    pages = ui_bindings.load_pages()
    by_id = {p["id"]: p for p in pages}
    updated, errors = [], []
    for item in body.items:
        case = store.get("testCases", item.caseId, pid)
        if not case:
            errors.append({"caseId": item.caseId, "error": "用例不存在"})
            continue
        if body.clear or not item.pageId:
            case["pageId"] = ""
            case["pagePath"] = ""
            case["pageName"] = ""
            case["poName"] = ""
            case["bindingSource"] = ui_bindings.SOURCE_NONE
            case.pop("bindingConfirmedAt", None)
        else:
            page = by_id.get(item.pageId)
            if not page:
                errors.append({"caseId": item.caseId, "error": f"页面不存在: {item.pageId}"})
                continue
            case["pageId"] = page["id"]
            case["pagePath"] = page["path"]
            case["pageName"] = page["name"]
            if item.poName:
                allowed = ui_bindings.PAGE_POS.get(page["path"], [])
                if item.poName not in allowed:
                    errors.append({"caseId": item.caseId,
                                   "error": f"流程 {item.poName} 不属于页面 {page['name']}"})
                    continue
                case["poName"] = item.poName
            else:
                case["poName"] = ""
            case["bindingSource"] = ui_bindings.SOURCE_HUMAN
            case["bindingConfirmedAt"] = now_label()
            case["bindingConfirmedBy"] = getattr(user, "email", "") or str(getattr(user, "id", ""))
        case["updatedAt"] = now_label()
        store.put("testCases", item.caseId, case)
        updated.append(item.caseId)

    return ok({"updated": len(updated), "caseIds": updated, "errors": errors})


@router.get("/ui/coverage/pages")
def ui_coverage_pages(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """页面视角反查：这个页面被哪些用例覆盖、能不能自动化。"""
    from .. import ui_bindings
    from ..ui_batch_runner import _functional_cases

    pages = [p for p in ui_bindings.load_pages() if p.get("projectId") == pid] or ui_bindings.load_pages()
    cases = _functional_cases(pid)
    rows = ui_bindings.page_coverage(pages, cases)
    return ok({
        "total": len(rows),
        "pagesWithPo": sum(1 for r in rows if r["poNames"]),
        "covered": sum(1 for r in rows if r["total"] > 0),
        "items": rows,
    })


@router.get("/ui/quality")
def ui_quality(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """四层质量指标。回答"这个通过率能不能信"，而不只是给一个百分比。

    L1 有效性（闸门）：绑定确认率、断言密度、样本量——决定结论能不能成立
    L2 结果：原始通过率 / 有效通过率（剔除绑定错误与未执行）
    L3 稳定：flake 率（同用例多次执行结果不一致）
    L4 覆盖：页面覆盖、用例绑定覆盖
    """
    import re as _re
    from collections import Counter, defaultdict

    from .. import ui_bindings
    from ..ui_batch_runner import _functional_cases
    from ..ui_step_compiler import compile_batch

    pages = [p for p in ui_bindings.load_pages() if p.get("projectId") == pid] or ui_bindings.load_pages()
    cases = _functional_cases(pid)
    compiled = compile_batch(cases)["compiled"]
    by_case = {c["caseId"]: c for c in compiled}

    # ---- L1 有效性
    kinds = Counter()
    confirmed = 0
    bindable = 0
    for c in cases:
        sug = ui_bindings.suggest(c, pages)
        res = ui_bindings.resolve(c, pages)
        kind = res.get("kind") if res.get("source") == ui_bindings.SOURCE_HUMAN else sug.get("kind")
        kinds[kind] += 1
        if kind in (ui_bindings.KIND_UI_PO, ui_bindings.KIND_UI_NO_PO, ui_bindings.KIND_UI_AMBIGUOUS):
            bindable += 1
        if res.get("source") == ui_bindings.SOURCE_HUMAN:
            confirmed += 1
    titles = Counter((c.get("title") or "").strip() for c in cases)
    unique_titles = len(titles)
    dup_cases = sum(v for v in titles.values() if v > 1)
    ready_cases = [c for c in compiled if c["summary"]["ready"]]
    assert_total = sum(c["summary"].get("assertions", 0) for c in ready_cases)
    density = round(assert_total / len(ready_cases), 2) if ready_cases else 0
    risks = Counter((c["summary"].get("binding") or {}).get("risk", "none") for c in compiled)

    # ---- 执行记录（单条 + 批次明细），按 caseId 聚合
    runs: list[dict[str, Any]] = [r for r in store.all("uiRuns", pid) if r.get("caseId")]
    for b in store.all("uiBatches", pid):
        for r in (b.get("results") or []):
            runs.append({**r, "batchId": b.get("id")})
    executed = len(runs)
    passed = sum(1 for r in runs if (r.get("verdict") or r.get("result")) == "通过")
    failed_runs = [r for r in runs if (r.get("verdict") or r.get("result")) == "失败"]

    # 有效执行 = 绑定到有 PO 的页面、且不是"规则认为不该走 UI"的
    effective_runs = []
    ineffective_runs = []
    for r in runs:
        c = by_case.get(r.get("caseId"))
        risk = ((c or {}).get("summary", {}).get("binding") or {}).get("risk", "none")
        (ineffective_runs if risk in ("mismatch", "blocked_no_po", "stale_po") else effective_runs).append(r)
    eff_passed = sum(1 for r in effective_runs if (r.get("verdict") or r.get("result")) == "通过")

    # 失败归因
    attr = Counter()
    for r in failed_runs:
        detail = ""
        for s in r.get("steps") or []:
            if s.get("status") == "failed":
                detail = str(s.get("detail") or "")
                break
        if not detail:
            attr["无明细"] += 1
        elif "找不到元素" in detail:
            attr["定位器失效"] += 1
        elif "不可交互" in detail or "遮挡" in detail:
            attr["元素被遮挡"] += 1
        elif _re.search(r"未出现预期文本|不应包含|URL 应|数量|未匹配到正则", detail):
            attr["断言不成立"] += 1
        elif "Timeout" in detail or "timeout" in detail:
            attr["超时"] += 1
        else:
            attr["其他"] += 1

    # ---- L3 稳定：同用例多次执行结果不一致
    per_case: dict[str, list[str]] = defaultdict(list)
    for r in runs:
        per_case[r["caseId"]].append(str(r.get("verdict") or r.get("result")))
    multi = {k: v for k, v in per_case.items() if len(v) > 1}
    flaky = {k: v for k, v in multi.items() if len(set(v)) > 1}
    durations = sorted(int(r.get("durationMs") or 0) for r in runs if r.get("durationMs"))

    def pct(p: float) -> int:
        return durations[min(len(durations) - 1, int(len(durations) * p))] if durations else 0

    # ---- L4 覆盖
    coverage_rows = ui_bindings.page_coverage(pages, cases)
    pages_with_po = sum(1 for r in coverage_rows if r["poNames"])
    covered_pages = sum(1 for r in coverage_rows if r["total"] > 0)

    # ---- 闸门：结论能不能对外说。
    # 分母用 bindable（需要绑页面的用例：ui_po + ui_page_no_po），
    # 接口/人工类用例本来就不该绑页面，算进去会稀释指标。
    confirm_rate = (confirmed / bindable * 100) if bindable else 0
    gates = []
    if executed < 20:
        gates.append(f"样本不足：仅 {executed} 次执行（建议 ≥20）")
    if density < 1:
        gates.append(f"断言密度过低：{density} 个/条（建议 ≥1）")
    if confirm_rate < 80:
        gates.append(
            f"绑定确认率 {confirm_rate:.1f}%（{confirmed}/{bindable}）："
            "多数用例仍按规则猜测的绑定执行，通过率不能作为结论"
        )
    trusted = not gates

    return ok({
        "generatedAt": now_label(),
        "gates": {"trusted": trusted, "reasons": gates},
        "l1Effectiveness": {
            "totalCases": len(cases), "uniqueTitles": unique_titles,
            "duplicateCases": dup_cases,
            "duplicateRate": round(dup_cases / len(cases) * 100, 1) if cases else 0,
            "byKind": {ui_bindings.KIND_LABEL.get(k, k): v for k, v in kinds.items()},
            "bindable": bindable, "confirmed": confirmed,
            "bindingConfirmedRate": round(confirm_rate, 1),
            "readyCases": len(ready_cases), "assertionDensity": density,
            "riskDistribution": dict(risks),
        },
        "l2Outcome": {
            "executed": executed,
            "rawPassRate": round(passed / executed * 100, 1) if executed else 0,
            "effectiveExecuted": len(effective_runs),
            "effectivePassRate": round(eff_passed / len(effective_runs) * 100, 1) if effective_runs else 0,
            "ineffectiveExecuted": len(ineffective_runs),
            "byVerdict": dict(Counter(str(r.get("verdict") or r.get("result")) for r in runs)),
            "failureAttribution": dict(attr),
            "durationP50": pct(0.5), "durationP95": pct(0.95),
        },
        "l3Stability": {
            "casesExecuted": len(per_case), "casesMultiRun": len(multi),
            "flakyCases": len(flaky), "flakeRate": round(len(flaky) / len(multi) * 100, 1) if multi else 0,
            "flakyDetail": [{"caseId": k, "verdicts": dict(Counter(v))} for k, v in list(flaky.items())[:10]],
        },
        "l4Coverage": {
            "pagesTotal": len(coverage_rows), "pagesWithPo": pages_with_po,
            "pagesCoveredByCases": covered_pages,
            "pagePoRate": round(pages_with_po / len(coverage_rows) * 100, 1) if coverage_rows else 0,
            "pageCoveredRate": round(covered_pages / len(coverage_rows) * 100, 1) if coverage_rows else 0,
        },
    })


@router.post("/ui/run-one")
def ui_run_one(body: UiRunOneRequest, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    """单条用例真实执行：临时编译这条 → 独占浏览器跑完 → 返回逐步证据。

    - 只跑一条，同步返回（5~15s），页面可直接渲染每步状态；
    - 独占浏览器池：Playwright sync API 与线程绑定，复用全局池会跨线程崩；
    - 写操作用例（下单/支付）必须 force=True，防页面误点产生真实订单；
    - 每一步截图 + 整段视频落盘（默认保存），返回签名 URL 供前端直接播放。
    """
    from ..ui_batch_runner import _order_no_for, _pay_id
    from ..ui_executor import BrowserPool, run_compiled
    from ..ui_step_compiler import compile_case, to_playwright_script

    case = must_doc("testCases", body.caseId, pid)
    ir = compile_case(case)
    summary = ir["summary"]
    if not summary.get("uiRunnable"):
        raise HTTPException(400, "这条用例没有可执行的 UI 步骤（只有业务规则描述），无法驱动浏览器")
    if summary.get("writeFlow") and not body.force:
        raise HTTPException(409, "这条用例会真实下单/支付，请勾选「允许真实写操作」后再执行")

    run_id = uid("UR")
    started_ms = int(time.time() * 1000)
    pool = BrowserPool(isolated=True)
    try:
        report = run_compiled(ir, delay_ms=body.delayMs or 300, pool=pool, run_id=run_id)
    finally:
        try:
            pool.close()
        except Exception:  # noqa: BLE001
            pass

    # 写操作的证据链：最终落在 /pay/{id} → 回查 commerce.order.order_no
    order_no = ""
    if summary.get("writeFlow"):
        order_no = _order_no_for(_pay_id(report.get("finalUrl", "")))

    verdict = report["verdict"]
    media = _media_payload(run_id, report.get("media"))
    store.put("uiRuns", run_id, {
        "id": run_id, "projectId": pid, "kind": "single",
        "script": ir["caseTitle"][:80], "caseId": ir["caseId"],
        "caseTitle": ir["caseTitle"], "module": ir.get("module", ""),
        "pageObject": summary.get("pageObject", ""),
        "browser": "Chromium(单条执行)",
        "result": "成功" if verdict == "通过" else verdict,
        "verdict": verdict, "steps": report["steps"],
        "assertions": report.get("assertions", 0),
        "assertionsPassed": report.get("assertionsPassed", 0),
        "finalUrl": report.get("finalUrl", ""), "pageText": report.get("pageText", ""),
        "orderNo": order_no, "writeFlow": bool(summary.get("writeFlow")),
        "screenshot": report.get("screenshot", ""),
        "media": report.get("media") or {},
        "startedAtMs": started_ms,
        "duration": f"{report['durationMs']}ms", "durationMs": report["durationMs"],
        "time": now_label(),
    })
    case["lastRun"] = {
        "at": now_label(), "mode": "ui", "verdict": verdict,
        "detail": f"UI 自动执行 {len(report['steps'])} 步 · 断言 {report['assertionsPassed']}/{report['assertions']}",
        "caseId": ir["caseId"],
    }
    store.put("testCases", body.caseId, case)

    prune = ui_media.prune_and_mark()
    return ok({
        "runId": run_id,
        "caseId": ir["caseId"],
        "caseTitle": ir["caseTitle"],
        "module": ir.get("module", ""),
        "pageObject": summary.get("pageObject", ""),
        "writeFlow": summary.get("writeFlow", False),
        "verdict": verdict,
        "steps": report["steps"],
        "assertions": report["assertions"],
        "assertionsPassed": report["assertionsPassed"],
        "finalUrl": report.get("finalUrl", ""),
        "pageText": report.get("pageText", ""),
        "orderNo": order_no,
        "screenshot": report.get("screenshot", ""),
        "stepShots": media["steps"],
        "video": media["video"],
        "videoUrl": media["videoUrl"],
        "mediaBytes": media["bytes"],
        "mediaUsage": ui_media.stats(),
        "mediaPrune": prune,
        "durationMs": report["durationMs"],
        "script": to_playwright_script(ir),
        "irSteps": [
            {"index": i, "raw": s["raw"], "keyword": s["keyword"],
             "args": s.get("args", {}), "note": s.get("note", "")}
            for i, s in enumerate(ir["steps"], 1)
        ],
    })


@router.post("/ui/run-cases")
def run_ui_cases(body: UiRunRequest, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    """用共享浏览器池真实执行编译后的 UI 自动化用例（步骤间 300ms 节流）。

    注意：单次请求内自建隔离池，避免 FastAPI 线程池换线程导致的 Playwright 线程亲和报错。
    """
    from ..ui_executor import BrowserPool, run_compiled

    scripts = [s for s in store.all("uiScripts", pid) if s.get("caseId") and s.get("ir")]
    if body.caseIds:
        wanted = set(body.caseIds)
        scripts = [s for s in scripts if s.get("caseId") in wanted]
    if not scripts:
        raise HTTPException(404, "没有已编译的 UI 自动化脚本，请先编译")

    results = []
    pool = BrowserPool(isolated=True)
    try:
        for s in scripts:
            report = run_compiled(s["ir"], delay_ms=body.delayMs or 300, pool=pool)
            report["caseTitle"] = s.get("caseTitle", "")
            results.append(report)
            run = {
                "id": uid("UR"), "projectId": pid, "script": s.get("name", ""),
                "caseId": s.get("caseId", ""), "browser": "Chromium(shared-pool)",
                "result": "成功" if report["verdict"] == "通过" else report["verdict"],
                "verdict": report["verdict"], "steps": report["steps"],
                "screenshot": report.get("screenshot", ""),
                "duration": f"{report['durationMs']}ms", "time": now_label(),
            }
            store.put("uiRuns", run["id"], run)
    finally:
        try:
            pool.close()
        except Exception:  # noqa: BLE001
            pass

    return ok({
        "total": len(results), "passed": sum(1 for r in results if r["verdict"] == "通过"),
        "failed": sum(1 for r in results if r["verdict"] == "失败"),
        "partial": sum(1 for r in results if r["verdict"] == "部分可执行"),
        "results": results,
    })


@router.get("/ui/pool-status")
def ui_pool_status(_: str = Depends(project_scope)) -> dict[str, Any]:
    """查看共享浏览器池资源状态（架构可观测性）。"""
    from ..ui_executor import POOL
    return ok(POOL.status())


# ---------------- UI 自动化：批量真实执行（后台任务 + 轮询） ----------------
@router.post("/ui/run-batch")
def ui_run_batch(body: UiBatchRequest, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    """启动批量真实执行任务（100+ 条同步执行会 HTTP 超时，故走后台线程）。"""
    from ..ui_batch_runner import start_job
    job_id = start_job(pid, limit=body.limit, max_write=body.maxWrite,
                       delay_ms=body.delayMs or 300, case_ids=body.caseIds or None,
                       only_confirmed=body.onlyConfirmed)
    return ok({"jobId": job_id, "status": "running",
               "note": f"已启动：最多 {body.limit} 条，写操作配额 {body.maxWrite}"
                       + ("，仅已确认绑定" if body.onlyConfirmed else "")})


@router.get("/ui/run-batch/{job_id}")
def ui_run_batch_status(job_id: str, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """轮询批量执行进度；完成后返回完整汇总（含每步状态与截图）。"""
    from ..ui_batch_runner import job_status
    job = job_status(job_id)
    if not job:
        raise HTTPException(404, "任务不存在或已被清理")
    return ok(job)


@router.post("/ui/compile-all")
def ui_compile_all(pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    """重新编译全部功能用例（v2：PO 真实操作 + 业务断言），落库 uiScripts。"""
    from ..ui_batch_runner import compile_and_store
    result = compile_and_store(pid)
    return ok({"stats": result["stats"]})


@router.post("/ui/recorder")
def add_recorder_step(body: RecorderStepIn, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    steps = store.all("recorderSteps", pid)
    step_id = max([int(step.get("id", 0)) for step in steps] + [0]) + 1
    store.put("recorderSteps", str(step_id), {"id": step_id, "projectId": pid, **body.model_dump()})
    return ok(store.all("recorderSteps", pid))


@router.delete("/ui/recorder")
def clear_recorder_steps(pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    store.replace("recorderSteps", [], project_id=pid)
    return ok([])


# ---------------- app automation ----------------
@router.get("/app/devices")
def list_devices(_: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("devices"))


@router.post("/app/devices/{device_id}/toggle")
def toggle_device(device_id: str, _: str = Depends(project_editor_scope)) -> dict[str, Any]:
    device = store.get("devices", device_id)
    if not device:
        raise HTTPException(404, "设备不存在")
    if device.get("status") == "在线":
        device["status"] = "离线"
        device["occupancy"] = "-"
    else:
        device["status"] = "在线"
        device["occupancy"] = "空闲"
    store.put("devices", device_id, device)
    return ok(store.all("devices"))


@router.post("/app/devices/{device_id}/release")
def release_device(device_id: str, _: str = Depends(project_editor_scope)) -> dict[str, Any]:
    device = store.get("devices", device_id)
    if not device:
        raise HTTPException(404, "设备不存在")
    device["occupancy"] = "空闲"
    store.put("devices", device_id, device)
    return ok(store.all("devices"))


@router.get("/app/flows")
def list_flows(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("flowNodes", pid))


@router.put("/app/flows")
def save_flows(body: FlowSave, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    store.replace("flowNodes", body.nodes, id_key="id", project_id=pid)
    return ok(store.all("flowNodes", pid))


@router.get("/app/runs")
def list_app_runs(pid: str = Depends(project_scope)) -> dict[str, Any]:
    return ok(store.all("appRuns", pid))


@router.post("/app/runs")
def run_app_flow(body: AppRunRequest, pid: str = Depends(project_editor_scope)) -> dict[str, Any]:
    run = {
        "id": uid("AR"), "projectId": pid, "flow": body.flow, "device": body.device,
        "result": "成功", "time": now_label(), "duration": "58s",
    }
    store.put("appRuns", run["id"], run)
    return ok(run)
