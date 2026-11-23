"""三次探测：验证"选规格 → 加购/立即购买 → 提交订单 → 收银台"的真实闭环。
重点回答三个问题：
1. 未选规格直接点「加入购物车」是否真的成功（还是被前端拦截）？
2. 选规格后加购，购物车角标数量是否真的增加？
3. 提交订单后是否生成真实订单号、能否进入收银台并支付？
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


def cart_badge(page) -> str:
    try:
        txt = page.locator("text=/购物车\\(\\d+\\)/").first.inner_text(timeout=2500)
        return txt.strip()
    except Exception:  # noqa: BLE001
        return "购物车(?)"


def toast(page) -> str:
    """抓取页面上的提示条（element-plus / 自定义 toast）"""
    page.wait_for_timeout(600)
    for sel in (".el-message", "[role='alert']", "[class*='toast']", "[class*='message']"):
        try:
            loc = page.locator(sel)
            if loc.count() > 0:
                return " | ".join(loc.all_inner_texts()[:3])[:200]
        except Exception:  # noqa: BLE001
            continue
    return ""


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.goto(BASE + "/login", wait_until="domcontentloaded")
        page.fill("input[placeholder='请输入 11 位手机号']", "13800000001")
        page.fill("input[placeholder='请输入 6 位验证码']", "123456")
        page.click("button:has-text('登录')")
        page.wait_for_timeout(1200)

        # A. 商品详情：不选规格直接加购
        page.goto(BASE + "/product/101", wait_until="domcontentloaded")
        page.wait_for_timeout(1000)
        before = cart_badge(page)
        page.click("button:has-text('加入购物车')")
        t1 = toast(page)
        after_raw = cart_badge(page)
        OUT["A_add_without_spec"] = {"before": before, "afterRaw": after_raw, "toast": t1}
        print("A 不选规格加购:", before, "->", after_raw, "| toast:", t1)

        # B. 选规格后加购
        page.wait_for_timeout(800)
        picked = []
        for label in ["128GB", "原色钛金属"]:
            try:
                page.click(f"button:has-text('{label}')", timeout=4000)
                picked.append(label)
                page.wait_for_timeout(400)
            except Exception as e:  # noqa: BLE001
                picked.append(f"{label}:FAIL {str(e)[:60]}")
        before2 = cart_badge(page)
        page.click("button:has-text('加入购物车')")
        t2 = toast(page)
        after2 = cart_badge(page)
        OUT["B_add_with_spec"] = {"picked": picked, "before": before2, "afterRaw": after2, "toast": t2}
        print("B 选规格加购:", picked, before2, "->", after2, "| toast:", t2)
        page.screenshot(path=str(SHOT / "13_addcart.png"))

        # C. 立即购买 → 确认订单（单件）
        page.goto(BASE + "/product/101", wait_until="domcontentloaded")
        page.wait_for_timeout(900)
        for label in ["128GB", "原色钛金属"]:
            try:
                page.click(f"button:has-text('{label}')", timeout=3000)
                page.wait_for_timeout(350)
            except Exception:  # noqa: BLE001
                pass
        page.click("button:has-text('立即购买')")
        page.wait_for_timeout(1800)
        OUT["C_buy_now"] = {"url": page.url}
        text = page.locator("#app").first.inner_text()[:600]
        OUT["C_buy_now"]["text"] = text
        print("C 立即购买 ->", page.url)
        page.screenshot(path=str(SHOT / "14_buynow.png"), full_page=True)

        # D. 提交订单
        if page.locator("button:has-text('提交订单')").count() > 0:
            page.click("button:has-text('提交订单')")
            page.wait_for_timeout(2500)
            t = toast(page)
            body = page.locator("#app").first.inner_text()
            nums = re.findall(r"[A-Z]?\d{15,}", body)
            OUT["D_submit"] = {"url": page.url, "toast": t, "orderNoCandidates": list(dict.fromkeys(nums))[:6],
                              "text": body[:500]}
            print("D 提交订单 ->", page.url, "| toast:", t, "| 订单号:", nums[:3])
            page.screenshot(path=str(SHOT / "15_submitted.png"), full_page=True)
        else:
            OUT["D_submit"] = {"error": "确认订单页无提交按钮"}

        # E. 待付款订单 → 收银台
        page.goto(BASE + "/orders", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        try:
            page.click("text=待付款", timeout=4000)
            page.wait_for_timeout(1200)
        except Exception:  # noqa: BLE001
            pass
        links = page.eval_on_selector_all(
            "a[href*='/orders/'], button",
            "els => els.map(e=>({href:e.getAttribute('href'), t:(e.innerText||'').trim().slice(0,24)})).filter(x=>x.href||x)"
        )
        OUT["E_orders_pending"] = {"actions": links[:25], "text": page.locator("#app").first.inner_text()[:500]}
        print("E 待付款订单动作:", json.dumps(links[:12], ensure_ascii=False))
        page.screenshot(path=str(SHOT / "16_pending_orders.png"), full_page=True)

        # 找到最新待付款订单详情 → 去支付
        first = next((x["href"] for x in links if x.get("href", "").startswith("/orders/")), None)
        if first:
            page.goto(BASE + first, wait_until="domcontentloaded")
            page.wait_for_timeout(1200)
            btns = page.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)")
            OUT["E_order_detail"] = {"url": page.url, "buttons": btns,
                                     "text": page.locator("#app").first.inner_text()[:600]}
            print("E 订单详情:", page.url, btns)
            page.screenshot(path=str(SHOT / "17_order_detail.png"), full_page=True)
            try:
                page.click("button:has-text('去支付')", timeout=4000)
                page.wait_for_timeout(1500)
                OUT["F_pay"] = {"url": page.url,
                                "buttons": page.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)"),
                                "text": page.locator("#app").first.inner_text()[:600]}
                print("F 收银台:", page.url)
                page.screenshot(path=str(SHOT / "18_pay.png"), full_page=True)
            except Exception as e:  # noqa: BLE001
                OUT["F_pay"] = {"error": f"无去支付按钮 {str(e)[:120]}"}

        ctx.close(); b.close()
    Path("/tmp/ui-probe/evidence3.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
    print("\n-> /tmp/ui-probe/evidence3.json")


if __name__ == "__main__":
    main()
