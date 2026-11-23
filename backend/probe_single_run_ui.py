"""验证「单条用例执行」在平台页面上真的可用。

流程：登录平台 → WebUI 自动化页 → 搜 TC-1001 → 选中 → 点「运行这条用例」
→ 等待回放面板 → 读取结论/步骤/断言/最终页面 → 截图。
再验证写操作保护：选 TC-1003（下单）时按钮应禁用并提示勾选。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8443"
SHOT = Path("/tmp/ui-probe")
SHOT.mkdir(parents=True, exist_ok=True)
OUT: dict = {}


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        pg = ctx.new_page()
        try:
            pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=20000)
            pg.wait_for_timeout(1000)
            pg.fill("input[type='email'], input[name='email'], input[placeholder*='邮箱']", "zhangwei@corp.com")
            pg.fill("input[type='password']", "Admin@12345")
            pg.click("button[type='submit'], button:has-text('登录')")
            pg.wait_for_timeout(2500)

            pg.goto(BASE + "/project/ecommerce/webui/scripts", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(2500)
            OUT["url"] = pg.url
            body = pg.locator("body").inner_text()
            OUT["hasSingleCard"] = "单条用例执行" in body
            OUT["hasRunBtn"] = "运行这条用例" in body
            OUT["indexHint"] = next((ln for ln in body.splitlines() if "条可直接执行" in ln), "")
            pg.screenshot(path=str(SHOT / "50_single_card.png"))

            # 搜索并选中 TC-1001
            search = pg.locator("input[placeholder*='搜索用例 ID']").first
            search.fill("TC-1001")
            pg.wait_for_timeout(600)
            row = pg.locator("button:has-text('TC-1001')").first
            OUT["rowText"] = row.inner_text().replace("\n", " | ")[:160]
            row.click()
            pg.wait_for_timeout(500)
            OUT["selectedLine"] = next(
                (ln for ln in pg.locator("body").inner_text().splitlines() if ln.startswith("已选")), "")
            pg.screenshot(path=str(SHOT / "51_selected.png"))

            # 真实执行
            pg.click("button:has-text('运行这条用例')")
            OUT["clickedAt"] = "ok"
            pg.wait_for_selector("text=单条执行回放", timeout=120000)
            pg.wait_for_timeout(1200)
            replay = pg.locator("div", has_text="单条执行回放").last
            OUT["replayText"] = replay.inner_text()[:1200].replace("\n", " | ")
            OUT["hasPassTag"] = "通过" in pg.locator("body").inner_text()
            OUT["shotImg"] = pg.locator("img[alt='执行截图']").count()
            pg.screenshot(path=str(SHOT / "52_replay.png"), full_page=True)

            # 展开第 2 步，验证能看到真实定位器与输入值
            pg.locator("button:has-text('输入手机号')").first.click()
            pg.wait_for_timeout(500)
            OUT["stepDetail"] = pg.evaluate("""() => {
              const el = [...document.querySelectorAll('div')].find(d => (d.textContent || '').startsWith('用例原文：输入手机号'));
              return el ? el.innerText.replace(/\\n/g, ' | ').slice(0, 400) : '(not found)';
            }""")
            pg.screenshot(path=str(SHOT / "54_step_detail.png"), full_page=True)

            # 写操作保护
            search.fill("TC-1003")
            pg.wait_for_timeout(600)
            pg.locator("button:has-text('TC-1003')").first.click()
            pg.wait_for_timeout(500)
            btn = pg.locator("button:has-text('运行这条用例')").first
            OUT["writeGuardDisabled"] = btn.is_disabled()
            OUT["writeHint"] = next(
                (ln for ln in pg.locator("body").inner_text().splitlines() if "勾选" in ln), "")
            pg.screenshot(path=str(SHOT / "53_write_guard.png"))
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal_single.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
            b.close()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
