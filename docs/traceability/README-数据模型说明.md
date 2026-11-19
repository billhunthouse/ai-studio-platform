# 数据模型说明（v2.1）

> 配套文件：`001-schema.sql`
> 本文解释 DDL 背后的设计决策与取舍，供评审和未来维护。

---

## 1. 新增表清单（10 张）

| 表 | 用途 | 阶段 |
| --- | --- | --- |
| `trace_pages` | 产品功能页面 | v0.5 |
| `trace_apis` | 接口 | v0.5 |
| `trace_tables` | 数据表（多库） | v0.5 |
| `trace_relations` | 统一关联（双向） | v0.5 |
| `trace_code_artifacts` | 代码制品（接口级） | MVP |
| `trace_releases` | 发布版本 + 快照 | MVP |
| `trace_scan_runs` | 扫描任务记录 | MVP |
| `trace_audit_logs` | 人工操作审计 | v0.5 |
| `requirements` +2 列 | planned_release / released_in | v0.5 |
| ENUM 类型 4 个 | 约束枚举值 | v0.5 |

> 现有 `users` / `projects` / `project_members` / `requirements` 复用，不重建。

---

## 2. 关键设计决策与取舍

### 2.1 为什么 Relation 用多态引用（无外键）

| 决策 | 理由 | 代价 | 缓解 |
| --- | --- | --- | --- |
| `src_type + src_id` 而非外键 | 6 种关系跨 5 类实体，外键无法表达多态 | 数据库不保证引用完整性 | 应用层创建时校验 src/dst 存在且同 project；定时孤儿检测任务 |

这是刻意取舍：用应用层的完整性校验，换关联模型的统一与灵活。

### 2.2 为什么关联只存一条

一条 Relation 有 `src` 和 `dst`，正反查询靠**双向索引**（`idx_rel_src` / `idx_rel_dst`）。
好处：不会出现"A→B"和"B→A"两条不一致的记录；更新一次即可。
语义：反向语义由 `rel_type` 的预定义映射给出（见架构文档），不存两条。

### 2.3 为什么关联数不落库

`Requirement` 的"关联页面数/接口数/表数"是**实时聚合**查询，不设冗余字段。
理由：冗余字段会因关联变更而过期，反而制造不一致。
性能兜底：千级数据实时聚合 <100ms；若规模上来，加物化视图而非冗余列。

### 2.4 为什么字段级不建 Column 表

`trace_tables.columns` 用 JSONB 存字段数组。
MVP 追溯粒度到"表"而非"字段"；字段信息用于展示和影响分析的辅助提示。
若 v2 需要"改某字段影响哪些接口"，再拆出 `trace_columns` 实体。

### 2.5 为什么版本用两个字段

```
Requirement.planned_release  -- 计划版本
Requirement.released_in      -- 实际版本
```
现实中存在"v2.1 提出、v2.3 才上线"的跨版本需求，单字段无法表达。
两者相等是常态，不等是例外——但必须能表达例外。

### 2.6 为什么审计分两张表

| 表 | 记录什么 |
| --- | --- |
| `trace_audit_logs` | 人的操作（CRUD、确认、驳回、触发扫描） |
| `trace_scan_runs` | 机器的操作（每次扫描的统计与结果） |

分开的理由：扫描每天跑会产生大量记录，与人工审计混在一起会淹没真正需要追责的人工操作。

---

## 3. 索引设计说明

| 索引 | 支撑的查询 |
| --- | --- |
| `idx_rel_src(project_id, src_type, src_id, status)` | 正向：给定实体看它指向谁 |
| `idx_rel_dst(project_id, dst_type, dst_id, status)` | **反向：给定实体看谁指向它** |
| `idx_rel_status(project_id, status, confidence)` | 待确认列表（按置信度排序） |
| `idx_rel_version` | 版本回溯与变更对比 |
| `idx_trace_apis USING gin(path)` | 路径模糊搜索（需 `pg_trgm` 扩展） |
| `idx_scan_project(project_id, started_at DESC)` | 扫描历史 |

启用 trigram 需先执行：`CREATE EXTENSION IF NOT EXISTS pg_trgm;`

---

## 4. 完整性校验清单（应用层必须实现）

DDL 无法约束的部分，必须在应用层实现：

- [ ] 创建 Relation 时，校验 src_id / dst_id 对应实体存在
- [ ] 校验 src 与 dst 属于同一 project_id
- [ ] 校验 rel_type 与 src_type/dst_type 组合合法（如 `SPLITS_INTO` 只能 requirement→page）
- [ ] 实体 status=removed 时，其关联自动转 stale
- [ ] 定时任务检测孤儿 Relation（src/dst 不存在）并告警
- [ ] 所有查询强制带 project_id（防越权）

---

## 5. 迁移顺序

1. `CREATE TYPE` 4 个枚举
2. 10 张业务表
3. `ALTER TABLE requirements` 加 2 列
4. 创建视图
5. 应用层完整性校验上线
6. 数据迁移（如有存量需求，planned/released 初始化为当前版本）

> 迁移应在维护窗口执行；`ALTER TABLE requirements` 加列用 `IF NOT EXISTS` 可重复执行。
