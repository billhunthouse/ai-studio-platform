"""验证「用例详情页 → 运行这条用例的 UI 步骤」是否真的执行。

流程：登录 → /project/ecommerce/testcases/TC-1001 → 点「运行这条用例的 UI 步骤」
→ 等待判定出现 → 读取逐步状态/断言/最终页面 → 截图。
再验证写操作保护：TC-1003 不勾选直接点，应弹出提示且不产生订单。
另验证深链：/project/ecommerce/webui/scripts?caseId=TC-1002 应自动选中。
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

            # 用例详情页
            pg.goto(BASE + "/project/ecommerce/testcases/TC-1001", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            body = pg.locator("body").inner_text()
            OUT["hasPanel"] = "Playwright UI 自动化" in body
            OUT["hasRunBtn"] = "运行这条用例的 UI 步骤" in body
            pg.screenshot(path=str(SHOT / "60_detail_panel.png"))

            pg.click("button:has-text('运行这条用例的 UI 步骤')")
            OUT["clickedAt"] = "ok"
            pg.wait_for_selector("text=最终页面：", timeout=120000)
            pg.wait_for_timeout(800)
            panel = pg.evaluate("""() => {
              const el = [...document.querySelectorAll('div')].find(d => (d.textContent || '').includes('Playwright UI 自动化 · 单条真实执行'));
              return el ? el.innerText.replace(/\\n/g, ' | ').slice(0, 900) : '(not found)';
            }""")
            OUT["panelText"] = panel
            pg.screenshot(path=str(SHOT / "61_detail_result.png"), full_page=True)

            # 写操作保护：TC-1003 不勾选写操作
            pg.goto(BASE + "/project/ecommerce/testcases/TC-1003", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(2500)
            pg.click("button:has-text('运行这条用例的 UI 步骤')")
            pg.wait_for_timeout(2500)
            OUT["writeToast"] = pg.evaluate("""() => {
              const t = document.body.innerText;
              const m = t.match(/这条用例会真实下单[^\\n]*/);
              return m ? m[0] : '(no toast)';
            }""")
            pg.screenshot(path=str(SHOT / "62_detail_write_guard.png"))

            # 深链预选
            pg.goto(BASE + "/project/ecommerce/webui/scripts?caseId=TC-1002", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            OUT["deeplinkSelected"] = pg.evaluate("""() => {
              const t = document.body.innerText;
              const m = t.match(/已选\\s*TC-\\d+[^\\n]*/);
              return m ? m[0] : '(not selected)';
            }""")
            pg.screenshot(path=str(SHOT / "63_deeplink.png"))
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal_detail.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
            b.close()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
