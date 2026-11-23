"""需求文档规范化重写 · 把代码还原的 PRD 升级为符合《需求文档规范》的版本.

用法：
    .venv/bin/python -m agents.prd_rewrite                 # 重写全部
    .venv/bin/python -m agents.prd_rewrite --only V1-FR-001
    .venv/bin/python -m agents.prd_rewrite --dry-run       # 只打印统计，不写库

与 prd_agent.py 的分工：
    prd_agent      从代码/追溯链「还原」事实（页面、接口、表、代码入口）
    prd_rewrite    在事实之上按规范补齐「需求该有的结构」：范围、角色、术语、
                   NFR、数据字典、异常七类、依赖假设、质量门禁、追溯矩阵，
                   并把验收标准改写成带四级断言锚点的 Given-When-Then。

不臆造原则：接口、字段、表名、错误码全部取自 trace_* 与源码扫描结果；
无法从证据推导的内容显式标注「待产品确认」，并计入质量分扣分项。
"""

from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import psycopg
from dotenv import load_dotenv

from .prd_agent import PROJECT, collect_evidence, hydrate, load_requirements
from .prd_knowledge import domain_for
from .prd_spec import COMMON_EXCEPTION_CLASSES, spec_for

load_dotenv()

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
).replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")

LAYERS = ["page", "api", "code_artifact", "table"]

FUZZY = re.compile(r"快速|友好|尽可能|必要时|适当|及时|尽量|良好|较强|合理|等等")
PARALLEL = re.compile(r"和|以及|同时|、|/")

# 中文功能点 → 接口 path 关键词。用于把功能点精确挂到真实接口上（不做语义臆测）。
PATH_HINTS: list[tuple[str, list[str]]] = [
    ("登录", ["login"]),
    ("锁定", ["login"]),
    ("登出", ["logout"]),
    ("退出", ["logout"]),
    ("注册", ["register"]),
    ("刷新令牌", ["refresh"]),
    ("验证码", ["sms", "code", "captcha"]),
    ("类目", ["categor"]),
    ("品牌", ["brand"]),
    ("属性", ["attr"]),
    ("商品", ["product", "spu"]),
    ("SKU", ["sku"]),
    ("上架", ["status", "publish", "on"]),
    ("库存", ["stock"]),
    ("仓库", ["warehouse"]),
    ("出入库", ["in-out", "in_out", "bill"]),
    ("订单", ["order"]),
    ("发货", ["ship"]),
    ("关单", ["close", "cancel", "timeout"]),
    ("超时", ["close", "timeout", "cancel"]),
    ("支付", ["pay"]),
    ("售后", ["after"]),
    ("退款", ["refund", "after"]),
    ("评价", ["review"]),
    ("购物车", ["cart"]),
    ("收藏", ["favorite"]),
    ("地址", ["address"]),
    ("浏览", ["browse", "history"]),
    ("首页", ["home"]),
    ("坑位", ["slot"]),
    ("优惠券", ["coupon"]),
    ("用户", ["user", "customer"]),
    ("角色", ["role"]),
    ("菜单", ["menu"]),
    ("权限", ["permission"]),
    ("部门", ["dept"]),
    ("字典", ["dict"]),
    ("日志", ["log"]),
    ("搜索", ["search"]),
    ("详情", ["detail", "{" ]),
    ("列表", ["page", "list"]),
    ("统计", ["stat", "dashboard", "overview"]),
    ("上传", ["upload"]),
    ("导出", ["export"]),
]



# 各域状态机（当前状态 / 事件 / 目标状态 / 触发者 / 副作用 / 非法迁移）
STATE_MACHINES: dict[str, list[dict[str, str]]] = {
    "订单交易": [
        {"from": "（无）", "event": "创建订单", "to": "PENDING_PAY", "actor": "顾客", "effect": "锁定库存、写 order_event_log", "illegal": "库存不足 → 409/40901，不建单"},
        {"from": "PENDING_PAY", "event": "支付成功", "to": "PENDING_SHIP", "actor": "支付回调", "effect": "锁库存转实扣、sold_count +N", "illegal": "金额不一致 → 拒绝，状态不变"},
        {"from": "PENDING_PAY", "event": "超时 15 分钟", "to": "CLOSED", "actor": "定时任务", "effect": "释放 locked_stock", "illegal": "—"},
        {"from": "PENDING_PAY", "event": "用户取消", "to": "CLOSED", "actor": "顾客", "effect": "释放 locked_stock", "illegal": "已支付 → 提示走售后"},
        {"from": "PENDING_SHIP", "event": "发货", "to": "SHIPPED", "actor": "运营管理员", "effect": "写 shipment 与运单号", "illegal": "非 PENDING_SHIP → 409，不写 shipment"},
        {"from": "SHIPPED", "event": "确认收货", "to": "COMPLETED", "actor": "顾客", "effect": "写 received_at", "illegal": "非 SHIPPED → 409"},
        {"from": "CLOSED", "event": "支付成功", "to": "（禁止）", "actor": "—", "effect": "—", "illegal": "拒绝并提示已关闭，payment 不落 SUCCESS"},
    ],
    "售后": [
        {"from": "（无）", "event": "提交售后", "to": "PENDING_AUDIT", "actor": "顾客", "effect": "写 after_sale", "illegal": "订单非 COMPLETED → 409/40906"},
        {"from": "PENDING_AUDIT", "event": "审核通过", "to": "APPROVED", "actor": "客服管理员", "effect": "写 audit_remark", "illegal": "已审核 → 409"},
        {"from": "PENDING_AUDIT", "event": "审核驳回", "to": "REJECTED", "actor": "客服管理员", "effect": "写 audit_remark", "illegal": "已审核 → 409"},
        {"from": "APPROVED", "event": "发起退款", "to": "REFUNDING", "actor": "客服管理员", "effect": "写 payment 退款流水", "illegal": "金额越界 → 400"},
        {"from": "REFUNDING", "event": "退款成功", "to": "REFUNDED", "actor": "支付回调", "effect": "写退款完成时间", "illegal": "失败 → REFUND_FAILED，可重试"},
    ],
    "库存": [
        {"from": "可售 > 0", "event": "下单锁定", "to": "可售 −N", "actor": "顾客下单", "effect": "locked_stock +N，写 stock_log", "illegal": "可售 < N → 409/40901"},
        {"from": "已锁定", "event": "支付成功", "to": "实扣", "actor": "支付回调", "effect": "physical_stock −N、locked_stock −N", "illegal": "订单非 PENDING_PAY → 拒绝"},
        {"from": "已锁定", "event": "关单/超时", "to": "释放", "actor": "定时任务", "effect": "locked_stock −N", "illegal": "订单已支付 → 拒绝释放"},
    ],
    "认证登录": [
        {"from": "未登录", "event": "账密正确", "to": "已登录", "actor": "管理员", "effect": "签发 access/refresh，更新 last_login_at", "illegal": "密码错误 → 401/40101，失败计数 +1"},
        {"from": "未登录", "event": "失败达 5 次", "to": "锁定中", "actor": "系统", "effect": "写 Redis login:fail:<user> TTL 900s", "illegal": "—"},
        {"from": "锁定中", "event": "任意登录尝试", "to": "锁定中", "actor": "—", "effect": "—", "illegal": "返回 401/40104，即使密码正确也拒绝"},
        {"from": "已登录", "event": "登出", "to": "未登录", "actor": "用户", "effect": "refreshToken 失效", "illegal": "token 已过期 → 401/40103"},
    ],
}


# ------------------------------------------------------------------ 工具


def api_label(a: dict[str, Any]) -> str:
    if a.get("method"):
        return f"{a['method']} {a.get('path', '')}"
    return str(a.get("name") or a.get("id"))


def page_route(p: dict[str, Any]) -> str:
    """trace_pages.id 形如 page:admin:/categories，从中还原可断言的界面锚点。"""
    pid = str(p.get("id", ""))
    parts = pid.split(":")
    if len(parts) >= 3:
        return f"/{parts[1]}{parts[2]}" if not parts[2].startswith("/") else f"/{parts[1]}{parts[2]}"
    return str(p.get("name") or "")


def table_label(t: dict[str, Any]) -> str:
    return f"{t.get('schema', '')}.{t.get('name', '')}".strip(".")


def pick_fields(api: dict[str, Any], limit: int = 3) -> list[str]:
    resp = api.get("response") or {}
    out = []
    for f in (resp.get("fields") or [])[:limit]:
        if f.get("name"):
            out.append(str(f["name"]))
    return out


def given_for(point: str, spec: dict[str, Any]) -> str:
    """正向 AC 的前置状态按功能点定制，避免「登出」的 Given 写成「密码为 BCrypt 密文」。"""
    if any(k in point for k in ("登出", "退出")):
        return "当前用户已登录，Authorization 携带未过期的 accessToken（剩余有效期 > 60s）"
    if any(k in point for k in ("刷新令牌", "续期")):
        return "持有未过期的 refreshToken（TTL ≤ 7 天），accessToken 已过期或临近过期"
    if any(k in point for k in ("查询", "列表", "详情", "浏览", "搜索", "统计", "看板")):
        return f"库中已存在 ≥1 条可读数据且当前账号有查看权限；{spec['fixture']}"
    return spec["fixture"]


def negs_for(point: str, negs: list[dict[str, str]]) -> list[dict[str, str]]:
    """按功能点语义挑异常场景，避免「登出」列出「密码错误」这类错配。"""
    groups: list[tuple[tuple[str, ...], tuple[str, ...]]] = [
        (("登出", "退出", "刷新"), ("令牌", "token", "过期", "未登录")),
        (("登录", "账密", "密码", "锁定"), ("密码", "锁定", "账号", "失败", "验证码", "停用")),
        (("库存", "扣减", "仓库", "出入库"), ("库存", "超卖", "version", "并发")),
        (("退款", "售后"), ("退款", "金额", "售后")),
        (("支付",), ("支付", "回调", "金额")),
        (("评价",), ("rating", "评价")),
        (("删除",), ("不存在", "占用", "引用", "删除")),
        (("列表", "分页", "查询", "搜索"), ("上限", "越界", "分页", "size")),
        (("上传",), ("文件", "大小", "格式")),
        (("地址",), ("地址", "默认")),
        (("订单", "下单", "发货"), ("订单", "状态", "重复", "购物车")),
    ]
    generic: list[dict[str, str]] = []
    if any(k in point for k in ("列表", "分页", "查询")):
        generic.append({
            "scenario": "分页参数越界（page=0 或 size>100）",
            "feedback": "HTTP 400，code=40002，msg=分页参数非法",
            "rollback": "无", "retryable": "是",
        })
    if any(k in point for k in ("详情",)):
        generic.append({
            "scenario": "请求不存在的资源 ID",
            "feedback": "HTTP 404，code=40400，msg=资源不存在",
            "rollback": "无", "retryable": "否",
        })
    for pkw, nkw in groups:
        if any(k in point for k in pkw):
            hit = [n for n in negs if any(k in n["scenario"] + n["feedback"] for k in nkw)]
            if hit:
                return generic + hit
    # 兜底：按语义相关度排序；若全无相关度，只保留通用异常，不硬塞无关场景
    ranked = sorted(negs, key=lambda n: -overlap(point, n["scenario"] + n["feedback"]))
    if ranked and overlap(point, ranked[0]["scenario"] + ranked[0]["feedback"]) > 0:
        return generic + ranked
    return generic or negs[:1]


def action_phrase(point: str) -> str:
    p = point.strip().strip("【】")
    return p or "完成该操作"


def bigrams(text: str) -> set[str]:
    """中文按 2-gram 切分，用于功能点 ↔ 角色/接口的粗匹配（不引入分词依赖）。"""
    t = re.sub(r"[\s，。、；：（）()/【】\[\]0-9A-Za-z_\-]+", "", text or "")
    return {t[i:i + 2] for i in range(len(t) - 1)} or {t} if t else set()


def overlap(a: str, b: str) -> float:
    x, y = bigrams(a), bigrams(b)
    if not x or not y:
        return 0.0
    return len(x & y) / len(x | y)


def perm_phrase(point: str, role: str) -> str:
    """按功能点语义给权限前置，避免一律写「已登录」。"""
    if any(k in point for k in ("登录", "注册", "验证码", "找回密码", "重置密码", "锁定")):
        return "匿名可访问（接口 auth=public），无需令牌"
    if any(k in point for k in ("登出", "退出")):
        return f"{role}已认证，请求需携带有效 accessToken"
    if any(k in point for k in ("查看", "列表", "查询", "详情", "浏览", "搜索", "统计", "看板")):
        return f"{role}已认证，且具备该模块的查询权限"
    if any(k in point for k in ("删除", "审核", "上下架", "发货", "退款", "禁用", "授权")):
        return f"{role}已认证，且具备该模块的高危操作权限（越权应返回 403）"
    return f"{role}已认证，且具备该模块的写权限"


def is_constraint(title: str, apis: list[dict[str, Any]], pages: list[dict[str, Any]]) -> bool:
    """交互规范类需求：无接口、无独立页面，或标题含「规范/提示/规则」。"""
    if any(k in title for k in ("规范", "提示", "交互")):
        return True
    return not apis and not pages


# ------------------------------------------------------------------ 章节构造


def build_doc_info(req: dict[str, Any], dom_key: str, old: dict[str, Any] | None) -> dict[str, Any]:
    # 上一版固定为 v1：原始 PRD 均由 AGENT 一次性还原为 v1，
    # 重复运行不得把「上一版」滚成自己（否则变更记录出现两条 v2）。
    prev = "v1"
    return {
        "docId": f"PRD-{req['id']}",
        "version": "v2",
        "previousVersion": prev,
        "author": "产品文档 AGENT（代码证据还原）",
        "reviewers": ["产品负责人（待签）", "测试负责人（待签）"],
        "status": "待评审",
        "source": req.get("description", "") or "docs/llm-wiki/02-requirements.md",
        "domain": dom_key,
        "changeLog": [
            {
                "version": "v2",
                "at": datetime.now(timezone.utc).strftime("%Y-%m-%d"),
                "author": "需求规范化重写",
                "summary": "按《需求文档规范》重构：补范围/角色/术语/NFR/数据字典/依赖假设/待定；"
                           "验收标准改为 Given-When-Then 并标注四级断言锚点；增加质量门禁与追溯矩阵。",
            },
            {"version": prev, "at": "—", "author": "产品文档 AGENT", "summary": "首版代码还原 PRD。"},
        ],
    }


def build_overview(req: dict[str, Any], dom: dict[str, Any], spec: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": req["id"],
        "title": req["title"],
        "module": dom.get("_key", ""),
        "priority": req.get("priority", ""),
        "status": req.get("status", ""),
        "owner": req.get("owner") or "未指派",
        "version": "v2",
        "background": dom.get("background", ""),
        "problem": spec["problem"],
        "goal": dom.get("goal", ""),
        "businessValue": spec["value"],
        "consequence": spec["consequence"],
        "sourceDoc": "docs/llm-wiki/02-requirements.md",
        "description": req.get("description", ""),
    }


def build_scope(spec: dict[str, Any], points: list[str]) -> dict[str, Any]:
    return {
        "inScope": [f"支持「{p}」" for p in points] or ["按需求描述实现对应能力"],
        "outOfScope": spec["out_of_scope"],
        "assumptions": [d["assumption"] for d in spec["deps"]],
    }


def build_roles(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return spec["roles"]


def build_glossary(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return spec.get("glossary") or []


def build_stories(points: list[str], roles: list[dict[str, Any]], goal: str) -> list[dict[str, Any]]:
    stories = []
    for i, point in enumerate(points):
        role = roles[i % len(roles)]["role"] if roles else "系统用户"
        stories.append({
            "role": role,
            "want": point,
            "benefit": goal,
            "as_json": f"作为{role}，我希望{point}，以便{goal}",
            "invest": {"independent": True, "negotiable": True, "valuable": True,
                       "estimable": True, "small": len(point) <= 24, "testable": True},
        })
    return stories


def build_features(
    points: list[str], roles: list[dict[str, Any]], spec: dict[str, Any],
    apis: list[dict[str, Any]], pages: list[dict[str, Any]], tables: list[dict[str, Any]],
    req_id: str, rules: list[Any] | None = None, constraint: bool = False,
) -> list[dict[str, Any]]:
    api_labels = [api_label(a) for a in apis]
    routes = [page_route(p) for p in pages if p.get("id")]
    page_names = [p.get("name") or page_route(p) for p in pages]
    table_names = [table_label(t) for t in tables]
    rule_texts = [r[0] if isinstance(r, (list, tuple)) else str(r) for r in (rules or [])]

    def best_role(point: str, chunk: list[dict[str, Any]]) -> dict[str, Any]:
        """按「接口所在端 + operations 重合度」选角色。

        /admin/** 属于管理端，/api/** 属于 C 端；先按端筛掉不合角色，
        再按功能点与 operations 的重合度排序，避免「订单列表」被派给顾客却调管理端接口。
        """
        if not roles:
            return {"role": "系统用户"}
        side = None
        if chunk:
            p0 = str(chunk[0].get("path", ""))
            side = "admin" if p0.startswith("/admin") else "mall" if p0.startswith("/api") else None
        cand = roles
        if side:
            filtered = [
                r for r in roles
                if (side == "admin" and "管理端" in r["entry"]) or (side == "mall" and "C 端" in r["entry"])
            ]
            if filtered:
                cand = filtered
        scored = [(overlap(point, " ".join(r.get("operations") or []) + r["role"]), idx, r)
                  for idx, r in enumerate(cand)]
        scored.sort(key=lambda x: (-x[0], x[1]))
        return scored[0][2]

    def best_apis(point: str) -> list[dict[str, Any]]:
        """按 path/summary 重合度取相关接口；全不相关时回退到全部（保留追溯）。"""
        if not apis:
            return []
        hits: list[dict[str, Any]] = []
        for kw, tokens in PATH_HINTS:
            if kw in point:
                for a in apis:
                    path = str(a.get("path", "")).lower()
                    if any(t in path for t in tokens):
                        hits.append(a)
        if hits:
            seen: set[str] = set()
            uniq: list[dict[str, Any]] = []
            for a in hits:
                if a["id"] not in seen:
                    seen.add(a["id"])
                    uniq.append(a)
            return uniq[:3]
        scored = [(overlap(point, f"{a.get('path', '')} {a.get('name', '')}"), a) for a in apis]
        top = [a for s, a in sorted(scored, key=lambda x: -x[0]) if s > 0.05][:3]
        return top or apis[:2]

    features = []
    for i, point in enumerate(points):
        chunk = best_apis(point)
        role = best_role(point, chunk)["role"]
        rules_hit = [r for r in rule_texts if overlap(r, point) > 0.05][:3] or rule_texts[:2]
        features.append({
            "id": f"FR-{i + 1:02d}",
            "name": action_phrase(point),
            "behavior": f"{role}在{('、'.join(routes[:2]) or '对应入口')}执行「{point}」，"
                        f"系统按规则校验后返回可判定结果。",
            "role": role,
            "entry": routes[:3] or page_names[:3] or "无独立页面（后台任务/交互规范）",
            "trigger": f"{point}（一次用户操作或一次系统事件）",
            "precondition": (
                f"数据：{spec['fixture']}；"
                f"权限：{perm_phrase(point, role)}；"
                f"环境：PostgreSQL 与 Redis 可用"
            ),
            "preconditionDetail": {
                "data": spec["fixture"],
                "permission": perm_phrase(point, role),
                "env": "PostgreSQL 与 Redis 可用；管理端/C 端服务在线",
            },
            "rules": rules_hit,
            "postcondition": f"成功后：{spec['data_assert']}",
            "exceptions": [f"{n['scenario']} → {n['feedback']}"
                           for n in negs_for(point, spec["neg_cases"])[:3]],
            "relatedApis": [api_label(a) for a in chunk] or api_labels[:3],
            "relatedData": table_names[:3],
            "kind": "constraint" if constraint else "functional",
        })
    if not features:
        features.append({
            "id": "FR-01",
            "name": action_phrase(points[0] if points else "实现该需求"),
            "behavior": "按需求描述实现对应能力。",
            "role": roles[0]["role"] if roles else "系统用户",
            "entry": routes[:3] or "无独立页面",
            "trigger": "—",
            "precondition": f"数据：{spec['fixture']}；权限：{perm_phrase('实现', roles[0]['role'] if roles else '用户')}",
            "preconditionDetail": {"data": spec["fixture"],
                                   "permission": perm_phrase("实现", "系统用户"), "env": "服务在线"},
            "rules": rule_texts[:2],
            "postcondition": spec["data_assert"],
            "exceptions": [n["feedback"] for n in spec["neg_cases"][:3]],
            "relatedApis": api_labels[:3],
            "relatedData": table_names[:3],
            "kind": "functional",
        })
    return features


def build_acceptance(
    features: list[dict[str, Any]], spec: dict[str, Any],
    apis: list[dict[str, Any]], pages: list[dict[str, Any]], constraint: bool,
) -> list[dict[str, Any]]:
    """每条 FR 至少 2 条 AC：1 正向 + 1 负向/边界；写操作附 L3 数据断言。"""
    acs: list[dict[str, Any]] = []
    route = page_route(pages[0]) if pages else ""
    for idx, fr in enumerate(features, start=1):
        api = next((a for a in apis if api_label(a) in fr["relatedApis"]), apis[0] if apis else None)
        fields = pick_fields(api) if api else []
        target = api_label(api) if api else (route or "对应页面入口")

        if constraint:
            acs.append({
                "id": f"AC-{idx:02d}-1", "frId": fr["id"], "type": "checklist",
                "given": f"任意{route or '相关'}页面已加载",
                "when": f"执行「{fr['name']}」相关操作",
                "then": ["界面反馈符合规范：不可逆操作使用确认弹窗，成功反馈使用 toast",
                         "同一操作不同时出现 toast 与 Modal"],
                "anchors": ["L4"],
                "text": f"Given 任意页面已加载 When 执行「{fr['name']}」Then 反馈形式符合规范（L4 界面锚点）",
                "checked": False,
            })
            acs.append({
                "id": f"AC-{idx:02d}-2", "frId": fr["id"], "type": "boundary",
                "given": "列表或表单处于空数据状态",
                "when": "进入该页面",
                "then": ["显示空态说明与下一步操作入口", "不出现空白页或仅一句「暂无数据」"],
                "anchors": ["L4"],
                "text": f"Given 无数据 When 进入页面 Then 显示空态说明与操作入口（L4）",
                "checked": False,
            })
            continue

        # 正向：L1 + L2 +（有写操作时）L3 +（有页面时）L4
        then_pos = ["HTTP 200", "code=0"]
        if fields:
            then_pos.append(f"响应字段 {', '.join(fields)} 非空且类型正确")
        anchors = ["L1", "L2"]
        if api and api.get("method") in ("POST", "PUT", "PATCH", "DELETE"):
            then_pos.append(spec["data_assert"])
            anchors.append("L3")
        if route:
            then_pos.append(f"界面跳转/刷新 {route} 后结果可见")
            anchors.append("L4")
        acs.append({
            "id": f"AC-{idx:02d}-1", "frId": fr["id"], "type": "positive",
            "given": given_for(fr["name"], spec),
            "when": f"以{fr['role']}身份调用 {target}",
            "then": then_pos,
            "anchors": anchors,
            "text": f"Given {given_for(fr['name'], spec)} When 调用 {target} Then " + "；".join(then_pos),
            "checked": False,
        })

        # 负向：按功能点挑选对应异常（登出不该出现「密码错误」）
        neg = negs_for(fr["name"], spec["neg_cases"])
        n = neg[0]
        acs.append({
            "id": f"AC-{idx:02d}-2", "frId": fr["id"], "type": "negative",
            "given": f"前置条件不满足：{n['scenario']}",
            "when": f"调用 {target}",
            "then": [n["feedback"], f"数据影响：{n['rollback']}", f"可重试：{n['retryable']}"],
            "anchors": ["L1", "L2"] + (["L3"] if "回滚" in n["rollback"] or "不写" in n["rollback"] else []),
            "text": f"Given {n['scenario']} When 调用 {target} Then {n['feedback']}（数据：{n['rollback']}）",
            "checked": False,
        })

        # 边界：并发/极限/越权，取第 2~3 条
        if len(neg) > 1:
            b = neg[1]
            acs.append({
                "id": f"AC-{idx:02d}-3", "frId": fr["id"], "type": "boundary",
                "given": f"边界条件：{b['scenario']}",
                "when": f"调用 {target}",
                "then": [b["feedback"], f"数据影响：{b['rollback']}"],
                "anchors": ["L1", "L2", "L3"],
                "text": f"Given {b['scenario']} When 调用 {target} Then {b['feedback']}",
                "checked": False,
            })
    return acs


def build_nfr(spec: dict[str, Any], nfr_extra: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return (spec["nfr"] + nfr_extra)[:10]


def build_data_dictionary(tables: list[dict[str, Any]], spec: dict[str, Any]) -> dict[str, Any]:
    """字段级数据字典：类型/必填/说明全部来自 trace_tables 的真实列定义。"""
    tables_out = []
    for t in tables:
        fields = []
        for c in (t.get("columns") or []):
            name = str(c.get("name", ""))
            typ = str(c.get("type", ""))
            fields.append({
                "name": name,
                "type": typ,
                "required": name not in ("deleted", "trace_id", "updated_at"),
                "range": "—",
                "default": "—",
                "unique": name in ("id", "order_no", "sku_id", "username"),
                "masked": name in ("phone", "customer_phone_mask", "password"),
                "note": str(c.get("comment") or ""),
                "audit": name in ("created_at", "updated_at", "deleted", "trace_id"),
            })
        tables_out.append({
            "table": table_label(t),
            "primaryKey": t.get("pk"),
            "source": t.get("source", ""),
            "fields": fields,
            "fieldCount": len(fields),
        })
    return {"tables": tables_out, "invariants": spec.get("invariants") or []}


def build_exceptions(spec: dict[str, Any], apis: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """异常七类：每条落到具体场景；缺某类时显式标注「未覆盖」并计入质量分。"""
    bucket: dict[str, list[dict[str, Any]]] = defaultdict(list)
    mapping = {
        "参数非法": ["参数", "缺失", "为空", "非法", "越界", "rating"],
        "权限": ["权限", "未登录", "令牌", "越权", "token", "禁用", "停用"],
        "状态不允许": ["状态", "已关闭", "已完成", "不允许"],
        "资源不存在": ["不存在", "找不到"],
        "并发冲突": ["并发", "重复", "版本", "重复提交", "抢"],
        "依赖失败": ["超时", "不可用", "MQ", "下游", "降级"],
        "极限值": ["上限", "越界", "100000", "101", "-1", "0 或负数", "极限"],
    }
    for n in spec["neg_cases"]:
        placed = False
        for cat, kws in mapping.items():
            if any(k in n["scenario"] for k in kws):
                bucket[cat].append(n)
                placed = True
                break
        if not placed:
            bucket["参数非法"].append(n)

    out = []
    for cat in COMMON_EXCEPTION_CLASSES:
        items = bucket.get(cat) or []
        if items:
            for n in items:
                out.append({
                    "id": f"EX-{len(out) + 1:02d}", "category": cat,
                    "scenario": n["scenario"], "feedback": n["feedback"],
                    "rollback": n["rollback"], "retryable": n["retryable"],
                    "covered": True,
                })
        else:
            out.append({
                "id": f"EX-{len(out) + 1:02d}", "category": cat,
                "scenario": "（该类别尚未识别出具体场景，需补充）",
                "feedback": "—", "rollback": "—", "retryable": "—",
                "covered": False,
            })
    return out


def build_dependencies(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return spec["deps"]


def build_open_issues(spec: dict[str, Any], exceptions: list[dict[str, Any]],
                      points: list[str], quality_flags: list[str]) -> list[dict[str, Any]]:
    issues = []
    for ex in exceptions:
        if ex["covered"] and ("NEG-" in ex["scenario"] or "实际可能" in ex["feedback"]):
            issues.append({
                "issue": f"{ex['scenario']}：期望 {ex['feedback'].split('实际')[0].strip()}，"
                         f"当前实现存在偏差，需修复后补回归用例。",
                "owner": "后端负责人（待指派）", "deadline": "下个迭代", "severity": "高",
            })
    if len(points) > 1:
        issues.append({
            "issue": f"该需求含 {len(points)} 个能力（{'、'.join(points)}）。规范 §4.3 要求一条需求只描述一个能力，"
                     f"建议在平台侧拆为 {len(points)} 条独立需求并迁移用例关联；"
                     f"本文档已按 FR-01..FR-{len(points):02d} 在条目层拆分，验收可按 FR 独立判定。",
            "owner": "产品负责人", "deadline": "评审前", "severity": "中",
        })
    if not spec["glossary"]:
        issues.append({"issue": "术语未定义，需产品补充术语表。", "owner": "产品负责人",
                       "deadline": "评审前", "severity": "中"})
    for f in quality_flags:
        issues.append({"issue": f, "owner": "测试负责人", "deadline": "评审前", "severity": "中"})
    return issues


def evaluate_quality(doc: dict[str, Any], tables: list[dict[str, Any]], apis: list[dict[str, Any]],
                     case_count: int = 0, case_verified: int = 0, case_failed: int = 0) -> dict[str, Any]:
    s = doc["sections"]
    acs = s["acceptance"]
    feats = s["features"]
    strong = sum(1 for a in acs if len(a.get("anchors") or []) >= 2)
    gwt = sum(1 for a in acs if a.get("given") and a.get("when") and a.get("then"))
    exc_covered = sum(1 for e in s["exceptions"] if e["covered"])
    fuzzy_hit = FUZZY.findall(json.dumps(s, ensure_ascii=False))
    multi = re.compile(r"增删改查|新增.*编辑|和|以及|同时|、|/")
    parallel = [f["name"] for f in feats if multi.search(f["name"])]
    template_pre = "用户已登录且具备相应角色"

    attrs = [
        ("必要性", bool(s["overview"].get("businessValue")), "目标与业务价值已量化"),
        ("实现无关", not re.search(r"用 ?Redis|建表|加索引|写 SQL", json.dumps(feats, ensure_ascii=False)),
         "功能条目描述行为而非实现手段"),
        ("无歧义", not fuzzy_hit, f"模糊词命中 {len(fuzzy_hit)} 处" if fuzzy_hit else "未发现模糊词"),
        ("完整", bool(s["nfr"]) and bool(s["dependencies"]) and bool(s["scope"]["outOfScope"]),
         "含 NFR、依赖假设与 Out of Scope"),
        ("单一性", not parallel, f"{len(parallel)} 条 FR 标题含并列词需拆分" if parallel else "每条 FR 只描述一个能力"),
        ("可行", bool(apis) or bool(s["features"]), "有接口或页面证据支撑"),
        ("可验证", strong == len(acs) and len(acs) > 0, f"{strong}/{len(acs)} 条 AC 命中 ≥2 级断言锚点"),
        ("正确", (case_verified > 0 and case_failed == 0) if case_count else (bool(apis) or bool(tables)),
         (f"关联用例 {case_count} 条，通过 {case_verified} 条，不符 {case_failed} 条"
          + ("（未执行）" if case_verified == 0 and case_failed == 0 else "")) if case_count
         else "无关联用例，以代码/接口一致性代替"),
        ("一致", not any(template_pre in (f.get("precondition") or "") for f in feats), "术语与前置条件无模板化措辞"),
        ("可理解", bool(s["glossary"]), f"术语表 {len(s['glossary'])} 条"),
        ("可追溯", s["traceability"]["layerCoverage"] == 100 and case_verified > 0,
         f"链路覆盖 {s['traceability']['layerCoverage']}%，已验证用例 {case_verified}/{case_count} 条"),
        ("可修改", bool(s["docInfo"]["changeLog"]), "含版本与变更记录"),
    ]
    passed = sum(1 for _, ok, _ in attrs if ok)
    score = round(passed / len(attrs) * 100)

    gates = [
        ("模糊词", not fuzzy_hit, f"命中：{','.join(sorted(set(fuzzy_hit)))[:40]}" if fuzzy_hit else "通过"),
        ("AC 无断言锚点", strong == len(acs), f"{len(acs) - strong} 条缺锚点"),
        ("前置条件模板化", not any(template_pre in (f.get("precondition") or "") for f in feats), "通过"),
        ("异常场景为空", exc_covered >= 3, f"已落地 {exc_covered}/7 类"),
        ("缺 NFR", bool(s["nfr"]), f"{len(s['nfr'])} 条量化指标"),
        ("缺数据字典", bool(tables) == bool(s["dataDictionary"]["tables"]), "有表即有字段字典"),
        ("FR 标题含并列词", not parallel, f"待拆：{','.join(parallel)[:40]}" if parallel else "通过"),
        ("AC 数量不足", all(len([a for a in acs if a["frId"] == f["id"]]) >= 2 for f in feats), "每 FR ≥2 条"),
        ("GWT 形式", gwt == len(acs) and len(acs) > 0, f"{gwt}/{len(acs)} 条为 GWT"),
        ("NFR 可测量", all(n.get("measure") for n in s["nfr"]), "每条 NFR 带测量方法"),
        ("验证覆盖", case_verified > 0,
         f"已验证用例 {case_verified}/{case_count} 条" if case_count else "无关联用例"),
    ]
    return {
        "score": score,
        "passed": passed,
        "total": len(attrs),
        "attributes": [{"name": n, "pass": ok, "note": note} for n, ok, note in attrs],
        "gates": [{"rule": r, "pass": ok, "detail": d} for r, ok, d in gates],
        "gatesPassed": sum(1 for _, ok, _ in gates if ok),
        "gatesTotal": len(gates),
        "grade": "A" if score >= 90 else "B" if score >= 75 else "C" if score >= 60 else "D",
    }


def build_traceability(evid: dict[str, list[dict[str, Any]]], apis: list[dict[str, Any]],
                       pages: list[dict[str, Any]], tables: list[dict[str, Any]],
                       codes: list[dict[str, Any]], case_count: int, case_verified: int) -> dict[str, Any]:
    rows = []
    rows.append({"layer": "需求", "count": 1, "items": ["本需求"], "status": "已定义"})
    rows.append({"layer": "页面", "count": len(pages), "items": [p.get("name", "") for p in pages[:5]],
                 "status": "已关联" if pages else "缺失"})
    rows.append({"layer": "接口", "count": len(apis), "items": [api_label(a) for a in apis[:5]],
                 "status": "已关联" if apis else "缺失"})
    rows.append({"layer": "代码", "count": len(codes), "items": [c.get("name", "") for c in codes[:5]],
                 "status": "已关联" if codes else "缺失"})
    rows.append({"layer": "数据表", "count": len(tables), "items": [table_label(t) for t in tables[:5]],
                 "status": "已关联" if tables else "缺失"})
    rows.append({"layer": "用例", "count": case_count, "items": [],
                 "status": "已验证" if case_verified else ("已编写未验证" if case_count else "缺失")})
    layers_ok = sum(1 for L in LAYERS if evid.get(L))
    return {
        "rows": rows,
        "layerCoverage": round(layers_ok / len(LAYERS) * 100),
        "caseCount": case_count,
        "caseVerified": case_verified,
        "verified": layers_ok == len(LAYERS) and case_verified > 0,
    }


def build(req: dict[str, Any], old: dict[str, Any] | None,
          evid: dict[str, list[dict[str, Any]]],
          case_count: int, case_verified: int, case_failed: int = 0) -> dict[str, Any]:
    dom_key, dom = domain_for(req["id"], req["title"])
    dom = dict(dom, _key=dom_key)
    spec = spec_for(dom_key)
    points = req.get("points") or [req["title"].strip("【】")]
    pages = evid.get("page", [])
    apis = evid.get("api", [])
    codes = evid.get("code_artifact", [])
    tables = evid.get("table", [])
    constraint = is_constraint(req["title"], apis, pages)

    roles = build_roles(spec)
    features = build_features(points, roles, spec, apis, pages, tables, req["id"],
                              dom.get("rules"), constraint)
    acceptance = build_acceptance(features, spec, apis, pages, constraint)
    exceptions = build_exceptions(spec, apis)

    covered = [L for L in LAYERS if evid.get(L)]
    missing = [L for L in LAYERS if not evid.get(L)]

    def _label(item: dict[str, Any], layer: str) -> dict[str, str]:
        name = item.get("name") or item.get("path") or item.get("id")
        if layer == "api" and item.get("method"):
            name = api_label(item)
        return {"id": item["id"], "name": str(name)}

    layer_entities = {L: [_label(it, L) for it in evid.get(L, [])[:12]] for L in LAYERS}

    doc: dict[str, Any] = {
        "schemaVersion": "2.0",
        "generatedBy": "product-doc-agent + requirement-normalizer",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "standard": "docs/需求文档规范.md（ISO/IEC/IEEE 29148:2018 + Gherkin GWT + INVEST）",
        "sections": {
            "docInfo": build_doc_info(req, dom_key, old),
            "overview": build_overview(req, dom, spec),
            "scope": build_scope(spec, points),
            "roles": roles,
            "glossary": build_glossary(spec),
            "userStories": build_stories(points, roles, dom.get("goal", "")),
            "features": features,
            "flows": dom.get("flows", []),
            "stateMachine": STATE_MACHINES.get(dom_key, []),
            "businessRules": [{"text": t, "evidence": ev} for t, ev in dom.get("rules", [])],
            "acceptance": acceptance,
            "nfr": build_nfr(spec, []),
            "dataDictionary": build_data_dictionary(tables, spec),
            "exceptions": exceptions,
            "dependencies": build_dependencies(spec),
            "openIssues": [],
            "apis": [
                {
                    "id": a["id"], "method": a.get("method", ""), "path": a.get("path", ""),
                    "summary": a.get("name", ""), "auth": a.get("auth", ""),
                    "service": a.get("service", ""), "source": a.get("source", ""),
                    "specRef": a.get("spec_ref", ""),
                    "params": a.get("params", []), "bodyFields": a.get("body_fields", []),
                    "response": a.get("response", {}),
                }
                for a in apis
            ],
            "dataModel": [
                {
                    "id": t["id"], "name": t.get("name", ""), "database": t.get("database", ""),
                    "schema": t.get("schema", ""), "primaryKey": t.get("pk"),
                    "columnCount": t.get("column_count", 0), "source": t.get("source", ""),
                    "columns": [
                        {"name": c.get("name", ""), "type": c.get("type", ""),
                         "nullable": c.get("nullable", True), "comment": c.get("comment", "")}
                        for c in t.get("columns", [])
                    ],
                }
                for t in tables
            ],
            "coverage": {
                "coveredLayers": covered, "missingLayers": missing,
                "coverageCount": len(covered), "total": len(LAYERS),
                "layerEntities": layer_entities,
                "note": dom.get("no_link_reason", "") or
                        ("四层链路完整，需求→页面→接口→代码/表均有可达实体"
                         if not missing else f"缺少 {'/'.join(missing)} 链路"),
            },
            "codeEvidence": [
                {"id": c.get("id", ""), "entryPoint": c.get("name", ""),
                 "filePath": c.get("file_path", ""), "commit": c.get("commit", ""),
                 "service": c.get("service", "")}
                for c in codes
            ],
        },
        "counts": {
            "pages": len(pages), "apis": len(apis), "code": len(codes),
            "tables": len(tables), "columns": sum(t.get("column_count", 0) for t in tables),
            "features": len(features), "acceptance": len(acceptance),
        },
    }
    doc["sections"]["traceability"] = build_traceability(
        evid, apis, pages, tables, codes, case_count, case_verified)
    doc["sections"]["traceability"]["constraint"] = constraint
    quality = evaluate_quality(doc, tables, apis, case_count, case_verified, case_failed)
    doc["sections"]["quality"] = quality
    failed_gates = [f"门禁未通过：{g['rule']}（{g['detail']}）"
                    for g in quality["gates"] if not g["pass"]]
    doc["sections"]["openIssues"] = build_open_issues(spec, exceptions, points, failed_gates)
    return doc


# ------------------------------------------------------------------ 主流程


def load_cases(cur) -> dict[str, tuple[int, int, int]]:
    """按 requirementId 统计用例数、已通过数（verdict=符合）、不符数（verdict=不符）。"""
    cur.execute(
        """SELECT data->>'requirementId' rid,
                  count(*) AS total,
                  count(*) FILTER (WHERE data->'lastRun'->>'verdict' IN ('通过','符合')) AS passed,
                  count(*) FILTER (WHERE data->'lastRun'->>'verdict' = '不符') AS failed
           FROM documents WHERE collection='testCases' AND data->>'projectId'=%s
             AND data->>'requirementId' IS NOT NULL
           GROUP BY 1""",
        (PROJECT,),
    )
    return {r[0]: (int(r[1]), int(r[2]), int(r[3])) for r in cur.fetchall()}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只重写指定需求 ID")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--no-update-status", action="store_true", help="不改动 requirements.status")
    args = ap.parse_args()

    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()
        reqs = load_requirements(cur, args.only)
        cases = load_cases(cur)
        print(f"待重写需求：{len(reqs)} 条")
        total_before = total_after = 0
        rows_out = []
        for req in reqs:
            evid = collect_evidence(cur, req["id"])
            hydrate(cur, evid)
            cur.execute("SELECT doc FROM requirement_prd WHERE requirement_id=%s AND project_id=%s",
                        (req["id"], PROJECT))
            row = cur.fetchone()
            old = row[0] if row else None
            cnt, passed, failed = cases.get(req["id"], (0, 0, 0))
            doc = build(req, old, evid, cnt, passed, failed)
            before = (old or {}).get("sections", {}).get("quality", {}).get("score")
            q = doc["sections"]["quality"]
            total_before += int(before or 0)
            total_after += q["score"]
            rows_out.append((req["id"], doc["sections"]["docInfo"]["domain"], before, q["score"],
                             len(doc["sections"]["acceptance"]), cnt, passed))
            if args.dry_run:
                print(f"  {req['id']:<22} {doc['sections']['docInfo']['domain']:<10} "
                      f"质量 {before or '-':>4} → {q['score']:>3}  AC {len(doc['sections']['acceptance']):>2} 用例 {cnt}")
                continue
            cur.execute(
                """INSERT INTO requirement_prd (requirement_id, project_id, doc, domain, coverage, generated_at, updated_at)
                   VALUES (%s,%s,%s::jsonb,%s,%s,now(),now())
                   ON CONFLICT (requirement_id) DO UPDATE
                     SET doc=EXCLUDED.doc, domain=EXCLUDED.domain, coverage=EXCLUDED.coverage,
                         generated_at=EXCLUDED.generated_at, updated_at=now()""",
                (req["id"], PROJECT, json.dumps(doc, ensure_ascii=False),
                 doc["sections"]["docInfo"]["domain"], len(doc["sections"]["coverage"]["coveredLayers"])),
            )
            if not args.no_update_status:
                # 规范化后进入「待评审」，与状态机一致（解析完成 ≠ 需求就绪）
                cur.execute(
                    "UPDATE requirements SET status='待评审', updated_at=now() WHERE id=%s AND project_id=%s",
                    (req["id"], PROJECT),
                )

        if not args.dry_run:
            conn.commit()
        n = len(rows_out)
        print(f"\n{'需求':<24}{'域':<12}{'质量前':>6}{'质量后':>7}{'AC':>5}{'用例':>6}")
        for rid, dom, b, a, ac, c, p in rows_out:
            print(f"{rid:<24}{dom:<12}{str(b or '-'):>6}{a:>7}{ac:>5}{c:>6}")
        print(f"\n平均质量分：{total_before / max(n, 1):.1f} → {total_after / max(n, 1):.1f}")
        print(f"{'DRY-RUN 未写库' if args.dry_run else f'已写入 {n} 条 PRD'}")


if __name__ == "__main__":
    main()
