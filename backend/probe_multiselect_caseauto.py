"""验证两处改造：
A. 用例脚本页：勾选多条 → 批量执行 → 执行记录折叠为一条批次；
B. 用例列表：自动化 是/否 列、非自动化运行按钮禁用、已自动化可点并真实执行。
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

            # ---------- A. 勾选多条批量执行 ----------
            pg.goto(BASE + "/project/ecommerce/webui/scripts", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3000)
            pg.fill("input[placeholder*='搜索用例 ID']", "TC-100")
            pg.wait_for_timeout(600)
            boxes = pg.locator("div.max-h-56 input[type='checkbox']")
            OUT["visibleRows"] = boxes.count()
            boxes.nth(0).check()
            boxes.nth(1).check()
            pg.wait_for_timeout(300)
            OUT["selectBtn"] = pg.locator("button:has-text('执行选中')").first.inner_text()
            pg.screenshot(path=str(SHOT / "74_multiselect.png"))

            pg.click("button:has-text('执行选中')")
            # 等批次完成（结果卡出现“查看批次详情”）
            pg.wait_for_selector("button:has-text('查看批次详情')", timeout=180000)
            pg.wait_for_timeout(800)
            OUT["batchToastDone"] = True
            OUT["batchLinkBtn"] = pg.locator("button:has-text('查看批次详情')").first.inner_text()
            pg.screenshot(path=str(SHOT / "75_multiselect_result.png"), full_page=True)
            pg.click("button:has-text('查看批次详情')")
            pg.wait_for_timeout(2500)
            OUT["batchPageUrl"] = pg.url
            OUT["batchPageHasTable"] = "批次内用例" in pg.locator("body").inner_text()

            # ---------- B. 用例列表自动化列 ----------
            pg.goto(BASE + "/project/ecommerce/testcases", wait_until="domcontentloaded", timeout=30000)
            pg.wait_for_timeout(3500)
            header = pg.locator("thead").inner_text()
            OUT["hasAutoColumn"] = "自动化" in header
            OUT["hasTestTypeHeader"] = "测试类型" in header
            OUT["filters"] = pg.eval_on_selector_all("select", "els => els.map(e => e.value).slice(0,4)")

            info = pg.evaluate("""() => {
              const rows = [...document.querySelectorAll('tbody tr')];
              const out = [];
              for (const r of rows) {
                const cells = [...r.querySelectorAll('td')].map(td => td.innerText.trim());
                if (cells.length < 6) continue;
                const auto = cells[4];
                const runBtn = [...r.querySelectorAll('button')].find(b => b.innerText.trim() === '运行');
                out.push({ id: cells[0], auto, disabled: runBtn ? runBtn.disabled : null });
              }
              return out;
            }""")
            OUT["sampleRows"] = info[:6]
            OUT["hasNo"] = any(x["auto"] == "否" for x in info)
            OUT["hasYes"] = any(x["auto"] == "是" for x in info)
            no_rows = [x for x in info if x["auto"] == "否"]
            yes_rows = [x for x in info if x["auto"] == "是"]
            OUT["noDisabled"] = all(x["disabled"] for x in no_rows) if no_rows else None
            OUT["yesEnabled"] = all(x["disabled"] is False for x in yes_rows) if yes_rows else None
            pg.screenshot(path=str(SHOT / "76_caselist_auto.png"))

            # 点一个“是”的运行 → UI 自动化弹窗
            if yes_rows:
                cid = yes_rows[0]["id"]
                pg.locator(f"tbody tr:has-text('{cid}') button:has-text('运行')").first.click()
                pg.wait_for_timeout(1200)
                OUT["uiModalOpen"] = "UI 自动化执行" in pg.locator("body").inner_text()
                pg.click("button:has-text('开始执行')")
                pg.wait_for_selector("text=判定", timeout=120000)
                pg.wait_for_timeout(600)
                dlg = pg.locator("[role='dialog']").last
                OUT["uiModalResult"] = dlg.inner_text().replace("\n", " | ")[:320]
                pg.screenshot(path=str(SHOT / "77_caselist_ui_run.png"))
        except Exception as e:  # noqa: BLE001
            OUT["fatal"] = str(e)[:400]
            try:
                pg.screenshot(path=str(SHOT / "fatal_multi.png"), full_page=True)
            except Exception:  # noqa: BLE001
                pass
        finally:
            ctx.close()
            b.close()
    print(json.dumps(OUT, ensure_ascii=False, indent=2)[:3000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
