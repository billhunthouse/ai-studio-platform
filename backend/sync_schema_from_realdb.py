"""按真实业务库（shang-postgres）的最终表结构，同步平台 trace_tables 的字段类型与索引。

数据源选择：直接读 information_schema.columns 和 pg_indexes，而非解析 migration SQL——
因为真实库是 DDL + 所有 ALTER 执行后的最终状态，最权威。

更新内容：
  columns[].type      精确类型（varchar(20)/smallint/numeric(12,2)/timestamptz…）
  columns[].nullable  真实可空性
  columns[].default   默认值
  indexes             真实索引（名称/定义/唯一性）
  primary_key         真实主键列（修正 Java 扫描器把 @TableId 之外的主键猜错的情况）

字段中文说明（comment）不覆盖——它由 field_glossary 补全，含 DDL/知识库证据标记。

用法：.venv/bin/python -m sync_schema_from_realdb [--dry-run]
"""
from __future__ import annotations

import argparse
import json

import psycopg

PLATFORM_DSN = "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform"
REAL_DSN = "postgresql://shang:shang@127.0.0.1:55434/shang"


def pg_type(data_type: str, max_len, precision, scale) -> str:
    """把 information_schema 的类型描述转成紧凑 PostgreSQL 写法。"""
    dt = data_type.lower()
    if dt == "character varying":
        return f"varchar({max_len})" if max_len else "varchar"
    if dt == "character":
        return f"char({max_len})" if max_len else "char"
    if dt == "timestamp with time zone":
        return "timestamptz"
    if dt == "timestamp without time zone":
        return "timestamp"
    if dt == "double precision":
        return "float8"
    if dt == "real":
        return "float4"
    if dt == "numeric":
        return f"numeric({precision},{scale})" if precision else "numeric"
    if dt == "integer":
        return "int4"
    if dt == "smallint":
        return "int2"
    if dt == "boolean":
        return "bool"
    return dt


def load_real_schema() -> dict[tuple[str, str], dict]:
    """读真实库全部业务表的列与索引。"""
    out: dict[tuple[str, str], dict] = {}
    with psycopg.connect(REAL_DSN) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT table_schema, table_name, column_name, data_type,
                   character_maximum_length, numeric_precision, numeric_scale,
                   is_nullable, column_default, ordinal_position
            FROM information_schema.columns
            WHERE table_schema IN ('identity', 'commerce')
            ORDER BY table_schema, table_name, ordinal_position
        """)
        for schema, table, name, dtype, maxlen, prec, scale, nullable, default, pos in cur.fetchall():
            key = (schema, table)
            out.setdefault(key, {"columns": [], "indexes": []})["columns"].append({
                "name": name,
                "type": pg_type(dtype, maxlen, prec, scale),
                "nullable": nullable == "YES",
                "default": (default or "").strip() or None,
                "position": pos,
            })

        # 真实主键（取 information_schema 的 key_column_usage）
        cur.execute("""
            SELECT tc.table_schema, tc.table_name, kcu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
              ON tc.constraint_name = kcu.constraint_name
             AND tc.table_schema = kcu.table_schema
            WHERE tc.constraint_type = 'PRIMARY KEY'
              AND tc.table_schema IN ('identity', 'commerce')
            ORDER BY tc.table_schema, tc.table_name, kcu.ordinal_position
        """)
        for schema, table, col in cur.fetchall():
            out.setdefault((schema, table), {"columns": [], "indexes": [], "pk": []}).setdefault("pk", []).append(col)

        # 真实索引（排除主键约束自动建的索引，单独保留业务索引）
        cur.execute("""
            SELECT schemaname, tablename, indexname, indexdef
            FROM pg_indexes
            WHERE schemaname IN ('identity', 'commerce')
            ORDER BY schemaname, tablename, indexname
        """)
        for schema, table, idx_name, idx_def in cur.fetchall():
            out.setdefault((schema, table), {"columns": [], "indexes": [], "pk": []})["indexes"].append({
                "name": idx_name,
                "definition": idx_def,
                "unique": idx_def.upper().startswith("CREATE UNIQUE INDEX"),
            })
    return out


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    real = load_real_schema()
    print(f"真实库读取 {len(real)} 张表（identity/commerce）")

    with psycopg.connect(PLATFORM_DSN) as conn:
        cur = conn.cursor()
        cur.execute("SELECT id, schema_name, name, columns, indexes, primary_key FROM trace_tables")
        rows = cur.fetchall()

        stats = {"type_changed": 0, "index_filled": 0, "pk_fixed": 0, "matched": 0, "missing": 0}
        changed_tables: list[str] = []
        for eid, schema, table, columns, old_indexes, old_pk in rows:
            key = (schema, table)
            if key not in real:
                stats["missing"] += 1
                continue
            r = real[key]
            stats["matched"] += 1

            # 按列名建立真实类型索引，更新平台 columns 数组
            real_cols = {c["name"].lower(): c for c in r["columns"]}
            new_columns = []
            table_changed = False
            for col in columns:
                rc = real_cols.get((col.get("name") or "").lower())
                if rc:
                    if col.get("type") != rc["type"]:
                        col["type"] = rc["type"]
                        stats["type_changed"] += 1
                        table_changed = True
                    # 可空性/默认值以真实库为准（Java 扫描器对 @Column(nullable=) 推断不全）
                    col["nullable"] = rc["nullable"]
                    if rc["default"]:
                        col["default"] = rc["default"]
                new_columns.append(col)

            new_pk = ",".join(r.get("pk", [])) or old_pk
            if old_pk != new_pk:
                stats["pk_fixed"] += 1
                table_changed = True

            new_indexes = r["indexes"]
            if (not old_indexes) and new_indexes:
                # pg_indexes 含主键自动索引；有非主键索引才算真正补全
                pk_names = {f"{table}_pkey"}
                business_idx = [ix for ix in new_indexes if ix["name"] not in pk_names]
                if business_idx:
                    stats["index_filled"] += 1
                    table_changed = True

            if table_changed:
                changed_tables.append(f"{schema}.{table}")
            if not args.dry_run:
                cur.execute("""
                    UPDATE trace_tables
                    SET columns = %s, indexes = %s, primary_key = %s, updated_at = now()
                    WHERE id = %s
                """, (json.dumps(new_columns, ensure_ascii=False), json.dumps(new_indexes, ensure_ascii=False), new_pk, eid))

        if not args.dry_run:
            conn.commit()

    print(f"匹配 {stats['matched']} 表 | 平台无对应真实表 {stats['missing']}")
    print(f"字段类型修正 {stats['type_changed']} 处 | 索引补全 {stats['index_filled']} 表 | 主键修正 {stats['pk_fixed']} 表")
    print(f"涉及表 {len(changed_tables)} 张：{', '.join(changed_tables[:12])}{' …' if len(changed_tables) > 12 else ''}")
    if args.dry_run:
        print("（DRY-RUN，未写库）")


if __name__ == "__main__":
    main()
