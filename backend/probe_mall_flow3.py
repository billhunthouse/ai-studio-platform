"""五次探测：dump 商品详情页的真实 DOM 结构（规格 chip、操作按钮、弹窗），
为精确 locator 提供依据；并验证「先选全规格 → 再点页面主按钮」能否真实加购成功。
"""
from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:5174"
OUT: dict = {}


def snap(pg, tag):
    data = {"url": pg.url, "popups": []}
    try:
        pops = pg.locator(".van-popup")
        for i in range(pops.count()):
            el = pops.nth(i)
            data["popups"].append({"visible": el.is_visible(), "text": el.inner_text()[:200]})
    except Exception:  # noqa: BLE001
        pass
    OUT[tag] = data
    return data


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
            pg.wait_for_timeout(1200)

            # 结构 dump
            OUT["chips"] = pg.eval_on_selector_all(
                "button[class*='chip']",
                "els=>els.map(e=>({t:e.innerText.trim().replace(/\\n/g,' '), cls:e.className, vis:!!e.offsetParent}))")
            OUT["allButtons"] = pg.eval_on_selector_all(
                "button",
                "els=>els.map(e=>({t:e.innerText.trim().replace(/\\n/g,' '), cls:e.className,"
                " inPopup: !!e.closest('.van-popup'), vis:!!e.offsetParent}))")
            OUT["badge"] = pg.locator("text=/购物车\\(\\d+\\)/").first.inner_text().strip()
            snap(pg, "step0")

            # 选容量 128GB
            for sel in ("button.chip:has-text('128GB')",):
                try:
                    pg.click(sel, timeout=4000)
                    pg.wait_for_timeout(400)
                    OUT["click_128"] = "ok"
                except Exception as e:  # noqa: BLE001
                    OUT["click_128"] = str(e)[:200]
            snap(pg, "after_128")

            # 选颜色（chip 且文本含"原色钛金属"，排除缺货）
            for sel in ("button.chip:not(.is-out):has-text('原色钛金属')", "button.chip:has-text('原色钛金属')"):
                try:
                    pg.click(sel, timeout=4000)
                    pg.wait_for_timeout(400)
                    OUT["click_color"] = f"ok via {sel}"
                    break
                except Exception as e:  # noqa: BLE001
                    OUT["click_color"] = str(e)[:200]
            snap(pg, "after_color")
            OUT["chips_after"] = pg.eval_on_selector_all(
                "button[class*='chip']", "els=>els.map(e=>e.innerText.trim().replace(/\\n/g,' ')+' :: '+e.className)")
            pg.screenshot(path="/tmp/ui-probe/23_spec_selected.png")

            # 点页面主按钮（排除 popup 内）
            try:
                pg.click("button.btn:has-text('加入购物车')", timeout=5000)
                OUT["add_click"] = "ok"
            except Exception as e:  # noqa: BLE001
                OUT["add_click"] = str(e)[:250]
            pg.wait_for_timeout(1800)
            OUT["badge_after"] = pg.locator("text=/购物车\\(\\d+\\)/").first.inner_text().strip()
            snap(pg, "after_add")
            OUT["body_tail"] = pg.locator("#app").first.inner_text()[-300:]
            pg.screenshot(path="/tmp/ui-probe/24_after_add_ok.png")
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:300]
        finally:
            ctx.close(); b.close()
    Path("/tmp/ui-probe/evidence5.json").write_text(json.dumps(OUT, ensure_ascii=False, indent=2))
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])


if __name__ == "__main__":
    main()
