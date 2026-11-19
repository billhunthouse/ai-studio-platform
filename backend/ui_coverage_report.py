"""UI 自动化覆盖：页面 / 需求两个视角的缺口清单。

UI 用例是 Cucumber feature，场景与页面的对应无法从步骤文本可靠推断，
因此这里用一张显式映射表（FEATURE_PAGES）登记"每个 feature 实际走到的页面"，
改 feature 时同步改这张表——比猜可靠。

用法：
  .venv/bin/python ui_coverage_report.py --repo /path/to/shang-pivot-master \
      --out docs/traceability/ui-coverage.md
"""
from __future__ import annotations

import argparse
import re
from collections import defaultdict
from pathlib import Path

import psycopg

DSN_DEFAULT = "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
PROJECT = "ecommerce"

# feature 文件 → 实际覆盖的页面（人工登记，与 feature 同改）
FEATURE_PAGES: dict[str, list[str]] = {
    "mall-login.feature": ["page:mall:/login"],
    "mall-cart.feature": ["page:mall:/", "page:mall:/product/:spuId",
                          "page:mall:/cart", "page:mall:/checkout"],
    "mall-order.feature": ["page:mall:/orders/:id"],
    "admin-console.feature": ["page:admin:/login", "page:admin:/dashboard",
                              "page:admin:/products"],
    "env-health.feature": [],
}


def parse_features(features_dir: Path) -> list[dict]:
    out = []
    for f in sorted(features_dir.glob("*.feature")):
        text = f.read_text(encoding="utf-8")
        tags = re.findall(r"@(UI-[A-Z0-9\-]+)", text)
        scenarios = re.findall(r"^\s*Scenario:\s*(.+)$", text, re.M)
        out.append({"file": f.name, "tags": tags, "scenarios": scenarios,
                    "pages": FEATURE_PAGES.get(f.name, [])})
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dsn", default=DSN_DEFAULT)
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    features = parse_features(Path(args.repo) / "ui_testcases/src/test/resources/features")

    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute("SELECT id, name FROM trace_pages WHERE project_id=%s", (args.project,))
        pages = dict(cur.fetchall())
        # 页面 → 需求
        cur.execute("""SELECT dst_id, src_id FROM trace_relations
                       WHERE project_id=%s AND rel_type='SPLITS_INTO'""", (args.project,))
        page_reqs: dict[str, list[str]] = defaultdict(list)
        for page_id, req_id in cur.fetchall():
            page_reqs[page_id].append(req_id)
        cur.execute("SELECT id, title, priority FROM requirements WHERE project_id=%s",
                    (args.project,))
        req_meta = {r[0]: (r[1], r[2]) for r in cur.fetchall()}

    covered_pages = {p for f in features for p in f["pages"]}
    covered_reqs = {r for p in covered_pages for r in page_reqs.get(p, [])}

    total_scenarios = sum(len(f["scenarios"]) for f in features
                          if f["file"] != "env-health.feature")

    lines = ["# UI 自动化覆盖报告", "",
             f"> 由 `backend/ui_coverage_report.py` 生成；feature 源 `ui_testcases/src/test/resources/features`。",
             "> 页面归属来自 trace_relations（需求 → 页面），页面与 feature 的对应见脚本内 FEATURE_PAGES 表。", ""]

    lines += ["## 汇总", "",
              f"- 业务 feature：{sum(1 for f in features if f['file'] != 'env-health.feature')} 个，"
              f"场景 {total_scenarios} 条",
              f"- 页面：{len(pages)} 个，被 UI 覆盖 {len(covered_pages)} 个"
              f"（{len(covered_pages)/max(1,len(pages)):.0%}）",
              f"- 需求：{len(req_meta)} 条，其中 {len(covered_reqs)} 条有 UI 用例"
              f"（{len(covered_reqs)/max(1,len(req_meta)):.0%}）", ""]

    lines += ["## 现有 feature 覆盖的页面", "",
              "| feature | 场景数 | 覆盖页面 |", "| --- | ---: | --- |"]
    for f in features:
        if not f["pages"]:
            continue
        names = "、".join(pages.get(p, p) for p in f["pages"])
        lines.append(f"| `{f['file']}` | {len(f['scenarios'])} | {names} |")

    lines += ["", "## 缺口页面（按归属需求的最高优先级排序）", "",
              "| 页面 | 路由 | 归属需求 | 优先级 |", "| --- | --- | --- | --- |"]
    order = {"P0": 0, "P1": 1, "P2": 2, "P3": 3}
    gaps = []
    for pid, name in pages.items():
        if pid in covered_pages:
            continue
        reqs = page_reqs.get(pid, [])
        pri = min((req_meta[r][1] for r in reqs if r in req_meta), key=lambda x: order.get(x, 9),
                  default="—")
        route = pid.split(":", 2)[-1]
        gaps.append((order.get(pri, 9), pid, name, route, reqs, pri))
    for _o, _pid, name, route, reqs, pri in sorted(gaps):
        lines.append(f"| {name} | `{route}` | {'、'.join(reqs) or '—'} | {pri} |")

    report = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
        print("报告已写出：", args.out)
    print(f"UI 覆盖页面 {len(covered_pages)}/{len(pages)}；需求 {len(covered_reqs)}/{len(req_meta)}；"
          f"缺口页面 {len(gaps)} 个（其中 P0 归属 {sum(1 for g in gaps if g[5]=='P0')} 个）")


if __name__ == "__main__":
    main()
