"""字段说明批量补全：填充 trace_tables.columns 中缺失的中文 comment.

来源优先级（agents/field_glossary.py）：
1. DDL 真实注释（shang-pivot migration 的 COMMENT ON COLUMN）
2. 知识字典（购物车/评价/运营位等源码无注释表）
3. 通用字段规则（id/created_at/…）

用法：
    cd backend && .venv/bin/python -m enrich_field_comments [--dry-run]
"""

from __future__ import annotations

import argparse
import os

import psycopg
from dotenv import load_dotenv

from agents.field_glossary import comment_for, parse_ddl_comments

load_dotenv()

DSN = os.environ.get(
    "DATABASE_URL", "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
).replace("postgresql+psycopg2://", "postgresql://").replace("postgresql+psycopg://", "postgresql://")

PROJECT = "ecommerce"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只统计，不写库")
    args = ap.parse_args()

    ddl = parse_ddl_comments()
    print(f"DDL 注释解析：{len(ddl)} 条")

    with psycopg.connect(DSN) as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT id, name, columns FROM trace_tables WHERE project_id=%s",
            (PROJECT,),
        )
        rows = cur.fetchall()

        filled = ddl_cnt = know_cnt = common_cnt = 0
        still_missing: list[str] = []
        for _tid, tname, columns in rows:
            changed = False
            for c in columns:
                if c.get("comment"):
                    continue
                hit = comment_for(tname, c.get("name", ""), ddl)
                if hit:
                    text, source = hit
                    # 标注说明来源，与平台证据分级风格一致
                    c["comment"] = text + ("〔DDL〕" if source == "DDL" else "")
                    changed = True
                    filled += 1
                    if source == "DDL":
                        ddl_cnt += 1
                    elif source == "KNOWLEDGE":
                        know_cnt += 1
                    else:
                        common_cnt += 1
                else:
                    still_missing.append(f"{tname}.{c.get('name')}")
            if changed and not args.dry_run:
                cur.execute(
                    "UPDATE trace_tables SET columns=%s::jsonb, updated_at=now() WHERE id=%s",
                    (psycopg.types.json.Jsonb(columns), _tid),
                )
        if not args.dry_run:
            conn.commit()

    print(f"\n补全 {filled} 个字段说明：DDL {ddl_cnt} / 知识字典 {know_cnt} / 通用 {common_cnt}")
    if still_missing:
        print(f"仍缺 {len(still_missing)} 个：")
        for item in still_missing:
            print(f"  {item}")
    else:
        print("所有字段说明均已覆盖 ✓")
    if args.dry_run:
        print("（dry-run 未写库）")


if __name__ == "__main__":
    main()
