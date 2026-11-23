"""反向验证（mutation test）：证明执行器真的在操作浏览器、断言真的会失败。

三组对照：
A. 原样执行登录用例          → 期望 通过
B. 篡改输入框定位器为不存在 → 期望 失败（detail: 找不到输入框）+ 失败截图
C. 篡改断言为不可能满足的文本 → 期望 失败（detail: 页面未出现预期文本）
D. 恢复原样再执行            → 期望 通过（证明 B/C 的失败不是环境问题）

如果 B/C 也能"通过"，说明执行器在自欺，报告不可信。这是验证"真跑"的关键实验。
"""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.store import store  # noqa: E402
from app.ui_step_compiler import compile_case  # noqa: E402
from app.ui_executor import run_compiled  # noqa: E402

PROJECT = "ecommerce"


def pick_login_case() -> dict:
    cases = [c for c in store.all("testCases", PROJECT)
             if "登录" in (c.get("title") or "") and (c.get("caseType") or "functional") == "functional"]
    if not cases:
        raise SystemExit("找不到登录类功能用例")
    return cases[0]


def show(tag: str, r: dict) -> None:
    print(f"\n## {tag}: verdict={r['verdict']}  {r['durationMs']}ms  finalUrl={r['finalUrl']}")
    for s in r["steps"]:
        mark = {"passed": "✓", "failed": "✗", "blocked": "-"}.get(s["status"], "?")
        print(f"   {mark} {s['index']:>2}. {s['raw'][:34]:<34} {s['detail'][:70]}")
    if r["screenshot"]:
        print(f"   截图: {r['screenshot']} (exists={Path(r['screenshot']).exists()})")


def main() -> int:
    case = pick_login_case()
    base_ir = compile_case(case)
    print(f"用例：{case['id']} {case['title']} · PO={base_ir['summary']['pageObject']}")

    # A. 原样
    a = run_compiled(copy.deepcopy(base_ir))
    show("A 原样执行", a)

    # B. 破坏 fill 定位器
    b_ir = copy.deepcopy(base_ir)
    for s in b_ir["steps"]:
        if s["keyword"] == "fill":
            s["args"]["locator"] = "input[placeholder='这个输入框不存在']"
            break
    b = run_compiled(b_ir)
    show("B 篡改定位器", b)

    # C. 破坏断言
    c_ir = copy.deepcopy(base_ir)
    for s in c_ir["steps"]:
        if s["keyword"] == "assert" and s["args"].get("kind") == "text":
            s["args"]["target"] = "这段文本在页面上绝对不存在-XYZ"
            break
    c = run_compiled(c_ir)
    show("C 篡改断言", c)

    # D. 恢复
    d = run_compiled(copy.deepcopy(base_ir))
    show("D 恢复后重跑", d)

    verdict = {
        "caseId": case["id"],
        "A_baseline": a["verdict"],
        "B_brokenLocator": b["verdict"],
        "B_detail": next((s["detail"] for s in b["steps"] if s["status"] == "failed"), ""),
        "C_brokenAssertion": c["verdict"],
        "C_detail": next((s["detail"] for s in c["steps"] if s["status"] == "failed"), ""),
        "D_restored": d["verdict"],
        "negativeTestPassed": (a["verdict"] == "通过" and b["verdict"] == "失败"
                               and c["verdict"] == "失败" and d["verdict"] == "通过"),
    }
    out = Path("/Users/imac/Desktop/AI_Studio/方案交互页面设计/docs/traceability/ui-negative-verify.json")
    out.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
    print("\n" + json.dumps(verdict, ensure_ascii=False, indent=2))
    print("\n反向验证结论：", "通过（执行器真实生效，断言会失败）" if verdict["negativeTestPassed"] else "未通过，执行器可能自欺")
    return 0 if verdict["negativeTestPassed"] else 1


if __name__ == "__main__":
    sys.exit(main())
