"""产品文档 AGENT 的读取接口：还原后的 PRD 文档。

数据由 backend/agents/prd_agent.py 生成，本模块只负责按需求 ID 读取与进度统计。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import project_editor_scope, project_scope
from ..db import get_db
from ..response import ok

router = APIRouter(prefix="/prd")


@router.get("/status")
def prd_status(pid: str = Depends(project_scope), db: Session = Depends(get_db)) -> dict[str, Any]:
    """还原进度：总需求数、已还原数、缺口列表。"""
    from ..models import Requirement
    from sqlalchemy import text

    total_ids = set(
        db.execute(
            select(Requirement.id).where(Requirement.project_id == pid, Requirement.parent_id.is_(None))
        ).scalars().all()
    )
    done_ids = set(
        db.execute(
            text("SELECT requirement_id FROM requirement_prd WHERE project_id = :pid"), {"pid": pid}
        ).scalars().all()
    )
    missing = sorted(total_ids - done_ids)
    return ok({
        "total": len(total_ids),
        "restored": len(done_ids & total_ids),
        "rate": round(len(done_ids & total_ids) / len(total_ids), 3) if total_ids else 0,
        "missing": missing,
    })


@router.get("/coverage")
def coverage(pid: str = Depends(project_scope), db: Session = Depends(get_db)) -> dict[str, Any]:
    """需求覆盖率总览：文档 / 追溯 / 用例 / 验收 四个维度.

    指标口径（与 docs/需求文档规范.md §9-10 一致）：
      requirementCoverage  有用例关联的需求 ÷ 需求总数      ← 主指标
      verifiedCoverage     有用例执行通过的需求 ÷ 需求总数
      traceCoverage        页面/接口/代码/表 四层全通的需求 ÷ 需求总数
      docCoverage          有规范化 PRD 的需求 ÷ 需求总数
      acAnchorRate         命中 ≥2 级断言锚点的 AC ÷ AC 总数
    """
    from collections import Counter

    from sqlalchemy import text

    from ..models import Requirement
    from .trace import TRACE_LAYERS, _reachable_layers, _relation_graph

    reqs = db.execute(
        select(Requirement.id, Requirement.title, Requirement.priority)
        .where(Requirement.project_id == pid)
    ).all()
    total = len(reqs)
    titles = {r.id: r.title for r in reqs}
    priorities = {r.id: r.priority for r in reqs}

    prd = {}
    for row in db.execute(
        text(
            """SELECT requirement_id,
                      (doc->'sections'->'quality'->>'score')::int        AS score,
                      (doc->'sections'->'quality'->>'gatesPassed')::int  AS gates,
                      (doc->'sections'->'quality'->>'gatesTotal')::int   AS gates_total,
                      (doc->'sections'->'quality'->>'grade')             AS grade,
                      COALESCE(jsonb_array_length(doc->'sections'->'acceptance'), 0) AS ac_total,
                      COALESCE((SELECT count(*) FROM jsonb_array_elements(doc->'sections'->'acceptance') a
                                WHERE jsonb_array_length(COALESCE(a->'anchors', '[]'::jsonb)) >= 2), 0) AS ac_strong,
                      COALESCE((doc->'sections'->'traceability'->>'layerCoverage')::int, 0) AS layer_cov,
                      doc->'sections'->'docInfo'->>'domain'              AS domain
               FROM requirement_prd WHERE project_id = :pid"""
        ),
        {"pid": pid},
    ).all():
        prd[row[0]] = {
            "score": row[1] or 0, "gatesPassed": row[2] or 0, "gatesTotal": row[3] or 0,
            "grade": row[4] or "D", "acTotal": row[5] or 0, "acStrong": row[6] or 0,
            "layerCoverage": row[7] or 0, "domain": row[8] or "未分类",
        }

    cases: dict[str, dict[str, int]] = {}
    for row in db.execute(
        text(
            """SELECT data->>'requirementId' AS rid,
                      count(*) AS total,
                      count(*) FILTER (WHERE data->'lastRun'->>'verdict' IN ('通过', '符合')) AS passed,
                      count(*) FILTER (WHERE data->'lastRun'->>'verdict' = '不符') AS failed,
                      -- 「跑过」不等于「通过」：跳过/已执行/不支持也算跑过，否则 notRun 会虚高
                      count(*) FILTER (WHERE data->'lastRun'->>'verdict' IS NOT NULL) AS executed,
                      count(*) FILTER (WHERE data->'lastRun'->>'verdict' IS NULL) AS not_run
               FROM documents
               WHERE collection = 'testCases' AND data->>'projectId' = :pid
                 AND data->>'requirementId' IS NOT NULL
                 -- 去重合并产生的归档副本不计入统计，否则「同一条用例算 N 次」的虚高会回来
                 AND COALESCE((data->>'archived')::boolean, false) = false
               GROUP BY 1"""
        ),
        {"pid": pid},
    ).all():
        cases[row[0]] = {"total": int(row[1]), "passed": int(row[2]),
                         "failed": int(row[3]), "executed": int(row[4]), "notRun": int(row[5])}

    adj = _relation_graph(db, pid)
    trace_by_req: dict[str, int] = {}
    layer_hits: Counter[str] = Counter()
    for r in reqs:
        found = _reachable_layers(adj, r.id)
        hit = sum(1 for k in TRACE_LAYERS if found[k])
        trace_by_req[r.id] = hit
        for k in TRACE_LAYERS:
            if found[k]:
                layer_hits[k] += 1

    def rate(n: int) -> float:
        return round(n / total, 3) if total else 0

    doc_ok = sum(1 for r in reqs if r.id in prd)
    trace_full = sum(1 for r in reqs if trace_by_req.get(r.id, 0) == len(TRACE_LAYERS))
    trace_linked = sum(1 for r in reqs if trace_by_req.get(r.id, 0) > 0)
    with_case = sum(1 for r in reqs if cases.get(r.id, {}).get("total", 0) > 0)
    verified = sum(1 for r in reqs if cases.get(r.id, {}).get("passed", 0) > 0)
    executed_reqs = sum(1 for r in reqs if cases.get(r.id, {}).get("executed", 0) > 0)

    ac_total = sum(p["acTotal"] for p in prd.values())
    ac_strong = sum(p["acStrong"] for p in prd.values())
    total_cases = sum(c["total"] for c in cases.values())
    executed = sum(c["executed"] for c in cases.values())
    passed = sum(c["passed"] for c in cases.values())

    # 按优先级 / 按业务域拆分，定位覆盖洼地
    def group(key_fn, label: str) -> list[dict[str, Any]]:
        buckets: dict[str, list[str]] = {}
        for r in reqs:
            buckets.setdefault(key_fn(r.id), []).append(r.id)
        out = []
        for k, ids in sorted(buckets.items()):
            c = sum(1 for i in ids if cases.get(i, {}).get("total", 0) > 0)
            v = sum(1 for i in ids if cases.get(i, {}).get("passed", 0) > 0)
            t = sum(1 for i in ids if trace_by_req.get(i, 0) == len(TRACE_LAYERS))
            out.append({
                label: k, "total": len(ids), "withCase": c, "verified": v, "traceFull": t,
                "caseRate": round(c / len(ids), 3), "verifyRate": round(v / len(ids), 3),
                "traceRate": round(t / len(ids), 3),
            })
        return out

    gaps = []
    for r in reqs:
        c = cases.get(r.id, {})
        missing = []
        if r.id not in prd:
            missing.append("doc")
        if trace_by_req.get(r.id, 0) < len(TRACE_LAYERS):
            missing.append("trace")
        if not c.get("total"):
            missing.append("case")
        elif not c.get("passed"):
            missing.append("verify")
        if missing:
            gaps.append({
                "id": r.id, "title": titles.get(r.id, ""), "priority": priorities.get(r.id, ""),
                "domain": prd.get(r.id, {}).get("domain", "未分类"),
                "missing": missing, "caseCount": c.get("total", 0),
                "passed": c.get("passed", 0), "score": prd.get(r.id, {}).get("score", 0),
            })
    gaps.sort(key=lambda g: (len(g["missing"]), g["priority"] != "P0", g["id"]))

    scores = sorted(p["score"] for p in prd.values())
    dist = Counter(
        "90-100" if s >= 90 else "75-89" if s >= 75 else "60-74" if s >= 60 else "<60"
        for s in scores
    )

    return ok({
        "requirementTotal": total,
        # 主指标：需求覆盖率 = 被用例覆盖的需求占比
        "requirementCoverage": rate(with_case),
        "verifiedCoverage": rate(verified),
        "docCoverage": rate(doc_ok),
        "traceCoverage": rate(trace_full),
        "traceLinkedRate": rate(trace_linked),
        "acAnchorRate": round(ac_strong / ac_total, 3) if ac_total else 0,
        "detail": {
            "withCase": with_case, "verified": verified, "docRestored": doc_ok,
            "caseExecutedReqs": executed_reqs,
            "traceFull": trace_full, "traceLinked": trace_linked,
            "acTotal": ac_total, "acStrong": ac_strong,
            "caseTotal": total_cases, "caseExecuted": executed, "casePassed": passed,
            "caseNotRun": total_cases - executed,
        },
        "layerCoverage": {k: layer_hits.get(k, 0) for k in TRACE_LAYERS},
        "quality": {
            "average": round(sum(scores) / len(scores), 1) if scores else 0,
            "min": scores[0] if scores else 0,
            "max": scores[-1] if scores else 0,
            "distribution": {k: dist.get(k, 0) for k in ("90-100", "75-89", "60-74", "<60")},
            "gatesPassed": sum(p["gatesPassed"] for p in prd.values()),
            "gatesTotal": sum(p["gatesTotal"] for p in prd.values()),
        },
        "byPriority": group(lambda i: priorities.get(i, "-"), "priority"),
        "byDomain": group(lambda i: prd.get(i, {}).get("domain", "未分类"), "domain"),
        "gaps": gaps,
    })


@router.get("/regression-plan")
def regression_plan(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """需求回归执行计划：把「已覆盖未验证」的需求编排成可执行批次。

    计划是现算的，不落库：批次进度直接读用例 lastRun，所以页面上的「已完成」
    永远等于真实执行情况，不会出现"计划表说做完了、用例还是没跑"的两张皮。
    """
    from ..regression_plan import build_plan

    return ok(build_plan(pid))


@router.get("/regression-plan/cases")
def regression_plan_cases(
    batchId: str,
    limit: int = 60,
    pid: str = Depends(project_scope),
) -> dict[str, Any]:
    """批次内用例明细（前端展开批次时按需拉取，避免计划接口返回上万字）。"""
    from ..regression_plan import batch_case_preview

    try:
        return ok(batch_case_preview(pid, batchId, limit=min(max(limit, 1), 200)))
    except KeyError:
        raise HTTPException(404, "批次不存在")


class PlanRunRequest(BaseModel):
    batchId: str
    limit: int = 0          # 0 表示跑整批
    force: bool = False     # DELETE 类写操作默认跳过，勾选后强制执行
    delayMs: int = 50       # 单条间隔，给被测服务留喘息时间


@router.post("/regression-plan/run")
def regression_plan_run(
    body: PlanRunRequest, pid: str = Depends(project_editor_scope)
) -> dict[str, Any]:
    """执行一个批次里的接口用例（后台线程，前端轮询进度）。"""
    from ..regression_plan import start_batch

    try:
        return ok(start_batch(pid, body.batchId, limit=body.limit, force=body.force,
                              delay_ms=max(0, min(body.delayMs, 2000))))
    except KeyError:
        raise HTTPException(404, "批次不存在")
    except ValueError as exc:
        raise HTTPException(400, str(exc))
    except RuntimeError as exc:
        raise HTTPException(409, str(exc))


@router.get("/regression-plan/run/{job_id}")
def regression_plan_run_status(job_id: str, pid: str = Depends(project_scope)) -> dict[str, Any]:
    """轮询批次执行进度，完成后返回最近 60 条结果。"""
    from ..regression_plan import job_status

    job = job_status(job_id)
    if not job or job.get("projectId") != pid:
        raise HTTPException(404, "任务不存在或已被清理")
    return ok(job)


@router.get("/{requirement_id}")
def get_prd(
    requirement_id: str,
    pid: str = Depends(project_scope),
    db: Session = Depends(get_db),
) -> dict[str, Any]:
    """按需求 ID 读取还原后的 PRD；未还原返回 404。"""
    from sqlalchemy import text

    row = db.execute(
        text(
            "SELECT doc, domain, coverage, updated_at FROM requirement_prd "
            "WHERE requirement_id = :rid AND project_id = :pid"
        ),
        {"rid": requirement_id, "pid": pid},
    ).fetchone()
    if not row:
        raise HTTPException(404, "该需求尚未还原，请运行产品文档 AGENT")
    return ok({
        "requirementId": requirement_id,
        "domain": row[1],
        "coverage": row[2],
        "generatedAt": row[3].isoformat() if row[3] else "",
        "doc": row[0],
    })


@router.post("/regenerate")
def regenerate(pid: str = Depends(project_scope)) -> dict[str, Any]:
    """触发 AGENT 重新还原（供界面手动刷新）。"""
    import subprocess
    import sys
    from pathlib import Path

    # prd.py 位于 backend/app/routers/，parents[2] 才是 backend 根目录
    backend_dir = Path(__file__).resolve().parents[2]
    proc = subprocess.run(
        [sys.executable, "-m", "agents.prd_agent"],
        cwd=backend_dir, capture_output=True, text=True, timeout=120,
    )
    if proc.returncode != 0:
        raise HTTPException(500, f"AGENT 运行失败：{proc.stderr[-500:]}")
    return ok({"message": "PRD 已重新生成", "output": proc.stdout[-1000:]})
