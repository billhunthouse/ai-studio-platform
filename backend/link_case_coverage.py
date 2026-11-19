"""把已有用例清单接到真实需求上，产出需求级覆盖率。

为什么需要这一步：`api_testcases/test_cases_inventory.md` 里 424 条用例的需求引用是
`需求：MALL-10` 这类旧编码，与 PRD（V1-FR-* / V2-FR-*）对不上，导致
"哪条需求测过了、哪条根本没测"无法回答（rule.md §3.5 / lint R28 的缺口）。

接通方式：用例 → (METHOD,path) → 接口 → 所在页面 → 需求（多对多自动展开）。

用法：
  .venv/bin/python link_case_coverage.py --inventory /path/to/test_cases_inventory.md \
      --out docs/traceability/case-coverage.md
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import psycopg

DSN_DEFAULT = "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
PROJECT = "ecommerce"
REQ_IN_BODY = re.compile(r"需求[：:]\s*([A-Z0-9\-]+(?:[、,，/]\s*[A-Z0-9\-]+)*)")


def _old_refs(note: str) -> list[str]:
    """备注里的旧需求编号（可能是"需求：MALL-10、MALL-11"这种复合写法）。"""
    refs: list[str] = []
    for m in REQ_IN_BODY.finditer(note):
        refs.extend(x for x in re.split(r"[、,，/\s]+", m.group(1)) if x)
    return refs


def parse_inventory(path: Path) -> list[dict]:
    """解析用例表：只取有 METHOD path 的行，其余（说明段、统计段）忽略。"""
    cases = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 14:
            continue
        cid = cells[0]
        if not re.match(r"^[A-Z][A-Z0-9_]*-\d{3}$", cid):
            continue
        m = re.match(r"(GET|POST|PUT|DELETE|PATCH)\s+(\S+)", cells[5])
        if not m:
            continue
        cases.append({
            "caseId": cid, "priority": cells[1], "type": cells[2], "title": cells[3],
            "api": f"{m.group(1)}:{m.group(2)}",
            "expectedHttp": cells[9], "expectedCode": cells[10],
            "note": cells[13],
            "oldReqRefs": _old_refs(cells[13]),
        })
    return cases


def build_maps(cur, project: str) -> tuple[dict, dict]:
    """api_id -> [page_id]，page_id -> [requirement_id]，requirement_id -> title。"""
    cur.execute("""SELECT src_id, dst_id FROM trace_relations
                   WHERE project_id=%s AND rel_type='TRIGGERS' AND status<>'stale'""", (project,))
    api_pages: dict[str, list[str]] = defaultdict(list)
    for page_id, api_id in cur.fetchall():
        api_pages[api_id].append(page_id)

    cur.execute("""SELECT src_id, dst_id FROM trace_relations
                   WHERE project_id=%s AND rel_type='SPLITS_INTO' AND status<>'stale'""", (project,))
    page_reqs: dict[str, list[str]] = defaultdict(list)
    for req_id, page_id in cur.fetchall():
        page_reqs[page_id].append(req_id)

    cur.execute("SELECT id, title, priority FROM requirements WHERE project_id=%s", (project,))
    req_meta = {r[0]: {"title": r[1], "priority": r[2]} for r in cur.fetchall()}
    return api_pages, page_reqs, req_meta


def requirement_of(api_id: str, api_pages: dict, page_reqs: dict) -> list[str]:
    out: list[str] = []
    for page_id in api_pages.get(api_id, []):
        for req_id in page_reqs.get(page_id, []):
            if req_id not in out:
                out.append(req_id)
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--dsn", default=DSN_DEFAULT)
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    cases = parse_inventory(Path(args.inventory))
    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        api_pages, page_reqs, req_meta = build_maps(cur, args.project)
        cur.execute("SELECT method, path FROM trace_apis WHERE project_id=%s", (args.project,))
        all_apis = {f"{m}:{p}" for m, p in cur.fetchall()}

    # 用例 → 需求
    req_cases: dict[str, list[dict]] = defaultdict(list)
    unlinked = []
    for c in cases:
        # 用例清单里记的是 `METHOD /path`，追溯库里接口 ID 带 `api:` 前缀
        reqs = requirement_of("api:" + c["api"], api_pages, page_reqs)
        c["reqs"] = reqs
        if not reqs:
            unlinked.append(c)
        for r in reqs:
            req_cases[r].append(c)

    # 接口维度覆盖（每接口的用例类型分布）
    api_cases: dict[str, list[dict]] = defaultdict(list)
    for c in cases:
        api_cases[c["api"]].append(c)

    lines = ["# 需求 → 用例覆盖矩阵", "",
             f"> 由 `backend/link_case_coverage.py` 生成；用例源 `test_cases_inventory.md`（{len(cases)} 条）。",
             "> 接通链路：用例 → 接口 → 页面 → 需求（trace_relations，来源 SPEC）。", ""]

    covered = [r for r in req_meta if req_cases.get(r)]
    uncovered = [r for r in req_meta if not req_cases.get(r)]
    lines += ["## 汇总", "",
              f"- 需求总数：{len(req_meta)}",
              f"- 有用例的需求：{len(covered)}（{len(covered)/max(1,len(req_meta)):.0%}）",
              f"- 无用例的需求：{len(uncovered)}",
              f"- 用例总数：{len(cases)}；无法归属到需求：{len(unlinked)} 条",
              f"- 代码里有、用例里没有的接口：{len(all_apis - set(api_cases))}", ""]

    lines += ["## 逐需求明细", "",
              "| 需求 | 优先级 | 标题 | 接口数 | 用例数 | P0 | 类型分布 |",
              "| --- | --- | --- | ---: | ---: | ---: | --- |"]
    for rid in sorted(req_meta):
        cs = req_cases.get(rid, [])
        apis = {c["api"] for c in cs}
        types = Counter(c["type"] for c in cs)
        p0 = sum(1 for c in cs if c["priority"] == "P0")
        lines.append(f"| {rid} | {req_meta[rid]['priority']} | {req_meta[rid]['title']} | "
                     f"{len(apis)} | {len(cs)} | {p0} | "
                     f"{'、'.join(f'{k}{v}' for k, v in types.items()) or '—'} |")

    if uncovered:
        lines += ["", "## 无用例的需求（缺口）", ""]
        for rid in uncovered:
            lines.append(f"- `{rid}` {req_meta[rid]['title']}")

    if unlinked:
        lines += ["", "## 无法归属需求的用例（接口没挂到任何页面）", ""]
        for c in unlinked[:40]:
            lines.append(f"- `{c['caseId']}` {c['api']}")

    # 接口级覆盖缺口：无用例 / 仅有 1 类
    thin = []
    for api in sorted(all_apis):
        cs = api_cases.get(api, [])
        if len(cs) < 3:
            thin.append({"api": api, "count": len(cs),
                         "types": [c["type"] for c in cs]})
    lines += ["", "## 用例偏薄的接口（少于 3 条，规范要求 ≥5 维度）", "",
              "| 接口 | 用例数 | 已有类型 |", "| --- | ---: | --- |"]
    for t in thin:
        lines.append(f"| `{t['api']}` | {t['count']} | {'、'.join(t['types']) or '无'} |")

    report = "\n".join(lines) + "\n"
    if args.out:
        Path(args.out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.out).write_text(report, encoding="utf-8")
        print("报告已写出：", args.out)
    else:
        print(report[:3000])

    print(f"\n需求覆盖 {len(covered)}/{len(req_meta)}，"
          f"缺 {len(uncovered)} 条；用例 {len(cases)} 条；"
          f"未覆盖接口 {len(all_apis - set(api_cases))} 个；薄接口 {len(thin)} 个")


if __name__ == "__main__":
    main()
