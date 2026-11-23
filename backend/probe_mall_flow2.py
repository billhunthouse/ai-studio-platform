"""四次探测（稳健版）：聚焦 van-popup 弹窗的成因与关闭方式，以及选规格后加购是否真成功。
每一步都用 try/except 兜住，保证能走到最后并落盘证据。
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174"
SHOT = Path("/tmp/ui-probe")
SHOT.mkdir(parents=True, exist_ok=True)
OUT: dict = {}


def popups(page):
    out = []
    for sel in (".van-popup", ".van-overlay", "[role='dialog']"):
        try:
            loc = page.locator(sel)
            for i in range(min(loc.count(), 3)):
                el = loc.nth(i)
                try:
                    out.append({"sel": sel, "visible": el.is_visible(), "text": el.inner_text()[:300],
                                "buttons": el.locator("button").all_inner_texts()[:10]})
                except Exception:  # noqa: BLE001
                    pass
        except Exception:  # noqa: BLE001
            pass
    return out


def badge(page):
    try:
        return page.locator("text=/购物车\\(\\d+\\)/").first.inner_text().strip()
    except Exception:  # noqa: BLE001
        return "?"


def main():
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1440, "height": 900})
        pg = ctx.new_page()
        try:
            pg.goto(BASE + "/login", wait_until="domcontentloaded")
            pg.fill("input[placeholder='请输入 11 位手机号']", "13800000001")
            pg.fill("input[placeholder='请输入 6 位验证码']", "123456")
            pg.click("button:has-text('登录')")
            pg.wait_for_timeout(1200)

            pg.goto(BASE + "/product/101", wait_until="domcontentloaded")
            pg.wait_for_timeout(1000)
            OUT["badge_before"] = badge(pg)
            OUT["popups_initial"] = popups(pg)

            # A. 不选规格直接加购
            pg.click("button:has-text('加入购物车')", timeout=5000)
            pg.wait_for_timeout(900)
            OUT["A_popup_after_click"] = popups(pg)
            OUT["A_badge"] = badge(pg)
            pg.screenshot(path=str(SHOT / "19_popup_after_add.png"))
            print("A popup:", json.dumps(OUT["A_popup_after_click"], ensure_ascii=False)[:500])

            # 关闭弹窗：Escape → 点遮罩 → 点关闭按钮
            for how in ("escape", "overlay", "close"):
                try:
                    if how == "escape":
                        pg.keyboard.press("Escape")
                    elif how == "overlay":
                        pg.locator(".van-overlay").first.click(timeout=1500, force=True)
                    else:
                        pg.locator(".van-popup button").first.click(timeout=1500)
                    pg.wait_for_timeout(500)
                    if not any(x["visible"] for x in popups(pg)):
                        OUT["closed_by"] = how
                        break
                except Exception:  # noqa: BLE001
                    continue
            print("关闭方式:", OUT.get("closed_by"), "| 弹窗:", json.dumps(popups(pg), ensure_ascii=False)[:200])

            # B. 选规格（128GB + 原色钛金属）→ 加购
            for label in ("128GB", "原色钛金属"):
                try:
                    pg.click(f"button:has-text('{label}')", timeout=3000)
                    pg.wait_for_timeout(300)
                except Exception as e:  # noqa: BLE001
                    OUT.setdefault("spec_fail", []).append(f"{label}:{str(e)[:60]}")
            OUT["selected_class"] = pg.eval_on_selector_all(
                "button", "els=>els.filter(e=>/128GB|原色钛金属|白色钛金属|256GB/.test(e.innerText)).map(e=>e.innerText.trim()+' :: '+e.className)"
            )[:6]
            before = badge(pg)
            pg.click("button:has-text('加入购物车')", timeout=5000)
            pg.wait_for_timeout(1500)
            OUT["B_badge"] = {"before": before, "after": badge(pg)}
            OUT["B_popup"] = popups(pg)
            pg.screenshot(path=str(SHOT / "20_add_with_spec.png"))
            print("B 加购:", OUT["B_badge"], json.dumps(OUT["B_popup"], ensure_ascii=False)[:300])

            # C. 立即购买 → 确认订单
            pg.goto(BASE + "/product/101", wait_until="domcontentloaded")
            pg.wait_for_timeout(800)
            for label in ("128GB", "原色钛金属"):
                try:
                    pg.click(f"button:has-text('{label}')", timeout=2500)
                    pg.wait_for_timeout(250)
                except Exception:  # noqa: BLE001
                    pass
            pg.click("button:has-text('立即购买')", timeout=5000)
            pg.wait_for_timeout(2000)
            OUT["C_url"] = pg.url
            OUT["C_text"] = pg.locator("#app").first.inner_text()[:400]
            OUT["C_buttons"] = pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)")
            print("C 立即购买 ->", pg.url)
            pg.screenshot(path=str(SHOT / "21_buynow.png"), full_page=True)

            # D. 提交订单
            if pg.locator("button:has-text('提交订单')").count():
                pg.click("button:has-text('提交订单')", timeout=6000)
                pg.wait_for_timeout(2500)
                OUT["D_url"] = pg.url
                OUT["D_popup"] = popups(pg)
                OUT["D_text"] = pg.locator("#app").first.inner_text()[:400]
                OUT["D_buttons"] = pg.eval_on_selector_all("button", "e=>e.map(x=>x.innerText.trim()).filter(Boolean)")
                print("D 提交订单 ->", pg.url, json.dumps(OUT["D_popup"], ensure_ascii=False)[:300])
                pg.screenshot(path=str(SHOT / "22_submitted.png"), full_page=True)
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal.png"))
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close(); b.close()
    Path("/tmp/ui-probe/evidence4.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
    print("\n-> evidence4.json")


if __name__ == "__main__":
    main()
