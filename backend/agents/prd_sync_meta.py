"""把规范化 PRD 的摘要同步回 requirements.description.

平台的「需求列表」「需求详情」读取 requirements.description，而该字段历史上存的是
「来源 docs/…｜模块 xx｜N 个接口」这类扫描元信息，不是业务描述。本脚本用 PRD 的
目标 / 范围 / 验收规模 / 质量分生成一段可读摘要，保留原始来源供追溯。

用法：
    .venv/bin/python -m agents.prd_sync_meta --dry-run
    .venv/bin/python -m agents.prd_sync_meta
"""

from __future__ import annotations

import argparse
import re

import psycopg

from .prd_rewrite import DSN, PROJECT


def build_summary(doc: dict) -> str:
    s = doc["sections"]
    ov = s["overview"]
    scope = s.get("scope") or {}
    acs = s.get("acceptance") or []
    q = s.get("quality") or {}
    tb = s.get("traceability") or {}
    counts = doc.get("counts") or {}

    in_scope = "、".join(x.replace("支持「", "").rstrip("」") for x in scope.get("inScope", [])[:5])
    strong = sum(1 for a in acs if len(a.get("anchors") or []) >= 2)
    lines = [
        f"【{ov.get('module') or '未分类'}】{re.sub(r'^【[^】]*】', '', ov.get('title', '')).strip()}　{ov.get('priority', '')}",
        f"目标：{ov.get('goal', '')}",
        f"范围：{in_scope or '—'}",
        f"验收：{len(acs)} 条 AC（{strong} 条含 ≥2 级断言锚点）· 规范符合度 {q.get('score', '-')} 分"
        f"（门禁 {q.get('gatesPassed', '-')}/{q.get('gatesTotal', '-')}）",
        f"关联：{counts.get('apis', 0)} 接口 · {counts.get('pages', 0)} 页面 · {counts.get('tables', 0)} 表"
        f" · 用例已验证 {tb.get('caseVerified', 0)}/{tb.get('caseCount', 0)}",
    ]
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT requirement_id, doc FROM requirement_prd WHERE project_id=%s ORDER BY requirement_id",
            (PROJECT,),
        )
        rows = cur.fetchall()
        print(f"待同步：{len(rows)} 条")
        for rid, doc in rows:
            if not doc or doc.get("schemaVersion") != "2.0":
                print(f"  {rid} 跳过（非规范化文档）")
                continue
            summary = build_summary(doc)
            if args.dry_run:
                print(f"\n=== {rid} ===\n{summary}")
                continue
            # 原始来源保留在末尾，便于追溯
            cur.execute("SELECT description FROM requirements WHERE id=%s AND project_id=%s", (rid, PROJECT))
            old = (cur.fetchone() or [""])[0] or ""
            m = re.search(r"来源[：:\s]*([^：:｜\s]+)", old)
            origin = m.group(1) if m else "docs/llm-wiki/02-requirements.md"
            cur.execute(
                "UPDATE requirements SET description=%s, updated_at=now() WHERE id=%s AND project_id=%s",
                (f"{summary}\n原始来源：{origin}", rid, PROJECT),
            )
        if not args.dry_run:
            conn.commit()
            print(f"已更新 {len(rows)} 条需求描述")


if __name__ == "__main__":
    main()
