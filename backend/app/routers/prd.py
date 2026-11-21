"""产品文档 AGENT 的读取接口：还原后的 PRD 文档。

数据由 backend/agents/prd_agent.py 生成，本模块只负责按需求 ID 读取与进度统计。
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import project_scope
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
