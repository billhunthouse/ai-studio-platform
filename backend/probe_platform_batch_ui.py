"""在平台界面上真实点一次「批量真实执行」，验证界面驱动闭环：
控件 → 后台任务 → 进度 → 结果面板（通过率 / 按 PO 汇总 / 逐条证据）。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8443"
SHOT = Path("/tmp/ui-probe")
OUT: dict = {}


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        pg = ctx.new_page()
        try:
            pg.goto(BASE + "/login", wait_until="domcontentloaded")
            pg.wait_for_timeout(900)
            pg.fill("input[type='email']", "zhangwei@corp.com")
            pg.fill("input[type='password']", "Admin@12345")
            pg.click("button[type='submit'], button:has-text('登录')")
            pg.wait_for_timeout(2000)
            pg.goto(BASE + "/project/ecommerce/webui/scripts", wait_until="domcontentloaded")
            pg.wait_for_timeout(2500)

            inputs = pg.locator("input")
            OUT["inputCount"] = inputs.count()
            # 条数 = 5，写操作配额 = 1
            inputs.nth(0).fill("5")
            inputs.nth(1).fill("1")
            pg.wait_for_timeout(300)
            pg.get_by_role("button", name="批量真实执行").click()
            OUT["clicked"] = True

            # 等待进度出现
            pg.wait_for_timeout(2500)
            OUT["progressShown"] = "执行中" in pg.locator("body").inner_text()
            pg.screenshot(path=str(SHOT / "43_batch_running.png"))

            # 等结果面板（最多 150s）
            ok = False
            for _ in range(50):
                pg.wait_for_timeout(3000)
                body = pg.locator("body").inner_text()
                if "真实执行结果" in body:
                    ok = True
                    break
            OUT["resultPanel"] = ok
            body = pg.locator("body").inner_text()
            for key in ("真实执行结果", "通过率", "按 Page Object 汇总", "逐条执行证据", "最终页面"):
                OUT[f"has_{key}"] = key in body
            pg.screenshot(path=str(SHOT / "44_batch_result.png"))
            OUT["bodyTail"] = body[-900:].replace("\n", " | ")
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:300]
            try:
                pg.screenshot(path=str(SHOT / "fatal_batch_ui.png"))
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
            b.close()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:2200])
    return 0


if __name__ == "__main__":
    sys.exit(main())
