"""Page Object 库：把高频业务流程封装为可复用的关键字序列。

设计：每个 PO 是一个"场景 → 可执行的 nav/click/fill/wait 步骤列表"的映射。
编译器遇到抽象步骤（"执行被测操作"/"按验收标准构造场景"）时，
根据用例的 module + title 匹配对应 PO，展开为具体 UI 步骤。

所有定位器来自 gen_ui_elements_from_source.py 从真实 Vue 源码提取的元素库。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

BASE_URL = "http://127.0.0.1:5174"
STEP_DELAY = 300

# 演示数据（与 shang-pivot migration + LoginForm.vue 的提示一致）
DEMO = {
    "phone": "13800000001",
    "phone2": "13900000002",
    "code": "123456",       # LoginForm.vue: 演示环境验证码固定为 123456
    "keyword": "手机",
    "qty": "2",
    "remark": "自动化测试备注",
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


# ---------------------------------------------------------------- 可复用流程
def flow_login() -> list[PoStep]:
    """登录流程（LoginForm.vue + LoginView.vue）"""
    return [
        nav("/login", "进入登录页"),
        fill("input[placeholder='请输入 11 位手机号']", DEMO["phone"], "输入手机号"),
        fill("input[placeholder='请输入 6 位验证码']", DEMO["code"], "输入验证码"),
        click("button:has-text('登录')", "点击登录按钮"),
        wait(600, "等待登录完成"),
    ]


def flow_search(keyword: str = "") -> list[PoStep]:
    """搜索商品（MallLayout.vue 顶部搜索框）"""
    return [
        nav("/", "进入首页"),
        fill("input[placeholder='搜索商品名称 / 副标题']", keyword or DEMO["keyword"], "输入搜索关键词"),
        click("button:has-text('搜索')", "点击搜索"),
        wait(500, "等待搜索结果"),
    ]


def flow_add_to_cart() -> list[PoStep]:
    """浏览商品详情并加入购物车（ProductView.vue）
    注意：首页商品卡片的链接文本是价格（如 ¥7999.00），不是商品名，
    因此直接导航到真实存在的商品 ID（seed 数据 101）。
    """
    return [
        nav("/product/101", "进入商品详情页"),
        wait(500, "等待商品详情加载"),
        click("button:has-text('加入购物车')", "加入购物车"),
        wait(500, "等待加购结果"),
    ]


def flow_cart_checkout() -> list[PoStep]:
    """购物车结算（CartView.vue → CheckoutView.vue）——需先登录"""
    return [
        *flow_login(),
        nav("/cart", "进入购物车"),
        click("button:has-text('去结算')", "点击去结算"),
        wait(500, "等待确认订单页"),
    ]


def flow_place_order() -> list[PoStep]:
    """完整下单：登录 → 加购 → 结算 → 提交订单（高频端到端流程）"""
    return [
        *flow_login(),
        *flow_add_to_cart(),
        *flow_cart_checkout(),
        click("button:has-text('提交订单')", "提交订单"),
        wait(600, "等待订单创建"),
    ]


def flow_pay() -> list[PoStep]:
    """支付收银台（PayView.vue）——需先登录。

    演示数据里的订单多已完成，直接导航到收银台验证页面与支付元素；
    有待付款订单时可将 path 换成该订单 ID 完成真实沙箱支付。
    """
    return [
        *flow_login(),
        nav("/pay/2121917386695561218", "进入收银台"),
        wait(600, "等待支付页加载"),
    ]


def flow_view_orders() -> list[PoStep]:
    """查看订单列表（OrdersView.vue）——需先登录"""
    return [
        *flow_login(),
        nav("/orders", "进入我的订单"),
        wait(500, "等待订单列表加载"),
    ]


def flow_after_sale() -> list[PoStep]:
    """申请售后（AfterSaleApplyView.vue）——需先登录，否则被重定向到登录页"""
    return [
        *flow_login(),
        nav("/after-sales/apply", "进入售后申请页"),
        wait(500, "等待售后表单加载"),
        fill("textarea[placeholder='请补充说明问题，最多 200 字']", DEMO["remark"], "填写问题说明"),
        click("button:has-text('提交申请')", "提交售后申请"),
        wait(600, "等待申请结果"),
    ]


def flow_favorites() -> list[PoStep]:
    """收藏夹（FavoritesView.vue）"""
    return [
        nav("/favorites", "进入我的收藏"),
        wait(400, "等待收藏列表"),
    ]


def flow_address() -> list[PoStep]:
    """地址管理（AddressView.vue）"""
    return [
        nav("/addresses", "进入收货地址"),
        wait(400, "等待地址列表"),
    ]


# ---------------------------------------------------------------- 场景匹配
# module/title 关键词 → PO 流程（按优先级排序，先匹配具体流程）
PO_RULES: list[tuple[list[str], str, Any]] = [
    (["售后"], "申请售后流程", flow_after_sale),
    (["支付"], "沙箱支付流程", flow_pay),
    (["下单", "提交订单", "订单创建", "订单交易"], "完整下单流程", flow_place_order),
    (["购物车", "加购"], "加入购物车流程", flow_add_to_cart),
    (["结算", "确认订单"], "购物车结算流程", flow_cart_checkout),
    (["订单"], "查看订单流程", flow_view_orders),
    (["收藏"], "收藏夹流程", flow_favorites),
    (["地址", "收货"], "地址管理流程", flow_address),
    (["搜索", "商品与类目"], "商品搜索流程", flow_search),
    (["登录", "认证"], "登录流程", flow_login),
    (["首页", "运营"], "首页浏览流程", lambda: [nav("/", "进入首页"), wait(400)]),
]

# 这些模块是业务规则/DB 一致性校验，不应伪装成 UI 自动化
NON_UI_MODULES = ["库存", "RBAC 权限", "权限与群组", "全站规范", "统计与导出",
                  "楼栋与户号", "物业费与水电", "主体与车辆", "商铺与车位", "物业"]


def match_po(module: str, title: str) -> tuple[str, list[PoStep]] | None:
    """按 module + title 匹配一个可复用的 PO 流程。"""
    for keywords, name, builder in PO_RULES:
        if any(k in module or k in title for k in keywords):
            if module in NON_UI_MODULES and not any(k in title for k in ["登录", "购物车", "订单"]):
                continue
            return name, builder()
    return None
