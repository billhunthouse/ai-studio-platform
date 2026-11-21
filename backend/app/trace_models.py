"""追溯平台 ORM 模型（v2.1）。

对应 docs/traceability/001-schema.sql。复用现有 users/projects/requirements。
"""
from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import JSON, Enum as SAEnum, ForeignKey, Index, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from .db import Base


def _now():
    return datetime.now(UTC).replace(tzinfo=None)


class TracePage(Base):
    __tablename__ = "trace_pages"

    id: Mapped[str] = mapped_column(String(120), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    feature_domain: Mapped[str] = mapped_column(String(100))
    prd_section: Mapped[str | None] = mapped_column(String(200))
    prototype_ref: Mapped[str | None] = mapped_column(String(500))
    business_owner: Mapped[str | None] = mapped_column(String(80))
    status: Mapped[str] = mapped_column(String(20), default="active")
    description: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("project_id", "name", "feature_domain", name="uq_trace_page"),)


class TraceApi(Base):
    __tablename__ = "trace_apis"

    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    method: Mapped[str] = mapped_column(String(10))
    path: Mapped[str] = mapped_column(String(200))
    summary: Mapped[str] = mapped_column(String(300), default="")
    service: Mapped[str] = mapped_column(String(100), index=True)
    request_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    response_schema: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    auth_requirement: Mapped[str] = mapped_column(String(50), default="public")
    internal_calls: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(20), default="active")
    source: Mapped[str] = mapped_column(
        SAEnum("SPEC", "CODE_SCAN", "DOC_PARSE", "HUMAN", "AI_INFER",
               name="relation_source_enum", create_type=False), default="SPEC")
    spec_ref: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (UniqueConstraint("project_id", "method", "path", name="uq_trace_api"),)


class TraceCodeArtifact(Base):
    __tablename__ = "trace_code_artifacts"

    id: Mapped[str] = mapped_column(String(300), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    repo: Mapped[str] = mapped_column(String(150))
    service: Mapped[str] = mapped_column(String(100))
    api_id: Mapped[str | None] = mapped_column(String(240), ForeignKey("trace_apis.id", ondelete="SET NULL"), index=True)
    file_path: Mapped[str] = mapped_column(String(500))
    entry_point: Mapped[str | None] = mapped_column(String(200))
    commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="active")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TraceTable(Base):
    __tablename__ = "trace_tables"

    id: Mapped[str] = mapped_column(String(240), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    database_name: Mapped[str] = mapped_column(String(100), index=True)
    service: Mapped[str] = mapped_column(String(100), index=True)
    schema_name: Mapped[str] = mapped_column(String(100), default="public")
    name: Mapped[str] = mapped_column(String(150))
    columns: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    indexes: Mapped[list[Any]] = mapped_column(JSONB, default=list)
    primary_key: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active")
    source: Mapped[str] = mapped_column(
        SAEnum("SPEC", "CODE_SCAN", "DOC_PARSE", "HUMAN", "AI_INFER",
               name="relation_source_enum", create_type=False), default="SPEC")
    ddl_ref: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint("project_id", "database_name", "schema_name", "name", name="uq_trace_table"),
    )


class TraceRelation(Base):
    __tablename__ = "trace_relations"

    id = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"))

    src_type: Mapped[str] = mapped_column(
        SAEnum("requirement", "page", "api", "code_artifact", "table",
               name="entity_type_enum", create_type=False))
    src_id: Mapped[str] = mapped_column(String(300))
    rel_type: Mapped[str] = mapped_column(
        SAEnum("SPLITS_INTO", "TRIGGERS", "EXPOSED_BY", "READS_WRITES",
               "CROSS_DB_READ", "DERIVED_FROM",
               name="relation_type_enum", create_type=False))
    dst_type: Mapped[str] = mapped_column(
        SAEnum("requirement", "page", "api", "code_artifact", "table",
               name="entity_type_enum", create_type=False))
    dst_id: Mapped[str] = mapped_column(String(300))

    source: Mapped[str] = mapped_column(
        SAEnum("SPEC", "CODE_SCAN", "DOC_PARSE", "HUMAN", "AI_INFER",
               name="relation_source_enum", create_type=False), default="HUMAN")
    confidence: Mapped[int] = mapped_column(default=100)
    status: Mapped[str] = mapped_column(
        SAEnum("proposed", "confirmed", "stale", "rejected",
               name="relation_status_enum", create_type=False), default="proposed")

    valid_from_release: Mapped[str | None] = mapped_column(String(20))
    valid_to_release: Mapped[str | None] = mapped_column(String(20))

    first_seen_scan = mapped_column(UUID(as_uuid=False), nullable=True)
    last_seen_scan = mapped_column(UUID(as_uuid=False), nullable=True)
    last_seen_commit: Mapped[str | None] = mapped_column(String(40))
    confirmed_by: Mapped[str | None] = mapped_column(String(40), ForeignKey("users.id", ondelete="SET NULL"))
    confirmed_at: Mapped[datetime | None] = mapped_column()
    note: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        UniqueConstraint(
            "project_id", "src_type", "src_id", "rel_type", "dst_type", "dst_id",
            name="uq_trace_relation",
        ),
        Index("idx_rel_src", "project_id", "src_type", "src_id", "status"),
        Index("idx_rel_dst", "project_id", "dst_type", "dst_id", "status"),
    )


class TraceRelease(Base):
    __tablename__ = "trace_releases"

    id: Mapped[str] = mapped_column(String(40), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    version: Mapped[str] = mapped_column(String(20))
    name: Mapped[str | None] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text, default="")
    changelog: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    released_at: Mapped[datetime | None] = mapped_column()
    created_by: Mapped[str | None] = mapped_column(String(40), ForeignKey("users.id", ondelete="SET NULL"))
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())

    __table_args__ = (UniqueConstraint("project_id", "version", name="uq_trace_release"),)


class TraceScanRun(Base):
    __tablename__ = "trace_scan_runs"

    id = mapped_column(UUID(as_uuid=False), primary_key=True, server_default=func.gen_random_uuid())
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    adapter: Mapped[str] = mapped_column(String(40))
    repo: Mapped[str | None] = mapped_column(String(150))
    commit_sha: Mapped[str | None] = mapped_column(String(40), index=True)
    trigger: Mapped[str] = mapped_column(String(10), default="manual")
    status: Mapped[str] = mapped_column(String(20), default="running")
    extracted_count: Mapped[int] = mapped_column(default=0)
    proposed_count: Mapped[int] = mapped_column(default=0)
    confirmed_count: Mapped[int] = mapped_column(default=0)
    stale_count: Mapped[int] = mapped_column(default=0)
    error_message: Mapped[str | None] = mapped_column(Text)
    started_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
    finished_at: Mapped[datetime | None] = mapped_column()
    started_by: Mapped[str | None] = mapped_column(String(40), ForeignKey("users.id", ondelete="SET NULL"))


class TraceAuditLog(Base):
    __tablename__ = "trace_audit_logs"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    project_id: Mapped[str] = mapped_column(String(40), ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    actor_id: Mapped[str | None] = mapped_column(String(40), ForeignKey("users.id", ondelete="SET NULL"))
    actor_name: Mapped[str] = mapped_column(String(80), default="")
    action: Mapped[str] = mapped_column(String(40))
    entity_type: Mapped[str | None] = mapped_column(
        SAEnum("requirement", "page", "api", "code_artifact", "table",
               name="entity_type_enum", create_type=False), nullable=True)
    entity_id: Mapped[str | None] = mapped_column(String(300))
    relation_id = mapped_column(UUID(as_uuid=False), nullable=True)
    before_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    after_data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reason: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now(), index=True)
