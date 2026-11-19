"""追溯平台数据库迁移（幂等，可重复执行）。

用法: .venv/bin/python migrate_traceability.py
执行前请确认 DATABASE_URL 指向目标库。
"""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv
from sqlalchemy import create_engine, text

load_dotenv(".env")
URL = os.environ["DATABASE_URL"]

# 1) 类型定义：用 DO 块保证幂等
TYPES_SQL = """
DO $$ BEGIN
  CREATE TYPE entity_type_enum AS ENUM (
    'requirement','page','api','code_artifact','table'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE relation_type_enum AS ENUM (
    'SPLITS_INTO','TRIGGERS','EXPOSED_BY','READS_WRITES','CROSS_DB_READ','DERIVED_FROM'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE relation_source_enum AS ENUM (
    'SPEC','CODE_SCAN','DOC_PARSE','HUMAN','AI_INFER'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;

DO $$ BEGIN
  CREATE TYPE relation_status_enum AS ENUM (
    'proposed','confirmed','stale','rejected'
  );
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
"""

# 2) pg_trgm 扩展（gin_trgm_ops 索引依赖）
EXT_SQL = "CREATE EXTENSION IF NOT EXISTS pg_trgm;"

# 3) 读取 DDL 文件里的建表/索引/视图部分（跳过 CREATE TYPE 段，已用幂等版本创建）
def load_ddl_body() -> str:
    p = Path(__file__).parent.parent / "docs" / "traceability" / "001-schema.sql"
    sql = p.read_text(encoding="utf-8")
    # 去掉开头的 4 个 CREATE TYPE ... ; 块（到第一个 CREATE TABLE 之前）
    idx = sql.find("CREATE TABLE trace_pages")
    if idx < 0:
        raise RuntimeError("DDL 文件结构异常：找不到 CREATE TABLE trace_pages")
    body = sql[idx:]
    # 去掉可能残留的 trigram 索引（下面用幂等方式单独建）
    lines = [ln for ln in body.splitlines() if "idx_trace_apis_path" not in ln]
    return "\n".join(lines)


IDX_TRIGRAM = "CREATE INDEX IF NOT EXISTS idx_trace_apis_path ON trace_apis USING gin (path gin_trgm_ops);"


def main() -> None:
    engine = create_engine(URL, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        print("[1/5] 创建枚举类型（幂等）")
        conn.execute(text(TYPES_SQL))
        print("[2/5] 创建 pg_trgm 扩展")
        conn.execute(text(EXT_SQL))
        print("[3/5] 建表 / 索引 / 视图")
        ddl = load_ddl_body()
        # 逐条执行，跳过空语句
        for stmt in [s.strip() for s in ddl.split(";") if s.strip()]:
            # 跳过纯注释块
            if all(line.strip().startswith("--") or not line.strip() for line in stmt.splitlines()):
                continue
            try:
                conn.execute(text(stmt))
            except Exception as exc:  # 幂等：已存在则跳过
                msg = str(exc)
                if any(k in msg for k in ("already exists", "duplicate key", "duplicate_object")):
                    continue
                raise
        print("[4/5] 创建 trigram 索引")
        conn.execute(text(IDX_TRIGRAM))
        print("[5/5] 验证结果")
        tables = conn.execute(text(
            "select tablename from pg_tables where schemaname='public' "
            "and tablename like 'trace_%' order by 1"
        )).scalars().all()
        cols = conn.execute(text(
            "select column_name from information_schema.columns "
            "where table_name='requirements' and column_name in ('planned_release','released_in')"
        )).scalars().all()
        print("  trace 表:", ", ".join(tables))
        print("  requirements 新列:", ", ".join(cols))
    print("迁移完成。")


if __name__ == "__main__":
    main()
