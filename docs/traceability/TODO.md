# 追溯平台 · 待办清单

> 状态：`v0.6`（2026-11-20）— 真实代码扫描 + 实体详情页
> v0.5 接入 AI_Studio（commit 1f90a8c），本版新增 Java 注解扫描器与三个实体详情页
> 说明：按优先级排列的待办清单，不按时间周期拆分；完成一项勾掉一项。

---

## P0 · 数据真实性（让平台里有真实数据）

- [x] 为 `ecommerce` 项目登记 PRD 侧实体：8 功能页面 / 11 接口 / 9 数据表 / 19 条人工关联（`backend/seed_traceability.py`）
  - 数据来源：`shang-pivot-master/docs/llm-wiki` 的页面地图 / 接口契约 / 数据模型
  - 代码层不再由脚本编造，改由扫描器从真实仓库生成
- [x] 清理冒烟测试数据（3 条关联 + 冒烟页面/接口/表已删除）
- [ ] 把现有 `requirements` 的 planned_release / released_in 填上真实版本
- [ ] 补充剩余需求的关联（当前 4 条需求已全覆盖，扩展到全部需求需先有 PRD 输入）

## P0 · 扫描器（自动发现）

- [x] **实现 Java 注解扫描适配器（P0）** — `backend/scanners/java_scanner.py`
  - 扫 24 个 Controller / 136 个端点：method、path、@Operation 摘要、@Parameter 参数、鉴权（读 SecurityConfig 的 permitAll 清单）
  - 扫 37 个 MyBatis 实体：表名（@TableName schema+value）、字段（含 BaseEntity 继承字段）、Java→PG 类型映射
  - 接口→表关联走两级证据：Service 的 Javadoc「关联表：」优先，没有就下钻方法体看 Mapper 调用
  - 一次扫描写一条 `trace_scan_runs`，重扫前清理上一轮 `source=CODE_SCAN` 的关联
  - 271 条扫描关联（136 条接口→代码 + 135 条接口→表），置信度 85/95
- [ ] 实现 OpenAPI 扫描适配器（P0）— 规范见 `001-adapter-spec.md` 2.1；Java 注解版已覆盖同源信息，优先级下调
- [ ] 实现 DDL 扫描适配器（P0，用于校验实体与真实 DDL 的漂移）— 规范见 2.3
- [ ] 实现 PRD 文档扫描适配器（P1，产出 proposed）— 规范见 2.4
- [ ] 增量扫描：基于 commit_sha 只处理 changed_files
- [ ] 漂移检测：扫描依据消失时把 confirmed 关联转 stale 并通知 Owner
- [ ] 扫描触发接入 CI（trigger=auto，不推送通知）

## P1 · 前端完善

- [ ] 实体管理页：功能页面 / 接口 / 数据表的独立列表与新建表单（当前只有 API，前端只做了追溯中心）
- [x] **实体详情跳转**：链路节点可点，统一走 `/project/:pid/trace/entity?type=&id=`
- [x] **接口详情页**：契约（方法/路径/鉴权/参数/请求体/响应）+ 实现代码 + 上下游 + 一键发起调试
- [x] **表详情页**：字段结构（类型/可空/主键/说明）+ 索引 + 读写方 + 反向需求
- [x] **功能页面详情页**：归属需求卡片（一键进需求详情）+ 调用接口 + 涉及数据表
- [x] **关系语义页**：把 6 种 rel_type 翻译成中文，并且说明哪几个可以精简
- [ ] 版本切换与版本对比视图
- [ ] 待确认页支持按来源/置信度筛选、行内查看 evidence
- [ ] 周报视图：本周确认数、stale 数、覆盖率变化
- [ ] 关联链路视图支持反向追溯（后端 `impact/backward` 已有，前端只接了正向）

## P0 · 已修复的口径问题（v0.6）

- [x] 「4 跳」是死选项：链路真实深度只有 3 层（需求→页面→接口→代码/表），
      下拉现在按后端返回的 `maxDepth` 生成，并在头部显示「链路共 N 层」
- [x] 清理了 v0.5 种子脚本编造的 6 个代码实体（`OrderController#create`、
      `AuthService#verifyCode` 等在真实仓库里并不存在，文件路径与 commit 都是假的），
      代码层改为完全由扫描器提供
- [x] 扫描器不再用占位摘要「POST /api/orders」覆盖 PRD 登记的中文接口说明

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

## 附：6 种 rel_type 到底是什么

| 枚举 | 中文 | 方向 | 回答的问题 | 例子 |
| --- | --- | --- | --- | --- |
| `SPLITS_INTO` | 拆分为 | 需求 → 页面 | 这条需求由哪几个页面承载 | REQ-018 → 确认订单页 |
| `TRIGGERS` | 调用接口 | 页面 → 接口 | 这个页面发哪些请求 | 确认订单页 → `POST /api/orders` |
| `EXPOSED_BY` | 由代码实现 | 接口 → 代码 | 接口落在哪个类/方法 | `POST /api/orders` → `StorefrontController#submit` |
| `READS_WRITES` | 读写数据表 | 接口/代码 → 表 | 这段逻辑动了哪些表 | `POST /api/orders` → order / order_item |
| `CROSS_DB_READ` | 跨库读取 | 接口/代码 → 表 | 是否读了别的库 | member-service 读 commerce.order |
| `DERIVED_FROM` | 派生自 | 子需求 → 主需求 | 子需求从哪来 | REQ-018-1 → REQ-018 |

**可以精简的两处**（本轮只做了界面中文化，枚举未动，避免破坏已有 47+271 条数据）：

1. `CROSS_DB_READ` 应该是 `READS_WRITES` + `cross_db` 布尔标记。现在跨库关系要建两条边，
   而且"跨库"这个结论其实是**表分布**算出来的（`impact/forward` 里已经在算），不需要独立枚举。
2. `EXPOSED_BY` 的命名方向是反的：主语是接口，谓语却是"被代码暴露"。语义上它就是 `IMPLEMENTS`。

建议的 v2 收敛方案（4 个枚举 + 1 个标记）：
`SPLITS_INTO` / `CALLS`（合并 TRIGGERS） / `IMPLEMENTS`（原 EXPOSED_BY） /
`READS_WRITES`（关系上带 `cross_db` 标记） / `DERIVED_FROM`。
迁移时写一条 `UPDATE trace_relations SET rel_type='IMPLEMENTS' WHERE rel_type='EXPOSED_BY'` 即可，不动业务表。

## 相关文件

- 架构：`../../../测开一体化/output/生产级追溯平台-架构设计v2.1终版.md`
- 详细设计：本目录 `001-schema.sql` / `001-api-contract.md` / `001-adapter-spec.md` / `prototype.html`
- 迁移：`backend/migrate_traceability.py`
- 冒烟：`backend/smoke_traceability.py`
- 后端：`backend/app/trace_models.py` / `backend/app/routers/trace.py`
- 前端：`src/api/trace.ts` / `src/pages/project/TraceCenter.tsx` / `src/pages/project/TraceEntity.tsx`
- 扫描器：`backend/scanners/java_scanner.py`

### 扫描器怎么跑

```bash
cd backend
# 只看解析结果（生成 scan_preview.json，不写库）
.venv/bin/python -m scanners.java_scanner --repo /path/to/shang-pivot-master/backend --dry-run

# 写库（幂等，可重复执行；重扫会覆盖上一轮 CODE_SCAN 结论，不动 HUMAN/SPEC）
.venv/bin/python -m scanners.java_scanner \
  --repo /path/to/shang-pivot-master/backend \
  --project ecommerce \
  --database-url postgresql://ai:***@127.0.0.1:55432/ai_test_platform
```
