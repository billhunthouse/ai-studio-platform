"""追溯平台 API（v2.1 · MVP）。

挂载于 /api/v1/trace，统一 X-Project-Id 隔离 + RBAC + 审计。
"""
from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import (
    ROLE_ADMIN, ROLE_DEVELOPER, ROLE_REVIEWER,
    get_current_user, project_editor_scope, project_reviewer_scope, project_scope, project_role,
)
from ..db import get_db
from ..models import Requirement, User
from ..response import ok
from ..trace_models import (
    TraceApi, TraceAuditLog, TraceCodeArtifact, TracePage, TraceRelation, TraceTable,
)

router = APIRouter(prefix="/trace")

# 实体类型 -> 模型/表名映射
ENTITY_MAP: dict[str, tuple[Any, str]] = {
    "requirement": (Requirement, "requirements"),
    "page": (TracePage, "trace_pages"),
    "api": (TraceApi, "trace_apis"),
    "code_artifact": (TraceCodeArtifact, "trace_code_artifacts"),
    "table": (TraceTable, "trace_tables"),
}
# 合法关系：src_type -> 允许的 (rel_type, dst_type)
VALID_RELATIONS: dict[str, set[tuple[str, str]]] = {
    "requirement": {("SPLITS_INTO", "page"), ("DERIVED_FROM", "requirement"), ("TRIGGERS", "api")},
    "page": {("TRIGGERS", "api")},
    "api": {("EXPOSED_BY", "code_artifact"), ("READS_WRITES", "table"), ("CROSS_DB_READ", "table")},
    "code_artifact": {("READS_WRITES", "table"), ("CROSS_DB_READ", "table")},
    "table": set(),
}
REVERSE_LABEL = {
    "SPLITS_INTO": "支撑需求", "TRIGGERS": "被触发", "EXPOSED_BY": "实现接口",
    "READS_WRITES": "被读写", "CROSS_DB_READ": "被跨库读", "DERIVED_FROM": "包含子需求",
}

# 关系语义字典：把枚举翻译成人话，并给出类别（用于前端配色/分组）
# category: structure 结构拆解 / call 调用 / implement 实现 / data 数据读写 / derive 派生
RELATION_META: list[dict[str, Any]] = [
    {
        "type": "SPLITS_INTO", "label": "拆分为", "reverseLabel": "支撑需求",
        "category": "structure", "from": "requirement", "to": "page",
        "question": "这条需求由哪几个功能页面承载？",
        "example": "REQ-018 优惠券 → 确认订单页 / 优惠券管理页",
        "note": "需求拆解，是追溯链的起点",
    },
    {
        "type": "TRIGGERS", "label": "调用接口", "reverseLabel": "被页面调用",
        "category": "call", "from": "page", "to": "api",
        "question": "这个页面会发起哪些请求？",
        "example": "确认订单页 → POST /api/orders",
        "note": "页面与接口的调用关系",
    },
    {
        "type": "EXPOSED_BY", "label": "由代码实现", "reverseLabel": "实现该接口",
        "category": "implement", "from": "api", "to": "code_artifact",
        "question": "这个接口最终落在哪个类/方法上？",
        "example": "POST /api/orders → OrderController#create",
        "note": "原名读起来是反的（代码暴露接口），语义上等于 IMPLEMENTS",
    },
    {
        "type": "READS_WRITES", "label": "读写数据表", "reverseLabel": "被读写",
        "category": "data", "from": "api|code_artifact", "to": "table",
        "question": "这段逻辑动了哪些表？",
        "example": "POST /api/orders → order / order_item / coupon",
        "note": "不区分读与写，避免枚举爆炸；读/写明细放 relation.note",
    },
    {
        "type": "CROSS_DB_READ", "label": "跨库读取", "reverseLabel": "被跨库读取",
        "category": "data", "from": "api|code_artifact", "to": "table",
        "question": "是否读了别的库？跨库会让事务与回滚失效",
        "example": "member-service → commerce.order（跨库）",
        "note": "本质是 READS_WRITES + 跨库标记，独立成枚举属于历史设计，建议后续收敛为 flag",
    },
    {
        "type": "DERIVED_FROM", "label": "派生自", "reverseLabel": "包含子需求",
        "category": "derive", "from": "requirement", "to": "requirement",
        "question": "这条子需求来自哪条主需求？",
        "example": "REQ-018-1 → REQ-018",
        "note": "需求拆分时的父子关系",
    },
]


# ---------- Schemas ----------
class RelationCreate(BaseModel):
    src_type: str
    src_id: str
    rel_type: str
    dst_type: str
    dst_id: str
    note: str = ""


class RelationConfirm(BaseModel):
    ids: list[str] = Field(default_factory=list)


class RelationReject(BaseModel):
    reason: str = ""


class PageCreate(BaseModel):
    name: str = Field(min_length=1)
    feature_domain: str
    code: str | None = None
    route: str | None = None
    prd_section: str | None = None
    prototype_ref: str | None = None
    business_owner: str | None = None
    description: str = ""


class ApiCreate(BaseModel):
    method: str
    path: str
    summary: str = ""
    service: str
    auth_requirement: str = "public"
    internal_calls: str = ""


class TableCreate(BaseModel):
    database_name: str
    service: str
    name: str
    schema_name: str = "public"
    columns: list[dict[str, Any]] = Field(default_factory=list)
    indexes: list[dict[str, Any]] = Field(default_factory=list)
    primary_key: str | None = None


class CodeArtifactCreate(BaseModel):
    repo: str
    service: str
    file_path: str
    entry_point: str | None = None
    commit_sha: str | None = None
    api_id: str | None = None


# ---------- helpers ----------
def _audit(db: Session, pid: str, user: User, action: str, entity_type: str | None = None,
           entity_id: str | None = None, before: dict | None = None, after: dict | None = None,
           reason: str = "") -> None:
    db.add(TraceAuditLog(
        project_id=pid, actor_id=user.id, actor_name=user.name, action=action,
        entity_type=entity_type, entity_id=entity_id,
        before_data=before or {}, after_data=after or {}, reason=reason,
    ))


def _entity_row(db: Session, etype: str, eid: str, pid: str):
    model, _ = ENTITY_MAP.get(etype, (None, ""))
    if model is None:
        raise HTTPException(400, f"未知实体类型: {etype}")
    obj = db.get(model, eid)
    project_field = "project_id"
    if obj is None or getattr(obj, project_field, None) != pid:
        raise HTTPException(404, f"{etype} 不存在: {eid}")
    return obj


def _entity_name(etype: str, obj) -> str:
    for attr in ("title", "name", "entry_point", "summary", "path"):
        v = getattr(obj, attr, None)
        if v:
            return str(v)
    return getattr(obj, "id", "")


def _validate_relation(src_type: str, rel_type: str, dst_type: str) -> None:
    allowed = VALID_RELATIONS.get(src_type, set())
    if (rel_type, dst_type) not in allowed:
        raise HTTPException(400, f"非法关系组合: {src_type} -{rel_type}-> {dst_type}")


# ---------- 实体 CRUD ----------
@router.get("/pages")
def list_pages(pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    rows = db.scalars(select(TracePage).where(TracePage.project_id == pid)).all()
    return ok([{"id": r.id, "name": r.name, "featureDomain": r.feature_domain,
                "prdSection": r.prd_section, "status": r.status} for r in rows])


@router.post("/pages")
def create_page(body: PageCreate, pid: str = Depends(project_editor_scope),
                user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    exists = db.scalar(select(TracePage).where(
        TracePage.project_id == pid, TracePage.name == body.name,
        TracePage.feature_domain == body.feature_domain))
    if exists:
        raise HTTPException(409, "同名功能页面已存在")
    # ID 规范 page:{proj}:{feature}-{seq}；未给 code 时回退随机串（兼容旧调用）
    if body.code:
        seq = (db.scalar(select(func.count()).select_from(TracePage).where(
            TracePage.project_id == pid,
            TracePage.feature_domain == body.feature_domain)) or 0) + 1
        eid = f"page:{pid}:{body.code}-{seq:03d}"
    else:
        eid = f"page:{pid}:{uuid.uuid4().hex[:8]}"
    payload = body.model_dump(exclude={"code", "route"})
    if body.route and not payload.get("prototype_ref"):
        payload["prototype_ref"] = body.route
    row = TracePage(id=eid, project_id=pid, **payload)
    db.add(row); _audit(db, pid, user, "create", "page", eid, after=payload)
    db.commit()
    return ok({"id": eid})


@router.get("/apis")
def list_apis(service: str | None = None, keyword: str | None = None,
              pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    q = select(TraceApi).where(TraceApi.project_id == pid)
    if service:
        q = q.where(TraceApi.service == service)
    if keyword:
        q = q.where(or_(TraceApi.path.contains(keyword), TraceApi.summary.contains(keyword)))
    rows = db.scalars(q).all()
    return ok([_api_public(db, pid, r) for r in rows])


@router.get("/api-contract")
def api_contract(path: str, method: str,
                 pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    """单个接口的完整契约（含参数/请求体字段），供 API 调试面板联动。"""
    row = db.scalar(select(TraceApi).where(
        TraceApi.project_id == pid, TraceApi.path == path,
        TraceApi.method == method.upper()))
    if not row:
        raise HTTPException(404, "接口不在追溯清单中")
    return ok({
        "id": row.id, "method": row.method, "path": row.path,
        "summary": row.summary, "service": row.service,
        "authRequirement": row.auth_requirement,
        "requestSchema": row.request_schema or {},
        "responseSchema": row.response_schema or {},
    })


def _api_public(db: Session, pid: str, r: TraceApi) -> dict[str, Any]:
    def cnt(etype: str, rel_type: str, reverse: bool = False) -> int:
        col = TraceRelation.dst_id if reverse else TraceRelation.src_id
        typecol = TraceRelation.dst_type if reverse else TraceRelation.src_type
        srccol = TraceRelation.src_id if reverse else TraceRelation.dst_id
        return db.scalar(select(func.count()).select_from(TraceRelation).where(
            TraceRelation.project_id == pid,
            TraceRelation.status == "confirmed",
            TraceRelation.rel_type == rel_type,
            col == r.id,
            typecol == etype,
        )) or 0
    return {
        "id": r.id, "method": r.method, "path": r.path, "summary": r.summary,
        "service": r.service, "authRequirement": r.auth_requirement,
        "status": r.status, "source": r.source,
        "upstreamRequirementCount": cnt("requirement", "TRIGGERS", reverse=True),
        "callingPageCount": cnt("page", "TRIGGERS", reverse=True),
        "readTablesCount": cnt("table", "READS_WRITES"),
    }


@router.post("/apis")
def create_api(body: ApiCreate, pid: str = Depends(project_editor_scope),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    eid = f"api:{body.method.upper()}:{body.path}"
    if db.get(TraceApi, eid):
        raise HTTPException(409, "接口已存在")
    row = TraceApi(id=eid, project_id=pid, method=body.method.upper(),
                   **{k: v for k, v in body.model_dump().items() if k != "method"})
    db.add(row); _audit(db, pid, user, "create", "api", eid, after=body.model_dump())
    db.commit()
    return ok({"id": eid})


@router.get("/tables")
def list_tables(service: str | None = None, pid: str = Depends(project_scope),
                db: Session = Depends(get_db)):
    q = select(TraceTable).where(TraceTable.project_id == pid)
    if service:
        q = q.where(TraceTable.service == service)
    rows = db.scalars(q).all()
    result = []
    for r in rows:
        upstream = db.scalar(select(func.count()).select_from(TraceRelation).where(
            TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
            TraceRelation.dst_type == "table", TraceRelation.dst_id == r.id,
        )) or 0
        result.append({
            "id": r.id, "database": r.database_name, "service": r.service,
            "schema": r.schema_name, "name": r.name,
            "columnCount": len(r.columns or []), "primaryKey": r.primary_key,
            "upstreamRequirementCount": upstream, "status": r.status,
        })
    return ok(result)


@router.post("/tables")
def create_table(body: TableCreate, pid: str = Depends(project_editor_scope),
                 user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    eid = f"table:{body.database_name}:{body.schema_name}:{body.name}"
    if db.get(TraceTable, eid):
        raise HTTPException(409, "表已存在")
    row = TraceTable(id=eid, project_id=pid, **body.model_dump())
    db.add(row); _audit(db, pid, user, "create", "table", eid, after=body.model_dump())
    db.commit()
    return ok({"id": eid})


# ---------- 代码层实体 ----------
@router.get("/code-artifacts")
def list_code_artifacts(service: str | None = None, pid: str = Depends(project_scope),
                        db: Session = Depends(get_db)):
    q = select(TraceCodeArtifact).where(TraceCodeArtifact.project_id == pid)
    if service:
        q = q.where(TraceCodeArtifact.service == service)
    rows = db.scalars(q).all()
    result = []
    for r in rows:
        upstream = db.scalar(select(func.count()).select_from(TraceRelation).where(
            TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
            TraceRelation.dst_type == "code_artifact", TraceRelation.dst_id == r.id,
        )) or 0
        downstream = db.scalar(select(func.count()).select_from(TraceRelation).where(
            TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
            TraceRelation.src_type == "code_artifact", TraceRelation.src_id == r.id,
        )) or 0
        result.append({
            "id": r.id, "repo": r.repo, "service": r.service, "filePath": r.file_path,
            "entryPoint": r.entry_point, "commitSha": r.commit_sha, "status": r.status,
            "upstreamApiCount": upstream, "downstreamTableCount": downstream,
        })
    return ok(result)


@router.post("/code-artifacts")
def create_code_artifact(body: CodeArtifactCreate, pid: str = Depends(project_editor_scope),
                         user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    key = body.entry_point or body.file_path
    eid = f"code:{body.repo}:{body.service}:{key}"
    if db.get(TraceCodeArtifact, eid):
        raise HTTPException(409, "代码实体已存在")
    row = TraceCodeArtifact(id=eid, project_id=pid, **body.model_dump())
    db.add(row); _audit(db, pid, user, "create", "code_artifact", eid, after=body.model_dump())
    db.commit()
    return ok({"id": eid})


# ---------- 实体详情（双向关联） ----------
@router.get("/entity")
def entity_detail(entity_type: str, entity_id: str, pid: str = Depends(project_scope),
                  db: Session = Depends(get_db)):
    # 用查询参数而非路径参数：复合 ID 含 / 和 {} 时路径参数会被 URL 解码导致路由失配
    etype, eid = entity_type, entity_id
    obj = _entity_row(db, etype, eid, pid)
    data = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    for k, v in list(data.items()):
        if hasattr(v, "isoformat"):
            data[k] = v.isoformat()

    upstream = db.scalars(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
        TraceRelation.dst_type == etype, TraceRelation.dst_id == eid,
    )).all()
    downstream = db.scalars(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
        TraceRelation.src_type == etype, TraceRelation.src_id == eid,
    )).all()

    def pkg(rels: list[TraceRelation], reverse: bool) -> list[dict[str, Any]]:
        out = []
        for r in rels:
            other_type, other_id = (r.src_type, r.src_id) if reverse else (r.dst_type, r.dst_id)
            other = None
            m, _ = ENTITY_MAP.get(other_type, (None, ""))
            if m:
                other = db.get(m, other_id)
            out.append({
                "relationId": str(r.id), "relType": r.rel_type,
                "directionLabel": REVERSE_LABEL.get(r.rel_type, r.rel_type) if reverse else r.rel_type,
                "type": other_type, "id": other_id,
                "name": _entity_name(other_type, other) if other else other_id,
                "source": r.source, "confidence": r.confidence,
            })
        return out

    return ok({"entity": data, "relations": {"upstream": pkg(upstream, True),
                                              "downstream": pkg(downstream, False)}})


@router.get("/relations/meta")
def relations_meta():
    """关系类型语义字典：把 SPLITS_INTO / TRIGGERS 之类的枚举翻译成人话。"""
    return ok({"items": RELATION_META,
               "categories": {
                   "structure": "结构拆解", "call": "调用",
                   "implement": "实现", "data": "数据读写", "derive": "派生",
               }})


@router.get("/detail")
def entity_detail_full(entity_type: str, entity_id: str,
                       pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    """实体详情页聚合接口：实体本身 + 上下游 + 按类型的扩展块。"""
    etype, eid = entity_type, entity_id
    obj = _entity_row(db, etype, eid, pid)
    base = {c.name: getattr(obj, c.name) for c in obj.__table__.columns}
    for k, v in list(base.items()):
        if hasattr(v, "isoformat"):
            base[k] = v.isoformat()

    def rel_pkg(rel: TraceRelation, other_type: str, other_id: str, reverse: bool) -> dict[str, Any]:
        m, _ = ENTITY_MAP.get(other_type, (None, ""))
        other = db.get(m, other_id) if m else None
        meta = next((x for x in RELATION_META if x["type"] == rel.rel_type), {})
        return {
            "relationId": str(rel.id), "relType": rel.rel_type,
            "relLabel": meta.get("reverseLabel" if reverse else "label", rel.rel_type),
            "category": meta.get("category", ""),
            "type": other_type, "id": other_id,
            "name": _entity_name(other_type, other) if other else other_id,
            "subtitle": _entity_subtitle(other_type, other),
            "source": rel.source, "confidence": rel.confidence,
        }

    up = [rel_pkg(r, r.src_type, r.src_id, True) for r in db.scalars(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
        TraceRelation.dst_type == etype, TraceRelation.dst_id == eid)).all()]
    down = [rel_pkg(r, r.dst_type, r.dst_id, False) for r in db.scalars(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
        TraceRelation.src_type == etype, TraceRelation.src_id == eid)).all()]

    extra: dict[str, Any] = {}

    if etype == "api":
        extra["contract"] = {
            "authRequirement": obj.auth_requirement,
            "service": obj.service,
            "specRef": obj.spec_ref,
            "requestSchema": obj.request_schema or {},
            "responseSchema": obj.response_schema or {},
            "internalCalls": obj.internal_calls or "",
        }
        extra["implementations"] = [
            {"filePath": c.file_path, "entryPoint": c.entry_point, "commitSha": c.commit_sha}
            for c in db.scalars(select(TraceCodeArtifact).where(
                TraceCodeArtifact.project_id == pid,
                or_(TraceCodeArtifact.api_id == eid,
                    TraceCodeArtifact.id.in_([r["id"] for r in down if r["type"] == "code_artifact"] or [""])),
            )).all()
        ]
        extra["tables"] = [{"id": r["id"], "name": r["name"], "subtitle": r["subtitle"]}
                           for r in down if r["type"] == "table"]
        extra["pages"] = [{"id": r["id"], "name": r["name"], "subtitle": r["subtitle"]}
                          for r in up if r["type"] == "page"]
        extra["implemented"] = bool(extra["implementations"])

    elif etype == "table":
        extra["columns"] = obj.columns or []
        extra["indexes"] = obj.indexes or []
        extra["primaryKey"] = obj.primary_key
        extra["writers"] = [{"type": r["type"], "id": r["id"], "name": r["name"],
                             "relLabel": r["relLabel"]} for r in up]
        back = _walk(db, pid, etype, eid, 4, reverse=True)
        extra["requirements"] = [x for x in back if x["type"] == "requirement"]

    elif etype == "page":
        extra["requirements"] = [{"id": r["id"], "name": r["name"]}
                                 for r in up if r["type"] == "requirement"]
        for r in up:
            if r["type"] == "requirement":
                m, _ = ENTITY_MAP["requirement"]
                req = db.get(m, r["id"])
                if req:
                    extra.setdefault("requirementDetail", {
                        "id": req.id, "title": req.title, "priority": req.priority,
                        "status": req.status, "owner": req.owner_name or "",
                        "description": (req.description or "")[:600],
                    })
        extra["apis"] = [{"id": r["id"], "name": r["name"], "subtitle": r["subtitle"]}
                         for r in down if r["type"] == "api"]
        extra["tables"] = [{"id": r["id"], "name": r["name"]}
                           for r in _walk(db, pid, etype, eid, 3, reverse=False) if r["type"] == "table"]

    elif etype == "code_artifact":
        extra["apis"] = [{"id": r["id"], "name": r["name"], "subtitle": r["subtitle"]}
                         for r in up if r["type"] == "api"]
        extra["tables"] = [{"id": r["id"], "name": r["name"]} for r in down if r["type"] == "table"]
        extra["filePath"] = obj.file_path
        extra["entryPoint"] = obj.entry_point

    elif etype == "requirement":
        extra["pages"] = [{"id": r["id"], "name": r["name"]} for r in down if r["type"] == "page"]
        reach = _reachable_layers(_relation_graph(db, pid), eid, 4)
        extra["layerCounts"] = {k: len(v) for k, v in reach.items()}

    return ok({"entity": base, "entityType": etype,
               "relations": {"upstream": up, "downstream": down}, "extra": extra})


def _entity_subtitle(etype: str, obj) -> str:
    if obj is None:
        return ""
    if etype == "api":
        return f"{obj.method} {obj.path}"
    if etype == "table":
        return f"{obj.database_name}.{obj.schema_name}.{obj.name}"
    if etype == "code_artifact":
        return obj.file_path or ""
    if etype == "page":
        return obj.feature_domain or ""
    if etype == "requirement":
        return f"{obj.priority} · {obj.status}"
    return ""


def _read_write_hint(columns: list[dict]) -> dict[str, int]:
    """（保留占位）字段级读写方向待扫描器支持方法体解析后再开放。"""
    return {"columnCount": len(columns)}


# ---------- 关联管理 ----------
@router.get("/relations")
def query_relations(direction: Literal["forward", "backward", "both"] = "both",
                    entity_type: str | None = None, entity_id: str | None = None,
                    rel_type: str | None = None, status: str = "confirmed",
                    release: str | None = None,
                    pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    if not entity_type or not entity_id:
        raise HTTPException(400, "entity_type 与 entity_id 必填")
    q = select(TraceRelation).where(TraceRelation.project_id == pid)
    if status != "all":
        q = q.where(TraceRelation.status == status)
    else:
        q = q.where(TraceRelation.status.in_(["confirmed", "proposed", "stale"]))
    if rel_type:
        q = q.where(TraceRelation.rel_type == rel_type)
    if release:
        q = q.where(or_(TraceRelation.valid_from_release.is_(None),
                        TraceRelation.valid_from_release <= release))
    if direction in ("forward", "both"):
        q = q.where(TraceRelation.src_type == entity_type, TraceRelation.src_id == entity_id)
    rows = list(db.scalars(q).all())
    if direction in ("backward", "both"):
        bq = select(TraceRelation).where(
            TraceRelation.project_id == pid,
            TraceRelation.dst_type == entity_type, TraceRelation.dst_id == entity_id,
        )
        if status != "all":
            bq = bq.where(TraceRelation.status == status)
        rows.extend(db.scalars(bq).all())
    seen: set[str] = set()
    items = []
    for r in rows:
        if str(r.id) in seen:
            continue
        seen.add(str(r.id))
        items.append({
            "relationId": str(r.id), "relType": r.rel_type,
            "src": {"type": r.src_type, "id": r.src_id},
            "dst": {"type": r.dst_type, "id": r.dst_id},
            "source": r.source, "confidence": r.confidence, "status": r.status,
            "validFromRelease": r.valid_from_release, "validToRelease": r.valid_to_release,
        })
    return ok({"total": len(items), "items": items})


@router.post("/relations")
def create_relation(body: RelationCreate, pid: str = Depends(project_editor_scope),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    _validate_relation(body.src_type, body.rel_type, body.dst_type)
    _entity_row(db, body.src_type, body.src_id, pid)
    _entity_row(db, body.dst_type, body.dst_id, pid)
    exists = db.scalar(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.src_type == body.src_type,
        TraceRelation.src_id == body.src_id, TraceRelation.rel_type == body.rel_type,
        TraceRelation.dst_type == body.dst_type, TraceRelation.dst_id == body.dst_id,
    ))
    if exists:
        raise HTTPException(409, "关联已存在")
    rid = str(uuid.uuid4())
    row = TraceRelation(
        id=rid, project_id=pid, src_type=body.src_type, src_id=body.src_id,
        rel_type=body.rel_type, dst_type=body.dst_type, dst_id=body.dst_id,
        source="HUMAN", confidence=100, status="confirmed",
        confirmed_by=user.id, confirmed_at=datetime.now(UTC).replace(tzinfo=None),
        note=body.note,
    )
    db.add(row); _audit(db, pid, user, "create_relation", body.src_type, body.src_id,
                        after=body.model_dump())
    db.commit()
    return ok({"relationId": rid, "status": "confirmed"})


@router.get("/relations/pending")
def pending_relations(status: str = "proposed", pid: str = Depends(project_scope),
                      db: Session = Depends(get_db)):
    rows = db.scalars(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == status,
    ).order_by(TraceRelation.confidence.desc())).all()
    stale_n = db.scalar(select(func.count()).select_from(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "stale")) or 0
    return ok({
        "total": len(rows), "staleCount": stale_n,
        "items": [{
            "relationId": str(r.id), "relType": r.rel_type,
            "src": {"type": r.src_type, "id": r.src_id},
            "dst": {"type": r.dst_type, "id": r.dst_id},
            "source": r.source, "confidence": r.confidence, "status": r.status,
            "note": r.note, "createdAt": r.created_at.isoformat() if r.created_at else None,
        } for r in rows],
    })


@router.post("/relations/{rid}/confirm")
def confirm_relation(rid: str, pid: str = Depends(project_reviewer_scope),
                     user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(TraceRelation, rid)
    if not row or row.project_id != pid:
        raise HTTPException(404, "关联不存在")
    if row.status not in ("proposed", "stale"):
        raise HTTPException(400, "只有 proposed/stale 可确认")
    before = {"status": row.status}
    row.status = "confirmed"
    row.confirmed_by = user.id
    row.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
    _audit(db, pid, user, "confirm_relation", row.src_type, row.src_id,
           before=before, after={"status": "confirmed"})
    db.commit()
    return ok({"status": "confirmed"})


@router.post("/relations/batch-confirm")
def batch_confirm(body: RelationConfirm, pid: str = Depends(project_reviewer_scope),
                  user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    done = 0
    for rid in body.ids:
        row = db.get(TraceRelation, rid)
        if row and row.project_id == pid and row.status in ("proposed", "stale"):
            row.status = "confirmed"
            row.confirmed_by = user.id
            row.confirmed_at = datetime.now(UTC).replace(tzinfo=None)
            _audit(db, pid, user, "confirm_relation", row.src_type, row.src_id,
                   after={"status": "confirmed", "batch": True})
            done += 1
    db.commit()
    return ok({"confirmed": done})


@router.post("/relations/{rid}/reject")
def reject_relation(rid: str, body: RelationReject, pid: str = Depends(project_reviewer_scope),
                    user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    row = db.get(TraceRelation, rid)
    if not row or row.project_id != pid:
        raise HTTPException(404, "关联不存在")
    row.status = "rejected"
    _audit(db, pid, user, "reject_relation", row.src_type, row.src_id,
           before={"status": row.status}, reason=body.reason)
    db.commit()
    return ok({"status": "rejected"})


# ---------- 影响分析 ----------
def _walk(db: Session, pid: str, etype: str, eid: str, max_hops: int,
          reverse: bool) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    visited: set[tuple[str, str]] = {(etype, eid)}
    frontier = [(etype, eid)]
    for hop in range(1, max_hops + 1):
        nxt: list[tuple[str, str]] = []
        for cur_type, cur_id in frontier:
            if reverse:
                rels = db.scalars(select(TraceRelation).where(
                    TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
                    TraceRelation.dst_type == cur_type, TraceRelation.dst_id == cur_id)).all()
                pairs = [(r.src_type, r.src_id, r.rel_type) for r in rels]
            else:
                rels = db.scalars(select(TraceRelation).where(
                    TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
                    TraceRelation.src_type == cur_type, TraceRelation.src_id == cur_id)).all()
                pairs = [(r.dst_type, r.dst_id, r.rel_type) for r in rels]
            for t, i, rt in pairs:
                if (t, i) in visited:
                    continue
                visited.add((t, i))
                m, _ = ENTITY_MAP.get(t, (None, ""))
                obj = db.get(m, i) if m else None
                result.append({"hop": hop, "type": t, "id": i,
                               "name": _entity_name(t, obj) if obj else i,
                               "relType": rt})
                nxt.append((t, i))
        frontier = nxt
        if not frontier:
            break
    return result


@router.get("/impact/forward")
def impact_forward(entity_type: str, entity_id: str, max_hops: int = 3,
                   pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    max_hops = min(max(1, max_hops), 5)
    # 先探明真实深度，再按请求上限裁剪：链路只有 3 层时不该给"4 跳"这种空选项
    full = _walk(db, pid, entity_type, entity_id, 5, reverse=False)
    max_depth = max((x["hop"] for x in full), default=0)
    result = [x for x in full if x["hop"] <= max_hops]
    # 跨库判定：链路里可达的数据表分布在多于一个 database 时告警
    db_names: set[str] = set()
    for x in result:
        if x["type"] == "table":
            tbl = db.get(TraceTable, x["id"])
            if tbl:
                db_names.add(tbl.database_name)
    depth_counts: dict[int, int] = {}
    for x in result:
        depth_counts[x["hop"]] = depth_counts.get(x["hop"], 0) + 1
    return ok({"root": {"type": entity_type, "id": entity_id},
               "affectedCount": len(result), "items": result,
               "maxDepth": max_depth, "depthCounts": depth_counts,
               "truncated": max_hops < max_depth,
               "crossDatabaseWarning": len(db_names) > 1,
               "databases": sorted(db_names)})


@router.get("/impact/backward")
def impact_backward(entity_type: str, entity_id: str, max_hops: int = 3,
                    pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    max_hops = min(max(1, max_hops), 5)
    result = _walk(db, pid, entity_type, entity_id, max_hops, reverse=True)
    reqs = [x for x in result if x["type"] == "requirement"]
    return ok({"root": {"type": entity_type, "id": entity_id},
               "upstreamRequirements": reqs, "allAffectedCount": len(result), "items": result})


# ---------- 总览 / 矩阵 / 审计 ----------
TRACE_LAYERS = ("page", "api", "code_artifact", "table")


def _relation_graph(db: Session, pid: str) -> dict[tuple[str, str], list[tuple[str, str]]]:
    """项目内 confirmed 关联的邻接表。"""
    rels = db.scalars(select(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "confirmed")).all()
    adj: dict[tuple[str, str], list[tuple[str, str]]] = {}
    for rel in rels:
        adj.setdefault((rel.src_type, rel.src_id), []).append((rel.dst_type, rel.dst_id))
    return adj


def _reachable_layers(adj, root_id: str, max_hop: int = 4) -> dict[str, set[str]]:
    """从需求出发多跳遍历，返回各层可达实体集合。"""
    found: dict[str, set[str]] = {k: set() for k in TRACE_LAYERS}
    seen = {("requirement", root_id)}
    frontier = [("requirement", root_id)]
    for _ in range(max_hop):
        nxt = []
        for node in frontier:
            for dst in adj.get(node, []):
                if dst in seen:
                    continue
                seen.add(dst)
                nxt.append(dst)
                if dst[0] in found:
                    found[dst[0]].add(dst[1])
        frontier = nxt
        if not frontier:
            break
    return found


@router.get("/overview")
def overview(pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == pid)).all()
    req_total = len(reqs)
    pending = db.scalar(select(func.count()).select_from(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "proposed")) or 0
    stale = db.scalar(select(func.count()).select_from(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "stale")) or 0
    # 覆盖率：四层（页面/接口/代码/表）均有可达实体的需求占比；linked 为至少有一层关联
    adj = _relation_graph(db, pid)
    full = linked = 0
    per_layer: dict[str, int] = {k: 0 for k in TRACE_LAYERS}
    gaps: list[dict[str, Any]] = []
    for r in reqs:
        found = _reachable_layers(adj, r.id)
        has = [k for k, v in found.items() if v]
        if has:
            linked += 1
        for k, v in found.items():
            if v:
                per_layer[k] += 1
        if len(has) == len(TRACE_LAYERS):
            full += 1
        else:
            gaps.append({"id": r.id, "title": r.title,
                         "missing": [k for k in TRACE_LAYERS if not found[k]]})
    return ok({
        "requirementTotal": req_total,
        "coverageRate": round(full / req_total, 3) if req_total else 0,
        "linkedRate": round(linked / req_total, 3) if req_total else 0,
        # 分层覆盖：哪一层断掉一眼可见，比一个总数有用
        "layerCoverage": per_layer,
        "gaps": gaps,
        "pendingRelationCount": pending, "staleRelationCount": stale,
    })


@router.get("/matrix")
def matrix(pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    """追踪矩阵：从需求出发按可达性统计各层实体数。

    注意：需求→接口/表 通常是二跳、三跳关系（经页面、代码），
    因此这里做多跳遍历而非只看一跳出边。
    """
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == pid).limit(200)).all()
    adj = _relation_graph(db, pid)
    rows = []
    for r in reqs:
        found = _reachable_layers(adj, r.id)
        counts = {k: len(v) for k, v in found.items()}
        filled = sum(1 for c in counts.values() if c > 0)
        missing = [e for e, c in counts.items() if c == 0]
        rows.append({
            "id": r.id, "title": r.title, "priority": r.priority, "status": r.status,
            **counts, "coverage": int(filled / 4 * 100), "missing": missing,
        })
    return ok({"columns": ["requirement", "page", "api", "code", "table", "coverage"],
               "rows": rows})


@router.get("/audit")
def audit_logs(limit: int = 100, pid: str = Depends(project_scope),
               user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    if project_role(pid, user, db) != ROLE_ADMIN and user.role != ROLE_ADMIN:
        raise HTTPException(403, "仅管理员可查看审计")
    rows = db.scalars(select(TraceAuditLog).where(
        TraceAuditLog.project_id == pid).order_by(TraceAuditLog.created_at.desc()).limit(limit)).all()
    return ok([{
        "actorName": r.actor_name, "action": r.action, "entityType": r.entity_type,
        "entityId": r.entity_id, "before": r.before_data, "after": r.after_data,
        "reason": r.reason, "createdAt": r.created_at.isoformat() if r.created_at else None,
    } for r in rows])
