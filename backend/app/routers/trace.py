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
    for attr in ("title", "name", "summary", "path"):
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
    eid = f"page:{pid}:{uuid.uuid4().hex[:8]}"
    exists = db.scalar(select(TracePage).where(
        TracePage.project_id == pid, TracePage.name == body.name,
        TracePage.feature_domain == body.feature_domain))
    if exists:
        raise HTTPException(409, "同名功能页面已存在")
    row = TracePage(id=eid, project_id=pid, **body.model_dump())
    db.add(row); _audit(db, pid, user, "create", "page", eid, after=body.model_dump())
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
    result = _walk(db, pid, entity_type, entity_id, max_hops, reverse=False)
    cross_db = any(x["type"] == "table" and
                   (db.get(TraceTable, x["id"]).database_name !=
                    (db.get(TraceTable, result[0]["id"]).database_name if result and result[0]["type"] == "table" else ""))
                   for x in result if db.get(TraceTable, x["id"]))
    return ok({"root": {"type": entity_type, "id": entity_id},
               "affectedCount": len(result), "items": result,
               "crossDatabaseWarning": bool(cross_db)})


@router.get("/impact/backward")
def impact_backward(entity_type: str, entity_id: str, max_hops: int = 3,
                    pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    max_hops = min(max(1, max_hops), 5)
    result = _walk(db, pid, entity_type, entity_id, max_hops, reverse=True)
    reqs = [x for x in result if x["type"] == "requirement"]
    return ok({"root": {"type": entity_type, "id": entity_id},
               "upstreamRequirements": reqs, "allAffectedCount": len(result), "items": result})


# ---------- 总览 / 矩阵 / 审计 ----------
@router.get("/overview")
def overview(pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    req_total = db.scalar(select(func.count()).select_from(Requirement).where(
        Requirement.project_id == pid)) or 0
    pending = db.scalar(select(func.count()).select_from(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "proposed")) or 0
    stale = db.scalar(select(func.count()).select_from(TraceRelation).where(
        TraceRelation.project_id == pid, TraceRelation.status == "stale")) or 0
    # 覆盖率：五层都有 confirmed 关联的需求占比（简化：有页面关联即算部分覆盖）
    with_pages = db.scalar(select(func.count(func.distinct(TraceRelation.src_id))).select_from(
        TraceRelation).where(TraceRelation.project_id == pid,
                             TraceRelation.src_type == "requirement",
                             TraceRelation.status == "confirmed")) or 0
    return ok({
        "requirementTotal": req_total,
        "coverageRate": round(with_pages / req_total, 3) if req_total else 0,
        "pendingRelationCount": pending, "staleRelationCount": stale,
    })


@router.get("/matrix")
def matrix(pid: str = Depends(project_scope), db: Session = Depends(get_db)):
    reqs = db.scalars(select(Requirement).where(Requirement.project_id == pid).limit(200)).all()
    rows = []
    for r in reqs:
        counts = {}
        for etype in ("page", "api", "code_artifact", "table"):
            counts[etype] = db.scalar(select(func.count()).select_from(TraceRelation).where(
                TraceRelation.project_id == pid, TraceRelation.status == "confirmed",
                TraceRelation.src_type == "requirement", TraceRelation.src_id == r.id,
                TraceRelation.dst_type == etype)) or 0
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
