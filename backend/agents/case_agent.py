"""测试工程师 AGENT · 资深测试工程师方法论驱动的专业用例生成.

角色画像与方法论见 docs/traceability/测试工程师AGENT-设计说明.md。

用法：
    cd backend
    .venv/bin/python -m agents.case_agent                       # 全量（无用例的需求）
    .venv/bin/python -m agents.case_agent --only V1-FR-006       # 单需求
    .venv/bin/python -m agents.case_agent --dry-run              # 只打印不写库

流水线：证据采集（复用 PRD AGENT 的追溯链 BFS）→ 测试分析（三张分析表）
→ 七类设计方法生成 → 质量自检 → 落库（testCases，待评审）。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from typing import Any

import psycopg
from dotenv import load_dotenv

from .prd_agent import collect_evidence, dsn, hydrate, load_requirements
from .prd_knowledge import domain_for

load_dotenv()

PROJECT = "ecommerce"


# ---------------------------------------------------------------- 状态机知识（真实代码证据）

# 状态机定义：迁移 + 代码证据。来自 OrderService/AfterSaleService/ProductService 等真实源码。
STATE_MACHINES: dict[str, dict[str, Any]] = {
    "订单交易": {
        "states": "PENDING_PAY / PENDING_SHIP / PENDING_RECEIVE / COMPLETED / CLOSED",
        "legal": [
            ("PENDING_PAY", "PENDING_SHIP", "沙箱支付成功", "OrderService：支付回调更新状态"),
            ("PENDING_SHIP", "PENDING_RECEIVE", "后台发货", "OrderService#ship：校验待发货后扣库存"),
            ("PENDING_RECEIVE", "COMPLETED", "确认收货", "OrderSubmitService#confirmReceive"),
            ("PENDING_PAY", "CLOSED", "超时/取消关单", "OrderSubmitService#close + 定时任务"),
        ],
        "illegal": [
            ("COMPLETED", "PENDING_PAY", "终态回退"),
            ("CLOSED", "PENDING_SHIP", "已关闭订单发货"),
            ("PENDING_PAY", "COMPLETED", "跳态（未支付直接完成）"),
        ],
        "guard": "发货仅允许 PENDING_SHIP → PENDING_RECEIVE（OrderService Javadoc）",
    },
    "售后服务": {
        "states": "PENDING_AUDIT / REFUNDING / COMPLETED / REJECTED",
        "legal": [
            ("PENDING_AUDIT", "REFUNDING", "审核同意退款", "AfterSaleService#approve"),
            ("REFUNDING", "COMPLETED", "退款完成", "AfterSaleService"),
            ("PENDING_AUDIT", "REJECTED", "审核拒绝（须填意见）", "AfterSaleController#reject"),
        ],
        "illegal": [
            ("REJECTED", "REFUNDING", "驳回单再次退款"),
            ("COMPLETED", "PENDING_AUDIT", "已完成售后重新审核"),
        ],
        "guard": "审核拒绝必须填写意见；同意后进入退款中（不可观测中间态）",
    },
    "商品与类目": {
        "states": "DRAFT / ON / OFF",
        "legal": [
            ("DRAFT", "ON", "上架（含定时上架）", "ProductService#onSale + Job"),
            ("ON", "OFF", "下架（单个/批量）", "ProductService#offSale"),
            ("OFF", "ON", "重新上架", "ProductService"),
        ],
        "illegal": [
            ("ON", "DRAFT", "上架商品回草稿"),
        ],
        "guard": "仅草稿状态商品可删除（ProductController）",
    },
    "会员与账号": {
        "states": "NORMAL / FROZEN",
        "legal": [
            ("NORMAL", "FROZEN", "后台冻结会员", "CustomerController 冻结接口"),
            ("FROZEN", "NORMAL", "后台解冻", "CustomerController"),
        ],
        "illegal": [
            ("FROZEN", "FROZEN", "冻结态重复冻结（应幂等或拒绝）"),
        ],
        "guard": "冻结会员不可下单",
    },
    "评价": {
        "states": "VISIBLE / HIDDEN",
        "legal": [
            ("VISIBLE", "HIDDEN", "后台隐藏不当评价", "ReviewAdminService"),
            ("HIDDEN", "VISIBLE", "后台恢复展示", "ReviewAdminService"),
        ],
        "illegal": [],
        "guard": "评价发表即 VISIBLE（StorefrontController）",
    },
}


# ---------------------------------------------------------------- 用例骨架


def _case(
    title: str, module: str, ctype: str, priority: str,
    precondition: str, steps: list[str], expected: str, *,
    design_method: str = "", related_api: str = "", test_data: str = "", db_check: str = "",
) -> dict[str, Any]:
    return {
        "title": title, "module": module, "type": ctype, "priority": priority,
        "precondition": precondition, "steps": steps, "expected": expected,
        "designMethod": design_method, "relatedApi": related_api,
        "testData": test_data, "dbCheck": db_check,
    }


def _clean(text: str, limit: int = 34) -> str:
    text = re.sub(r"〔.*?〕", "", str(text)).strip()
    text = text.replace("\n", " ")
    return text if len(text) <= limit else text[:limit] + "…"


# ---------------------------------------------------------------- AGENT 本体


class SeniorTestEngineerAgent:
    """资深测试工程师 AGENT：分析 → 设计 → 自检三段式。"""

    def __init__(self, cur, project_id: str = PROJECT):
        self.cur = cur
        self.pid = project_id

    # ---------------- Stage 1-2 输入解析 + 证据采集

    def analyze(self, req: dict[str, Any]) -> dict[str, Any]:
        req_id = req["id"]
        evid = collect_evidence(self.cur, req_id)
        hydrate(self.cur, evid)

        self.cur.execute(
            "SELECT doc FROM requirement_prd WHERE requirement_id=%s AND project_id=%s",
            (req_id, self.pid),
        )
        row = self.cur.fetchone()
        prd = (row[0] if row else {}) or {}
        s = prd.get("sections", {})
        dom_key, dom = domain_for(req_id, req["title"])

        # 状态机匹配：先精确域，再按规则文本关键词（订单/售后规则可能挂在交易域下）
        sm = STATE_MACHINES.get(dom_key)
        if not sm:
            rules_text = " ".join(r.get("text", "") for r in s.get("businessRules", []))
            for key, machine in STATE_MACHINES.items():
                if key[:2] in rules_text:
                    sm = machine
                    break

        # PRD jsonb 里的 exceptions/rules 是 dict（psycopg 自动转换），归一化成元组
        negs_raw = s.get("exceptions", [])
        negs = [
            (n.get("id", "") if isinstance(n, dict) else n[0],
             n.get("scenario", "") if isinstance(n, dict) else n[1])
            for n in negs_raw
        ]
        rules_raw = s.get("businessRules", [])
        rules = [
            (r.get("text", "") if isinstance(r, dict) else r[0],
             r.get("evidence", "") if isinstance(r, dict) else (r[1] if len(r) > 1 else ""))
            for r in rules_raw
        ]
        return {
            "reqId": req_id,
            "title": req["title"],
            "domain": dom_key,
            "points": req.get("points") or [],
            "features": [f.get("name", "") for f in s.get("features", [])],
            "ac": [a.get("text", "") for a in s.get("acceptance", [])],
            "apis": [
                {
                    "id": a["id"], "method": a.get("method", ""), "path": a.get("path", ""),
                    "summary": a.get("name", ""), "auth": a.get("auth", ""),
                    "params": a.get("params", []), "bodyFields": a.get("body_fields", []),
                }
                for a in evid.get("api", [])
            ],
            "tables": [
                {"name": t.get("name", ""), "columns": t.get("columns", [])}
                for t in evid.get("table", [])
            ],
            "rules": rules,
            "negs": negs,
            "flows": s.get("flows", []),
            "stateMachine": sm,
        }

    # ---------------- Stage 3-4 测试分析 + 用例设计

    def design(self, a: dict[str, Any]) -> list[dict[str, Any]]:
        cases: list[dict[str, Any]] = []
        for fn in (
            self._positive, self._param_matrix, self._state_transitions,
            self._negatives, self._concurrency_idempotency, self._security, self._consistency,
        ):
            cases.extend(fn(a))

        # Stage 5 质量自检：去重（同标题）+ 数量上限
        seen: set[str] = set()
        unique = []
        for c in cases:
            if c["title"] in seen:
                continue
            seen.add(c["title"])
            c["requirementId"] = a["reqId"]
            unique.append(c)
        return unique[:40]

    # —— 1. 场景法：主流程 + 验收标准

    def _positive(self, a: dict) -> list[dict]:
        module = a["domain"]
        cases: list[dict] = []
        api_main = a["apis"][0] if a["apis"] else None
        api_ref = f"{api_main['method']} {api_main['path']}" if api_main else ""

        features = a["features"] or a["points"] or [a["title"]]
        for feat in features[:6]:
            steps = ["以具备权限的账号进入对应功能页面"]
            if api_main:
                steps.append(f"调用 {api_main['method']} {api_main['path']}（{api_main['summary']}），参数全部合法")
            steps.append("提交并观察系统响应与数据变化")
            cases.append(_case(
                title=f"{_clean(feat, 24)}-主流程成功",
                module=module, ctype="正向", priority="P0",
                precondition="账号已登录且具备该功能权限；前置业务数据（商品/库存/会员等）已就绪",
                steps=steps,
                expected="业务操作成功：返回 HTTP 200 且业务码为 0；列表/详情数据与操作结果一致",
                design_method="场景法（主流程）", related_api=api_ref,
                test_data="合法参数集（含必填项、合法枚举值）",
            ))
        for i, ac_item in enumerate(a["ac"][:4]):
            cases.append(_case(
                title=f"验收点{i + 1}：{_clean(ac_item, 26)}",
                module=module, ctype="正向", priority="P1",
                precondition="满足该验收标准给定的前提条件",
                steps=["按验收标准描述构造场景", "执行被测操作", "逐项核对验收标准"],
                expected=_clean(ac_item, 60),
                design_method="场景法（验收标准核对）",
            ))
        return cases

    # —— 2/3. 边界值分析 + 等价类（无效类）：接口参数矩阵

    def _param_matrix(self, a: dict) -> list[dict]:
        module = a["domain"]
        cases: list[dict] = []
        # 每个需求最多取 3 个接口做参数矩阵（写接口优先）
        apis = sorted(a["apis"], key=lambda x: x["method"] == "GET")[:3]
        for api in apis:
            api_ref = f"{api['method']} {api['path']}"
            fields = [
                *(p for p in api["params"] if isinstance(p, dict) and p.get("name")),
                *(f for f in api["bodyFields"] if isinstance(f, dict) and f.get("name")),
            ]
            # 必填字段：为空/缺失
            for f in fields:
                if not f.get("required"):
                    continue
                name = str(f.get("name"))
                cases.append(_case(
                    title=f"{api['path']} 必填参数 {name} 缺失",
                    module=module, ctype="异常", priority="P0",
                    precondition=f"可访问 {api_ref}（{api['summary']}）",
                    steps=[f"构造请求但不传必填参数 {name}", "其余参数合法", "发起请求"],
                    expected="HTTP 4xx（或业务码非 0）明确提示参数缺失；不产生任何数据写入",
                    design_method="等价类划分（无效类·必填缺失）", related_api=api_ref,
                ))
                break  # 每接口 1 条必填缺失即可，避免同质
            # 类型/枚举：每接口取前 2 个字段
            for f in fields[:2]:
                name, ftype = str(f.get("name")), str(f.get("type", ""))
                desc = str(f.get("description", ""))
                enums = re.findall(r"\b[A-Z][A-Z_]{2,}\b", desc)
                if enums:
                    cases.append(_case(
                        title=f"{api['path']} 参数 {name} 非法枚举值",
                        module=module, ctype="异常", priority="P1",
                        precondition=f"可访问 {api_ref}",
                        steps=[f"将 {name} 设为不在取值范围的值（如 INVALID / 随机串）", "发起请求"],
                        expected=f"请求被拒：返回明确错误提示合法取值（{ ' / '.join(enums[:4]) }），不改变业务数据",
                        design_method="等价类划分（无效枚举类）", related_api=api_ref,
                        test_data=f"{name}=INVALID_X",
                    ))
                elif "int" in ftype.lower() or "long" in ftype.lower() or "big" in ftype.lower():
                    cases.append(_case(
                        title=f"{api['path']} 数值参数 {name} 边界与非法值",
                        module=module, ctype="边界", priority="P1",
                        precondition=f"可访问 {api_ref}",
                        steps=[f"依次将 {name} 设为 0、-1、999999999", "每种取值各发起一次请求"],
                        expected="按业务规则判定：非法负值/超限被拒并返回明确错误；合法边界值正常处理；任何情况不写脏数据",
                        design_method="边界值分析（0/负数/极大值）", related_api=api_ref,
                    ))
                else:
                    cases.append(_case(
                        title=f"{api['path']} 字符串参数 {name} 超长与类型非法",
                        module=module, ctype="边界", priority="P1",
                        precondition=f"可访问 {api_ref}",
                        steps=[f"将 {name} 设为 10000+ 字符超长串（或全空格）", "发起请求", "再设为对应字段类型的非法形态（如注入标签 <script>）"],
                        expected="超长被拒或安全截断返回 4xx，而非 500；非法形态不引发服务端异常",
                        design_method="边界值分析（长度上界）", related_api=api_ref,
                    ))
            # 分页参数（通用边界）
            page_params = [p for p in fields if str(p.get("name")) in ("page", "size", "pageSize") ]
            if page_params:
                cases.append(_case(
                    title=f"{api['path']} 分页参数边界（page=0/size=0/超大 size）",
                    module=module, ctype="边界", priority="P1",
                    precondition=f"列表数据 ≥ 3 条",
                    steps=["分别以 page=0、page=1、size=0、size=1000 请求列表", "观察返回结构与性能"],
                    expected="分页参数按默认值兜底或明确拒绝；size 超大有上限保护；返回结构完整不报 500",
                    design_method="边界值分析（分页边界）", related_api=api_ref,
                ))
        return cases

    # —— 4. 状态迁移法

    def _state_transitions(self, a: dict) -> list[dict]:
        sm = a.get("stateMachine")
        if not sm:
            return []
        module = a["domain"]
        state_api = next((f"{x['method']} {x['path']}" for x in a["apis"]
                          if x["method"] in ("POST", "PUT")), "")
        cases: list[dict] = []
        for src, dst, action, evidence in sm.get("legal", []):
            cases.append(_case(
                title=f"{src} → {dst}（{action}）",
                module=module, ctype="状态流转", priority="P0",
                precondition=f"构造一笔处于 {src} 状态的业务单据，操作人具备相应权限",
                steps=[f"确认单据当前状态为 {src}", f"执行「{action}」操作", "刷新单据并核对状态与时间戳"],
                expected=f"单据状态变为 {dst}，状态时间戳更新；流水/日志留痕。证据：{evidence}",
                design_method="状态迁移法（合法迁移）", related_api=state_api,
                db_check=f"更新后状态字段={dst}",
            ))
        for src, dst, why in sm.get("illegal", []):
            cases.append(_case(
                title=f"非法迁移拦截：{src} → {dst}（{_clean(why, 20)}）",
                module=module, ctype="状态流转", priority="P0",
                precondition=f"构造一笔处于 {src} 状态的单据",
                steps=[f"尝试通过接口/页面将单据从 {src} 迁移到 {dst}", "观察系统响应与数据"],
                expected=f"迁移被守卫拒绝：返回业务错误码与原因，状态保持 {src} 不变，无任何副作用（库存/资金不受影响）",
                design_method="状态迁移法（非法迁移）", related_api=state_api,
                db_check=f"状态字段仍为 {src}；相关库存/金额字段不变",
            ))
        return cases

    # —— 5. 负面清单转化

    def _negatives(self, a: dict) -> list[dict]:
        module = a["domain"]
        return [
            _case(
                title=f"[{nid}] {_clean(scenario, 28)}",
                module=module, ctype="异常", priority="P0",
                precondition="已构造该负面场景要求的异常数据或环境",
                steps=[f"构造场景：{_clean(scenario, 50)}", "执行目标操作", "观察响应、数据与日志"],
                expected="按负面场景的测试含义被正确拦截（业务错误码，非 500）；若实际放行，则为产品缺陷需提单",
                design_method="错误推测法（负面清单 NEG）",
            )
            for nid, scenario in a.get("negs", [])[:6]
        ]

    # —— 6. 并发与幂等（错误推测法）

    def _concurrency_idempotency(self, a: dict) -> list[dict]:
        rules_text = " ".join(r[0] if isinstance(r, tuple) else str(r) for r in a["rules"])
        cases: list[dict] = []
        module = a["domain"]
        write_api = next((f"{x['method']} {x['path']}" for x in a["apis"]
                          if x["method"] in ("POST", "PUT")), "")

        if "幂等" in rules_text or "idempotent" in rules_text.lower():
            cases.append(_case(
                title="重复提交幂等校验（同一幂等键二次提交）",
                module=module, ctype="并发幂等", priority="P0",
                precondition="已登录，拿到有效的下单/提交幂等键",
                steps=["首次携带幂等键提交，确认成功", "携带同一幂等键立即再次提交", "核对订单数量与库存"],
                expected="第二次提交返回与首次一致的结果（幂等成功）或明确的重复提示；不产生第二笔订单、不二次扣减库存",
                design_method="错误推测法（幂等键重复）", related_api=write_api,
                db_check="订单数=1；库存流水无重复记录",
            ))
        if "乐观锁" in rules_text or "version" in rules_text.lower() or "SELECT FOR UPDATE" in rules_text:
            cases.append(_case(
                title="并发下单同一 SKU 库存不超卖",
                module=module, ctype="并发幂等", priority="P0",
                precondition="SKU 库存仅剩 1 件，准备两个并发会话",
                steps=["两个会话同时提交购买 1 件该 SKU 的订单", "等待并发完成", "核对订单数与库存字段"],
                expected="仅 1 笔订单成功，另一笔返回库存不足；库存不为负（乐观锁/行锁生效）",
                design_method="错误推测法（并发竞争）", related_api=write_api,
                db_check="stock.physical_stock - locked_stock ≥ 0",
            ))
        return cases

    # —— 7. 安全测试

    def _security(self, a: dict) -> list[dict]:
        module = a["domain"]
        cases: list[dict] = []
        protected = [x for x in a["apis"] if "login" in str(x.get("auth", ""))]
        public = [x for x in a["apis"] if str(x.get("auth", "")) == "public"]
        api = protected[0] if protected else (a["apis"][0] if a["apis"] else None)
        if api:
            api_ref = f"{api['method']} {api['path']}"
            cases.append(_case(
                title=f"未登录访问 {api['path']}",
                module=module, ctype="安全", priority="P0",
                precondition="不携带任何访问令牌",
                steps=[f"直接请求 {api_ref}（无 Authorization 头）", "观察响应"],
                expected="返回 401 未授权；响应体不泄露业务数据与堆栈信息",
                design_method="安全测试（鉴权）", related_api=api_ref,
            ))
            cases.append(_case(
                title=f"越权访问他人资源 {api['path']}",
                module=module, ctype="安全", priority="P0",
                precondition="登录用户 A；存在属于用户 B 的资源（订单/售后单等）",
                steps=[f"使用 A 的令牌请求 {api_ref}，资源 ID 指向 B 的数据", "观察响应内容"],
                expected="被拒绝（404/403/业务错误码），仅返回 A 有权的数据；不发生越权读写",
                design_method="安全测试（水平越权）", related_api=api_ref,
            ))
        # 敏感字段脱敏（订单手机号有 mask 字段的真实证据）
        cols = [c.get("name", "") for t in a["tables"] for c in t.get("columns", [])]
        if any("mask" in str(c) or "phone" in str(c) or "password" in str(c) for c in cols):
            cases.append(_case(
                title="敏感字段脱敏与不回传",
                module=module, ctype="安全", priority="P1",
                precondition="存在含手机号/密码等敏感字段的查询接口",
                steps=["以合法身份查询含敏感字段的列表/详情", "检查响应 JSON 中敏感字段形态", "尝试用响应中数据登录/联系"],
                expected="手机号等以脱敏形态返回（如 138****1234）；密码类字段任何接口不回传；明文不可恢复",
                design_method="安全测试（数据脱敏）",
            ))
        # 公开接口不得暴露内部信息
        if public:
            p = public[0]
            cases.append(_case(
                title=f"公开接口 {p['path']} 不泄露内部信息",
                module=module, ctype="安全", priority="P2",
                precondition="无需登录即可访问该公开接口",
                steps=[f"请求 {p['method']} {p['path']}", "检查响应体与错误分支"],
                expected="仅返回对外必要字段；错误响应不含堆栈、SQL、内部路径",
                design_method="安全测试（信息泄露）", related_api=f"{p['method']} {p['path']}",
            ))
        return cases

    # —— 8. 数据一致性校验

    def _consistency(self, a: dict) -> list[dict]:
        rules_text = " ".join(r[0] if isinstance(r, tuple) else str(r) for r in a["rules"])
        cases: list[dict] = []
        module = a["domain"]

        if "快照" in rules_text or any("snapshot" in str(c.get("name", "")) for t in a["tables"] for c in t.get("columns", [])):
            cases.append(_case(
                title="下单快照一致性（商品信息变更不影响已有订单）",
                module=module, ctype="数据一致性", priority="P1",
                precondition="存在在售商品；账号可下单",
                steps=["下单成功后记录订单明细的商品标题/单价/规格", "后台修改该商品标题、价格、下架", "查询原订单明细"],
                expected="订单明细仍为下单时快照（标题/价格/规格/图片不变）；列表与详情一致",
                design_method="数据一致性校验（快照不变式）",
                db_check="order_item.title/price/specs 与下单时一致，不随 spu/sku 变更",
            ))
        if "库存" in rules_text:
            cases.append(_case(
                title="库存不变式校验（physical ≥ locked，可售非负）",
                module=module, ctype="数据一致性", priority="P1",
                precondition="选定 SKU 与仓库，记录当前库存",
                steps=["执行一轮完整业务操作（下单→支付→发货 / 或出入库调整）", "每步之后核对库存三元组", "计算可售库存 = physical - locked"],
                expected="任一时刻 physical_stock ≥ locked_stock ≥ 0；每笔库存变动在 stock_log 有对应流水（类型、数量、原因可对账）",
                design_method="数据一致性校验（不变式+流水对账）",
                db_check="stock.physical_stock ≥ locked_stock；stock_log 变动合计 = 库存差值",
            ))
        if "金额" in rules_text or any("amount" in str(c.get("name", "")) or "price" in str(c.get("name", "")) for t in a["tables"] for c in t.get("columns", [])):
            cases.append(_case(
                title="金额合计一致性（明细小计之和 = 订单总额 + 运费关系）",
                module=module, ctype="数据一致性", priority="P1",
                precondition="存在含 ≥2 个明细的订单",
                steps=["查询订单 total_amount / pay_amount / freight", "逐条取明细 subtotal 与 quantity", "手工计算核对"],
                expected="total_amount = Σ(subtotal)；pay_amount 与 total_amount、freight 的关系符合业务定义；金额为 2 位小数无浮点误差",
                design_method="数据一致性校验（金额对账）",
                db_check="Σ(order_item.subtotal) = order.total_amount",
            ))
        return cases


# ---------------------------------------------------------------- 主流程（CLI / 被路由调用）


def existing_case_keys(cur, project_id: str) -> dict[str, set[str]]:
    """已有用例：requirementId → 标题集合（避免重复生成）。"""
    cur.execute(
        "SELECT data->>'requirementId', data->>'title' FROM documents WHERE collection='testCases'"
    )
    out: dict[str, set[str]] = {}
    for rid, title in cur.fetchall():
        if rid:
            out.setdefault(rid, set()).add(title or "")
    return out


def next_case_number(cur) -> int:
    cur.execute(
        """SELECT coalesce(max((substring(doc_id from '[0-9]+$'))::int), 0)
           FROM documents WHERE collection='testCases' AND doc_id ~ '^TC-[0-9]+$'"""
    )
    return int(cur.fetchone()[0] or 0) + 1


def generate_for_requirement(agent: SeniorTestEngineerAgent, req: dict, dry_run: bool = False,
                             overwrite: bool = False) -> list[dict[str, Any]]:
    a = agent.analyze(req)
    cases = agent.design(a)
    for c in cases:
        c["source"] = "测试工程师AGENT"
        c["owner"] = "资深测试工程师 AGENT"
        c["status"] = "待评审"
        c["version"] = "v1"
    if dry_run:
        return cases
    # 落库交给路由层（store 管理编号与写入），CLI 模式在这里直接写
    return cases


def main() -> None:
    ap = argparse.ArgumentParser(description="测试工程师 AGENT")
    ap.add_argument("--only", help="只生成指定需求 ID")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--overwrite", action="store_true", help="覆盖已有 AGENT 用例（同需求同标题）")
    args = ap.parse_args()

    with psycopg.connect(dsn()) as conn:
        cur = conn.cursor()
        agent = SeniorTestEngineerAgent(cur)
        reqs = load_requirements(cur, args.only)

        have = existing_case_keys(cur, PROJECT)
        no_case = [r for r in reqs if not have.get(r["id"])]

        targets = reqs if args.only else no_case
        print(f"目标需求：{len(targets)} 条（全量 {len(reqs)}，已有用例 {len(reqs) - len(no_case)}）")

        seq = next_case_number(cur)
        total = 0
        for req in targets:
            cases = generate_for_requirement(agent, req, dry_run=True)
            skip = 0
            if not args.overwrite:
                existing = have.get(req["id"], set())
                cases = [c for c in cases if c["title"] not in existing]
                skip = len(agent.design(agent.analyze(req))) - len(cases) if False else 0
            if args.dry_run:
                print(f"\n=== {req['id']} {req['title']} → {len(cases)} 条 ===")
                for c in cases[:5]:
                    print(f"  [{c['type']}/{c['priority']}] {c['title']}（{c['designMethod']}）")
                if len(cases) > 5:
                    print(f"  … 其余 {len(cases) - 5} 条")
                total += len(cases)
                continue
            for c in cases:
                case_id = f"TC-{seq}"
                seq += 1
                cur.execute(
                    """INSERT INTO documents (collection, doc_id, seq, data)
                       VALUES ('testCases', %s,
                               (SELECT coalesce(max(seq),0)+1 FROM documents WHERE collection='testCases'),
                               %s::jsonb)""",
                    (case_id, json.dumps({**c, "id": case_id, "projectId": PROJECT,
                                          "updatedAt": None}, ensure_ascii=False)),
                )
            total += len(cases)
            print(f"  {req['id']:<22} {len(cases):>3} 条（累计 {total}）")
        if not args.dry_run:
            conn.commit()
            print(f"\n完成：测试工程师 AGENT 共生成 {total} 条用例（状态=待评审）")
        else:
            print(f"\n（dry-run 预览，共 {total} 条）")


if __name__ == "__main__":
    main()
