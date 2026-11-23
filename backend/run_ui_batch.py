"""UI 自动化批量真实执行 CLI（与 HTTP 接口共用 app/ui_batch_runner.py 的同一套内核）。

真实执行：打开尚品汇前端 → 点击 → 断言 → 失败截图 → 落库 uiRuns。
写操作（下单/支付）受 --max-write 配额保护，避免耗尽演示库存/污染订单表。

用法：
    backend/.venv/bin/python backend/run_ui_batch.py --limit 120 --max-write 8 --tag full
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.ui_batch_runner import execute_batch  # noqa: E402
from app.ui_executor import POOL  # noqa: E402

PROJECT = "ecommerce"
DOCS = Path("/Users/imac/Desktop/AI_Studio/方案交互页面设计/docs/traceability")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=120, help="最多执行多少条用例")
    ap.add_argument("--max-write", type=int, default=8, help="写操作用例（下单/支付）真实执行配额")
    ap.add_argument("--delay", type=int, default=300, help="步骤间节流 ms")
    ap.add_argument("--tag", default="", help="报告文件名后缀")
    args = ap.parse_args()

    started = time.time()

    def on_progress(p: dict) -> None:
        mark = "✓" if p["verdict"] == "通过" else "✗"
        print(f"  [{p['index']}/{p['total']}] {mark} {p['caseId']} {p['pageObject']} {p['verdict']}",
              flush=True)

    print(f"[1/3] 编译 {PROJECT} 功能用例并落库 uiScripts…", flush=True)
    summary = execute_batch(PROJECT, limit=args.limit, max_write=args.max_write,
                            delay_ms=args.delay, progress=on_progress)

    print(f"\n[2/3] 真实执行完成：{summary['executed']} 条 · 通过 {summary['passed']} · "
          f"失败 {summary['failed']} · 部分 {summary['partial']} · "
          f"跳过 {summary['skippedCount']} · 通过率 {summary['passRate']}% · "
          f"耗时 {round(time.time() - started, 1)}s", flush=True)

    DOCS.mkdir(parents=True, exist_ok=True)
    tag = f"-{args.tag}" if args.tag else ""
    out = DOCS / f"ui-real-run{tag}.json"
    out.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[3/3] 结果 → {out}", flush=True)
    print(f"      浏览器池：{POOL.status()}", flush=True)
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
