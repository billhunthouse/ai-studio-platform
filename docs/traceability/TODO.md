# 追溯平台 · 待办清单

> 状态：`v0.5 已完成并接入 AI_Studio`（commit 1f90a8c）+ `真实数据已导入`
> 说明：按优先级排列的待办清单，不按时间周期拆分；完成一项勾掉一项。

---

## P0 · 数据真实性（让平台里有真实数据）

- [x] 为 `ecommerce` 项目批量登记真实实体：8 功能页面 / 11 接口 / 6 代码实体 / 9 数据表，47 条关联（脚本 `backend/seed_traceability.py`）
  - 数据来源：`shang-pivot-master/docs/llm-wiki` 的 03 页面地图 / 04 接口契约 / 05 数据模型
- [x] 清理冒烟测试数据（3 条关联 + 冒烟页面/接口/表已删除）
- [ ] 把现有 `requirements` 的 planned_release / released_in 填上真实版本
- [ ] 补充剩余需求的关联（当前 4 条需求已全覆盖，扩展到全部需求需先有 PRD 输入）

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
- [ ] 关联链路视图支持反向追溯（后端 `impact/backward` 已有，前端只接了正向）

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
| 关联维护 | 人工登记为主，扫描器待实现；已导入 47 条真实关联 |
| 影响分析 | 一到四跳可用（含代码层），多跳权重计算未做 |
| 版本 | 表结构已支持 Release 快照，接口/页面未接 |
| 审计 | 后端记录完整，前端查询页未做 |
| 前端 | 追溯中心 4 个 Tab 可用；实体独立管理页未做 |
| 数据 | ecommerce 项目 4 条需求五层全覆盖（页面/接口/代码/表） |

### 数据导入说明

真实数据由 `backend/seed_traceability.py` 导入，幂等可重跑：

```bash
cd backend
export $(grep -E '^SEED_ADMIN_PASSWORD=' .env | xargs)
.venv/bin/python seed_traceability.py
```

数据依据 `shang-pivot-master/docs/llm-wiki`：
- 页面 8 个：`/checkout`、`/orders/:id`、`/orders`、`/after-sales/apply`、`/admin/aftersales`、`/admin/coupons`、`/login`、`/member`
- 接口 11 个：来自 04-接口契约的 C 端与后台路径
- 表 9 张：`commerce`（order/order_item/after_sale/payment/coupon）+ `member`（member/member_level/points_log/sms_code）
- 代码 6 个：`OrderController#create`、`OrderService#calcAmount`、`AfterSaleController#apply`、`AfterSaleService#audit`、`AuthService#verifyCode`、`MemberService#benefits`

> 注：`/member`、`/login`、`coupon`/`sms_code` 等实体的路由与表名是根据需求描述合理推导的，
> 其余均直接来自 llm-wiki 文档。若与真实代码仓库有出入，以仓库为准修正。

---

## 相关文件

- 架构：`../../../测开一体化/output/生产级追溯平台-架构设计v2.1终版.md`
- 详细设计：本目录 `001-schema.sql` / `001-api-contract.md` / `001-adapter-spec.md` / `prototype.html`
- 迁移：`backend/migrate_traceability.py`
- 冒烟：`backend/smoke_traceability.py`
- 后端：`backend/app/trace_models.py` / `backend/app/routers/trace.py`
- 前端：`src/api/trace.ts` / `src/pages/project/TraceCenter.tsx`
