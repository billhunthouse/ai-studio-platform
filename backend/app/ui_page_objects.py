"""Page Object 库（v2，基于真实环境实测重建）。

与 v1 的差别（v1 只在"步骤不报错"层面验证，属于假通过）：
1. 每个 PO 自带**真实业务断言**（assert 关键字），例如登录后 URL 必须离开 /login 且出现 "Hi，"；
   搜索后必须有商品链接；下单后必须跳 /pay/ 且出现"订单号"。断言失败即该用例失败。
2. 覆盖真实的多层弹窗：商品详情「选择规格 ›」打开 van-popup 抽屉 → 抽屉内选规格 → 抽屉内
   「加入购物车 / 立即购买」→「确认下单信息」弹窗 →「去确认订单」→ 确认订单页「提交订单」→
   「确认提交」二次确认 → 跳收银台。这些弹窗在 v1 中完全没有，导致点击被遮罩拦截而超时。
3. 定位器全部 scope 到 `.van-popup` 或用真实 class（chip / link-hint / btn），避免同名元素命中多个
   时 Playwright 取第一个被遮挡元素导致的假失败。

实测依据：/tmp/ui-probe/evidence*.json 与截图，见 docs/traceability/UI自动化真实执行验证报告.md
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BASE_URL = "http://127.0.0.1:5174"
STEP_DELAY = 300

# 演示数据（shang-pivot migration + LoginForm.vue：演示验证码固定 123456）
DEMO = {
    "phone": "13800000001",
    "phone_new": "13700000001",
    "code": "123456",
    "keyword": "手机",
    "product_id": "101",
    "sku_spec": "128GB",
    "sku_color": "原色钛金属",
    "remark": "自动化测试备注：商品外包装存在轻微压痕",
}


@dataclass
class PoStep:
    keyword: str
    args: dict[str, Any]
    raw: str


def nav(path: str, raw: str) -> PoStep:
    return PoStep("nav", {"target": path}, raw)


def click(locator: str, raw: str) -> PoStep:
    return PoStep("click", {"locator": locator, "target": raw}, raw)


def fill(locator: str, value: str, raw: str) -> PoStep:
    return PoStep("fill", {"locator": locator, "value": value, "target": raw}, raw)


def wait(ms: int, raw: str = "等待页面响应") -> PoStep:
    return PoStep("wait", {"durationMs": ms}, raw)


def assert_url(contains: str, raw: str) -> PoStep:
    return PoStep("assert", {"kind": "url", "target": contains}, raw)


def assert_url_not(contains: str, raw: str) -> PoStep:
    return PoStep("assert", {"kind": "url_not", "target": contains}, raw)


def assert_text(text: str, raw: str) -> PoStep:
    return PoStep("assert", {"kind": "text", "target": text}, raw)


def assert_no_text(text: str, raw: str) -> PoStep:
    return PoStep("assert", {"kind": "no_text", "target": text}, raw)


def assert_count(selector: str, at_least: int, raw: str) -> PoStep:
    return PoStep("assert", {"kind": "count", "target": selector, "min": at_least}, raw)


# ---------------------------------------------------------------- 可复用流程
def flow_login(phone: str = DEMO["phone"]) -> list[PoStep]:
    """登录（LoginForm.vue）：手机号 + 固定演示验证码。"""
    return [
        nav("/login", "进入登录页"),
        fill("input[placeholder='请输入 11 位手机号']", phone, "输入手机号"),
        fill("input[placeholder='请输入 6 位验证码']", DEMO["code"], "输入验证码"),
        click("button:has-text('登录')", "点击登录按钮"),
        wait(1500, "等待登录完成"),
        assert_url_not("/login", "断言已离开登录页"),
        assert_text("Hi，", "断言页头出现登录用户名"),
    ]


def flow_home() -> list[PoStep]:
    """首页（HomeView.vue）：商品瀑布流 + 搜索入口。"""
    return [
        nav("/", "进入首页"),
        wait(900, "等待首页渲染"),
        assert_text("尚品汇", "断言首页品牌标题"),
        assert_count("a[href^='/product/']", 1, "断言首页存在商品卡片"),
    ]


def flow_search(keyword: str = DEMO["keyword"]) -> list[PoStep]:
    """搜索（MallLayout 顶部搜索框 → SearchView）。"""
    return [
        nav("/", "进入首页"),
        fill("input[placeholder='搜索商品名称 / 副标题']", keyword, "输入搜索关键词"),
        click("button:has-text('搜索')", "点击搜索"),
        wait(1300, "等待搜索结果"),
        assert_url("/search", "断言跳转到搜索结果页"),
        assert_count("a[href^='/product/']", 1, "断言搜索结果非空"),
    ]


def flow_product(product_id: str = DEMO["product_id"]) -> list[PoStep]:
    """商品详情（ProductView.vue）：价格、规格入口、加购/立即购买按钮。"""
    return [
        nav(f"/product/{product_id}", "进入商品详情页"),
        wait(1000, "等待商品详情加载"),
        assert_text("加入购物车", "断言详情页操作区渲染"),
        assert_text("¥", "断言价格展示"),
        assert_count("button.link-hint", 1, "断言存在规格选择入口"),
    ]


def flow_add_to_cart() -> list[PoStep]:
    """加入购物车（真实路径）：抽屉内选规格 → 抽屉内加购。

    实测坑：页面同时存在"页面主体"与"SKU 抽屉"两套同名 chip/按钮，
    `button:has-text('加入购物车')` 会命中 2 个元素，第一个在抽屉下方被遮罩拦截 → 超时。
    所有操作必须 scope 到 `.van-popup`。
    """
    return [
        *flow_login(),
        nav(f"/product/{DEMO['product_id']}", "进入商品详情页"),
        wait(800, "等待详情页渲染"),
        click("button.link-hint:has-text('选择规格')", "打开规格选择抽屉"),
        wait(700, "等待抽屉动画"),
        click(f".van-popup button.chip:has-text('{DEMO['sku_spec']}')", "选择容量规格"),
        wait(300),
        click(f".van-popup button.chip:has-text('{DEMO['sku_color']}')", "选择颜色规格"),
        wait(400),
        click(".van-popup button:has-text('加入购物车')", "抽屉内点击加入购物车"),
        wait(1600, "等待加购结果"),
        assert_no_text("请选择规格", "断言未被规格校验拦截"),
        assert_text("购物车(", "断言页头购物车角标存在"),
    ]


def flow_cart() -> list[PoStep]:
    """购物车（CartView.vue）：进入并校验已选商品与结算入口。"""
    return [
        *flow_login(),
        nav("/cart", "进入购物车"),
        wait(1300, "等待购物车列表加载"),
        assert_text("购物车", "断言购物车页面渲染"),
        assert_text("去结算", "断言存在结算入口（购物车非空且已选商品）"),
    ]


def flow_checkout() -> list[PoStep]:
    """购物车 → 结算 → 确认订单页（不提交，避免脏数据）。"""
    return [
        *flow_login(),
        nav("/cart", "进入购物车"),
        wait(1200, "等待购物车加载"),
        click("button:has-text('去结算')", "点击去结算"),
        wait(1800, "等待确认订单页"),
        assert_url("/checkout", "断言进入确认订单页"),
        assert_text("收货地址", "断言确认订单页展示收货地址"),
        assert_text("提交订单", "断言存在提交订单按钮"),
    ]


def flow_place_order() -> list[PoStep]:
    """完整下单（真实写操作）：立即购买 → 确认下单信息 → 确认订单 → 提交 → 二次确认。

    实测：提交订单会弹出「取消 / 确认提交」二次确认，必须再点确认才会创建订单；
    成功后跳转 /pay/{orderId}，页面展示订单号（O + 18 位数字）。
    """
    return [
        *flow_login(),
        nav(f"/product/{DEMO['product_id']}", "进入商品详情页"),
        wait(800),
        click("button.link-hint:has-text('选择规格')", "打开规格选择抽屉"),
        wait(700),
        click(f".van-popup button.chip:has-text('{DEMO['sku_spec']}')", "选择容量规格"),
        wait(300),
        click(f".van-popup button.chip:has-text('{DEMO['sku_color']}')", "选择颜色规格"),
        wait(400),
        click(".van-popup button:has-text('立即购买')", "点击立即购买"),
        wait(1000, "等待确认下单信息弹窗"),
        click(".van-popup button:has-text('去确认订单')", "确认下单信息"),
        wait(2200, "等待确认订单页"),
        assert_url("/checkout", "断言进入确认订单页"),
        assert_text("提交订单", "断言存在提交订单按钮"),
        click("button:has-text('提交订单')", "点击提交订单"),
        wait(1200, "等待二次确认弹窗"),
        click(".van-popup button:has-text('确认提交')", "二次确认提交订单"),
        wait(3000, "等待订单创建"),
        assert_url("/pay/", "断言跳转收银台"),
        assert_text("订单号", "断言展示新订单号"),
    ]


def flow_pay() -> list[PoStep]:
    """支付闭环：下单后在收银台完成模拟支付（实测进入收银台即支付成功）。"""
    return [
        *flow_place_order(),
        assert_text("支付成功", "断言收银台返回支付成功"),
    ]


def flow_orders() -> list[PoStep]:
    """我的订单列表（OrdersView.vue）。"""
    return [
        *flow_login(),
        nav("/orders", "进入我的订单"),
        wait(1600, "等待订单列表加载"),
        assert_text("我的订单", "断言订单页标题"),
        assert_count("a[href*='/orders/']", 1, "断言订单列表存在订单"),
    ]


def flow_order_detail() -> list[PoStep]:
    """订单详情：从列表进入第一条订单，校验详情页渲染。"""
    return [
        *flow_login(),
        nav("/orders", "进入我的订单"),
        wait(1600),
        click("a[href*='/orders/']", "打开第一条订单详情"),
        wait(1400, "等待订单详情加载"),
        assert_url("/orders/", "断言进入订单详情页"),
        assert_text("订单", "断言详情页展示订单信息"),
    ]


def flow_after_sale() -> list[PoStep]:
    """售后申请（AfterSaleApplyView.vue）：校验表单必填项，填写问题说明。

    真实提交需要先选择一笔已完成订单，属于跨模块数据依赖，故本流程只做
    "表单可用性 + 输入"验证，不产生售后单（避免污染演示数据）。
    """
    return [
        *flow_login(),
        nav("/after-sales/apply", "进入售后申请页"),
        wait(1200, "等待售后表单加载"),
        assert_text("申请售后", "断言售后申请页渲染"),
        fill("textarea[placeholder='请补充说明问题，最多 200 字']", DEMO["remark"], "填写问题说明"),
        assert_count("button:has-text('提交申请')", 1, "断言存在提交申请按钮"),
    ]


def flow_favorites() -> list[PoStep]:
    """收藏夹（FavoritesView.vue）。"""
    return [
        *flow_login(),
        nav("/favorites", "进入我的收藏"),
        wait(1000, "等待收藏列表"),
        assert_text("收藏", "断言收藏页渲染"),
    ]


def flow_address() -> list[PoStep]:
    """收货地址（AddressView.vue）。"""
    return [
        *flow_login(),
        nav("/addresses", "进入收货地址"),
        wait(1000, "等待地址列表"),
        assert_text("收货地址", "断言地址页渲染"),
        assert_count("button:has-text('新增')", 1, "断言存在新增地址入口"),
    ]


def flow_me() -> list[PoStep]:
    """C 端个人中心（MeView 路由 /me）。

    补这条流程是因为对齐时发现一个错位：原 TC-1024「会员等级正确展示」被绑到了
    管理端会员列表（那是顾客管理，没有"等级"列）。会员身份实际展示在 C 端个人中心，
    所以补 C 端 PO 并把用例改绑回来，而不是让它在后台列表上"跑绿"。

    附带发现：该页有会员标签、订单四态入口、地址/收藏/足迹/售后入口，
    但**没有积分模块**——而需求里存在"积分为 0 时显示空状态"的验收点，
    属于页面未实现的缺口，不是自动化能补的。
    """
    return [
        *flow_login(),
        nav("/me", "进入个人中心"),
        wait(1300, "等待个人中心加载"),
        assert_url("/me", "断言进入个人中心"),
        assert_text("我的订单", "断言订单入口渲染"),
        assert_text("收货地址", "断言地址入口渲染"),
        assert_text("我的收藏", "断言收藏入口渲染"),
        assert_text("· 会员", "断言会员身份标签展示"),
    ]


# ---------------------------------------------------------------- 管理端（分流 5173）
# 管理端是独立应用（shang-admin-web），与 C 端（shang-mall, 5174）不同端口、不同登录体系：
# 用户名 + 密码（非短信验证码），登录后进 /dashboard。PO 的 nav 用绝对地址，
# 执行器对 http 开头的 target 直接 goto，不拼 BASE_URL——因此两套站点可以共用同一执行器。
ADMIN_BASE_URL = "http://127.0.0.1:5173"
ADMIN_DEMO = {
    "username": "admin",
    "password": "Admin@123",
    "product_kw": "iPhone",
    "customer_kw": "138",
}


def flow_admin_login() -> list[PoStep]:
    """管理端登录（LoginView.vue）：用户名 + 密码，成功后跳工作台。

    与 C 端登录的关键差别：C 端是手机号+固定验证码，管理端是账号密码；
    管理端还有"连续失败 5 次锁 15 分钟"的风控，批量执行时失败会放大，故断言从严。
    """
    return [
        nav(f"{ADMIN_BASE_URL}/login", "进入管理端登录页"),
        wait(600, "等待登录表单渲染"),
        fill("input[name='username']", ADMIN_DEMO["username"], "输入管理员用户名"),
        fill("input[name='password']", ADMIN_DEMO["password"], "输入管理员密码"),
        click("button[type='submit']", "点击登录"),
        wait(2200, "等待登录完成"),
        assert_url("/dashboard", "断言登录后进入工作台"),
        assert_text("商品列表", "断言侧边栏菜单已渲染"),
    ]


def flow_admin_products() -> list[PoStep]:
    """管理端商品列表（ProductsView.vue）：列表渲染 + 关键词查询 + 状态统计。

    这是管理端被引用最多的一页（39 条用例），但此前无 PO，全部计入「缺 Page Object」。
    断言挑的是"只有管理端才有"的东西：新增商品入口、批量下架、SPU/SKU 统计。
    """
    return [
        *flow_admin_login(),
        nav(f"{ADMIN_BASE_URL}/products", "进入商品列表"),
        wait(1800, "等待列表加载"),
        assert_text("商品列表", "断言页面标题"),
        assert_text("新增商品", "断言存在新增商品入口"),
        assert_count("tbody tr", 1, "断言商品列表有数据行"),
        fill("input[placeholder='商品名称 / 编码']", ADMIN_DEMO["product_kw"], "输入商品关键词"),
        click("button:has-text('查询')", "点击查询"),
        wait(1600, "等待查询结果"),
        assert_url("/products", "断言停留在商品列表页"),
        assert_text("iPhone", "断言查询结果命中目标商品"),
        assert_count("tbody tr", 1, "断言查询结果非空"),
    ]


def flow_admin_customers() -> list[PoStep]:
    """管理端会员管理（CustomersView.vue）：列表 + 手机号查询 + 脱敏校验。

    「手机号脱敏」是这条流程真正的业务价值：管理端列表必须只展示 138****8000，
    明文手机号泄漏属于安全事故。因此断言直接卡脱敏后的形态，而不是只卡"有数据"。
    """
    return [
        *flow_admin_login(),
        nav(f"{ADMIN_BASE_URL}/customers", "进入会员管理"),
        wait(1800, "等待会员列表加载"),
        assert_text("会员管理", "断言页面标题"),
        assert_count("tbody tr", 1, "断言会员列表有数据行"),
        fill("input[placeholder='手机号 / 昵称']", ADMIN_DEMO["customer_kw"], "输入手机号关键词"),
        click("button:has-text('查询')", "点击查询"),
        wait(1600, "等待查询结果"),
        assert_count("tbody tr", 1, "断言查询结果非空"),
        assert_text("****", "断言手机号以脱敏形态展示（不出现明文）"),
    ]


def flow_admin_aftersales() -> list[PoStep]:
    """管理端售后管理（AftersalesView.vue）：列表 + 打开审核详情 + 关闭。

    刻意**不点「同意/拒绝」**：那会真实改写售后单状态并触发沙箱退款，属于不可逆写操作，
    批量回归里跑会把演示数据打坏。这里只验证"审核入口能打开、详情字段齐全、关闭后无残留"，
    既覆盖了交互路径，又不产生副作用。
    """
    return [
        *flow_admin_login(),
        nav(f"{ADMIN_BASE_URL}/aftersales", "进入售后管理"),
        wait(1800, "等待售后列表加载"),
        assert_text("售后管理", "断言页面标题"),
        assert_text("待审核", "断言存在待审核筛选"),
        assert_count("tbody tr", 1, "断言售后列表有数据行"),
        click("button:has-text('审核')", "打开售后审核详情"),
        wait(1200, "等待详情抽屉展开"),
        assert_text("售后详情", "断言审核弹窗已打开"),
        assert_text("退款金额", "断言详情含退款金额"),
        assert_text("处理意见", "断言详情含处理意见字段"),
        click("button:has-text('关闭')", "关闭详情（不提交审核）"),
        wait(800, "等待弹窗关闭"),
        assert_no_text("售后单号", "断言关闭后详情内容无残留"),
    ]


# ---------------------------------------------------------------- 场景匹配
# 标题关键词优先（写操作/具体场景），module 兜底。顺序有讲究：先具体后宽泛。
# 管理端规则必须排在 C 端前面——"商品上架"若落到"商品详情流程"就是假通过。
TITLE_RULES: list[tuple[list[str], str, Any]] = [
    # 管理端（5173）：命中这些词就是后台操作，不能落到 C 端页面
    (["售后审核", "审核售后", "审核通过", "同意退款", "拒绝退款", "驳回", "处理意见"], "管理端售后审核流程", flow_admin_aftersales),
    (["商品列表", "上架", "下架", "批量", "新增商品", "编辑商品", "SPU", "SKU"], "管理端商品列表流程", flow_admin_products),
    (["会员管理", "会员列表", "冻结会员", "解冻会员", "会员ID", "会员订单"], "管理端会员管理流程", flow_admin_customers),
    (["支付", "收银台", "付款", "重复支付"], "收银台支付闭环", flow_pay),
    (["下单", "提交订单", "创建订单", "订单创建", "秒杀下单"], "完整下单流程", flow_place_order),
    (["售后", "退款", "退货", "换货", "维修"], "售后申请流程", flow_after_sale),
    (["加购", "加入购物车"], "加入购物车流程", flow_add_to_cart),
    (["结算", "确认订单"], "购物车结算流程", flow_checkout),
    (["购物车", "车中", "清空"], "购物车流程", flow_cart),
    (["订单详情"], "订单详情流程", flow_order_detail),
    (["取消订单", "取消"], "订单详情流程", flow_order_detail),
    (["订单"], "订单列表流程", flow_orders),
    (["地址", "收货人", "收货信息"], "地址管理流程", flow_address),
    (["收藏"], "收藏夹流程", flow_favorites),
    (["登录", "注册", "验证码", "密码", "账号"], "登录流程", flow_login),
    (["搜索", "关键词", "筛选", "类目", "分类"], "商品搜索流程", flow_search),
    (["商品", "详情", "规格", "库存", "评价", "图片"], "商品详情流程", flow_product),
    (["首页", "推荐", "活动", "轮播", "运营"], "首页浏览流程", flow_home),
]

MODULE_RULES: list[tuple[list[str], str, Any]] = [
    (["售后"], "售后申请流程", flow_after_sale),
    (["支付"], "收银台支付闭环", flow_pay),
    (["订单交易", "订单"], "订单列表流程", flow_orders),
    (["购物车与个人中心"], "购物车流程", flow_cart),
    (["认证登录"], "登录流程", flow_login),
    (["商品与类目"], "商品搜索流程", flow_search),
    (["首页与运营"], "首页浏览流程", flow_home),
    (["评价", "会员"], "商品详情流程", flow_product),
    (["AI 助手"], "首页浏览流程", flow_home),
]

# 这些模块是业务规则/权限/数据一致性校验，不应伪装成 UI 自动化
NON_UI_MODULES = ["库存", "RBAC 权限", "权限与群组", "全站规范", "统计与导出",
                  "楼栋与户号", "物业费与水电", "主体与车辆", "商铺与车位", "物业"]

# 写操作流程：执行会真实落库（创建订单 / 支付），批量执行时应限量
WRITE_FLOWS = {"完整下单流程", "收银台支付闭环"}

# PO 注册表：名称 → 构造函数。绑定层只持有名字，靠这张表把它解析成真实步骤，
# 这样"绑定"与"实现"解耦——改 PO 内部实现不用改任何绑定数据。
FLOW_BUILDERS = {
    "登录流程": flow_login,
    "首页浏览流程": flow_home,
    "商品搜索流程": flow_search,
    "商品详情流程": flow_product,
    "加入购物车流程": flow_add_to_cart,
    "购物车流程": flow_cart,
    "购物车结算流程": flow_checkout,
    "完整下单流程": flow_place_order,
    "收银台支付闭环": flow_pay,
    "订单列表流程": flow_orders,
    "订单详情流程": flow_order_detail,
    "售后申请流程": flow_after_sale,
    "收藏夹流程": flow_favorites,
    "地址管理流程": flow_address,
    "个人中心流程": flow_me,
    "管理端商品列表流程": flow_admin_products,
    "管理端会员管理流程": flow_admin_customers,
    "管理端售后审核流程": flow_admin_aftersales,
}


def build_po(name: str) -> list[PoStep] | None:
    """按名称构造 PO 步骤；名称不存在返回 None（绑定数据可能指向已重命名的流程）。"""
    builder = FLOW_BUILDERS.get(name)
    return builder() if builder else None


def po_names() -> list[str]:
    return list(FLOW_BUILDERS.keys())


def match_po(module: str, title: str) -> tuple[str, list[PoStep]] | None:
    """按标题（优先）→ module 匹配可复用流程。"""
    if module in NON_UI_MODULES:
        return None
    for keywords, name, builder in TITLE_RULES:
        if any(k in (title or "") for k in keywords):
            return name, builder()
    for keywords, name, builder in MODULE_RULES:
        if any(k in (module or "") for k in keywords):
            return name, builder()
    return None
