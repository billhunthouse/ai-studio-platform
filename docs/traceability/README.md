# 生产级追溯平台 · 详细设计包

> 版本 v2.1 · 2026-11-19
> 对应架构文档：`../output/生产级追溯平台-架构设计v2.1终版.md`
> 状态：详细设计完成（数据库 / API / 页面原型 / 扫描器），**尚未写实现代码**。

---

## 一、设计包结构

| 序号 | 文件 | 内容 | 状态 |
| --- | --- | --- | --- |
| 1 | `db/001-schema.sql` | 10 张表 DDL + 4 枚举 + 2 视图 + 隔离策略 | ✅ |
| 2 | `db/README-数据模型说明.md` | 设计决策、取舍、索引、完整性校验清单 | ✅ |
| 3 | `api/001-api-contract.md` | 约 46 个接口契约（CRUD/关联/影响/扫描/版本/审计） | ✅ |
| 4 | `prototype/index.html` | 8 页高保真可点击原型 | ✅ |
| 5 | `scanner/001-adapter-spec.md` | 四类扫描适配器规范 + 置信度 + 增量 + 漂移 | ✅ |

---

## 二、四份设计如何衔接

```
DDL (数据怎么存)
  ↓
API 契约 (数据怎么访问)
  ↓
页面原型 (用户怎么操作)
  ↓
扫描器规范 (数据怎么自动进来)
```

- DDL 里的 `trace_relations` 双向索引 → 支撑 API 的 `direction=forward/backward`
- API 的 `relations/pending` → 支撑原型的"待确认关联"页
- API 的 `impact/*` → 支撑原型的"影响范围分析"和"追踪矩阵"
- 扫描器的 `proposed/confirmed/stale` → 对应 DDL 的 status 枚举 + 原型的待确认页

---

## 三、关键设计一致性检查

| 设计项 | DDL | API | 原型 | 扫描器 |
| --- | --- | --- | --- | --- |
| 双向关联 | idx_rel_src/dst | direction=both | 上游/下游区块 | — |
| 来源分级 | source 枚举 | source 过滤 | 来源标签 | 置信度规则 |
| 状态机 | status 枚举 | confirm/reject | 待确认页 | proposed/stale |
| 版本区间 | valid_from/to | release 参数 | 切换版本 | — |
| 多库 | database+service | — | 数据库分组 | CROSS_DB_READ |
| 接口级粒度 | api_id 字段 | internal_calls | 内部调用描述 | 注解适配器 |
| Page 产品功能页 | feature_domain/prd_section | — | 功能页面标签 | PRD 适配器 |
| 审计 | audit + scan_runs | /audit + /scans | — | ScanRun 记录 |

---

## 四、下一步（实现阶段，需你确认）

详细设计已完成，若进入实现，建议顺序：

1. **先落 DDL**（I0）：建表 + 枚举 + 索引，加 requirements 两列
2. **再实体 CRUD + 关联服务**（I1）：支撑 v0.5 核心版
3. **接页面**（I2）：用原型作为高保真参考
4. **扫描器**（I3）：先 OpenAPI + DDL 两个 P0 适配器
5. **影响分析 + 版本 + 审计**（I4）

按 ARCHITECTURE-AGENT.md 规范，实现前建议再做一次"实现就绪检查"：
- 技术栈确认（复用 AI_Studio）
- 目标目录确认（作为 AI_Studio 模块还是独立项目）
- 数据库迁移窗口
- 是否需要我先做 v0.5 的精确任务拆解

---

## 五、原型使用说明

`prototype/index.html` 可直接用浏览器打开：
- 点击左侧菜单切换 8 个页面
- 点击需求 ID / 接口 / 表节点跳转详情页
- 演示数据基于尚品汇真实场景（商家回复评价、优惠券叠加等）
- 样式沿用 AI_Studio 的 Precision Workspace token（#2d5bff 主色 / #0b1220 顶栏 / #f5f7fb 背景）
