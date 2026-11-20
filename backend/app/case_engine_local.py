"""系统内部用例生成引擎 · 不依赖外部 LLM.

基于产品文档 AGENT 还原出的 PRD（业务规则/异常边界/接口/验收标准）+ 追溯链，
用结构化模板与规则推导生成测试用例。适用于：未配置外部 AI API、离线环境、
或需要对生成结果有确定性的场景。

与外部 AI 引擎输出同构的用例结构，前端无需区分。
"""

from __future__ import annotations

import re
from typing import Any

STRATEGY_CN = {
    "正向流程": "正向",
    "边界值": "边界",
    "异常场景": "异常",
    "安全": "安全",
}


def _parse_prd(prd_doc: dict[str, Any] | None) -> dict[str, Any]:
    """把 PRD 文档拍平成生成用例所需的结构。"""
    if not prd_doc:
        return {"rules": [], "neg": [], "apis": [], "ac": [], "features": [], "columns": []}
    s = prd_doc.get("sections", {})
    return {
        "rules": [r.get("text", "") for r in s.get("businessRules", [])],
        "neg": [(n.get("id", ""), n.get("scenario", "")) for n in s.get("exceptions", [])],
        "apis": [(a.get("method", ""), a.get("path", ""), a.get("summary", ""),
                  a.get("bodyFields", [])) for a in s.get("apis", [])],
        "ac": [a.get("text", "") for a in s.get("acceptance", [])],
        "features": [f.get("name", "") for f in s.get("features", [])],
        "columns": [c.get("name", "") for t in s.get("dataModel", [])
                    for c in t.get("columns", [])],
        "domain": s.get("overview", {}).get("module", ""),
    }


def _case(title: str, module: str, kind: str, priority: str,
          pre: str, steps: list[str], expected: str) -> dict[str, Any]:
    return {
        "title": title, "module": module, "type": kind, "priority": priority,
        "precondition": pre, "steps": steps, "expected": expected,
    }


def _snippet(text: str, limit: int = 42) -> str:
    text = re.sub(r"〔.*?〕", "", text).strip()
    return text if len(text) <= limit else text[:limit] + "…"


def gen_positive(title: str, module: str, features: list[str], ac: list[str], apis: list) -> list[dict]:
    """正向流程：每个功能点/验收标准一条主流程用例。"""
    cases: list[dict] = []
    api_sample = apis[0] if apis else None
    base_steps = ["进入对应页面或调用入口", "按业务要求填写必填信息", "提交并观察系统响应"]
    if api_sample and api_sample[2]:
        base_steps[1] = f"调用 {api_sample[0]} {api_sample[1]}（{api_sample[2]}），填写合法参数"

    for i, feat in enumerate(features[:6]):
        cases.append(_case(
            title=f"{_snippet(feat, 26)}-主流程成功",
            module=module, kind="正向", priority="P0",
            pre="用户已登录且具备相应权限，前置数据已就绪",
            steps=[f"{feat}：{base_steps[0]}", *base_steps[1:]],
            expected="操作成功，返回预期结果，相关数据状态正确更新",
        ))
    for i, item in enumerate(ac[:6]):
        cases.append(_case(
            title=f"验收点{i + 1}：{_snippet(item, 26)}",
            module=module, kind="正向", priority="P1",
            pre="满足验收前提的数据与环境",
            steps=["按验收标准描述执行操作", "校验系统输出与状态"],
            expected=item,
        ))
    if not cases:
        cases.append(_case(
            title=f"{_snippet(title, 30)}-主流程",
            module=module, kind="正向", priority="P0",
            pre="用户已登录，前置数据就绪",
            steps=base_steps,
            expected="业务按预期完成，无报错",
        ))
    return cases


def gen_boundary(title: str, module: str, rules: list[str], apis: list, columns: list[str]) -> list[dict]:
    """边界值：必填为空、超长、极值与状态边界。"""
    cases: list[dict] = []
    body_fields = []
    for _m, _p, _s, fields in apis:
        for f in fields:
            name = f.get("name") if isinstance(f, dict) else str(f)
            if name and name not in [b.get("name") for b in body_fields]:
                body_fields.append({"name": name, "type": (f.get("type") if isinstance(f, dict) else "string")})

    target = body_fields[0]["name"] if body_fields else (columns[0] if columns else "关键字段")
    cases.append(_case(
        title=f"{target} 为空提交",
        module=module, kind="边界", priority="P0",
        pre="已进入目标页面/接口",
        steps=[f"将 {target} 置空", "其余字段填写合法值", "提交"],
        expected="校验拦截并给出明确必填提示，不产生脏数据",
    ))
    cases.append(_case(
        title=f"{target} 超长输入",
        module=module, kind="边界", priority="P1",
        pre="已进入目标页面/接口",
        steps=[f"为 {target} 输入远超上限长度的字符串", "提交"],
        expected="服务端拒绝或截断，返回 4xx 而非 500",
    ))
    cases.append(_case(
        title="数值型字段极值",
        module=module, kind="边界", priority="P1",
        pre="存在数值/数量类字段",
        steps=["分别输入 0、负数、超大数值", "提交并观察"],
        expected="按业务规则校验；非法值返回明确错误，不写库",
    ))
    for rule in rules:
        if any(k in rule for k in ("状态", "TTL", "阈值", "15 分钟", "1-5", "500 字")):
            cases.append(_case(
                title=f"状态/阈值边界：{_snippet(rule, 24)}",
                module=module, kind="边界", priority="P1",
                pre="构造处于边界条件的数据",
                steps=["将对象置于临界状态", "执行目标操作"],
                expected="严格按规则判定放行或拒绝",
            ))
            if len(cases) >= 8:
                break
    return cases[:8]


def gen_exception(title: str, module: str, neg: list, rules: list) -> list[dict]:
    """异常场景：把 PRD 的负面清单 NEG 逐条转成可执行用例。"""
    cases: list[dict] = []
    for nid, scenario in neg:
        cases.append(_case(
            title=f"[{nid}] {_snippet(scenario, 30)}",
            module=module, kind="异常", priority="P0",
            pre="已构造该负面场景所需的异常数据",
            steps=[scenario, "执行目标操作", "观察系统行为"],
            expected="按测试含义应被正确拦截；若实际放行则暴露产品缺陷，需记录",
        ))
    if not cases:
        for rule in rules[:3]:
            if any(k in rule for k in ("必须", "仅", "不可", "拒绝", "守卫")):
                cases.append(_case(
                    title=f"违反规则：{_snippet(rule, 26)}",
                    module=module, kind="异常", priority="P1",
                    pre="构造违反该规则的数据",
                    steps=["执行违反规则的操作", "观察系统响应"],
                    expected="被明确拒绝并给出原因，不产生副作用",
                ))
    if not cases:
        cases.append(_case(
            title=f"{_snippet(title, 28)}-异常输入",
            module=module, kind="异常", priority="P1",
            pre="测试数据准备完成",
            steps=["提交不合法/不存在的关联对象", "观察"],
            expected="返回明确错误，不发生部分写入",
        ))
    return cases[:8]


def gen_security(title: str, module: str, apis: list, rules: list) -> list[dict]:
    """安全：鉴权、越权、令牌通用性。"""
    cases: list[dict] = []
    public = [a for a in apis if "免" in str(a[0]) or "public" in str(a[0])]
    protected = [a for a in apis if a and a[0] and a not in public]
    sample = protected[0] if protected else (apis[0] if apis else None)
    endpoint = f"{sample[0]} {sample[1]}" if sample else "目标接口"

    cases.append(_case(
        title="未登录访问受保护接口",
        module=module, kind="安全", priority="P0",
        pre="无有效登录态",
        steps=[f"不带 token 调用 {endpoint}"],
        expected="返回 401，不泄露业务数据",
    ))
    cases.append(_case(
        title="越权访问他人资源",
        module=module, kind="安全", priority="P0",
        pre="已登录为普通用户 A",
        steps=["使用 A 的 token 访问属于用户 B 的资源 ID", "观察"],
        expected="被拒绝或仅返回无权数据，不越权读写",
    ))
    for rule in rules:
        if "令牌" in rule or "token" in rule.lower() or "脱敏" in rule:
            cases.append(_case(
                title=f"令牌/脱敏校验：{_snippet(rule, 24)}",
                module=module, kind="安全", priority="P1",
                pre="准备两类令牌或敏感字段",
                steps=["使用不同体系令牌交叉访问", "查看敏感字段展示"],
                expected="令牌不通用；敏感信息已脱敏",
            ))
            break
    return cases[:5]


def generate(title: str, module_hint: str, strategies: list[str],
             prd_doc: dict[str, Any] | None = None, context: str = "") -> list[dict[str, Any]]:
    """内部引擎主入口。输出与外部 AI 引擎同构的用例列表。"""
    info = _parse_prd(prd_doc)
    module = info["domain"] or module_hint or "通用"
    cases: list[dict[str, Any]] = []
    mapper = {
        "正向流程": lambda: gen_positive(title, module, info["features"] or [title], info["ac"], info["apis"]),
        "边界值": lambda: gen_boundary(title, module, info["rules"], info["apis"], info["columns"]),
        "异常场景": lambda: gen_exception(title, module, info["neg"], info["rules"]),
        "安全": lambda: gen_security(title, module, info["apis"], info["rules"]),
    }
    for st in strategies:
        key = STRATEGY_CN.get(st, st)
        fn = mapper.get(st)
        if not fn:
            continue
        for c in fn():
            c["type"] = key
            cases.append(c)
    if not cases:
        cases = gen_positive(title, module, [title], [], [])
    # 去重：同标题只保留一条
    seen: set[str] = set()
    unique = []
    for c in cases:
        if c["title"] in seen:
            continue
        seen.add(c["title"])
        unique.append(c)
    return unique
