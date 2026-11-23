"""七次探测：走通「立即购买 → 确认下单信息弹窗 → 确认订单页 → 提交订单 → 待付款 → 收银台 → 支付」。

这是电商最高价值的端到端链路，也是 UI 自动化必须真实跑通的场景。
每步记录 url / 文本 / 按钮，确认真实业务结果（订单号、订单状态）。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174"
SHOT = Path("/tmp/ui-probe")
OUT: dict = {}


def login(pg):
    pg.goto(BASE + "/login", wait_until="domcontentloaded")
    pg.fill("input[placeholder='请输入 11 位手机号']", "13800000001")
    pg.fill("input[placeholder='请输入 6 位验证码']", "123456")
    pg.click("button:has-text('登录')")
    pg.wait_for_timeout(1300)


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        try:
            login(pg)
            pg.goto(BASE + "/product/101", wait_until="domcontentloaded")
            pg.wait_for_timeout(900)
            pg.click("button.link-hint:has-text('选择规格')")
            pg.wait_for_timeout(600)
            pg.click(".van-popup button.chip:has-text('128GB')")
            pg.wait_for_timeout(250)
            pg.click(".van-popup button.chip:has-text('原色钛金属')")
            pg.wait_for_timeout(350)
            pg.click(".van-popup button:has-text('立即购买')")
            pg.wait_for_timeout(900)

            # 确认下单信息弹窗
            OUT["confirmDialog"] = {"visible": pg.locator(".van-popup").first.is_visible(),
                                    "text": pg.locator(".van-popup").first.inner_text()[:250],
                                    "buttons": pg.locator(".van-popup button").all_inner_texts()}
            pg.click(".van-popup button:has-text('去确认订单')", timeout=5000)
            pg.wait_for_timeout(2200)
            OUT["checkout"] = {"url": pg.url,
                               "submit": pg.locator("button:has-text('提交订单')").count(),
                               "text": pg.locator("#app").first.inner_text()[:400]}
            print("确认订单页 ->", pg.url)
            pg.screenshot(path=str(SHOT / "31_checkout.png"), full_page=True)

            # 提交订单 → 二次确认弹窗「确认提交」
            if pg.locator("button:has-text('提交订单')").count():
                pg.click("button:has-text('提交订单')")
                pg.wait_for_timeout(1200)
                OUT["submitConfirmDialog"] = pg.eval_on_selector_all(
                    ".van-popup button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)")
                try:
                    pg.click(".van-popup button:has-text('确认提交')", timeout=5000)
                    OUT["submitConfirm"] = "clicked"
                except Exception as e:  # noqa: BLE001
                    OUT["submitConfirm"] = str(e)[:150]
                pg.wait_for_timeout(3000)
                body = pg.locator("#app").first.inner_text()
                OUT["submitted"] = {"url": pg.url, "orderNos": list(dict.fromkeys(re.findall(r"O\d{15,}", body)))[:3],
                                    "text": body[:400],
                                    "buttons": pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)")}
                print("提交后 ->", pg.url, "| 订单号:", OUT["submitted"]["orderNos"])
                pg.screenshot(path=str(SHOT / "32_after_submit.png"), full_page=True)

            # 订单列表 → 待付款
            pg.goto(BASE + "/orders", wait_until="domcontentloaded")
            pg.wait_for_timeout(1800)
            tabs = pg.eval_on_selector_all(
                "[class*='tab'], [role='tab'], .filter button, button",
                "e=>e.map(x=>x.innerText.trim()).filter(t=>t&&t.length<6).slice(0,12)")
            OUT["orderTabs"] = tabs
            OUT["ordersUrl"] = pg.url
            # 用 DOM 里真实存在的待付款 tab 点击
            try:
                pg.get_by_text("待付款", exact=True).first.click(timeout=4000)
            except Exception as e:  # noqa: BLE001
                OUT["tabClickErr"] = str(e)[:120]
            pg.wait_for_timeout(1500)
            OUT["pendingUrl"] = pg.url
            OUT["pendingText"] = pg.locator("#app").first.inner_text()[:600]
            OUT["pendingLinks"] = pg.eval_on_selector_all(
                "a[href*='/orders/']", "e=>e.slice(0,6).map(x=>x.getAttribute('href'))")
            print("待付款 tab ->", pg.url, OUT["pendingLinks"])
            pg.screenshot(path=str(SHOT / "33_pending.png"), full_page=True)

            # 订单详情 → 去支付
            href = (OUT["pendingLinks"] or [None])[0]
            if href:
                pg.goto(BASE + href, wait_until="domcontentloaded")
                pg.wait_for_timeout(1300)
                OUT["detail"] = {"url": pg.url,
                                 "buttons": pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)"),
                                 "text": pg.locator("#app").first.inner_text()[:400]}
                print("订单详情:", OUT["detail"]["buttons"])
                pg.screenshot(path=str(SHOT / "34_order_detail.png"), full_page=True)
                if pg.locator("button:has-text('去支付')").count():
                    pg.click("button:has-text('去支付')")
                    pg.wait_for_timeout(2000)
                    OUT["cashier"] = {"url": pg.url,
                                      "buttons": pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)"),
                                      "text": pg.locator("#app").first.inner_text()[:500]}
                    print("收银台 ->", pg.url, OUT["cashier"]["buttons"])
                    pg.screenshot(path=str(SHOT / "35_cashier.png"), full_page=True)
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal7.png"))
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close(); b.close()
    Path("/tmp/ui-probe/evidence7.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
    print("\n-> evidence7.json")


if __name__ == "__main__":
    main()
