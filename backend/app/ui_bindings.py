"""用例 → 页面 → Page Object 的三层绑定。

为什么需要这一层
----------------
原实现只有 `match_po(module, title)`：拿用例标题里的关键词直接去猜 14 个
Page Object 之一。用例与 41 个页面之间没有任何显式关系，于是三个问题都答不出来：

1. 「这条用例测的是哪个页面？」——答不出，只能看 module 猜；
2. 「这个页面被哪些用例覆盖？」——答不出，反向查询不存在；
3. 「为什么这条用例不可执行？」——答不出，只会显示"未自动化"。

更糟的是它会**误命中**：标题含「金额合计一致性（明细小计之和 = 订单总额 + 运费）」
的用例，因为带「订单」二字被展开成「订单列表流程」，跑一遍列表页就标"通过"，
而它真正要验的是 DB 里的金额关系——这类"绿"是假绿。

本模块把绑定拆成三层，每层可独立维护、可人工改正：

    用例 --TESTS--> 页面(page:mall:/cart) --IMPLEMENTED_BY--> PO(购物车流程)

设计取舍
--------
- **绑页面，不绑 PO。** 页面路由是稳定锚点（改版少），PO 是可重构的实现细节。
  用例只声明"我在哪个页面验证"，PO 由「页面 + 标题意图」推导出来。
- **五分类代替二元可执行。** 不可执行不再是黑盒，而是四种可命名、可派活的缺口。
- **规则建议 ≠ 结论。** 规则只产出 `proposed` 建议，编译默认不采信，
  人工确认（`bindingSource=human`）后才生效——避免"机器猜的绑定"污染执行结论。
"""
from __future__ import annotations

import re
from typing import Any

# ---------------------------------------------------------------- 分类常量
KIND_UI_PO = "ui_po"                  # 页面已知 + 有 PO → 可执行
KIND_UI_NO_PO = "ui_page_no_po"       # 页面已知 + 该页确实没有 PO → 缺 PO 清单
KIND_UI_AMBIGUOUS = "ui_ambiguous"    # 页面有多个 PO，标题无法区分 → 需人选流程
KIND_API = "api"                      # 接口/数据校验 → 不该走 UI
KIND_MANUAL = "manual"                # 视觉/规范/探索 → 人工
KIND_UNBOUND = "unbound"              # 判不出 → 体检

SOURCE_HUMAN = "human"                # 人工确认，权威
SOURCE_RULE = "rule"                  # 规则推断，待确认
SOURCE_NONE = "none"

KIND_LABEL = {
    KIND_UI_PO: "可执行",
    KIND_UI_NO_PO: "缺 Page Object",
    KIND_UI_AMBIGUOUS: "待选流程",
    KIND_API: "接口/数据校验",
    KIND_MANUAL: "人工验证",
    KIND_UNBOUND: "待归类",
}

# ---------------------------------------------------------------- 页面 ↔ PO
# PO 声明自己覆盖哪些页面（一个 PO 可从多页进入，如"下单"从商品详情或购物车发起）
PO_PAGES: dict[str, list[str]] = {
    "登录流程": ["/login"],
    "首页浏览流程": ["/"],
    "商品搜索流程": ["/", "/search", "/category"],
    "商品详情流程": ["/product/:spuId"],
    "加入购物车流程": ["/product/:spuId"],
    "购物车流程": ["/cart"],
    "购物车结算流程": ["/cart", "/checkout"],
    "完整下单流程": ["/product/:spuId", "/checkout"],
    "收银台支付闭环": ["/pay/:orderId", "/checkout"],
    "订单列表流程": ["/orders"],
    "订单详情流程": ["/orders", "/orders/:id"],
    "售后申请流程": ["/after-sales", "/after-sales/apply"],
    "地址管理流程": ["/addresses"],
    "收藏夹流程": ["/favorites"],
    "个人中心流程": ["/me"],
    # 管理端（独立应用 5173）：页面路由与 C 端同名不同站点，靠 /admin 前缀区分
    "管理端商品列表流程": ["/admin/products"],
    "管理端会员管理流程": ["/admin/customers"],
    "管理端售后审核流程": ["/admin/aftersales"],
}

# 反查：页面路径 → 候选 PO（可能多个，需要靠标题意图再挑）
PAGE_POS: dict[str, list[str]] = {}
for _po, _paths in PO_PAGES.items():
    for _p in _paths:
        PAGE_POS.setdefault(_p, []).append(_po)

# 同一页面多个 PO 时，用标题关键词挑（顺序即优先级）
PO_TITLE_HINTS: dict[str, list[str]] = {
    "首页浏览流程": ["首页", "推荐", "轮播", "导航", "运营位"],
    "完整下单流程": ["下单", "提交订单", "创建订单", "秒杀下单"],
    "购物车结算流程": ["结算", "确认订单"],
    "收银台支付闭环": ["支付", "收银台", "付款", "重复支付"],
    "订单详情流程": ["详情"],
    "订单列表流程": ["列表", "我的订单", "全部订单"],
    "商品详情流程": ["详情", "规格", "库存", "评价", "图片"],
    "加入购物车流程": ["加购", "加入购物车"],
    "商品搜索流程": ["搜索", "关键词", "筛选", "类目", "分类"],
    "个人中心流程": ["个人中心", "会员等级", "我的", "积分"],
    "管理端商品列表流程": ["商品列表", "上架", "下架", "批量", "新增商品", "编辑商品", "SPU", "SKU"],
    "管理端会员管理流程": ["会员", "客户", "冻结", "解冻", "手机号"],
    "管理端售后审核流程": ["审核", "同意", "拒绝", "驳回", "处理意见"],
}

# ---------------------------------------------------------------- 管理端准入闸门
# 管理端页面存在一个致命误绑风险：C 端也有"商品""售后""订单"这些词，
# 若不加区分，"商品详情页库存展示"会被绑到管理端商品列表，跑一遍列表就标通过 —— 又一类假绿。
# 因此管理端页面只有**标题明确带后台意图**时才参选，否则该候选直接出局（不是降权，是不许上桌）。
ADMIN_PAGES: set[str] = {p for p in PAGE_POS if p.startswith("/admin/")} | {
    "/admin/products", "/admin/customers", "/admin/aftersales",
    "/admin/orders", "/admin/reviews", "/admin/inventory", "/admin/in-out",
    "/admin/users", "/admin/roles", "/admin/menus", "/admin/depts",
    "/admin/home-slots", "/admin/site-brand", "/admin/categories", "/admin/login",
}
ADMIN_SIGNALS: list[str] = [
    "管理端", "后台", "管理员", "运营后台", "审核", "上架", "下架", "商品列表",
    "会员管理", "会员列表", "冻结", "解冻", "批量", "处理意见", "驳回", "SPU", "SKU",
    "可售库存", "出入库", "同意", "拒绝", "审核通过",
]

# 反向信号：标题自己说了"这是前台在验"，再多的"审核/上架"字样也不能绑管理端。
# 实测反例：TC-1182「验收点3：C 端列表不出现 OFF 或已删除的 SPU」曾被绑到管理端商品列表，
# 跑一遍后台列表就标通过——这正是要消灭的假绿。
FRONT_SIGNALS: list[str] = ["C 端", "C端", "顾客端", "用户端", "前台", "买家", "购物车页", "商城页"]

# 只存在于管理端的业务域：这些模块的用例必然是后台操作，不需要标题再自证。
ADMIN_MODULES: set[str] = {"RBAC 权限", "权限与群组", "库存", "评价"}


def is_admin_page(path: str) -> bool:
    return path in ADMIN_PAGES


def admin_allowed(title: str, module: str = "") -> tuple[bool, str]:
    """管理端页面准入判定，返回 (是否允许, 判定依据)。

    三条规则，从严到宽：
    1. 标题带前台信号 → 一票否决（哪怕标题也含"上架"）；
    2. 标题带后台信号 → 允许；
    3. 模块本身只存在于管理端（RBAC 权限 / 库存 / 评价）→ 允许。
    """
    title = title or ""
    if _score(FRONT_SIGNALS, title) > 0:
        return False, "标题含前台信号（C 端/顾客端），不绑管理端页"
    if _score(ADMIN_SIGNALS, title) > 0:
        return True, "标题含后台信号"
    if (module or "") in ADMIN_MODULES:
        return True, f"模块「{module}」仅存在于管理端"
    return False, "标题无后台意图，管理端页不参选"


# ---------------------------------------------------------------- 模块 → 页面
# 业务域到页面的粗映射。一个模块对应多个页面是常态（"商品与类目"跨 C 端与管理端），
# 所以这里只给候选集，具体由标题意图在候选里打分挑选。
MODULE_PAGES: dict[str, list[str]] = {
    "认证登录": ["/login", "/admin/login"],
    "登录": ["/login"],
    "首页与运营": ["/", "/promo/:code", "/admin/home-slots", "/admin/site-brand"],
    "商品与类目": ["/product/:spuId", "/search", "/category", "/admin/products", "/admin/categories"],
    "购物车与个人中心": ["/cart", "/checkout", "/me", "/addresses", "/favorites", "/history", "/settings"],
    "订单交易": ["/orders", "/orders/:id", "/checkout", "/admin/orders"],
    "订单": ["/orders"],
    "支付": ["/pay/:orderId"],
    "售后": ["/after-sales/apply", "/after-sales", "/after-sales/:id", "/admin/aftersales"],
    "评价": ["/admin/reviews"],
    "库存": ["/admin/inventory", "/admin/in-out"],
    # "会员"既有管理端顾客管理，也有 C 端个人中心的会员等级/权益，两者不能混。
    # 标题没线索时宁可判"待归类"，也不硬绑到后台列表上。
    "会员": ["/admin/customers", "/me"],
    "RBAC 权限": ["/admin/users", "/admin/roles", "/admin/menus", "/admin/depts"],
    "AI 助手": ["(global)"],
    "全站规范": [],
}

# 页面路径 → 标题意图关键词（用于在模块候选集里挑具体页面）
PAGE_TITLE_HINTS: dict[str, list[str]] = {
    "/login": ["登录", "注册", "验证码", "密码", "账号"],
    "/admin/login": ["管理端登录", "后台登录", "管理员登录"],
    "/": ["首页", "推荐", "轮播", "导航"],
    "/promo/:code": ["活动", "专区", "促销", "秒杀"],
    "/category": ["分类", "类目", "品牌"],
    "/search": ["搜索", "筛选", "关键词", "排序"],
    "/product/:spuId": ["商品详情", "规格", "主图", "加购", "加入购物车", "图片"],
    "/cart": ["购物车", "清空", "车中"],
    "/checkout": ["结算", "确认订单", "提交订单", "下单"],
    "/orders": ["订单列表", "我的订单", "全部订单"],
    "/orders/:id": ["订单详情", "订单信息"],
    "/pay/:orderId": ["支付", "收银台", "付款"],
    # 只留页面真实存在的意图词。"积分"看似该在这里，但个人中心当前没有积分模块，
    # 若把积分用例引到这个页面，跑一遍"会员标签"就标通过——又是一条假绿，宁可判待归类。
    "/me": ["个人中心", "我的", "会员等级"],
    "/settings": ["个人设置", "设置"],
    "/addresses": ["地址", "收货人", "收货信息"],
    "/favorites": ["收藏"],
    "/history": ["足迹", "浏览记录"],
    "/after-sales": ["售后", "退款", "退货"],
    "/after-sales/apply": ["申请售后", "售后申请"],
    "/after-sales/:id": ["售后详情"],
    "/admin/products": ["商品列表", "上架", "下架", "批量", "编辑商品", "新增商品", "SPU", "SKU"],
    "/admin/categories": ["类目管理", "品牌管理", "类目", "品牌"],
    "/admin/inventory": ["低库存", "预警", "可售库存", "库存"],
    "/admin/in-out": ["出入库", "入库单", "出库单"],
    "/admin/orders": ["发货", "订单管理", "后台订单"],
    "/admin/aftersales": ["售后审核", "审核", "同意", "拒绝", "驳回", "处理意见", "售后单"],
    "/admin/reviews": ["回复", "评价管理", "星级"],
    "/admin/customers": ["会员管理", "会员列表", "会员", "客户", "冻结", "解冻"],
    "/admin/users": ["用户管理", "重置密码", "禁用", "账号"],
    "/admin/roles": ["角色", "权限"],
    "/admin/menus": ["菜单", "权限"],
    "/admin/depts": ["部门"],
    "/admin/home-slots": ["运营位", "首页配置"],
    "/admin/site-brand": ["品牌", "站点"],
}

# ---------------------------------------------------------------- 非 UI 判定
# 命中即说明"这条用例验的东西在页面之外"。带 reason 是为了能向人解释为什么踢出 UI 队列。
DATA_VERIFY_PATTERNS: list[tuple[str, str]] = [
    (r"金额|total_amount|pay_amount|subtotal|运费|合计|小计", "金额关系需比对 DB/接口字段，页面只展示结果不暴露计算过程"),
    (r"库存|physical|locked|available|sold_count|超卖|扣减|释放", "库存不变式属于数据层断言"),
    (r"脱敏|不回传|敏感字段", "字段级校验，需检查响应体"),
    (r"幂等|idempotentKey|重复提交|重复支付", "幂等性需接口重放验证"),
    (r"\bSQL\b|数据库|表结构|索引|约束|CHECK|外键|DB ", "数据库结构/约束校验"),
    (r"返回\s*(200|400|401|403|404|500)|HTTP|状态码|接口|API|token|accessToken|鉴权", "接口契约校验"),
    (r"并发|行锁|读-改-写|竞态|锁", "并发正确性需专用事务/压测环境"),
    (r"精度|浮点|字符串不丢|序列化", "序列化精度校验"),
    (r"不变式|一致性|快照", "数据不变式/快照一致性需比对库内字段"),
]
MANUAL_PATTERNS: list[tuple[str, str]] = [
    (r"文案一致|按钮顺序|规范|布局|视口|H5|响应式|样式|像素", "视觉/交互规范需多视口截图人工比对"),
    (r"探索|易用|体验", "探索性测试"),
    (r"埋点|统计|报表", "需数据侧核对"),
    (r"灰度|上线|发布|回滚", "发布流程，非功能验证"),
]
# 明确的 UI 动作词：出现时优先按页面归类，而不是判为接口用例
UI_STRONG_PATTERNS = [
    r"点击|单击|输入|填写|勾选|下拉|拖拽|上传",
    r"页面|弹窗|弹层|抽屉|按钮|表单|列表页|详情页|首页|浮窗",
    r"展示|显示|可见|置灰|禁用|跳转",
]


def _hit(patterns: list[tuple[str, str]], text: str) -> str:
    for pat, reason in patterns:
        if re.search(pat, text or ""):
            return reason
    return ""


def _score(hints: list[str], text: str) -> int:
    return sum(1 for h in hints if h and h in text)


def load_pages() -> list[dict[str, Any]]:
    """从 trace_pages 读页面清单（不带 project 过滤时取全部，调用方按需过滤）。"""
    try:
        from sqlalchemy import select

        from .db import SessionLocal
        from .trace_models import TracePage

        with SessionLocal() as db:
            rows = db.scalars(select(TracePage)).all()
        return [
            {"id": r.id, "name": r.name, "path": r.prd_section,
             "domain": r.feature_domain, "projectId": r.project_id}
            for r in rows
        ]
    except Exception:
        return []


def page_lookup(pages: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {p["path"]: p for p in pages if p.get("path")}


def suggest(case: dict[str, Any], pages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """给出这条用例的绑定建议（不落库）。

    返回：
      kind        五分类之一
      pageId/pageName/pagePath  建议页面（可能为空）
      poName      推导出的 Page Object（可能为空）
      source      建议来源：rule / none
      confidence  0~100，规则命中的确信度
      needsReview 是否需要人工确认
      reason      为什么是这个结论（给人和给前端看）
    """
    pages = pages if pages is not None else load_pages()
    by_path = page_lookup(pages)
    module = (case.get("module") or "").strip()
    title = (case.get("title") or "").strip()
    steps = case.get("steps") or []
    if isinstance(steps, list):
        step_text = " ".join(str(s) for s in steps)
    else:
        step_text = str(steps)
    text = f"{title} {step_text}"
    ui_score = _score(UI_STRONG_PATTERNS, text)

    def out(kind: str, reason: str, **kw: Any) -> dict[str, Any]:
        base = {
            "kind": kind, "kindLabel": KIND_LABEL[kind],
            "pageId": "", "pageName": "", "pagePath": "", "poName": "",
            "source": SOURCE_RULE if kind != KIND_UNBOUND else SOURCE_NONE,
            "confidence": 0, "needsReview": True, "reason": reason,
        }
        base.update(kw)
        return base

    # 1) 数据/接口类：没有 UI 动作词时才判出去，避免把"购物车页面金额展示正确"误踢
    data_reason = _hit(DATA_VERIFY_PATTERNS, text)
    if data_reason and ui_score == 0:
        return out(KIND_API, data_reason, confidence=80)

    # 2) 视觉/规范类
    manual_reason = _hit(MANUAL_PATTERNS, text)
    if manual_reason and ui_score <= 1:
        return out(KIND_MANUAL, manual_reason, confidence=70)

    # 3) 页面归类：模块给候选集，标题意图在候选里打分
    candidates = MODULE_PAGES.get(module, [])
    if not candidates:
        return out(KIND_UNBOUND, f"模块「{module or '空'}」没有登记对应页面，需人工指定")

    ranked: list[tuple[int, str]] = []
    allow_admin, admin_why = admin_allowed(title, module)
    skipped_admin = 0
    for path in candidates:
        cand = by_path.get(path)
        if not cand:
            continue
        # 管理端准入闸门：不带后台意图时 /admin/* 页面不参选。
        # 否则"商品详情页库存展示"会被绑到管理端商品列表，跑一遍列表就标通过——假绿。
        if is_admin_page(path) and not allow_admin:
            skipped_admin += 1
            continue
        sc = _score(PAGE_TITLE_HINTS.get(path, []), title) * 2 + _score(PAGE_TITLE_HINTS.get(path, []), step_text)
        ranked.append((sc, path))
    if not ranked:
        if skipped_admin and skipped_admin == len([p for p in candidates if p in by_path]):
            return out(
                KIND_UNBOUND,
                f"模块「{module}」只对应管理端页面，但{admin_why}，需人工指定或补全标题",
                confidence=35, needsReview=True,
            )
        return out(KIND_UNBOUND, f"模块「{module}」映射的页面在页面表中不存在，页面清单可能已变更")
    ranked.sort(key=lambda x: (-x[0], candidates.index(x[1])))
    best_score, best_path = ranked[0]
    tie = [p for s, p in ranked if s == best_score]
    cand = by_path[best_path]
    ambiguous = len(tie) > 1 and best_score > 0

    # 4) 页面 → PO
    po_candidates = PAGE_POS.get(best_path, [])
    po_name = ""
    if len(po_candidates) == 1:
        po_name = po_candidates[0]
    elif len(po_candidates) > 1:
        scored = [(_score(PO_TITLE_HINTS.get(po, []), title), po) for po in po_candidates]
        scored.sort(key=lambda x: -x[0])
        if scored[0][0] > 0:
            po_name = scored[0][1]
        else:
            po_name = ""      # 有 PO 但挑不出 → 仍需人工，不硬猜
            ambiguous = True

    conf = 55 + min(best_score * 5, 25) + (15 if po_name else 0)
    if best_score == 0:
        # 标题里没有任何页面线索，纯靠模块兜底 → 这种"猜"不值得给建议，
        # 交给人指定比给一个错页面更有价值（错绑会直接导致假通过）。
        names = [by_path[p]["name"] for _, p in ranked[:3] if p in by_path]
        return out(
            KIND_UNBOUND,
            f"模块「{module}」跨多个页面（{'、'.join(names)}），标题未指明具体页面，需人工指定",
            confidence=45, needsReview=True,
        )
    if ambiguous:
        conf = min(conf, 55)

    if not po_name:
        if po_candidates:
            return out(
                KIND_UI_AMBIGUOUS,
                f"页面「{cand['name']}」有 {len(po_candidates)} 个可用流程（{'、'.join(po_candidates)}），"
                "标题未指明具体操作，需人工选定",
                pageId=cand["id"], pageName=cand["name"], pagePath=best_path,
                confidence=conf, needsReview=True,
            )
        return out(
            KIND_UI_NO_PO,
            f"页面「{cand['name']}」已定位，但该页暂无 Page Object，需新增该页的自动化流程",
            pageId=cand["id"], pageName=cand["name"], pagePath=best_path,
            confidence=conf, needsReview=True,
        )
    return out(
        KIND_UI_PO,
        f"模块「{module}」→ 页面「{cand['name']}」→ 流程「{po_name}」",
        pageId=cand["id"], pageName=cand["name"], pagePath=best_path,
        poName=po_name, confidence=conf, needsReview=ambiguous or best_score == 0,
    )


def resolve(case: dict[str, Any], pages: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """解析一条用例的**生效**绑定：人工确认优先，其次规则建议，最后未绑定。

    与 suggest() 的区别：suggest 只给建议，resolve 决定编译实际采用哪个页面/PO。
    """
    pages = pages if pages is not None else load_pages()
    by_id = {p["id"]: p for p in pages}
    by_path = page_lookup(pages)
    page_id = (case.get("pageId") or "").strip()
    page_path = (case.get("pagePath") or "").strip()
    source = (case.get("bindingSource") or SOURCE_NONE).strip() or SOURCE_NONE

    page = by_id.get(page_id) if page_id else None
    if not page and page_path:
        page = by_path.get(page_path)

    if page:
        po_candidates = PAGE_POS.get(page["path"], [])
        manual_po = (case.get("poName") or "").strip()
        po_name = ""
        if manual_po and manual_po in po_candidates:
            # 人工选定的流程优先于任何规则推断
            po_name = manual_po
        elif len(po_candidates) == 1:
            po_name = po_candidates[0]
        elif len(po_candidates) > 1:
            scored = [(_score(PO_TITLE_HINTS.get(po, []), case.get("title") or ""), po) for po in po_candidates]
            scored.sort(key=lambda x: -x[0])
            po_name = scored[0][1] if scored[0][0] > 0 else ""
        if po_name:
            kind = KIND_UI_PO
            reason = f"已绑定页面「{page['name']}」，使用流程「{po_name}」"
        elif po_candidates:
            kind = KIND_UI_AMBIGUOUS
            reason = (f"已绑定页面「{page['name']}」，该页有 {len(po_candidates)} 个流程"
                      f"（{'、'.join(po_candidates)}），需选定一个")
        else:
            kind = KIND_UI_NO_PO
            reason = f"已绑定页面「{page['name']}」，但该页暂无 PO"
        return {
            "kind": kind,
            "pageId": page["id"], "pageName": page["name"], "pagePath": page["path"],
            "poName": po_name, "source": source if source != SOURCE_NONE else SOURCE_HUMAN,
            "confidence": 100 if source == SOURCE_HUMAN else 60,
            "needsReview": source != SOURCE_HUMAN or kind == KIND_UI_AMBIGUOUS,
            "reason": reason,
        }
    # 没有显式绑定 → 退回规则建议（保持旧行为，但标记来源）
    sug = suggest(case, pages)
    sug["needsReview"] = True
    return sug


def page_coverage(pages: list[dict[str, Any]], cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """页面视角的覆盖反查：每个页面被多少用例覆盖、能否执行。"""
    buckets: dict[str, dict[str, Any]] = {
        p["id"]: {"pageId": p["id"], "pageName": p["name"], "pagePath": p["path"],
                  "domain": p.get("domain") or "", "poNames": PAGE_POS.get(p["path"], []),
                  "total": 0, "confirmed": 0, "runnable": 0, "caseIds": []}
        for p in pages
    }
    for c in cases:
        r = resolve(c, pages)
        pid = r.get("pageId")
        if not pid or pid not in buckets:
            continue
        b = buckets[pid]
        b["total"] += 1
        b["caseIds"].append(c.get("id"))
        if r.get("source") == SOURCE_HUMAN:
            b["confirmed"] += 1
        if r.get("kind") == KIND_UI_PO:
            b["runnable"] += 1
    rows = list(buckets.values())
    rows.sort(key=lambda x: (-x["total"], x["pagePath"]))
    return rows
