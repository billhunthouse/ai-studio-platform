"""小样本真实执行：验证 v2 编译器 + PO + 断言执行器在真实站点上的效果。
挑选 6 条覆盖不同 PO 的用例，逐条真实跑，输出每步状态。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, "/Users/imac/Desktop/AI_Studio/方案交互页面设计/backend")

from app.store import store  # noqa: E402
from app.ui_step_compiler import compile_case  # noqa: E402
from app.ui_executor import run_compiled  # noqa: E402

PICK = {
    "商品搜索流程", "登录流程", "订单列表流程", "购物车流程",
    "完整下单流程", "售后申请流程", "加入购物车流程", "商品详情流程",
}

cases = [c for c in store.all("testCases", "ecommerce")
         if (c.get("caseType") or ("api" if c.get("relatedApi") else "functional")) == "functional"]
seen: set[str] = set()
picked = []
for c in cases:
    ir = compile_case(c)
    po = ir["summary"]["pageObject"]
    if po in PICK and po not in seen:
        seen.add(po)
        picked.append((c, ir))

out = []
for c, ir in picked[:6]:
    print(f"\n=== {c['id']} {c['title'][:50]} | PO={ir['summary']['pageObject']} | 断言={ir['summary']['assertions']}")
    r = run_compiled(ir)
    print(f"  verdict={r['verdict']} 耗时={r['durationMs']}ms")
    for s in r["steps"]:
        mark = {"passed": "✓", "failed": "✗", "blocked": "-"}.get(s["status"], "?")
        print(f"   {mark} {s['index']:>2}. {s['raw'][:38]:<38} {s['detail'][:60]}")
    out.append({"caseId": c["id"], "po": ir["summary"]["pageObject"], **r})

Path("/tmp/ui-probe/sample_run.json").write_text(json.dumps(out, ensure_ascii=False, indent=2))
print("\n通过:", sum(1 for r in out if r["verdict"] == "通过"), "/", len(out))
