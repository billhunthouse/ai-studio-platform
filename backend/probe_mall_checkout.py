"""二次探测：确认订单页可用性（地址/提交）、购物车内容、待付款订单 ID、收银台。
目标是为 PO 补全"可真实提交"的前置条件与动态数据来源。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174"
SHOT = Path("/tmp/ui-probe")
SHOT.mkdir(parents=True, exist_ok=True)
OUT: dict = {}


def dump(page, name: str, extra: dict | None = None):
    try:
        text = page.locator("main, #app").first.inner_text(timeout=3000)
    except Exception:  # noqa: BLE001
        text = page.locator("body").inner_text()
    info = {"url": page.url, "text": text[:1500]}
    if extra:
        info.update(extra)
    OUT[name] = info
    print(f"\n===== {name} | {page.url} =====")
    print(text[:700])


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # 登录
        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.fill("input[placeholder='请输入 11 位手机号']", "13800000001")
        page.fill("input[placeholder='请输入 6 位验证码']", "123456")
        page.click("button:has-text('登录')")
        page.wait_for_timeout(1200)

        # 购物车真实内容
        page.goto(BASE + "/cart", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        dump(page, "cart", {
            "urls": page.eval_on_selector_all("a[href*='/product/']", "e=>e.slice(0,5).map(x=>x.getAttribute('href'))"),
            "checkboxes": page.locator("input[type=checkbox]").count(),
            "结算按钮文本": page.eval_on_selector_all(
                "button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean).slice(0,15)"),
        })
        page.screenshot(path=str(SHOT / "10_cart_full.png"), full_page=True)

        # 点去结算
        try:
            page.click("button:has-text('去结算')", timeout=4000)
            page.wait_for_timeout(1500)
            dump(page, "checkout_after_click", {
                "buttons": page.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean).slice(0,20)"),
                "inputs": page.locator("input").count(),
                "textareas": page.locator("textarea").count(),
                "addressCandidates": page.locator("text=/收货|地址|张三|新增/").count(),
            })
            page.screenshot(path=str(SHOT / "11_checkout_full.png"), full_page=True)
        except Exception as e:  # noqa: BLE001
            OUT["checkout_after_click"] = {"error": str(e)[:300]}

        # 订单列表：找待付款订单
        page.goto(BASE + "/orders", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        orders = page.eval_on_selector_all(
            "a[href*='/order'], a[href*='/pay'], button",
            "els => els.map(e => ({tag:e.tagName, href:e.getAttribute('href'), t:(e.innerText||'').trim().slice(0,20)})).filter(x=>x.href||x.t)"
        )
        dump(page, "orders", {"actions": orders[:40]})
        ids = re.findall(r"/pay/(\d{10,})", json.dumps(orders, ensure_ascii=False))
        print("待支付订单ID:", ids[:5])
        OUT["payOrderIds"] = ids[:5]

        # 用真实待付款订单进收银台
        if ids:
            page.goto(BASE + f"/pay/{ids[0]}", wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            dump(page, "pay_page", {
                "payButtons": page.eval_on_selector_all(
                    "button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean).slice(0,20)"),
            })
            page.screenshot(path=str(SHOT / "12_pay.png"), full_page=True)

        # 商品详情：立即购买 vs 加购的真实行为
        page.goto(BASE + "/product/101", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        dump(page, "product", {
            "buttons": page.eval_on_selector_all(
                "button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean).slice(0,20)"),
        })

        ctx.close(); b.close()
    Path("/tmp/ui-probe/evidence2.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
    print("\n-> /tmp/ui-probe/evidence2.json")


if __name__ == "__main__":
    main()
