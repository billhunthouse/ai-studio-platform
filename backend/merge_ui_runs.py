"""合并多次真实执行结果（CLI 全量 + 接口补跑）为一份最终报告数据源。

用法：
    backend/.venv/bin/python backend/merge_ui_runs.py
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

DOCS = Path("/Users/imac/Desktop/AI_Studio/方案交互页面设计/docs/traceability")


def db_verify() -> dict:
    """直连真实库交叉验证：UI 操作是否真的写进了 commerce.order。"""
    try:
        import os

        import psycopg
        dsn = os.getenv("REAL_DB_DSN", "postgresql://shang:shang@127.0.0.1:55434/shang")
        with psycopg.connect(dsn, connect_timeout=4) as conn, conn.cursor() as cur:
            cur.execute('select count(*) from commerce."order"')
            total = cur.fetchone()[0]
            cur.execute("""select count(*), coalesce(sum(pay_amount),0), min(order_no), max(order_no)
                           from commerce."order" where created_at >= '2026-11-21 08:20'""")
            n, amount, lo, hi = cur.fetchone()
            cur.execute("""select status, count(*) from commerce."order"
                           where created_at >= '2026-11-21 08:20' group by status""")
            by_status = {k: v for k, v in cur.fetchall()}
        return {"totalOrders": total, "createdDuringRun": n, "amountSum": str(amount),
                "orderNoRange": [lo, hi], "byStatus": by_status, "source": dsn}
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)[:200]}


def main() -> int:
    parts = [DOCS / "ui-real-run-full.json", DOCS / "ui-real-run-api.json"]
    merged_results: dict[str, dict] = {}
    skipped: list[dict] = []
    compiled = None
    for p in parts:
        if not p.exists():
            continue
        d = json.loads(p.read_text(encoding="utf-8"))
        compiled = compiled or d.get("compiled")
        for r in d["results"]:
            merged_results[r["caseId"]] = r  # 同一用例以后跑的为准
        skipped.extend(d.get("skippedCases", []))

    results = list(merged_results.values())
    passed = [r for r in results if r["verdict"] == "通过"]
    failed = [r for r in results if r["verdict"] == "失败"]
    partial = [r for r in results if r["verdict"] == "部分可执行"]
    executed_ids = {r["caseId"] for r in results}
    skipped = [s for s in skipped if s["caseId"] not in executed_ids]

    by_po: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "partial": 0})
    for r in results:
        b = by_po[r["pageObject"] or "（无）"]
        b["total"] += 1
        b["passed" if r["verdict"] == "通过" else "failed" if r["verdict"] == "失败" else "partial"] += 1

    out = {
        "generatedAt": json.loads(parts[0].read_text(encoding="utf-8"))["generatedAt"],
        "target": "http://127.0.0.1:5174 (尚品汇 C 端真实前端) + http://127.0.0.1:8086 (真实后端) + PostgreSQL 55434",
        "compiled": compiled,
        "executed": len(results),
        "passed": len(passed), "failed": len(failed), "partial": len(partial),
        "skippedCount": len(skipped),
        "passRate": round(len(passed) / len(results) * 100, 1) if results else 0,
        "totalSeconds": round(sum(r.get("seconds", 0) for r in results), 1),
        "writeExecuted": sum(1 for r in results if r.get("writeFlow")),
        "assertions": sum(r.get("assertions", 0) for r in results),
        "assertionsPassed": sum(r.get("assertionsPassed", 0) for r in results),
        "byPageObject": dict(sorted(by_po.items(), key=lambda kv: -kv[1]["total"])),
        "failures": [{"caseId": r["caseId"], "caseTitle": r["caseTitle"], "pageObject": r["pageObject"],
                      "failedStep": next((s["raw"] for s in r["steps"] if s["status"] == "failed"), ""),
                      "detail": next((s["detail"] for s in r["steps"] if s["status"] == "failed"), ""),
                      "finalUrl": r.get("finalUrl", ""), "screenshot": r.get("screenshot", "")} for r in failed],
        "skippedCases": skipped,
        "results": results,
        "sources": [str(p.name) for p in parts if p.exists()],
        "dbVerify": db_verify(),
    }
    dst = DOCS / "ui-real-run-final.json"
    dst.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"合并 {len(parts)} 份 → {dst}")
    print(f"执行 {out['executed']} · 通过 {out['passed']} · 失败 {out['failed']} · "
          f"通过率 {out['passRate']}% · 断言 {out['assertionsPassed']}/{out['assertions']} · "
          f"写操作 {out['writeExecuted']} · 跳过 {out['skippedCount']}")
    orders = [n for r in results for n in r.get("orderNos", [])]
    print(f"真实订单 {len(orders)} 笔：{orders}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
