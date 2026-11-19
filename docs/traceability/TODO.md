# 追溯平台 · 待办清单

> 状态：`v0.5 已完成并接入 AI_Studio`（commit 1f90a8c）
> 说明：按优先级排列的待办清单，不按时间周期拆分；完成一项勾掉一项。

---

## P0 · 数据真实性（让平台里有真实数据）

- [ ] 为 `ecommerce` 项目批量登记真实实体：从 PRD 导入功能页面、从 OpenAPI 导入接口、从 schema.sql 导入数据表
- [ ] 把现有 `requirements` 的 planned_release / released_in 填上真实版本
- [ ] 清理冒烟测试数据（page:ecommerce:617e33e5、api:GET:/api/smoke/{id}、table:smoke_db:public:smoke_table 及其关联）
- [ ] 用真实需求"商家回复评价"走一遍完整关联，替换演示数据

## P0 · 扫描器（自动发现，当前全是人工登记）

- [ ] 实现 OpenAPI 扫描适配器（P0，最快见效）— 规范见 `001-adapter-spec.md` 2.1
- [ ] 实现 DDL 扫描适配器（P0）— 规范见 2.3
- [ ] 实现 Java 注解扫描适配器（P1）— 规范见 2.2
- [ ] 实现 PRD 文档扫描适配器（P1，产出 proposed）— 规范见 2.4
- [ ] 增量扫描：基于 commit_sha 只处理 changed_files
- [ ] 漂移检测：扫描依据消失时把 confirmed 关联转 stale 并通知 Owner
- [ ] 扫描触发接入 CI（trigger=auto，不推送通知）

## P1 · 前端完善

- [ ] 实体管理页：功能页面 / 接口 / 数据表的独立列表与新建表单（当前只有 API，前端只做了追溯中心）
- [ ] 实体详情跳转：从追溯中心点击节点跳到对应实体详情（当前显示在一页内）
- [ ] 接口详情页：契约 + 实现代码 + 上下游（原型已有设计，见 prototype.html）
- [ ] 表详情页：字段表格 + 读写代码 + 反向需求（原型已有设计）
- [ ] 版本切换与版本对比视图
- [ ] 待确认页支持按来源/置信度筛选、行内查看 evidence
- [ ] 周报视图：本周确认数、stale 数、覆盖率变化

## P1 · 治理与质量

- [ ] 后端补全 Pydantic Schema 校验（当前部分 body 用 dict 直传）
- [ ] 关联创建的完整性校验：src/dst 同项目、类型组合合法（后端已做，需补测试）
- [ ] 孤儿关联定时检测任务（src/dst 实体被删后残留的 Relation）
- [ ] 越权自动化测试：非项目成员访问 trace 接口应 403
- [ ] 审计日志查询页（后端接口已有，前端未接）
- [ ] 影响分析加单元测试（当前只做了端到端冒烟）

## P2 · 增强能力

- [ ] CodeArtifact 接口级 → 字段级追溯（拆出 trace_columns 实体）
- [ ] 完整力导向关系图谱页（当前是列表式链路）
- [ ] AI_INFER 来源：默认关闭，管理员可开启，产出必须人工确认
- [ ] 影响分析输出自动关联测试用例集合
- [ ] 全局搜索：粘贴任意 ID 直达详情（前端搜索框是占位）
- [ ] Release 快照与对比视图（后端表已建，无接口/页面）

## P2 · 运维

- [ ] 数据库迁移纳入 Alembic（当前是独立脚本 migrate_traceability.py）
- [ ] 备份策略：定期 pg_dump（当前只有迁移前一次性备份）
- [ ] 监控：扫描失败率、待确认积压告警
- [ ] 文档：部署说明、扫描器配置说明

---

## 已知边界（当前版本的诚实说明）

| 能力 | 当前状态 |
| --- | --- |
| 关联维护 | 人工登记为主，扫描器待实现 |
| 影响分析 | 一跳到三跳已可用，多跳权重计算未做 |
| 版本 | 表结构已支持 Release 快照，接口/页面未接 |
| 审计 | 后端记录完整，前端查询页未做 |
| 前端 | 追溯中心 4 个 Tab 可用；实体独立管理页未做 |
| 数据 | ecommerce 项目仅冒烟测试数据，需导入真实数据 |

---

## 相关文件

- 架构：`../../../测开一体化/output/生产级追溯平台-架构设计v2.1终版.md`
- 详细设计：本目录 `001-schema.sql` / `001-api-contract.md` / `001-adapter-spec.md` / `prototype.html`
- 迁移：`backend/migrate_traceability.py`
- 冒烟：`backend/smoke_traceability.py`
- 后端：`backend/app/trace_models.py` / `backend/app/routers/trace.py`
- 前端：`src/api/trace.ts` / `src/pages/project/TraceCenter.tsx`
