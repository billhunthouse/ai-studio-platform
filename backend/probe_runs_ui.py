"""验证执行记录页：倒序、批次折叠、单条抽屉里的每步截图与视频。

检查点：
1. 页签顺序 = 用例脚本 / 执行记录 / 录制回放 / 元素库，且副标题小字已删除；
2. 列表倒序，首行是最新批次；
3. 单条记录 → 抽屉里有 N 张步骤截图（真实加载）+ video 元素；
4. 批次行 → 跳到 /webui/runs/{id} 子页面，里面能逐条看截图与视频。
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

            pg.goto(BASE + "/project/ecommerce/webui/runs", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            body = pg.locator("body").inner_text()
            tabs = pg.evaluate("""() => {
              const names = ['用例脚本','执行记录','录制回放','元素库'];
              const bs = [...document.querySelectorAll('button')]
                .filter(b => names.includes(b.innerText.trim()))
                .map(b => ({ t: b.innerText.trim(), x: b.getBoundingClientRect().x, y: b.getBoundingClientRect().y }))
                .filter(b => b.y > 80 && b.y < 220);
              bs.sort((a,b) => a.x - b.x);
              return bs.map(b => b.t);
            }""")
            OUT["tabOrder"] = tabs
            OUT["hintRemoved"] = "维护元素库" not in body
            OUT["statsHead"] = " ".join(body.splitlines()[:6])[:160]

            rows = pg.locator("tbody tr")
            OUT["rowCount"] = rows.count()
            OUT["first3Rows"] = [rows.nth(i).inner_text().replace("\n", " | ")[:150] for i in range(min(3, rows.count()))]
            pg.screenshot(path=str(SHOT / "70_runs_list.png"))

            # 单条记录（第 2 行）→ 抽屉
            rows.nth(1).locator("button").last.click()
            pg.wait_for_timeout(1500)
            drawer = pg.locator("[role='dialog']").last
            OUT["drawerTitle"] = drawer.locator("h3").first.inner_text()
            OUT["drawerImgs"] = drawer.locator("img").count()
            OUT["drawerVideos"] = drawer.locator("video").count()
            OUT["imgLoaded"] = pg.evaluate("""() => {
              const imgs = [...document.querySelectorAll("[role='dialog'] img")];
              return imgs.map(i => ({ w: i.naturalWidth, src: (i.getAttribute('src')||'').slice(0, 50) })).slice(0, 3);
            }""")
            pg.screenshot(path=str(SHOT / "71_single_drawer.png"))
            pg.keyboard.press("Escape")
            pg.wait_for_timeout(600)

            # 批次行（第 1 行）→ 子页面
            rows.nth(0).click()
            pg.wait_for_timeout(2500)
            OUT["batchUrl"] = pg.url
            bbody = pg.locator("body").inner_text()
            OUT["hasBatchTable"] = "批次内用例" in bbody
            OUT["batchStats"] = " ".join([ln for ln in bbody.splitlines() if ln in ("用例数", "通过", "失败", "通过率", "总耗时")])[:80]
            brows = pg.locator("tbody tr")
            OUT["batchCaseRows"] = brows.count()
            pg.screenshot(path=str(SHOT / "72_batch_page.png"), full_page=True)

            brows.nth(0).locator("button").last.click()
            pg.wait_for_timeout(1500)
            d2 = pg.locator("[role='dialog']").last
            OUT["batchDrawerTitle"] = d2.locator("h3").first.inner_text()
            OUT["batchDrawerImgs"] = d2.locator("img").count()
            OUT["batchDrawerVideos"] = d2.locator("video").count()
            pg.screenshot(path=str(SHOT / "73_batch_case_drawer.png"))
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal_runs.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
            b.close()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
