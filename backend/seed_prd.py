"""从 llm-wiki 的需求目录与页面地图重建追溯实体与关联。

数据源（只读，全部来自真实仓库文档）：
  docs/llm-wiki/02-requirements.md   需求 53 条（V1/V2/EXT）
  docs/llm-wiki/04-page-map.md       页面 ↔ 接口 映射（C 端 20 + 管理端 22）

产出的关联：
  需求 --SPLITS_INTO--> 功能页面       （来源 SPEC，置信度 95）
  功能页面 --TRIGGERS--> 接口           （来源 SPEC，置信度 95）

为什么要这一步：v0.5 的种子脚本里 4 条需求 / 8 个页面是按演示需要编的
（"优惠券管理""会员中心 /member"在真实系统里并不存在），
导致"功能点是否被覆盖"这个问题根本无法回答。改成从 PRD 文档解析后可追溯、可重跑。

用法：
  .venv/bin/python seed_prd.py --repo /path/to/shang-pivot-master --dry-run   # 只看差异
  .venv/bin/python seed_prd.py --repo /path/to/shang-pivot-master            # 写库
"""
from __future__ import annotations

import argparse
import re
from dataclasses import dataclass, field
from pathlib import Path

import psycopg

DSN_DEFAULT = "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
PROJECT = "ecommerce"


@dataclass
class ReqFact:
    id: str
    module: str
    title: str
    priority: str
    pages: list[str] = field(default_factory=list)
    api_count: int = 0
    points: list[str] = field(default_factory=list)


@dataclass
class PageFact:
    app: str          # mall | admin
    route: str
    name: str
    view: str
    apis: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        # 需求目录（02-requirements.md）用 page:admin:/users 的形式书写，
        # 而页面地图的路由带部署前缀 /admin/users —— 统一去掉前缀，保证两处引用同一 ID。
        if self.route == "(global)":
            return "page:mall:ai-assistant"
        route = self.route
        if self.app == "admin" and route.startswith("/admin"):
            route = route[len("/admin"):] or "/"
        return f"page:{self.app}:{route}"


# ----------------------------------------------------------------- 解析
def parse_requirements(path: Path) -> list[ReqFact]:
    """解析需求目录表格。功能描述按顿号拆成功能点——这就是"功能点"的定义粒度。"""
    rows: list[ReqFact] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) < 6 or not re.match(r"^(V1|V2|EXT)-", cells[0]):
            continue
        rid, module, func, pri, pages_cell, api_n = cells[:6]
        pages = [p.strip() for p in pages_cell.split(",") if p.strip().startswith("page:")]
        points = [p.strip() for p in re.split(r"[、,，]", func) if p.strip()]
        rows.append(ReqFact(
            id=rid, module=module, title=func,
            priority=pri.split("/")[0].strip(),   # "P0/P1" 取主优先级
            pages=pages,
            api_count=int(api_n) if api_n.isdigit() else 0,
            points=points,
        ))
    return rows


def parse_page_map(path: Path) -> list[PageFact]:
    """解析页面 ↔ API 映射。按 `## ` 小节判断是 C 端还是管理端。"""
    app = "mall"
    pages: list[PageFact] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if stripped.startswith("## "):
            app = "admin" if "管理端" in stripped else "mall"
            continue
        if not stripped.startswith("|"):
            continue
        cells = [c.strip() for c in stripped.strip("|").split("|")]
        if len(cells) < 4:
            continue
        route_cell = cells[0].strip("` ")
        if not route_cell.startswith("/") and route_cell != "(global)":
            continue
        view = cells[2].strip("` ")
        apis = re.findall(r"`(GET|POST|PUT|DELETE|PATCH)\s+([^`]+)`", cells[3])
        pages.append(PageFact(
            app=("global" if route_cell == "(global)" else app),
            route=route_cell,
            name=cells[1],
            view=view,
            apis=[f"{m}:{p.strip()}" for m, p in apis],
        ))
    return pages


# ----------------------------------------------------------------- 写库
def clear_old(cur, project: str) -> dict[str, int]:
    """清掉 v0.5 编造的演示数据（真实仓库里不存在这些页面/需求）。"""
    stats = {}
    cur.execute("SELECT id FROM requirements WHERE project_id=%s", (project,))
    req_ids = [r[0] for r in cur.fetchall()]
    cur.execute("SELECT id FROM trace_pages WHERE project_id=%s", (project,))
    page_ids = [r[0] for r in cur.fetchall()]
    all_ids = req_ids + page_ids
    if all_ids:
        cur.execute(
            """DELETE FROM trace_relations WHERE project_id=%s
               AND (src_id = ANY(%s) OR dst_id = ANY(%s))""", (project, all_ids, all_ids))
        stats["relations"] = cur.rowcount
    cur.execute("DELETE FROM requirements WHERE project_id=%s", (project,))
    stats["requirements"] = cur.rowcount
    cur.execute("DELETE FROM trace_pages WHERE project_id=%s", (project,))
    stats["pages"] = cur.rowcount
    return stats


def write(cur, project: str, reqs: list[ReqFact], pages: list[PageFact]) -> dict[str, int]:
    n_req = n_page = 0
    for r in reqs:
        cur.execute(
            """INSERT INTO requirements
                 (id, project_id, kind, title, priority, status, owner_name, version,
                  description, points, generations, split_status)
               VALUES (%s,%s,'main',%s,%s,'已解析','未指派','v1',%s,%s::jsonb,'[]'::jsonb,'未拆分')
               ON CONFLICT (id) DO UPDATE
                 SET title=EXCLUDED.title, priority=EXCLUDED.priority,
                     description=EXCLUDED.description, points=EXCLUDED.points,
                     updated_at=now()""",
            (r.id, project, f"【{r.module}】{r.title}", r.priority,
             f"来源 docs/llm-wiki/02-requirements.md｜模块 {r.module}｜"
             f"页面 {', '.join(r.pages) or '无'}｜{r.api_count} 个接口",
             __import__("json").dumps(r.points, ensure_ascii=False)))
        n_req += cur.rowcount

    for p in pages:
        cur.execute(
            """INSERT INTO trace_pages
                 (id, project_id, name, feature_domain, prd_section, prototype_ref,
                  business_owner, status, description)
               VALUES (%s,%s,%s,%s,%s,%s,'未指派','active',%s)
               ON CONFLICT (id) DO UPDATE
                 SET name=EXCLUDED.name, feature_domain=EXCLUDED.feature_domain,
                     prototype_ref=EXCLUDED.prototype_ref, description=EXCLUDED.description,
                     updated_at=now()""",
            (p.id, project, p.name, _domain_of(p), p.route, p.view,
             f"路由 {p.route}｜视图 {p.view}｜调用 {len(p.apis)} 个接口"))
        n_page += cur.rowcount

    # 需求 → 页面
    n_rel = 0
    for r in reqs:
        for pid in r.pages:
            cur.execute(
                """INSERT INTO trace_relations
                     (project_id, src_type, src_id, rel_type, dst_type, dst_id,
                      source, confidence, status, note)
                   VALUES (%s,'requirement',%s,'SPLITS_INTO','page',%s,'SPEC',95,'confirmed',%s)
                   ON CONFLICT DO NOTHING""",
                (project, r.id, pid, "来源: 02-requirements.md 的页面列"))
            n_rel += cur.rowcount

    # 页面 → 接口
    for p in pages:
        for api in p.apis:
            api_id = "api:" + api
            cur.execute(
                """INSERT INTO trace_relations
                     (project_id, src_type, src_id, rel_type, dst_type, dst_id,
                      source, confidence, status, note)
                   VALUES (%s,'page',%s,'TRIGGERS','api',%s,'SPEC',95,'confirmed',%s)
                   ON CONFLICT DO NOTHING""",
                (project, p.id, api_id, "来源: 04-page-map.md 的调用接口列"))
            n_rel += cur.rowcount
    return {"requirements": n_req, "pages": n_page, "relations": n_rel}


def _domain_of(p: PageFact) -> str:
    if p.app == "admin":
        return "管理端"
    if p.app == "global":
        return "全局"
    return "商城C端"


def audit(cur, project: str, reqs: list[ReqFact], pages: list[PageFact]) -> dict:
    """核对功能点覆盖：页面是否存在、接口是否被扫描到。"""
    cur.execute("SELECT id FROM trace_pages WHERE project_id=%s", (project,))
    page_ids = {r[0] for r in cur.fetchall()}
    cur.execute("SELECT id FROM trace_apis WHERE project_id=%s", (project,))
    api_ids = {r[0] for r in cur.fetchall()}

    missing_pages = sorted({pid for r in reqs for pid in r.pages if pid not in page_ids})
    wanted_apis = {a for p in pages for a in p.apis}
    missing_apis = sorted(a for a in wanted_apis if ("api:" + a) not in api_ids)
    no_page_req = [r.id for r in reqs if not r.pages]
    no_api_page = [p.id for p in pages if not p.apis]
    return {
        "req_total": len(reqs), "page_total": len(pages),
        "api_referenced": len(wanted_apis), "api_in_db": len(api_ids),
        "missing_pages": missing_pages, "missing_apis": missing_apis,
        "req_without_page": no_page_req, "page_without_api": no_api_page,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="shang-pivot-master 根目录")
    ap.add_argument("--dsn", default=DSN_DEFAULT)
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    wiki = Path(args.repo) / "docs" / "llm-wiki"
    reqs = parse_requirements(wiki / "02-requirements.md")
    pages = parse_page_map(wiki / "04-page-map.md")
    print(f"解析：需求 {len(reqs)} 条 / 页面 {len(pages)} 个 / "
          f"功能点 {sum(len(r.points) for r in reqs)} 个")

    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        before = audit(cur, args.project, reqs, pages)
        print("改造前核对：", {k: (v if not isinstance(v, list) else len(v))
                          for k, v in before.items()})
        if before["missing_pages"]:
            print("  需求引用了但库里没有的页面：", before["missing_pages"])
        if before["missing_apis"]:
            print(f"  页面调用了但未被扫描的接口（{len(before['missing_apis'])} 个）：",
                  before["missing_apis"][:12])

        if args.dry_run:
            print("空跑结束，未写库")
            return

        cleared = clear_old(cur, args.project)
        print("清理旧数据：", cleared)
        stats = write(cur, args.project, reqs, pages)
        conn.commit()
        print("写库：", stats)
        after = audit(cur, args.project, reqs, pages)
        print("改造后核对：", {k: (v if not isinstance(v, list) else len(v))
                          for k, v in after.items()})
        if after["missing_apis"]:
            print(f"  仍未被扫描的接口 {len(after['missing_apis'])} 个（需补扫描规则）")
        if after["req_without_page"]:
            print("  无页面落点的需求：", after["req_without_page"])


if __name__ == "__main__":
    main()
