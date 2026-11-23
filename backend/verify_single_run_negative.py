"""反向验证：单条执行链路真的会失败（不是"永远通过"）。

做法：拿 TC-1001 的编译结果，把 baseUrl 指向一个不存在的前端端口（59999），
用与 /ui/run-one 相同的执行内核跑一遍，必须判为「失败」并给出真实错误。
"""
from __future__ import annotations

import json
import sys

sys.path.insert(0, "/Users/imac/Desktop/AI_Studio/方案交互页面设计/backend")

from app.store import store  # noqa: E402
from app.ui_executor import BrowserPool, run_compiled  # noqa: E402
from app.ui_step_compiler import compile_case  # noqa: E402

case = store.get("testCases", "TC-1001", "ecommerce")
if not case:
    print(json.dumps({"error": "TC-1001 不存在"}, ensure_ascii=False))
    raise SystemExit(1)

ir = compile_case(case)
# 基线：真实环境
pool = BrowserPool(isolated=True)
baseline = run_compiled(ir, delay_ms=200, pool=pool)

# 破坏：指向不存在的端口
broken_ir = dict(ir)
broken_ir["baseUrl"] = "http://127.0.0.1:59999"
broken_ir["steps"] = [dict(s) for s in ir["steps"]]
broken = run_compiled(broken_ir, delay_ms=200, pool=pool)
pool.close()

failed_steps = [s for s in broken["steps"] if s["status"] == "failed"]
out = {
    "A_baseline": baseline["verdict"],
    "A_assertions": f"{baseline['assertionsPassed']}/{baseline['assertions']}",
    "B_brokenVerdict": broken["verdict"],
    "B_failedStep": (failed_steps[0]["raw"] if failed_steps else ""),
    "B_detail": (failed_steps[0]["detail"][:160] if failed_steps else ""),
    "negativeTestPassed": baseline["verdict"] == "通过" and broken["verdict"] == "失败",
}
print(json.dumps(out, ensure_ascii=False, indent=2))
