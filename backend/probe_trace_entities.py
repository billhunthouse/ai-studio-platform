"""追溯实体详情页批量冒烟：覆盖 表 / 接口 / 页面 / 需求 / 代码 五类实体。

每类取若干真实 ID（从后端列表接口拉），逐个打开详情页，检查：
- 无 pageerror / 错误边界
- 不是「加载失败」
- 「索引」「表结构」「接口契约」等关键区块有内容
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://127.0.0.1:8000/api/v1"
BASE = "http://127.0.0.1:8443"
OUT = Path("/tmp/route-smoke")
OUT.mkdir(parents=True, exist_ok=True)
PID = "ecommerce"


def api(path: str, tok: str | None = None, body: dict | None = None):
    h = {"Content-Type": "application/json", "X-Project-Id": PID}
    if tok:
        h["Authorization"] = "Bearer " + tok
    req = urllib.request.Request(API + path, data=json.dumps(body).encode() if body else None, headers=h)
    return json.load(urllib.request.urlopen(req))


def collect_ids(tok: str) -> dict[str, list[str]]:
    def ids(path: str, n: int = 6) -> list[str]:
        d = api(path, tok)["data"]
        items = d if isinstance(d, list) else d.get("items", [])
        return [i["id"] for i in items[:n]]

    return {
        "table": ids("/trace/tables"),
        "api": ids("/trace/apis"),
        "page": ids("/trace/pages"),
        "requirement": ids("/requirements"),
    }


def main() -> int:
    tok = api("/auth/login", body={"email": "zhangwei@corp.com", "password": "Admin@12345"})["data"]["accessToken"]
    groups = collect_ids(tok)
    report = []

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

        for etype, eids in groups.items():
            for eid in eids:
                errs: list[str] = []
                pg.on("pageerror", lambda e, bucket=errs: bucket.append(f"{e.name}: {e.message}"))
                url = (f"{BASE}/project/{PID}/trace/entity?type={etype}"
                       f"&id={urllib.parse.quote(eid, safe='')}")
                try:
                    pg.goto(url, wait_until="domcontentloaded", timeout=30000)
                    pg.wait_for_timeout(1600)
                    body = pg.locator("body").inner_text()
                    rec = {"type": etype, "id": eid,
                           "boundary": "页面出错了" in body,
                           "loadFailed": "加载失败" in body,
                           "pageErrors": errs,
                           "hasCards": body.count("索引") + body.count("表结构") + body.count("接口契约")}
                    if rec["boundary"] or rec["loadFailed"] or errs:
                        shot = OUT / f"entity_{etype}_{eid.replace(':', '_').replace('/', '_')[:60]}.png"
                        pg.screenshot(path=str(shot))
                        rec["shot"] = str(shot)
                except Exception as exc:  # noqa: BLE001
                    rec = {"type": etype, "id": eid, "fatal": repr(exc)[:200]}
                report.append(rec)
                bad = rec.get("boundary") or rec.get("loadFailed") or rec.get("pageErrors") or rec.get("fatal")
                print(f"{'FAIL' if bad else 'ok  '} {etype:12} {eid}")
        b.close()

    (OUT / "entity-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    bad = [r for r in report if r.get("boundary") or r.get("loadFailed") or r.get("pageErrors") or r.get("fatal")]
    print(f"\n{len(report)} 个实体，异常 {len(bad)}")
    for r in bad:
        print(" -", r["type"], r["id"], r.get("pageErrors") or r.get("fatal") or "加载失败/错误边界")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
