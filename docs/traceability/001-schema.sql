-- ============================================================
-- 生产级追溯平台 — 数据库 DDL (v2.1)
-- 目标库：PostgreSQL 16（复用 AI_Studio 现有库）
-- 约定：
--   1. 本文件只新增追溯相关表，不修改现有 users/projects/requirements 结构
--   2. 需要在 requirements 表补充 2 个字段（见文件末尾 ALTER）
--   3. 所有表带 project_id，强制项目隔离
--   4. 多态关联用 entity_type + entity_id，不用多态外键
--   5. ID 生成后不可变，语义变更走 status=deprecated
-- ============================================================

-- ------------------------------------------------------------
-- 1. 枚举类型（PostgreSQL ENUM，便于约束与索引）
-- ------------------------------------------------------------
CREATE TYPE entity_type_enum AS ENUM (
  'requirement', 'page', 'api', 'code_artifact', 'table'
);

CREATE TYPE relation_type_enum AS ENUM (
  'SPLITS_INTO',     -- 需求 -> 页面
  'TRIGGERS',        -- 页面 -> 接口
  'EXPOSED_BY',      -- 接口 -> 代码
  'READS_WRITES',    -- 代码 -> 表
  'CROSS_DB_READ',   -- 跨库读
  'DERIVED_FROM'     -- 子需求 -> 主需求
);

CREATE TYPE relation_source_enum AS ENUM (
  'SPEC', 'CODE_SCAN', 'DOC_PARSE', 'HUMAN', 'AI_INFER'
);

CREATE TYPE relation_status_enum AS ENUM (
  'proposed', 'confirmed', 'stale', 'rejected'
);

-- ------------------------------------------------------------
-- 2. 产品功能页面 (Page)
--    语义：PRD/原型视角的功能页面，不是前端路由
-- ------------------------------------------------------------
CREATE TABLE trace_pages (
  id              VARCHAR(120) PRIMARY KEY,   -- page:{project}:{feature}-{seq}
  project_id      VARCHAR(40)  NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  name            VARCHAR(200) NOT NULL,       -- 功能页面名称，如"商品详情页"
  feature_domain  VARCHAR(100) NOT NULL,       -- 功能域：商品/订单/用户/评价
  prd_section     VARCHAR(200),                -- PRD 章节来源，如"V2-FR-015 3.2"
  prototype_ref   VARCHAR(500),                -- 原型图引用（Figma node URL 或文件路径）
  business_owner  VARCHAR(80),                 -- 业务负责人
  status          VARCHAR(20)  NOT NULL DEFAULT 'active', -- active/deprecated/removed
  description     TEXT         DEFAULT '',
  created_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE(project_id, name, feature_domain)
);
CREATE INDEX idx_trace_pages_project ON trace_pages(project_id);
CREATE INDEX idx_trace_pages_domain  ON trace_pages(project_id, feature_domain);
COMMENT ON TABLE trace_pages IS '产品功能页面（PRD/原型视角），非前端路由';

-- ------------------------------------------------------------
-- 3. 接口 (Api)
-- ------------------------------------------------------------
CREATE TABLE trace_apis (
  id                VARCHAR(240) PRIMARY KEY,  -- api:{METHOD}:{path}
  project_id        VARCHAR(40)  NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  method            VARCHAR(10)  NOT NULL,
  path              VARCHAR(200) NOT NULL,
  summary           VARCHAR(300) NOT NULL DEFAULT '',
  service           VARCHAR(100) NOT NULL,     -- 所属微服务
  request_schema    JSONB        DEFAULT '{}'::jsonb,
  response_schema   JSONB        DEFAULT '{}'::jsonb,
  auth_requirement  VARCHAR(50)  DEFAULT 'public', -- public/login/role:xxx
  internal_calls    TEXT         DEFAULT '',    -- 接口级粒度下，Service 内部调用的描述
  status            VARCHAR(20)  NOT NULL DEFAULT 'active',
  source            relation_source_enum DEFAULT 'SPEC',
  spec_ref          VARCHAR(500),              -- OpenAPI 文件位置
  created_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at        TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE(project_id, method, path)
);
CREATE INDEX idx_trace_apis_project ON trace_apis(project_id);
CREATE INDEX idx_trace_apis_service ON trace_apis(project_id, service);
CREATE INDEX idx_trace_apis_path    ON trace_apis USING gin (path gin_trgm_ops); -- 需 pg_trgm
COMMENT ON TABLE trace_apis IS '接口实体；粒度到接口级，内部调用存描述字段';

-- ------------------------------------------------------------
-- 4. 代码制品 (CodeArtifact) — 接口级
-- ------------------------------------------------------------
CREATE TABLE trace_code_artifacts (
  id            VARCHAR(300) PRIMARY KEY,  -- code:{repo}:{service}:{api_id_hash}
  project_id    VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  repo          VARCHAR(150) NOT NULL,
  service       VARCHAR(100) NOT NULL,
  api_id        VARCHAR(240) REFERENCES trace_apis(id) ON DELETE SET NULL,
  file_path     VARCHAR(500) NOT NULL,     -- 仓库相对路径
  entry_point   VARCHAR(200),              -- 入口方法签名（描述性，非独立实体）
  commit_sha    VARCHAR(40),               -- 最近一次扫描到的 commit
  status        VARCHAR(20) NOT NULL DEFAULT 'active',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_trace_code_project ON trace_code_artifacts(project_id);
CREATE INDEX idx_trace_code_api     ON trace_code_artifacts(api_id);
CREATE INDEX idx_trace_code_commit  ON trace_code_artifacts(commit_sha);
COMMENT ON TABLE trace_code_artifacts IS '代码制品，接口级粒度；一格对应一个 Controller 入口';

-- ------------------------------------------------------------
-- 5. 数据表 (Table) — 多服务多库
-- ------------------------------------------------------------
CREATE TABLE trace_tables (
  id            VARCHAR(240) PRIMARY KEY,  -- table:{database}:{schema}:{name}
  project_id    VARCHAR(40)  NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  database_name VARCHAR(100) NOT NULL,     -- 数据库实例名（order_db）
  service       VARCHAR(100) NOT NULL,     -- 归属微服务
  schema_name   VARCHAR(100) NOT NULL DEFAULT 'public',
  name          VARCHAR(150) NOT NULL,
  columns       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    -- [{name,type,nullable,default,comment,primary_key}]
  indexes       JSONB        NOT NULL DEFAULT '[]'::jsonb,
    -- [{name,columns,unique}]
  primary_key   VARCHAR(200),
  status        VARCHAR(20)  NOT NULL DEFAULT 'active',
  source        relation_source_enum DEFAULT 'SPEC',
  ddl_ref       VARCHAR(500),
  created_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  updated_at    TIMESTAMPTZ  NOT NULL DEFAULT now(),
  UNIQUE(project_id, database_name, schema_name, name)
);
CREATE INDEX idx_trace_tables_project ON trace_tables(project_id);
CREATE INDEX idx_trace_tables_service ON trace_tables(project_id, service);
CREATE INDEX idx_trace_tables_db      ON trace_tables(project_id, database_name);
COMMENT ON TABLE trace_tables IS '数据表实体，带 database+service 双归属；字段级信息存 JSONB，MVP 不建 Column 实体';

-- ------------------------------------------------------------
-- 6. 统一关联表 (Relation) — 双向可查的核心
-- ------------------------------------------------------------
CREATE TABLE trace_relations (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id            VARCHAR(40)  NOT NULL REFERENCES projects(id) ON DELETE CASCADE,

  src_type              entity_type_enum NOT NULL,
  src_id                VARCHAR(300) NOT NULL,
  rel_type              relation_type_enum NOT NULL,
  dst_type              entity_type_enum NOT NULL,
  dst_id                VARCHAR(300) NOT NULL,

  source                relation_source_enum NOT NULL,
  confidence            SMALLINT     NOT NULL DEFAULT 100 CHECK (confidence BETWEEN 0 AND 100),
  status                relation_status_enum NOT NULL DEFAULT 'proposed',

  -- 版本区间：关联在哪个发布版本区间内有效
  valid_from_release    VARCHAR(20),
  valid_to_release      VARCHAR(20),

  -- 扫描溯源
  first_seen_scan       UUID,
  last_seen_scan        UUID,
  last_seen_commit      VARCHAR(40),
  confirmed_by          VARCHAR(40) REFERENCES users(id) ON DELETE SET NULL,
  confirmed_at          TIMESTAMPTZ,

  note                  TEXT DEFAULT '',
  created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

  -- 同一对实体 + 同一关系类型只允许一条
  UNIQUE(project_id, src_type, src_id, rel_type, dst_type, dst_id)
);
-- 双向查询：源端与目标端都建复合索引
CREATE INDEX idx_rel_src ON trace_relations(project_id, src_type, src_id, status);
CREATE INDEX idx_rel_dst ON trace_relations(project_id, dst_type, dst_id, status);
CREATE INDEX idx_rel_type ON trace_relations(project_id, rel_type);
CREATE INDEX idx_rel_status ON trace_relations(project_id, status, confidence);
CREATE INDEX idx_rel_version ON trace_relations(project_id, valid_from_release, valid_to_release);
COMMENT ON TABLE trace_relations IS '统一关联表。一对关系只存一条，通过 src/dst 双向索引实现双向查询';
COMMENT ON COLUMN trace_relations.status IS 'proposed=待确认, confirmed=生效, stale=依据消失待复核, rejected=已驳回';

-- ------------------------------------------------------------
-- 7. 发布版本 (Release)
-- ------------------------------------------------------------
CREATE TABLE trace_releases (
  id            VARCHAR(40) PRIMARY KEY,   -- REL-{SEQ} 或 vX.Y.Z
  project_id    VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  version       VARCHAR(20) NOT NULL,      -- v2.3.0
  name          VARCHAR(120),
  description   TEXT DEFAULT '',
  changelog     JSONB DEFAULT '[]'::jsonb, -- {added:[],removed:[],deprecated:[]}
  snapshot      JSONB DEFAULT '{}'::jsonb, -- 冻结的 confirmed 关联快照
  released_at   TIMESTAMPTZ,
  created_by    VARCHAR(40) REFERENCES users(id) ON DELETE SET NULL,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE(project_id, version)
);
CREATE INDEX idx_release_project ON trace_releases(project_id, released_at DESC);
COMMENT ON TABLE trace_releases IS '系统发布版本；需求版本与之对齐，快照冻结当时的 confirmed 关联';

-- ------------------------------------------------------------
-- 8. 扫描任务记录 (ScanRun) — 与人工审计分表
-- ------------------------------------------------------------
CREATE TABLE trace_scan_runs (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  project_id      VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  adapter         VARCHAR(40) NOT NULL,   -- openapi/annotation/ddl/prd/ai_infer
  repo            VARCHAR(150),
  commit_sha      VARCHAR(40),
  trigger         VARCHAR(10) NOT NULL DEFAULT 'manual', -- manual/auto
  status          VARCHAR(20) NOT NULL DEFAULT 'running', -- running/success/failed
  extracted_count INT DEFAULT 0,
  proposed_count  INT DEFAULT 0,
  confirmed_count INT DEFAULT 0,
  stale_count     INT DEFAULT 0,
  error_message   TEXT,
  started_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ,
  started_by      VARCHAR(40) REFERENCES users(id) ON DELETE SET NULL
);
CREATE INDEX idx_scan_project ON trace_scan_runs(project_id, started_at DESC);
CREATE INDEX idx_scan_commit  ON trace_scan_runs(project_id, commit_sha);
COMMENT ON TABLE trace_scan_runs IS '扫描任务记录。trigger=auto 的定时扫描不通知，只更新待确认列表';

-- ------------------------------------------------------------
-- 9. 审计日志 (AuditLog) — 人工操作
-- ------------------------------------------------------------
CREATE TABLE trace_audit_logs (
  id            BIGSERIAL PRIMARY KEY,
  project_id    VARCHAR(40) NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
  actor_id      VARCHAR(40) REFERENCES users(id) ON DELETE SET NULL,
  actor_name    VARCHAR(80) NOT NULL DEFAULT '',
  action        VARCHAR(40) NOT NULL,  -- create/update/delete/confirm/reject/scan_trigger
  entity_type   entity_type_enum,
  entity_id     VARCHAR(300),
  relation_id   UUID,
  before_data   JSONB DEFAULT '{}'::jsonb,
  after_data    JSONB DEFAULT '{}'::jsonb,
  reason        TEXT DEFAULT '',
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_audit_project ON trace_audit_logs(project_id, created_at DESC);
CREATE INDEX idx_audit_entity  ON trace_audit_logs(project_id, entity_type, entity_id);
CREATE INDEX idx_audit_actor   ON trace_audit_logs(actor_id, created_at DESC);
COMMENT ON TABLE trace_audit_logs IS '人工操作审计；扫描结果审计在 trace_scan_runs，两表分开';

-- ------------------------------------------------------------
-- 10. 需求表补充字段（对齐发布版本）
--     AI_Studio 现有 requirements 表增加两列，不改其他结构
-- ------------------------------------------------------------
ALTER TABLE requirements
  ADD COLUMN IF NOT EXISTS planned_release VARCHAR(20),
  ADD COLUMN IF NOT EXISTS released_in     VARCHAR(20);

COMMENT ON COLUMN requirements.planned_release IS '计划发布版本，如 v2.3';
COMMENT ON COLUMN requirements.released_in     IS '实际上线版本，可与 planned_release 不同（跨版本需求）';
CREATE INDEX IF NOT EXISTS idx_req_planned_release ON requirements(project_id, planned_release);
CREATE INDEX IF NOT EXISTS idx_req_released_in     ON requirements(project_id, released_in);

-- ============================================================
-- 视图：双向关联查询的便捷视图（可选，应用层也可直接查表）
-- ============================================================

-- 正向：给定实体，看它指向谁
CREATE OR REPLACE VIEW v_relation_forward AS
SELECT r.project_id, r.src_type, r.src_id, r.rel_type,
       r.dst_type, r.dst_id, r.source, r.status
FROM trace_relations r
WHERE r.status = 'confirmed';

-- 反向：给定实体，看谁指向它（双向可查的 SQL 层保证）
CREATE OR REPLACE VIEW v_relation_backward AS
SELECT r.project_id, r.dst_type AS queried_type, r.dst_id AS queried_id,
       r.rel_type, r.src_type AS from_type, r.src_id AS from_id,
       r.source, r.status
FROM trace_relations r
WHERE r.status = 'confirmed';

-- ============================================================
-- 数据隔离说明
-- ============================================================
-- 应用层必须：
--   1. 所有查询强制带 project_id 条件（RLS 可选，见下）
--   2. 请求头 X-Project-Id 与用户 project_members 权限校验
--   3. 关联创建时校验 src/dst 实体均属于同一 project_id
--
-- 可选 RLS（如需数据库层兜底）：
-- ALTER TABLE trace_relations ENABLE ROW LEVEL SECURITY;
-- CREATE POLICY p_rel_project ON trace_relations
--   USING (project_id = current_setting('app.project_id', true));
-- ============================================================
