"""产品文档 AGENT · 从追溯链与真实代码逆向还原需求文档（PRD）.

用法：
    .venv/bin/python -m agents.prd_agent                    # 生成全部需求
    .venv/bin/python -m agents.prd_agent --only V1-FR-003    # 只生成一条
    .venv/bin/python -m agents.prd_agent --dry-run           # 只打印不写库

流水线见 docs/traceability/产品文档AGENT-设计说明.md。
"""

from __future__ import annotations

import argparse
import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from typing import Any

import psycopg
from dotenv import load_dotenv

from .prd_knowledge import domain_for

load_dotenv()

PROJECT = "ecommerce"
DSN = os.environ.get(
    "DATABASE_URL", "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
).replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")

LAYERS = ["page", "api", "code_artifact", "table"]
LAYER_CN = {"page": "功能页面", "api": "接口", "code_artifact": "实现代码", "table": "数据表"}


def dsn() -> str:
    return DSN


# ---------------------------------------------------------------- 证据采集


def collect_evidence(cur, req_id: str) -> dict[str, list[dict[str, Any]]]:
    """沿 trace_relations 多跳 BFS，采集需求可达的 page/api/code/table。

    关系方向：requirement-SPLITS_INTO->page-TRIGGERS->api
              api-EXPOSED_BY->code_artifact, api/code-READS_WRITES->table
    """
    # 现场 BFS（正向邻接）：从需求出发多跳遍历，保证每条需求的 PRD 都基于最新关联
    cur.execute(
        """SELECT src_id, src_type, dst_id, dst_type, rel_type FROM trace_relations
           WHERE project_id=%s AND status='confirmed'""",
        (PROJECT,),
    )
    adj: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for src_id, _src_type, dst_id, dst_type, rel in cur.fetchall():
        adj[src_id].append((dst_id, dst_type, rel))

    out = defaultdict(list)
    seen = {req_id}
    queue = [(req_id, 0)]
    while queue:
        node, hop = queue.pop(0)
        if hop >= 5:
            continue
        for dst_id, dst_type, rel in adj.get(node, []):
            if dst_id in seen:
                continue
            seen.add(dst_id)
            out[dst_type].append({"id": dst_id, "hop": hop + 1, "rel_type": rel})
            queue.append((dst_id, hop + 1))
    return out


def hydrate(cur, evid: dict[str, list[dict[str, Any]]]) -> None:
    """把实体 id 补成带名称/契约/字段的完整对象。"""
    # pages
    for item in evid.get("page", []):
        cur.execute("SELECT name, description, feature_domain FROM trace_pages WHERE id=%s", (item["id"],))
        r = cur.fetchone()
        item.update(name=r[0] if r else item["id"], description=r[1] if r else "", domain=r[2] if r else "")

    # apis：带完整契约
    for item in evid.get("api", []):
        cur.execute(
            """SELECT method, path, summary, service, request_schema, response_schema,
                      auth_requirement, spec_ref, source FROM trace_apis WHERE id=%s""",
            (item["id"],),
        )
        r = cur.fetchone()
        if r:
            req_schema = r[4] or {}
            item.update(
                name=r[2] or f"{r[0]} {r[1]}", method=r[0], path=r[1], service=r[3],
                params=req_schema.get("params", []), body_fields=req_schema.get("bodyFields", []),
                response=r[5] or {}, auth=r[6] or "", spec_ref=r[7] or "", source=r[8] or "",
            )
        else:
            item.update(name=item["id"], method="", path="", params=[], body_fields=[], response={}, auth="")

    # code artifacts
    for item in evid.get("code_artifact", []):
        cur.execute(
            "SELECT entry_point, file_path, commit_sha, service FROM trace_code_artifacts WHERE id=%s",
            (item["id"],),
        )
        r = cur.fetchone()
        item.update(
            name=r[0] if r else item["id"], file_path=r[1] if r else "",
            commit=r[2] if r else "", service=r[3] if r else "",
        )

    # tables：带字段
    for item in evid.get("table", []):
        cur.execute(
            """SELECT name, database_name, schema_name, columns, primary_key, source FROM trace_tables
               WHERE id=%s""",
            (item["id"],),
        )
        r = cur.fetchone()
        if r:
            cols = r[3] or []
            item.update(
                name=r[0], database=r[1], schema=r[2], columns=cols,
                pk=r[4], source=r[5] or "", column_count=len(cols),
            )
        else:
            item.update(name=item["id"], columns=[], column_count=0)

    for key in evid:
        evid[key].sort(key=lambda x: x.get("hop", 9))


# ---------------------------------------------------------------- PRD 组装


def build_prd(req_id: str, req: dict[str, Any], evid: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    title = req["title"]
    dom_key, dom = domain_for(req_id, title)
    points = req.get("points") or []
    pages = evid.get("page", [])
    apis = evid.get("api", [])
    codes = evid.get("code_artifact", [])
    tables = evid.get("table", [])

    covered = [L for L in LAYERS if evid.get(L)]
    missing = [L for L in LAYERS if not evid.get(L)]
    coverage = len(covered)

    # 章节 1 概述
    overview = {
        "id": req_id,
        "title": title,
        "module": dom_key,
        "priority": req.get("priority", ""),
        "status": req.get("status", ""),
        "owner": req.get("owner", "未指派"),
        "version": req.get("version", "v1"),
        "background": dom["background"],
        "goal": dom["goal"],
        "sourceDoc": "docs/llm-wiki/02-requirements.md",
        "description": req.get("description", ""),
    }

    # 章节 2 用户故事
    roles = dom.get("roles", ["系统用户"])
    stories = [
        {
            "role": roles[i % len(roles)],
            "want": point,
            "benefit": dom["goal"],
            "as_json": f"作为{roles[i % len(roles)]}，我希望{point}，以便{dom['goal']}",
        }
        for i, point in enumerate(points)
    ] or [
        {"role": roles[0], "want": title.strip("【】"), "benefit": dom["goal"],
         "as_json": f"作为{roles[0]}，我希望{title}，以便{dom['goal']}"}
    ]

    # 章节 3 功能规格：每个功能点配入口页面与涉及接口
    api_names = [a["name"] for a in apis]
    features = []
    for i, point in enumerate(points):
        features.append({
            "id": f"FR-{i + 1:02d}",
            "name": point,
            "behavior": f"{point}——{dom['goal']}",
            "entry": [p["name"] for p in pages] or "无独立页面（交互规范/后台任务）",
            "apis": api_names[:8],
            "precondition": "用户已登录且具备相应角色" if roles[0] != "顾客/会员" else "用户已登录（部分浏览无需登录）",
        })

    # 章节 4 业务规则
    rules = [{"text": text, "evidence": ev} for text, ev in dom.get("rules", [])]

    # 章节 5 接口清单
    api_list = [
        {
            "id": a["id"], "method": a.get("method", ""), "path": a.get("path", ""),
            "summary": a.get("name", ""), "auth": a.get("auth", ""),
            "service": a.get("service", ""), "source": a.get("source", ""),
            "specRef": a.get("spec_ref", ""),
            "params": a.get("params", []), "bodyFields": a.get("body_fields", []),
            "response": a.get("response", {}),
        }
        for a in apis
    ]

    # 章节 6 数据模型
    tables_list = [
        {
            "id": t["id"], "name": t.get("name", ""), "database": t.get("database", ""),
            "schema": t.get("schema", ""), "primaryKey": t.get("pk"),
            "columnCount": t.get("column_count", 0), "source": t.get("source", ""),
            "columns": [
                {"name": c.get("name", ""), "type": c.get("type", ""),
                 "nullable": c.get("nullable", True), "comment": c.get("comment", "")}
                for c in t.get("columns", [])
            ],
        }
        for t in tables
    ]

    # 章节 7 异常与边界
    exceptions = [
        {"id": nid, "scenario": text, "evidence": "06-business-rules.md §7"}
        for nid, text in dom.get("neg", [])
    ]

    # 章节 8 验收标准
    ac = [{"id": f"AC-{i + 1:02d}", "text": text, "checked": False}
          for i, text in enumerate(dom.get("ac", []))]

    # 章节 9 覆盖与缺口：layerEntities 供前端点击跳转到追溯实体详情页
    def _entity_label(item: dict[str, Any], layer: str) -> dict[str, str]:
        name = item.get("name") or item.get("path") or item.get("id")
        if layer == "api" and item.get("method"):
            name = f"{item['method']} {item.get('path')}"
        return {"id": item["id"], "name": str(name)}

    layer_entities = {
        L: [_entity_label(it, L) for it in evid.get(L, [])[:12]] for L in LAYERS
    }
    coverage_sec = {
        "coveredLayers": covered, "missingLayers": missing,
        "coverageCount": coverage, "total": len(LAYERS),
        "layerEntities": layer_entities,
        "note": dom.get("no_link_reason", "") or
                ("四层链路完整，需求→页面→接口→代码/表均有可达实体"
                 if not missing else f"缺少 {('/'.join(LAYER_CN[m] for m in missing))} 链路"),
    }

    # 章节 10 代码证据
    code_evidence = [
        {"id": c.get("id", ""), "entryPoint": c.get("name", ""), "filePath": c.get("file_path", ""),
         "commit": c.get("commit", ""), "service": c.get("service", "")}
        for c in codes
    ]

    return {
        "schemaVersion": "1.0",
        "generatedBy": "product-doc-agent",
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "sections": {
            "overview": overview,
            "userStories": stories,
            "features": features,
            "businessRules": rules,
            "apis": api_list,
            "dataModel": tables_list,
            "exceptions": exceptions,
            "acceptance": ac,
            "coverage": coverage_sec,
            "codeEvidence": code_evidence,
            "flows": dom.get("flows", []),
        },
        "counts": {
            "pages": len(pages), "apis": len(apis), "code": len(codes),
            "tables": len(tables), "columns": sum(t.get("column_count", 0) for t in tables),
        },
    }


# ---------------------------------------------------------------- 主流程


def load_requirements(cur, only: str | None) -> list[dict[str, Any]]:
    if only:
        cur.execute(
            """SELECT id, title, priority, status, owner_name, version, description, points
               FROM requirements WHERE project_id=%s AND id=%s""",
            (PROJECT, only),
        )
    else:
        cur.execute(
            """SELECT id, title, priority, status, owner_name, version, description, points
               FROM requirements WHERE project_id=%s ORDER BY id""",
            (PROJECT,),
        )
    out = []
    for r in cur.fetchall():
        pts = r[7]
        if isinstance(pts, str):
            try:
                pts = json.loads(pts)
            except Exception:
                pts = []
        out.append({
            "id": r[0], "title": r[1], "priority": r[2], "status": r[3],
            "owner": r[4] or "", "version": r[5] or "v1",
            "description": r[6] or "", "points": pts or [],
        })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", help="只生成指定需求 ID")
    ap.add_argument("--dry-run", action="store_true", help="只打印，不写库")
    args = ap.parse_args()

    with psycopg.connect(dsn()) as conn:
        cur = conn.cursor()
        reqs = load_requirements(cur, args.only)
        print(f"待还原需求：{len(reqs)} 条")
        ok_count = 0
        for req in reqs:
            evid = collect_evidence(cur, req["id"])
            hydrate(cur, evid)
            prd = build_prd(req["id"], req, evid)
            cov = prd["counts"]
            dom_key, _ = domain_for(req["id"], req["title"])
            if args.dry_run:
                print(f"\n=== {req['id']} [{dom_key}] ===")
                print(json.dumps(prd, ensure_ascii=False, indent=2)[:1500])
                continue
            cur.execute(
                """INSERT INTO requirement_prd (requirement_id, project_id, doc, domain, coverage, updated_at)
                   VALUES (%s,%s,%s::jsonb,%s,%s,now())
                   ON CONFLICT (requirement_id) DO UPDATE
                     SET doc=EXCLUDED.doc, domain=EXCLUDED.domain,
                         coverage=EXCLUDED.coverage, updated_at=now()""",
                (req["id"], PROJECT, json.dumps(prd, ensure_ascii=False), dom_key,
                 prd["sections"]["coverage"]["coverageCount"]),
            )
            ok_count += 1
            print(f"  {req['id']:<22} {dom_key:<10} "
                  f"页面{cov['pages']} 接口{cov['apis']} 代码{cov['code']} 表{cov['tables']}")
        if not args.dry_run:
            conn.commit()
            print(f"\n完成：写入 {ok_count} 条 PRD")


if __name__ == "__main__":
    main()
