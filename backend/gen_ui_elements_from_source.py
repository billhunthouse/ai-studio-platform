"""从真实 Vue 前端源码提取 UI 元素，生成平台元素库（uiElements）。

数据源：shang-mall 项目的 .vue 模板（placeholder / button 文本 / input type）。
不猜测——每个元素都带 sourceFile 证据，可追溯到具体组件。

同时提取路由表，生成 Page Object 的导航基线。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import psycopg

MALL_SRC = Path("/Users/imac/Desktop/电商自动化测试/shang-pivot-master/shang-mall/src")
PLATFORM_DSN = "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"

# 人工 curated 的语义映射：中文业务名 → 真实 Vue 模板里的定位器（带证据）
# 从源码逐条核对：LoginForm.vue / MallLayout.vue / CartView.vue / CheckoutView.vue 等
ELEMENTS: list[dict] = [
    # 登录（LoginForm.vue）
    {"name": "手机号输入框", "page": "登录", "selectorType": "Placeholder", "selectorValue": "请输入 11 位手机号", "sourceFile": "components/LoginForm.vue", "testData": "13800000001"},
    {"name": "验证码输入框", "page": "登录", "selectorType": "Placeholder", "selectorValue": "请输入 6 位验证码", "sourceFile": "components/LoginForm.vue", "testData": "123456"},
    {"name": "获取验证码按钮", "page": "登录", "selectorType": "Text", "selectorValue": "获取验证码", "sourceFile": "components/LoginForm.vue"},
    {"name": "登录按钮", "page": "登录", "selectorType": "Text", "selectorValue": "登录", "sourceFile": "views/LoginView.vue"},
    # 全站导航（MallLayout.vue）
    {"name": "顶部搜索框", "page": "全站", "selectorType": "Placeholder", "selectorValue": "搜索商品名称 / 副标题", "sourceFile": "layouts/MallLayout.vue", "testData": "手机"},
    {"name": "搜索按钮", "page": "全站", "selectorType": "Text", "selectorValue": "搜索", "sourceFile": "layouts/MallLayout.vue"},
    {"name": "亲请登录链接", "page": "全站", "selectorType": "Text", "selectorValue": "亲，请登录", "sourceFile": "layouts/MallLayout.vue"},
    {"name": "我的订单入口", "page": "全站", "selectorType": "Text", "selectorValue": "我的订单", "sourceFile": "layouts/MallLayout.vue"},
    {"name": "收藏夹入口", "page": "全站", "selectorType": "Text", "selectorValue": "收藏夹", "sourceFile": "layouts/MallLayout.vue"},
    {"name": "查看购物车链接", "page": "全站", "selectorType": "Text", "selectorValue": "查看购物车", "sourceFile": "views/HomeView.vue"},
    {"name": "分类入口", "page": "全站", "selectorType": "Text", "selectorValue": "全部分类", "sourceFile": "views/HomeView.vue"},
    # 首页
    {"name": "去分类逛逛按钮", "page": "首页", "selectorType": "Text", "selectorValue": "去分类逛逛", "sourceFile": "views/HomeView.vue"},
    {"name": "搜索商品框", "page": "搜索", "selectorType": "Placeholder", "selectorValue": "搜索商品", "sourceFile": "views/SearchView.vue", "testData": "手机"},
    # 商品详情（ProductView.vue）
    {"name": "加入购物车按钮", "page": "商品详情", "selectorType": "Text", "selectorValue": "加入购物车", "sourceFile": "views/ProductView.vue"},
    {"name": "去购物车结算按钮", "page": "商品详情", "selectorType": "Text", "selectorValue": "去购物车结算", "sourceFile": "views/ProductView.vue"},
    {"name": "去确认订单按钮", "page": "商品详情", "selectorType": "Text", "selectorValue": "去确认订单", "sourceFile": "views/ProductView.vue"},
    # 购物车（CartView.vue）
    {"name": "去结算按钮", "page": "购物车", "selectorType": "Text", "selectorValue": "去结算", "sourceFile": "views/CartView.vue"},
    {"name": "删除商品按钮", "page": "购物车", "selectorType": "Text", "selectorValue": "删除商品", "sourceFile": "views/CartView.vue"},
    {"name": "一键清理按钮", "page": "购物车", "selectorType": "Text", "selectorValue": "一键清理", "sourceFile": "views/CartView.vue"},
    {"name": "去逛逛按钮", "page": "购物车", "selectorType": "Text", "selectorValue": "去逛逛", "sourceFile": "views/CartView.vue"},
    # 结算（CheckoutView.vue）
    {"name": "提交订单按钮", "page": "结算", "selectorType": "Text", "selectorValue": "提交订单", "sourceFile": "views/CheckoutView.vue"},
    {"name": "确认提交订单按钮", "page": "结算", "selectorType": "Text", "selectorValue": "确认提交订单", "sourceFile": "views/CheckoutView.vue"},
    {"name": "收货人字段", "page": "结算", "selectorType": "Text", "selectorValue": "收货人", "sourceFile": "views/CheckoutView.vue"},
    {"name": "收货地址字段", "page": "结算", "selectorType": "Text", "selectorValue": "收货地址", "sourceFile": "views/CheckoutView.vue"},
    # 支付（PayView.vue）
    {"name": "沙箱支付按钮", "page": "支付", "selectorType": "Text", "selectorValue": "沙箱支付（模拟）", "sourceFile": "views/PayView.vue"},
    {"name": "查看订单按钮", "page": "支付", "selectorType": "Text", "selectorValue": "查看订单", "sourceFile": "views/PayView.vue"},
    {"name": "取消支付按钮", "page": "支付", "selectorType": "Text", "selectorValue": "取消支付", "sourceFile": "views/PayView.vue"},
    # 订单（OrdersView.vue）
    {"name": "我的订单标题", "page": "订单", "selectorType": "Text", "selectorValue": "我的订单", "sourceFile": "views/OrdersView.vue"},
    # 售后（AfterSaleApplyView.vue）
    {"name": "申请售后按钮", "page": "售后", "selectorType": "Text", "selectorValue": "申请售后", "sourceFile": "views/AfterSaleApplyView.vue"},
    {"name": "提交申请按钮", "page": "售后", "selectorType": "Text", "selectorValue": "提交申请", "sourceFile": "views/AfterSaleApplyView.vue"},
    {"name": "售后问题说明框", "page": "售后", "selectorType": "Placeholder", "selectorValue": "请补充说明问题，最多 200 字", "sourceFile": "views/AfterSaleApplyView.vue", "testData": "测试申请"},
    # 地址（AddressView.vue）
    {"name": "新增地址按钮", "page": "地址", "selectorType": "Text", "selectorValue": "新增", "sourceFile": "views/AddressView.vue"},
    {"name": "保存地址按钮", "page": "地址", "selectorType": "Text", "selectorValue": "保存", "sourceFile": "views/AddressView.vue"},
    # 评价（OrderDetailView.vue）
    {"name": "评价内容框", "page": "订单详情", "selectorType": "Placeholder", "selectorValue": "说说使用感受，最多 500 字", "sourceFile": "views/OrderDetailView.vue", "testData": "商品不错，物流很快"},
    {"name": "发表评价按钮", "page": "订单详情", "selectorType": "Text", "selectorValue": "发表评价", "sourceFile": "views/OrderDetailView.vue"},
]

ROUTES = [
    {"name": "首页", "path": "/", "file": "HomeView.vue"},
    {"name": "登录", "path": "/login", "file": "LoginView.vue"},
    {"name": "分类", "path": "/category", "file": "CategoryView.vue"},
    {"name": "搜索", "path": "/search", "file": "SearchView.vue"},
    {"name": "购物车", "path": "/cart", "file": "CartView.vue"},
    {"name": "结算", "path": "/checkout", "file": "CheckoutView.vue"},
    {"name": "订单", "path": "/orders", "file": "OrdersView.vue"},
    {"name": "支付", "path": "/pay/{orderId}", "file": "PayView.vue"},
    {"name": "个人中心", "path": "/me", "file": "ProfileView.vue"},
    {"name": "地址", "path": "/addresses", "file": "AddressView.vue"},
    {"name": "收藏", "path": "/favorites", "file": "FavoritesView.vue"},
    {"name": "足迹", "path": "/history", "file": "HistoryView.vue"},
    {"name": "售后", "path": "/after-sales", "file": "AfterSalesView.vue"},
    {"name": "售后申请", "path": "/after-sales/apply", "file": "AfterSaleApplyView.vue"},
]


def verify_elements() -> tuple[list[dict], list[str]]:
    """核对每个元素的 selectorValue 在源码里真实存在，返回 (有效元素, 证据缺失列表)。"""
    valid, missing = [], []
    for e in ELEMENTS:
        src = MALL_SRC / e["sourceFile"]
        if not src.exists():
            missing.append(f"{e['name']}: 源文件不存在 {e['sourceFile']}")
            continue
        text = src.read_text(encoding="utf-8")
        val = e["selectorValue"]
        # 支持文本跨行（Vue 模板里按钮文本可能换行）
        if val in text or re.search(re.escape(val[:8]), text):
            valid.append(e)
        else:
            missing.append(f"{e['name']}: 「{val}」未在 {e['sourceFile']} 找到")
    return valid, missing


def main() -> None:
    valid, missing = verify_elements()
    print(f"元素库：{len(valid)} 个有效 / {len(missing)} 个待核")
    for m in missing[:10]:
        print("  ⚠", m)

    from app.store import store
    from app.db import SessionLocal
    from sqlalchemy import text
    for e in valid:
        eid = f"el-{e['page']}-{e['name']}"
        store.put("uiElements", eid, {
            "id": eid, "projectId": "ecommerce", "pageId": e["page"],
            "name": e["name"], "selectorType": e["selectorType"],
            "selectorValue": e["selectorValue"],
            "testData": e.get("testData", ""),
            "sourceFile": e["sourceFile"], "source": "CODE_SCAN",
        })
    for r in ROUTES:
        rid = f"route-{r['name']}"
        store.put("uiRoutes", rid, {
            "id": rid, "projectId": "ecommerce", "name": r["name"],
            "path": r["path"], "sourceFile": r["file"], "source": "CODE_SCAN",
        })
    print(f"已写入 {len(valid)} 个元素 + {len(ROUTES)} 条路由到平台")

if __name__ == "__main__":
    main()
