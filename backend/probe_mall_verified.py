"""六次探测：验证修正后的真实路径是否成立。

修正认知：商品详情页的「选择规格 ›」会打开 van-popup 抽屉，抽屉内也有同名 chip 与操作按钮，
导致 `button:has-text(...)` 命中 2 个元素、第一个被遮挡 → 点击超时（假失败/假通过）。
正确做法：所有规格与操作按钮都 scope 到 `.van-popup`。

本脚本验证：
1. 抽屉内选规格 + 加购，购物车角标是否真 +1；
2. 抽屉内立即购买 → 确认订单 → 提交订单，是否生成真实订单号；
3. 订单详情 → 去支付 → 收银台 → 支付，是否真实闭环。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174"
SHOT = Path("/tmp/ui-probe")
OUT: dict = {}


def badge(pg) -> int:
    try:
        txt = pg.locator("text=/购物车\\(\\d+\\)/").first.inner_text()
        m = re.search(r"\((\d+)\)", txt)
        return int(m.group(1)) if m else -1
    except Exception:  # noqa: BLE001
        return -1


def toast(pg) -> str:
    for sel in (".van-toast", ".el-message", "[role='alert']"):
        try:
            loc = pg.locator(sel)
            if loc.count() and loc.first.is_visible():
                return loc.first.inner_text().strip()[:120]
        except Exception:  # noqa: BLE001
            pass
    return ""


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

            # ---------- 1. 抽屉内加购 ----------
            pg.goto(BASE + "/product/101", wait_until="domcontentloaded")
            pg.wait_for_timeout(1000)
            b0 = badge(pg)
            pg.click("button.link-hint:has-text('选择规格')", timeout=5000)
            pg.wait_for_timeout(700)
            OUT["drawer_open"] = pg.locator(".van-popup").first.is_visible()
            pg.click(".van-popup button.chip:has-text('128GB')", timeout=4000)
            pg.wait_for_timeout(300)
            pg.click(".van-popup button.chip:has-text('原色钛金属')", timeout=4000)
            pg.wait_for_timeout(400)
            OUT["drawer_selected"] = pg.eval_on_selector_all(
                ".van-popup button.chip[class*='active']", "e=>e.map(x=>x.innerText.trim())")
            pg.screenshot(path=str(SHOT / "25_drawer.png"))
            pg.click(".van-popup button:has-text('加入购物车')", timeout=5000)
            pg.wait_for_timeout(1600)
            b1 = badge(pg)
            OUT["add_to_cart"] = {"badgeBefore": b0, "badgeAfter": b1, "toast": toast(pg), "delta": b1 - b0}
            pg.screenshot(path=str(SHOT / "26_added.png"))
            print("加购角标:", b0, "->", b1, "| toast:", toast(pg))

            # ---------- 2. 立即购买 → 提交订单 ----------
            pg.goto(BASE + "/product/101", wait_until="domcontentloaded")
            pg.wait_for_timeout(900)
            pg.click("button.link-hint:has-text('选择规格')", timeout=5000)
            pg.wait_for_timeout(600)
            pg.click(".van-popup button.chip:has-text('128GB')", timeout=4000)
            pg.wait_for_timeout(300)
            pg.click(".van-popup button.chip:has-text('原色钛金属')", timeout=4000)
            pg.wait_for_timeout(400)
            pg.click(".van-popup button:has-text('立即购买')", timeout=5000)
            pg.wait_for_timeout(2200)
            OUT["checkout"] = {"url": pg.url,
                               "hasSubmit": pg.locator("button:has-text('提交订单')").count() > 0,
                               "text": pg.locator("#app").first.inner_text()[:300]}
            print("立即购买 ->", pg.url)
            pg.screenshot(path=str(SHOT / "27_checkout.png"), full_page=True)

            if pg.locator("button:has-text('提交订单')").count():
                pg.click("button:has-text('提交订单')", timeout=6000)
                pg.wait_for_timeout(2800)
                body = pg.locator("#app").first.inner_text()
                OUT["submit"] = {
                    "url": pg.url, "toast": toast(pg),
                    "orderNos": list(dict.fromkeys(re.findall(r"O\d{15,}", body)))[:3],
                    "text": body[:350],
                }
                print("提交订单 ->", pg.url, "| 订单号:", OUT["submit"]["orderNos"])
                pg.screenshot(path=str(SHOT / "28_after_submit.png"), full_page=True)

            # ---------- 3. 待付款订单 → 去支付 → 收银台 ----------
            pg.goto(BASE + "/orders", wait_until="domcontentloaded")
            pg.wait_for_timeout(1500)
            try:
                pg.click("text=待付款", timeout=4000)
                pg.wait_for_timeout(1300)
            except Exception:  # noqa: BLE001
                pass
            actions = pg.eval_on_selector_all(
                "a[href*='/orders/'], button",
                "e=>e.map(x=>({href:x.getAttribute('href'),t:(x.innerText||'').trim().slice(0,20)})).slice(0,25)")
            OUT["pending"] = actions
            print("待付款列表动作:", json.dumps(actions[:10], ensure_ascii=False))
            pg.screenshot(path=str(SHOT / "29_pending.png"), full_page=True)

            href = next((a["href"] for a in actions if (a.get("href") or "").startswith("/orders/")), None)
            if href:
                pg.goto(BASE + href, wait_until="domcontentloaded")
                pg.wait_for_timeout(1200)
                OUT["orderDetail"] = {"url": pg.url,
                                      "buttons": pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)")}
                print("订单详情:", OUT["orderDetail"]["buttons"])
                if pg.locator("button:has-text('去支付')").count():
                    pg.click("button:has-text('去支付')")
                    pg.wait_for_timeout(1800)
                    OUT["cashier"] = {"url": pg.url,
                                      "buttons": pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)"),
                                      "text": pg.locator("#app").first.inner_text()[:400]}
                    print("收银台:", pg.url, OUT["cashier"]["buttons"])
                    pg.screenshot(path=str(SHOT / "30_cashier.png"), full_page=True)
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal6.png"))
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close(); b.close()
    Path("/tmp/ui-probe/evidence6.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
    print("\n-> evidence6.json")


if __name__ == "__main__":
    main()
