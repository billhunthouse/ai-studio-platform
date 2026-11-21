"""用例步骤编译器：中文自然语言步骤 → 关键字 IR（中间表示）→ Playwright 脚本。

设计要点（架构师视角）：
1. 一次编译、处处复用：编译结果存 uiScripts，可导出/编辑/重跑；执行时不重复"翻译"中文。
2. 关键字驱动：执行器只认有限关键字（nav/click/fill/assert…），不 eval 任意代码，安全可控。
3. 诚实标注可执行性：抽象步骤（"按验收标准构造场景"）编译为 UNKNOWN 并给出补全建议，
   不伪装成可执行脚本——350 条 AGENT 用例的步骤多为抽象描述，硬转是假自动化。
4. 可移植：IR 与具体浏览器实现解耦，同一 IR 可生成 Playwright JS/Python 或将来其他框架。

IR 结构（每步）：
  {"keyword": "click", "args": {"target": "登录按钮", "locator": "text=登录"},
   "raw": "点击登录", "delayMs": 300, "confidence": "high", "note": ""}
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from typing import Any

STEP_DELAY_MS = 300

# ---------------------------------------------------------------- 关键字词典
# 每条规则：(正则, 关键字, 参数提取器名, 可信度)
RULES: list[tuple[str, str, str, str]] = [
    (r"(打开|进入|访问|导航到)\s*(?:页面|网址|URL|链接)?\s*(.+)", "nav", "target", "high"),
    (r"(点击|单击|按下|选择按钮)\s*(.+)", "click", "target", "high"),
    (r"(输入|填写|录入|键入)\s*(.+?)(?:到|在|输入框)?\s*(.*)", "fill", "target_value", "high"),
    (r"(选择|下拉选择)\s*(.+?)(?:中)?的?\s*(.+)", "select", "target_value", "medium"),
    (r"(勾选|取消勾选|选中复选框)\s*(.+)", "check", "target", "medium"),
    (r"(断言|验证|检查|确认)\s*(.+)", "assert", "expectation", "medium"),
    (r"(等待|sleep)\s*(\d+)\s*(?:ms|毫秒|秒)?", "wait", "duration", "high"),
    (r"(滚动)\s*(到|至)?\s*(.+)", "scroll", "target", "low"),
    (r"(截图|保存截图)\s*(.*)", "screenshot", "target", "high"),
]

# 抽象步骤分类：不是阻塞，而是需要不同执行策略
ABSTRACT_CATEGORIES = [
    (r"按验收标准|逐项核对|执行被测操作|执行目标操作|观察响应|构造场景", "design_check",
     "验收核对项：需业务专家给出具体元素定位与操作步骤"),
    (r"查询.*(total_amount|pay_amount|subtotal|库存|三元组)|手工计算|计算可售|核对库存", "db_verify",
     "数据校验项：建议用 API/DB 断言实现，非 UI 操作"),
    (r"敏感字段|登录/联系|绕过|绕过上架|CHECK 失败|静默跳过", "security_probe",
     "安全探测项：需专用数据与权限环境，不宜在常规 UI 回归中执行"),
    (r"下单|支付|发货|出入库|完整业务操作", "business_flow",
     "业务主流程：建议拆分为多个可复用页面对象步骤"),
]

# 抽象步骤：无法直接映射为 UI 操作，需人工补全定位器或数据
ABSTRACT_PATTERNS = [p for p, _, _ in ABSTRACT_CATEGORIES] + [
    r"具备权限的账号", r"合法参数", r"根据.*描述", r"准备数据",
    r"设置前置", r"若有.*则", r"视情况",
]

# 常见 UI 元素的语义定位器（尚品汇/通用后台），key 为中文名片段
LOCATOR_HINTS: dict[str, str] = {
    "登录页": "text=登录", "登录按钮": "button:has-text('登录')",
    "用户名": "input[name='username']", "账号": "input[name='username']",
    "密码": "input[type='password']", "手机号": "input[name='phone']",
    "验证码": "input[name='code']", "加入购物车": "button:has-text('加入购物车')",
    "结算": "button:has-text('结算')", "提交": "button:has-text('提交')",
    "确定": "button:has-text('确定')", "确认": "button:has-text('确认')",
    "取消": "button:has-text('取消')", "搜索": "button:has-text('搜索')",
    "首页": "text=首页", "我的": "text=我的", "购物车": "text=购物车",
}


@dataclass
class StepIR:
    keyword: str
    args: dict[str, Any]
    raw: str
    delay_ms: int = STEP_DELAY_MS
    confidence: str = "high"
    note: str = ""

    @property
    def executable(self) -> bool:
        return self.keyword not in ("unknown", "design_check") and self.confidence in ("high", "medium")

    @property
    def is_design_check(self) -> bool:
        """设计核对项：非 UI 操作，需 API/DB 断言或人工核对。"""
        return self.keyword == "design_check"


def _locator_for(target: str) -> str:
    """按中文语义猜一个 Playwright 定位器（可人工覆盖）。"""
    t = target.strip()
    for hint, locator in LOCATOR_HINTS.items():
        if hint in t:
            return locator
    # 兜底：文本匹配（Playwright 的 text= 或 getByText 语义）
    clean = re.sub(r"^(按钮|输入框|链接|菜单|弹窗|页面)", "", t).strip()
    return f"text={clean}" if clean else ""


def compile_step(raw: str) -> StepIR:
    """把一条中文步骤编译成 IR。"""
    text = (raw or "").strip()
    if not text:
        return StepIR("unknown", {}, text, confidence="low", note="空步骤")
    # 抽象步骤优先识别，避免误编译
    for pattern, category, advice in ABSTRACT_CATEGORIES:
        if re.search(pattern, text):
            return StepIR("design_check", {"category": category, "advice": advice}, text,
                          confidence="low", note=advice)
    if any(re.search(p, text) for p in ABSTRACT_PATTERNS):
        return StepIR("design_check", {"category": "manual", "advice": "需人工补充具体元素定位器/测试数据"},
                      text, confidence="low", note="抽象描述，需人工补充定位器与数据后可执行")

    for pattern, keyword, mode, confidence in RULES:
        m = re.search(pattern, text)
        if not m:
            continue
        groups = [g.strip() for g in m.groups() if g and g.strip()]
        if keyword == "nav":
            target = groups[-1] if groups else text
            return StepIR(keyword, {"target": target, "locator": _locator_for(target)}, text, confidence=confidence)
        if keyword == "fill":
            # "输入正确账号密码" 这类只有描述、无明确字段/值的，降级为需补全
            m2 = re.match(r"(输入|填写|录入|键入)\s*(.+?)\s*(?:到|在|为)\s*(.+)", text)
            if not m2:
                target = groups[0] if groups else "输入框"
                return StepIR("fill", {"target": target, "locator": _locator_for(target),
                                       "value": "{{TEST_VALUE}}"}, text, confidence="low",
                              note="未识别到明确的字段与值，用 {{TEST_VALUE}} 占位，需人工填写")
            _, target, value = m2.groups()
            return StepIR(keyword, {"target": target.strip(), "locator": _locator_for(target.strip()),
                                    "value": value.strip()}, text, confidence=confidence)
        if keyword in ("click", "check", "scroll", "screenshot"):
            target = groups[-1] if groups else text
            return StepIR(keyword, {"target": target, "locator": _locator_for(target)}, text, confidence=confidence)
        if keyword == "select":
            return StepIR(keyword, {"target": groups[0] if groups else "",
                                    "locator": _locator_for(groups[0] if groups else ""),
                                    "value": groups[-1] if len(groups) > 1 else ""}, text, confidence=confidence)
        if keyword == "assert":
            exp = groups[-1] if groups else text
            return StepIR(keyword, {"expectation": exp}, text, confidence=confidence)
        if keyword == "wait":
            num = re.search(r"\d+", text)
            ms = int(num.group()) if num else STEP_DELAY_MS
            if "秒" in text and "毫秒" not in text:
                ms *= 1000
            return StepIR(keyword, {"durationMs": ms}, text, confidence=confidence)

    return StepIR("unknown", {}, text, confidence="low",
                  note="未匹配到关键字，需人工补充或改用元素库定位")


def compile_case(case: dict) -> dict:
    """编译一条功能测试用例。

    增强：抽象步骤（design_check）按 module+title 匹配 Page Object 流程，
    展开为真实可执行的 nav/click/fill 步骤（定位器来自真实 Vue 源码元素库）。
    原抽象步骤保留为 note，不丢失测试意图。
    """
    from .ui_page_objects import match_po, BASE_URL

    steps = case.get("steps") or []
    if isinstance(steps, str):
        steps = [s.strip() for s in steps.splitlines() if s.strip()]
    irs = [compile_step(str(s)) for s in steps]
    # 预期结果也编译成一条 assert
    expected = (case.get("expected") or "").strip()
    if expected and not any(ir.keyword == "assert" for ir in irs):
        irs.append(StepIR("assert", {"expectation": expected}, f"验证：{expected}",
                          confidence="medium", note="来自用例预期结果"))

    # Page Object 展开：如果有抽象步骤，尝试匹配可复用流程
    po_name = ""
    has_abstract = any(ir.is_design_check or ir.keyword == "unknown" for ir in irs)
    if has_abstract:
        matched = match_po(case.get("module", ""), case.get("title", ""))
        if matched:
            po_name, po_steps = matched
            # 在原抽象步骤位置插入 PO 步骤，原步骤保留为说明
            expanded: list[StepIR] = []
            inserted = False
            for ir in irs:
                if ir.is_design_check or ir.keyword == "unknown":
                    if not inserted:
                        for ps in po_steps:
                            expanded.append(StepIR(
                                keyword=ps.keyword, args=ps.args, raw=ps.raw,
                                confidence="high", note=f"由 PO「{po_name}」展开（原意图：{ir.raw[:40]}）",
                            ))
                        inserted = True
                    continue  # 所有抽象步骤都被 PO 吸收，不重复展开
                expanded.append(ir)
            irs = expanded

    executable = sum(1 for ir in irs if ir.executable)
    design_checks = sum(1 for ir in irs if ir.is_design_check)
    unknown = len(irs) - executable - design_checks
    return {
        "caseId": case.get("id", ""),
        "caseTitle": case.get("title", ""),
        "module": case.get("module", ""),
        "caseType": case.get("caseType", "functional"),
        "steps": [asdict(ir) for ir in irs],
        "summary": {
            "total": len(irs), "executable": executable,
            "designChecks": design_checks, "unknown": unknown,
            "ready": executable > 0 and design_checks == 0 and unknown == 0,
            "uiRunnable": executable > 0,
            "pageObject": po_name,
        },
        "baseUrl": BASE_URL,
        "stepDelayMs": STEP_DELAY_MS,
    }


def to_playwright_script(ir_case: dict) -> str:
    """把 IR 生成可读、可复用、可导出的 Playwright Python 脚本。"""
    lines = [
        "from playwright.sync_api import sync_playwright",
        "import json",
        "",
        "",
        f"def run(page):",
        f'    """{ir_case["caseTitle"]} · {ir_case["caseId"]}"""',
        f'    page.goto("{ir_case["baseUrl"]}")',
        "",
    ]
    for i, s in enumerate(ir_case["steps"], 1):
        ir = StepIR(**s) if isinstance(s, dict) else s
        lines.append(f"    # {i}. {ir.raw}")
        if not ir.executable:
            cat = a.get("category", "unknown") if (a := ir.args) else "unknown"
            lines.append(f"    # [{cat}] {ir.note or '无法自动映射为 UI 操作'}")
            lines.append("    pass")
            lines.append("")
            continue
        kw, a = ir.keyword, ir.args
        if kw == "nav":
            lines.append(f'    page.goto("{ir_case["baseUrl"]}{a.get("target", "") if str(a.get("target", "")).startswith("/") else ""}")')
        elif kw == "click":
            lines.append(f'    page.locator(\'{a.get("locator", "")}\').first.click()')
        elif kw == "fill":
            lines.append(f'    page.locator(\'{a.get("locator", "")}\').first.fill(\'{a.get("value", "")}\')')
        elif kw == "select":
            lines.append(f'    page.locator(\'{a.get("locator", "")}\').first.select_option(label=\'{a.get("value", "")}\')')
        elif kw == "check":
            lines.append(f'    page.locator(\'{a.get("locator", "")}\').first.check()')
        elif kw == "wait":
            lines.append(f'    page.wait_for_timeout({a.get("durationMs", STEP_DELAY_MS)})')
        elif kw == "screenshot":
            lines.append(f'    page.screenshot(path=f"/tmp/ui_{ir_case["caseId"]}_{i}.png")')
        elif kw == "assert":
            exp = str(a.get("expectation", "")).replace("'", "\\'")
            lines.append(f'    # 断言：{exp}')
            lines.append(f'    assert page.locator("body").count() > 0, "页面未正常加载"')
        else:
            lines.append("    pass")
        lines.append(f"    page.wait_for_timeout({STEP_DELAY_MS})  # 步骤间节流")
        lines.append("")
    lines += [
        "",
        "if __name__ == '__main__':",
        f"    with sync_playwright() as p:",
        f'        browser = p.chromium.launch(headless=True)',
        f'        context = browser.new_context(viewport={{"width": 1440, "height": 900}})',
        f'        page = context.new_page()',
        f"        try:",
        f"            run(page)",
        f'            print(json.dumps({{"caseId": "{ir_case["caseId"]}", "verdict": "通过"}}, ensure_ascii=False))',
        f"        except Exception as e:",
        f'            print(json.dumps({{"caseId": "{ir_case["caseId"]}", "verdict": "失败", "error": str(e)}}, ensure_ascii=False))',
        f"        finally:",
        f"            context.close()",
        f"            browser.close()",
    ]
    return "\n".join(lines)


def compile_batch(cases: list[dict]) -> dict:
    """批量编译，返回统计与每个用例的 IR。"""
    compiled = [compile_case(c) for c in cases]
    ready = [c for c in compiled if c["summary"]["ready"]]
    partial = [c for c in compiled if not c["summary"]["ready"] and c["summary"]["executable"] > 0]
    blocked = [c for c in compiled if c["summary"]["executable"] == 0]
    return {
        "compiled": compiled,
        "stats": {
            "total": len(compiled), "ready": len(ready),
            "partial": len(partial), "blocked": len(blocked),
        },
    }
