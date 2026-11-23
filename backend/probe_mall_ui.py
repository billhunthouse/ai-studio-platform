"""真实场景探测：用 Playwright 逐步走通尚品汇前端（127.0.0.1:5174）关键页面，
输出每步的真实 DOM 证据（URL / 关键文本 / 元素计数 / 控制台错误），
用于校验 Page Object 定位器在当前真实环境下是否有效。

运行：backend/.venv/bin/python backend/probe_mall_ui.py
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174"
SHOT = Path("/tmp/ui-probe")
try:
    SHOT.mkdir(exist_ok=True)
except OSError:
    pass

PHONE = "13800000001"
CODE = "123456"
EVIDENCE: list[dict] = []


def rec(step: str, page, extra: dict | None = None) -> None:
    body = ""
    try:
        body = page.locator("body").inner_text(timeout=3000)[:400].replace("\n", " | ")
    except Exception as e:  # noqa: BLE001
        body = f"<body读取失败 {e}>"
    item = {"step": step, "url": page.url, "title": page.title(), "bodyHead": body}
    if extra:
        item.update(extra)
    EVIDENCE.append(item)
    print(f"[{step}] url={page.url}  {body[:120]}")


def count(page, sel: str) -> int:
    try:
        return page.locator(sel).count()
    except Exception:  # noqa: BLE001
        return -1


def main() -> int:
    errors: list[str] = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(f"{m.type}: {m.text[:160]}") if m.type == "error" else None)

        # 1. 首页
        page.goto(BASE + "/", wait_until="domcontentloaded", timeout=15000)
        page.wait_for_timeout(800)
        rec("首页", page, {
            "搜索框": count(page, "input[placeholder='搜索商品名称 / 副标题']"),
            "搜索按钮": count(page, "button:has-text('搜索')"),
            "商品链接": count(page, "a[href^='/product/']"),
            "商品ID样本": page.eval_on_selector_all(
                "a[href^='/product/']", "els => els.slice(0,8).map(e => e.getAttribute('href'))"),
            "登录入口": count(page, "text=登录"),
        })
        page.screenshot(path=str(SHOT / "01_home.png"), full_page=False)

        # 2. 搜索
        try:
            page.fill("input[placeholder='搜索商品名称 / 副标题']", "手机", timeout=5000)
            page.click("button:has-text('搜索')", timeout=5000)
            page.wait_for_timeout(1200)
            rec("搜索-手机", page, {"商品链接": count(page, "a[href^='/product/']")})
            page.screenshot(path=str(SHOT / "02_search.png"))
        except Exception as e:  # noqa: BLE001
            rec("搜索-手机", page, {"error": str(e)[:200]})

        # 3. 未登录访问订单页（应被重定向）
        page.goto(BASE + "/orders", wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        rec("未登录-订单页", page)

        # 4. 登录
        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.wait_for_timeout(500)
        rec("登录页", page, {
            "手机号框": count(page, "input[placeholder='请输入 11 位手机号']"),
            "验证码框": count(page, "input[placeholder='请输入 6 位验证码']"),
            "登录按钮": count(page, "button:has-text('登录')"),
            "页面输入框": page.eval_on_selector_all(
                "input", "els => els.map(e => e.placeholder + '|' + e.name + '|' + e.type)"),
        })
        page.fill("input[placeholder='请输入 11 位手机号']", PHONE)
        page.fill("input[placeholder='请输入 6 位验证码']", CODE)
        page.click("button:has-text('登录')")
        page.wait_for_timeout(1500)
        rec("登录后", page, {
            "localStorage": page.evaluate("Object.keys(localStorage)"),
            "token片段": page.evaluate("(localStorage.getItem('token')||localStorage.getItem('mall_token')||'').slice(0,12)"),
        })
        page.screenshot(path=str(SHOT / "03_after_login.png"))

        # 5. 商品详情 + 加购
        page.goto(BASE + "/product/101", wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        rec("商品详情101", page, {
            "加购按钮": count(page, "button:has-text('加入购物车')"),
            "立即购买": count(page, "button:has-text('立即购买')"),
            "SKU/数量": count(page, "input[type='number']"),
        })
        page.screenshot(path=str(SHOT / "04_product.png"))
        if count(page, "button:has-text('加入购物车')") > 0:
            page.click("button:has-text('加入购物车')")
            page.wait_for_timeout(1200)
            rec("加购后", page)

        # 6. 购物车
        page.goto(BASE + "/cart", wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        rec("购物车", page, {
            "去结算按钮": count(page, "button:has-text('去结算')"),
            "全选": count(page, "input[type='checkbox']"),
            "商品行": count(page, "[class*='cart'] li, [class*='cart'] tr"),
        })
        page.screenshot(path=str(SHOT / "05_cart.png"))

        # 7. 结算 / 确认订单
        if count(page, "button:has-text('先去逛逛')") or True:
            pass
        page.goto(BASE + "/checkout", wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        rec("确认订单", page, {
            "提交订单": count(page, "button:has-text('提交订单')"),
            "地址块": count(page, "[class*='address']"),
            "body长度": len(page.locator("body").inner_text()),
        })
        page.screenshot(path=str(SHOT / "06_checkout.png"))

        # 8. 订单列表
        page.goto(BASE + "/orders", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        rec("订单列表", page, {
            "订单号出现": count(page, "text=/\\d{15,}/"),
            "待付款": count(page, "text=待付款"),
        })
        page.screenshot(path=str(SHOT / "07_orders.png"))

        # 9. 售后申请
        page.goto(BASE + "/after-sales/apply", wait_until="domcontentloaded")
        page.wait_for_timeout(800)
        rec("售后申请", page, {
            "textarea": count(page, "textarea[placeholder='请补充说明问题，最多 200 字']"),
            "提交申请": count(page, "button:has-text('提交申请')"),
        })
        page.screenshot(path=str(SHOT / "08_aftersale.png"))

        # 10. 收藏 / 地址
        page.goto(BASE + "/favorites", wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        rec("收藏夹", page)
        page.goto(BASE + "/addresses", wait_until="domcontentloaded")
        page.wait_for_timeout(700)
        rec("地址管理", page, {"新增地址": count(page, "button:has-text('新增')")})
        page.screenshot(path=str(SHOT / "09_address.png"))

        ctx.close()
        browser.close()

    out = Path("/tmp/ui-probe/evidence.json")
    out.write_text(json.dumps({"evidence": EVIDENCE, "consoleErrors": errors[:20]}, ensure_ascii=False, indent=2))
    print(f"\n证据已写入 {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
