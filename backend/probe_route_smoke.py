"""全站路由冒烟：逐页打开，捕获运行时异常 / 错误边界 / 控制台报错。

用法：.venv/bin/python probe_route_smoke.py [--headed]
输出：/tmp/route-smoke/report.json + 每个异常页截图
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8443"
OUT = Path("/tmp/route-smoke")
OUT.mkdir(parents=True, exist_ok=True)

PROJECT = "ecommerce"

PROJECT_ROUTES = [
    "overview",
    "requirements",
    "requirements/REQ-021",
    "trace",
    "testcases",
    "testcases/generate",
    "testcases/review",
    "api",
    "api/debug",
    "api/suites",
    "api/reports",
    "webui/scripts",
    "webui/runs",
    "webui/bindings",
    "webui/recorder",
    "webui",
    "app",
    "app/flow",
    "app/runs",
    "ai/chat",
    "ai/workflow",
    "knowledge",
    "knowledge/documents",
    "knowledge/recall",
    "knowledge/learning",
    "tasks",
    "tasks/agent-eval",
    "tasks/compare",
]

GLOBAL_ROUTES = [
    "dashboard",
    "skills/list",
    "skills/mcp",
    "mcp",
    "team/members",
    "team/roles",
    "team/assignments",
    "profile/info",
    "profile/security",
    "profile/assets",
    "profile/keys",
]

ADMIN_ROUTES = [
    "models/providers",
    "models/routing",
    "models/test",
    "system/users",
    "system/health",
    "system/notifications",
    "audit/logs",
]

EXTRA_ROUTES = [
    f"/project/{PROJECT}/trace/entity?type=table&id=table%3Ashang_mall%3Acommerce%3Aorder",
    f"/project/{PROJECT}/trace/entity?type=api&id=api%3Aorder%3AGET%3A%2Fapi%2Fv1%2Forders",
    f"/project/{PROJECT}/trace/entity?type=page&id=page%3Aorder-list",
    f"/project/{PROJECT}/trace/entity?type=requirement&id=REQ-021",
]


def targets() -> list[str]:
    out = [f"/project/{PROJECT}/{r}" for r in PROJECT_ROUTES]
    out += [f"/{r}" for r in GLOBAL_ROUTES]
    out += [f"/admin/{r}" for r in ADMIN_ROUTES]
    out += EXTRA_ROUTES
    return out


def main() -> int:
    only = None
    for a in sys.argv[1:]:
        if a.startswith("--only="):
            only = a.split("=", 1)[1]

    report: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(headless=True)
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        pg = ctx.new_page()

        pg.goto(BASE + "/login", wait_until="domcontentloaded", timeout=30000)
        pg.wait_for_timeout(1200)
        pg.fill("input[type='email'], input[name='email'], input[placeholder*='邮箱']", "zhangwei@corp.com")
        pg.fill("input[type='password']", "Admin@12345")
        pg.click("button[type='submit'], button:has-text('登录')")
        pg.wait_for_timeout(2500)

        for path in targets():
            if only and only not in path:
                continue
            errs: list[str] = []
            console: list[str] = []

            def on_err(e, bucket=errs):
                bucket.append(f"{e.name}: {e.message}")

            def on_console(m, bucket=console):
                if m.type == "error":
                    bucket.append(m.text[:300])

            pg.on("pageerror", on_err)
            pg.on("console", on_console)
            try:
                pg.goto(BASE + path, wait_until="domcontentloaded", timeout=30000)
                pg.wait_for_timeout(2200)
                body = pg.locator("body").inner_text()
                boundary = "页面出错了" in body
                blank = len(body.strip()) < 40
                rec = {"path": path, "boundary": boundary, "blank": blank,
                       "pageErrors": errs, "consoleErrors": console}
                if boundary or errs or blank:
                    shot = OUT / (path.strip("/").replace("/", "_").replace("?", "_").replace("=", "-")
                                  .replace("&", "_").replace("%", "")[:80] + ".png")
                    pg.screenshot(path=str(shot), full_page=False)
                    rec["shot"] = str(shot)
                    m = pg.locator("text=页面出错了").first
                    if m.count():
                        rec["boundaryText"] = m.locator("xpath=..").inner_text()[:400]
            except Exception as exc:  # noqa: BLE001
                rec = {"path": path, "fatal": repr(exc)[:300]}
            finally:
                pg.remove_listener("pageerror", on_err)
                pg.remove_listener("console", on_console)
            report.append(rec)
            flag = "FAIL" if rec.get("boundary") or rec.get("pageErrors") or rec.get("fatal") else "ok"
            print(f"{flag:4} {path}")
        b.close()

    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in report if r.get("boundary") or r.get("pageErrors") or r.get("fatal")]
    print(f"\n{len(report)} 页，异常 {len(bad)} 页")
    for r in bad:
        print(" -", r["path"], r.get("pageErrors") or r.get("fatal") or r.get("boundaryText"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
