"""迁移：产品文档 AGENT 的 PRD 存储表。

幂等，可重复执行。独立于 trace 迁移，因为 PRD 是文档产物，不是追溯表。
"""

from __future__ import annotations

import os

import psycopg
from dotenv import load_dotenv

load_dotenv()

DDL = """
CREATE TABLE IF NOT EXISTS requirement_prd (
  requirement_id VARCHAR(40) PRIMARY KEY REFERENCES requirements(id) ON DELETE CASCADE,
  project_id VARCHAR(40) NOT NULL,
  doc JSONB NOT NULL,
  domain VARCHAR(60),
  coverage INTEGER DEFAULT 0,
  generated_at TIMESTAMPTZ DEFAULT now(),
  updated_at TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_prd_project ON requirement_prd(project_id);
"""


def dsn() -> str:
    raw = os.environ.get("DATABASE_URL", "postgresql://ai:ai_local_password@127.0.0.1:55432/ai_test_platform")
    return raw.replace("postgresql+psycopg2://", "postgresql://")


def main() -> None:
    with psycopg.connect(dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.commit()
    print("requirement_prd 迁移完成（幂等）")


if __name__ == "__main__":
    main()
