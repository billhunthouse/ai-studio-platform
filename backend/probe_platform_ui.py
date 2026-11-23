"""验证平台界面（8443）上的「UI 自动化执行台」是否真的可用。

步骤：登录平台 → 进入 /project/ecommerce/webui/scripts → 检查执行台控件 →
（可选）点一次「批量真实执行」（小样本），确认进度条与结果面板渲染。
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
        ctx = b.new_context(viewport={"width": 1600, "height": 1000}, ignore_https_errors=True)
        pg = ctx.new_page()
        try:
            pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=20000)
            pg.wait_for_timeout(1200)
            OUT["loginUrl"] = pg.url
            OUT["loginInputs"] = pg.eval_on_selector_all(
                "input", "e=>e.map(x=>({type:x.type,ph:x.placeholder,name:x.name}))")
            pg.screenshot(path=str(SHOT / "40_platform_login.png"))

            # 填账号密码
            try:
                pg.fill("input[type='email'], input[name='email'], input[placeholder*='邮箱']", "zhangwei@corp.com")
                pg.fill("input[type='password']", "Admin@12345")
                pg.click("button[type='submit'], button:has-text('登录')")
                pg.wait_for_timeout(2500)
            except Exception as e:  # noqa: BLE001
                OUT["loginFillError"] = str(e)[:200]
            OUT["afterLoginUrl"] = pg.url
            pg.screenshot(path=str(SHOT / "41_after_login.png"))

            # 进入 UI 自动化脚本页
            pg.goto(BASE + "/project/ecommerce/webui/scripts", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            OUT["scriptsUrl"] = pg.url
            body = pg.locator("body").inner_text()
            OUT["hasConsole"] = "UI 自动化执行台" in body
            OUT["hasBatchBtn"] = "批量真实执行" in body
            OUT["hasLimitInput"] = pg.locator("input").count()
            OUT["bodyHead"] = body[:400].replace("\n", " | ")
            pg.screenshot(path=str(SHOT / "42_ui_console.png"), full_page=False)
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:300]
            try:
                pg.screenshot(path=str(SHOT / "fatal_platform.png"))
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
            b.close()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:1800])
    return 0


if __name__ == "__main__":
    sys.exit(main())
