"""给"孤儿接口"补页面归属：代码里有、页面地图没列的辅助接口。

背景：04-page-map.md 只记录了各页面的**主要**调用，像 /admin/auth/me、/admin/files/view、
/api/files/presign 这类辅助端点没有落点，导致它们的用例无法归属需求（覆盖矩阵里 70 条用例
无法接线）。

做法：按路径段相似度找最像的**已挂载接口**，继承它的页面。这类推断不是事实，
所以写 source=AI_INFER、confidence=80、status=proposed，在界面上可被人工确认或否决。

用法：
  .venv/bin/python link_orphan_apis.py --dry-run
  .venv/bin/python link_orphan_apis.py --write
"""
from __future__ import annotations

import argparse
from collections import defaultdict
from pathlib import Path

import psycopg

DSN_DEFAULT = "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
PROJECT = "ecommerce"
MIN_SCORE = 0.5          # 低于这个相似度不猜，宁可留空

# 路径里不携带语义的段
STOP = {"api", "admin", "v1"}

# 路径相似度在跨端（C 端 /api vs 管理端 /admin）时毫无意义——/admin/auth/me 与 /api/me
# 段几乎相同，但一个是管理员会话、一个是会员资料。这些用人工映射兜底，宁可写死也不猜。
MANUAL: dict[str, list[str]] = {
    "api:GET:/admin/auth/me": ["page:admin:/login"],
    "api:POST:/admin/auth/refresh": ["page:admin:/login"],
    "api:POST:/admin/auth/logout": ["page:admin:/login"],
    "api:POST:/api/auth/refresh": ["page:mall:/login"],
    "api:POST:/api/auth/phone": ["page:mall:/login"],
    "api:GET:/api/site/brand": ["page:mall:/"],
    "api:GET:/api/cart": ["page:mall:/cart"],
    "api:GET:/api/payment/{orderId}/status": ["page:mall:/pay/:orderId"],
    "api:GET:/api/products/{spuId}/reviews": ["page:mall:/product/:spuId"],
    "api:GET:/api/files/view": ["page:mall:/orders/:id"],
    "api:POST:/api/files/presign": ["page:mall:/after-sales/apply"],
    "api:POST:/api/files/confirm": ["page:mall:/after-sales/apply"],
    "api:GET:/admin/files/view": ["page:admin:/products/edit"],
    "api:POST:/admin/files/presign": ["page:admin:/products/edit"],
    "api:POST:/admin/files/confirm": ["page:admin:/products/edit"],
    "api:GET:/admin/warehouses": ["page:admin:/inventory"],
    "api:POST:/admin/warehouses": ["page:admin:/inventory"],
    "api:PUT:/admin/warehouses/{id}": ["page:admin:/inventory"],
}


def segments(path: str) -> set[str]:
    out = set()
    for s in path.strip("/").split("/"):
        if not s or s.startswith("{") or s in STOP:
            continue
        out.add(s)
    return out


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    return len(a & b) / len(a | b)


def side(path: str) -> str:
    return "admin" if path.startswith("/admin") else "mall"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dsn", default=DSN_DEFAULT)
    ap.add_argument("--project", default=PROJECT)
    ap.add_argument("--write", action="store_true")
    args = ap.parse_args()

    with psycopg.connect(args.dsn) as conn, conn.cursor() as cur:
        cur.execute("""SELECT id, method, path FROM trace_apis WHERE project_id=%s""",
                    (args.project,))
        apis = cur.fetchall()

        cur.execute("""SELECT dst_id, src_id FROM trace_relations
                       WHERE project_id=%s AND rel_type='TRIGGERS' AND status<>'stale'""",
                    (args.project,))
        api_pages: dict[str, list[str]] = defaultdict(list)
        for api_id, page_id in cur.fetchall():
            api_pages[api_id].append(page_id)

        orphans = [(aid, m, p) for aid, m, p in apis if aid not in api_pages]
        mounted = [(aid, p) for aid, _m, p in apis if aid in api_pages]
        print(f"孤儿接口 {len(orphans)} 个 / 已挂载 {len(mounted)} 个\n")

        plan = []
        for aid, method, path in orphans:
            if aid in MANUAL:
                plan.append((aid, method, path, "人工映射", 1.0, MANUAL[aid], "HUMAN"))
                print(f"  {method:6} {path:34} → 人工映射 页面 {','.join(MANUAL[aid])}")
                continue
            segs = segments(path)
            best, best_score = None, 0.0
            for other_id, other_path in mounted:
                if side(path) != side(other_path):
                    continue          # 跨端不做相似度推断
                score = jaccard(segs, segments(other_path))
                if score > best_score:
                    best, best_score = other_id, score
            if best and best_score >= MIN_SCORE:
                pages = api_pages[best]
                plan.append((aid, method, path, best, round(best_score, 2), pages, "AI_INFER"))
                print(f"  {method:6} {path:34} → 参照 {best:44} 相似度 {best_score:.2f} "
                      f"页面 {','.join(pages)}")
            else:
                print(f"  {method:6} {path:34} → 无足够相似接口（{best_score:.2f}），跳过")

        if not args.write:
            print(f"\n空跑：可补 {len(plan)} 条，未写库")
            return

        rows = 0
        for _aid, _m, _p, ref, score, pages, src in plan:
            for page_id in pages:
                cur.execute(
                    """INSERT INTO trace_relations
                         (project_id, src_type, src_id, rel_type, dst_type, dst_id,
                          source, confidence, status, note)
                       VALUES (%s,'page',%s,'TRIGGERS','api',%s,%s,%s,%s,%s)
                       ON CONFLICT DO NOTHING""",
                    (args.project, page_id, _aid, src, int(score * 100),
                     "confirmed" if src == "HUMAN" else "proposed",
                     "页面地图未列此端点，按语义人工指定"
                     if src == "HUMAN" else
                     f"页面地图未列此端点，按路径相似度({ref})推断，待人工确认"))
                rows += cur.rowcount
        conn.commit()
        print(f"\n写库 {rows} 条")


if __name__ == "__main__":
    main()
