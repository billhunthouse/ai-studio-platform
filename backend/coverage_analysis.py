"""追溯覆盖率分析：回答"功能点是否被完整映射"与"关联关系是否建立"。

输出三类结论：
1. 需求级四层覆盖（页面/接口/代码/表）——缺口清单可直接派活；
2. 接口级契约完整度（参数/请求体/鉴权/响应/代码/表）——决定能不能生成合格用例；
3. 文档与代码漂移（页面地图引用 vs 扫描结果）——文档写了但代码没有、或反之。

用法：
  .venv/bin/python coverage_analysis.py --repo /path/to/shang-pivot-master [--json out.json]
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg

from seed_prd import DSN_DEFAULT, PROJECT, parse_page_map, parse_requirements

LAYERS = ["page", "api", "code_artifact", "table"]


def load_graph(cur, project: str) -> dict[str, list[tuple[str, str]]]:
    """src_id -> [(rel_type, dst_id)]，一次查全图，避免 N+1。"""
    cur.execute(
        """SELECT src_id, rel_type, dst_id FROM trace_relations
           WHERE project_id=%s AND status <> 'stale'""", (project,))
    adj: dict[str, list[tuple[str, str]]] = {}
    for src, rel, dst in cur.fetchall():
        adj.setdefault(src, []).append((rel, dst))
    return adj


def reachable_layers(adj, root: str, max_hop: int = 6) -> dict[str, list[str]]:
    """从需求出发多跳可达的各层实体（去重，保序）。"""
    found: dict[str, list[str]] = {k: [] for k in LAYERS}
    seen = {root}
    frontier = [root]
    for _ in range(max_hop):
        nxt = []
        for node in frontier:
            for _rel, dst in adj.get(node, []):
                if dst in seen:
                    continue
                seen.add(dst)
                # 按 ID 形态判定层：代码实体是 `Controller#method`，没有统一前缀
                if dst.startswith("page:"):
                    found["page"].append(dst)
                elif dst.startswith("api:"):
                    found["api"].append(dst)
                elif dst.startswith("table:"):
                    found["table"].append(dst)
                elif "#" in dst:
                    found["code_artifact"].append(dst)
                nxt.append(dst)
        frontier = nxt
        if not frontier:
            break
    return found


def analyse(cur, project: str) -> dict:
    adj = load_graph(cur, project)

    cur.execute("SELECT id, title, priority FROM requirements WHERE project_id=%s ORDER BY id",
                (project,))
    reqs = cur.fetchall()
    cur.execute("SELECT id, name FROM trace_pages WHERE project_id=%s", (project,))
    page_names = dict(cur.fetchall())
    cur.execute("SELECT id, method, path, summary, auth_requirement, request_schema, response_schema "
                "FROM trace_apis WHERE project_id=%s", (project,))
    apis = {r[0]: r for r in cur.fetchall()}

    req_rows = []
    layer_hit = {k: 0 for k in LAYERS}
    for rid, title, pri in reqs:
        found = reachable_layers(adj, rid)
        missing = [k for k in LAYERS if not found[k]]
        for k in LAYERS:
            if found[k]:
                layer_hit[k] += 1
        req_rows.append({
            "id": rid, "title": title, "priority": pri,
            "counts": {k: len(found[k]) for k in LAYERS},
            "missing": missing,
            "pages": [page_names.get(p, p) for p in found["page"]],
            "full": not missing,
        })

    # 接口级：契约完整度与下游连接
    api_rows = []
    for aid, (_, method, path, summary, auth, req_schema, resp_schema) in apis.items():
        schema = req_schema or {}
        if isinstance(schema, str):
            schema = json.loads(schema)
        params = schema.get("params") or []
        body = schema.get("bodyFields") or []
        has_code = any(r == "EXPOSED_BY" for r, _ in adj.get(aid, []))
        tables = [d for r, d in adj.get(aid, []) if r == "READS_WRITES"]
        resp = resp_schema or {}
        if isinstance(resp, str):
            resp = json.loads(resp)
        gaps = []
        if not has_code:
            gaps.append("无实现代码")
        if not tables:
            gaps.append("未关联数据表")
        if method in ("POST", "PUT", "PATCH") and not body:
            gaps.append("写接口无请求体字段")
        if not params and method in ("GET", "DELETE"):
            gaps.append("无查询/路径参数（可能只按路径取数）")
        if not resp.get("fields") and not resp.get("type"):
            gaps.append("无响应结构")
        api_rows.append({
            "id": aid, "method": method, "path": path, "summary": summary,
            "auth": str(auth), "paramCount": len(params), "bodyCount": len(body),
            "tableCount": len(tables), "hasCode": has_code, "gaps": gaps,
        })

    # 页面级
    page_rows = []
    for pid, name in page_names.items():
        apis_of_page = [d for r, d in adj.get(pid, []) if r == "TRIGGERS"]
        page_rows.append({"id": pid, "name": name, "apiCount": len(apis_of_page)})

    total = len(reqs) or 1
    return {
        "summary": {
            "requirementTotal": len(reqs),
            "pageTotal": len(page_names),
            "apiTotal": len(apis),
            "reqFullCoverage": sum(1 for r in req_rows if r["full"]),
            "reqFullRate": round(sum(1 for r in req_rows if r["full"]) / total, 3),
            "layerHitRate": {k: round(v / total, 3) for k, v in layer_hit.items()},
            "layerHit": layer_hit,
        },
        "requirementGaps": [r for r in req_rows if not r["full"]],
        "apiGaps": [a for a in api_rows if a["gaps"]],
        "pagesWithoutApi": [p for p in page_rows if p["apiCount"] == 0],
        "apiWithNoTable": [a for a in api_rows if not a["tableCount"]],
    }


def drift(repo: Path) -> dict:
    """文档（页面地图）与代码（扫描）的差异。"""
    wiki = repo / "docs" / "llm-wiki"
    reqs = parse_requirements(wiki / "02-requirements.md")
    pages = parse_page_map(wiki / "04-page-map.md")
    documented = {a for p in pages for a in p.apis}
    # 扫描结果从预览文件读（scanner --dry-run 产出），避免再连一次库
    preview = Path(__file__).parent / "scan_preview.json"
    scanned = set()
    if preview.exists():
        data = json.loads(preview.read_text())
        scanned = {f"{a['method']}:{a['path']}" for a in data["apis"]}
    return {
        "documentedNotInCode": sorted(documented - scanned) if scanned else [],
        "codeNotDocumented": sorted(scanned - documented) if scanned else [],
        "documented": len(documented), "scanned": len(scanned),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True)
    ap.add_argument("--dsn", default=DSN_DEFAULT)
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--json", default="")
    args = ap.parse_args()

    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        result = analyse(cur, args.project)
    result["drift"] = drift(Path(args.repo))

    s = result["summary"]
    print(f"需求 {s['requirementTotal']} 条｜页面 {s['pageTotal']} 个｜接口 {s['apiTotal']} 个")
    print(f"四层全覆盖：{s['reqFullCoverage']}/{s['requirementTotal']} = {s['reqFullRate']:.0%}")
    print("各层命中率：" + "  ".join(f"{k}={v:.0%}" for k, v in s["layerHitRate"].items()))
    print(f"\n需求缺口 {len(result['requirementGaps'])} 条：")
    for r in result["requirementGaps"]:
        print(f"  {r['id']} {r['title'][:28]} 缺 {', '.join(r['missing'])}")
    print(f"\n接口缺口 {len(result['apiGaps'])} 个（前 10）：")
    for a in result["apiGaps"][:10]:
        print(f"  {a['method']:5} {a['path']:42} {', '.join(a['gaps'])}")
    d = result["drift"]
    print(f"\n文档引用接口 {d['documented']}，扫描到 {d['scanned']}")
    if d["documentedNotInCode"]:
        print("  文档有、代码无：", d["documentedNotInCode"][:10])
    if d["codeNotDocumented"]:
        print(f"  代码有、文档无 {len(d['codeNotDocumented'])} 个（前 10）：",
              d["codeNotDocumented"][:10])
    if args.json:
        Path(args.json).write_text(json.dumps(result, ensure_ascii=False, indent=2))
        print("\n已写出", args.json)


if __name__ == "__main__":
    main()
