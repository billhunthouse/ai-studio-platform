# 产品文档 AGENT · 设计说明

> 目标：把"需求 → 功能页面 → 接口 → 实现代码 → 数据表"这条已经建好的追溯链，
> 逆向还原成**专业产品经理会写的需求文档（PRD）**，并展示在需求详情里。
> 核心原则：**文档里的每一句话都要有代码或源码证据支撑，不凭空编造。**

---

## 1. 为什么需要这个 AGENT

现在的 52 条需求只有一行标题 + 几个拆解点（如"角色、权限绑定、数据范围"），
点开详情页看不到真正的需求文档。而真实的业务细节散落在四处：

| 证据源 | 能还原什么 | 谁维护 |
|---|---|---|
| `02-requirements.md` | 需求编号、模块、功能、优先级、页面、接口数 | 需求文档 |
| `06-business-rules.md` | 状态机、校验规则、边界、负面清单 | 代码事实 |
| `trace_apis` / `trace_tables` / `trace_code_artifacts` | 接口契约、表字段、代码入口 | 扫描器 |
| 真实 Java 源码 | 参数校验、副作用、异常分支 | 代码 |

AGENT 的职责就是把这四源**Compile 成一份结构化 PRD**，每条需求都还原出：
背景与目标、用户故事、功能规格、业务规则、状态机、接口清单、数据模型、异常场景、验收标准、代码证据。

---

## 2. AGENT 流水线（7 个 Stage）

```
Stage 1  需求解析     从 requirements 表取标题/功能点/模块/优先级
   ↓
Stage 2  证据采集     沿 trace_relations 多跳遍历，拿到 page/api/code/table 全链
   ↓
Stage 3  契约补全     从 trace_apis 取 method/path/参数/请求体/响应/鉴权
                      从 trace_tables 取字段名/类型/主键/索引
   ↓
Stage 4  规则归因     按需求 ID 匹配业务域规则（订单状态机/售后状态机/库存不变式…）
                      从 06-business-rules.md + 源码提取该需求真正适用的规则
   ↓
Stage 5  文档生成     用 PRD 模板组装 10 个章节，每个章节附 evidence 引用
   ↓
Stage 6  缺口标注     四层链路有缺口的需求，在文档里显式标"⚠ 未覆盖层"
   ↓
Stage 7  落库 + 索引   写入 requirement_prd 表，前端按需求 ID 读取展示
```

---

## 3. PRD 文档结构（10 章节）

| # | 章节 | 内容 | 证据来源 |
|---|---|---|---|
| 1 | 需求概述 | 编号/标题/模块/优先级/版本/背景目标 | requirements + 02-requirements |
| 2 | 用户故事 | 角色 + 场景 + 价值（As a…I want…so that…） | 模块规则 + 页面 |
| 3 | 功能规格 | 每个功能点的详细行为、入口、前置条件 | points + trace 页面 |
| 4 | 业务规则 | 状态机、校验、不变式、副作用 | 06-business-rules + 源码 |
| 5 | 接口清单 | method/path/摘要/鉴权/参数/请求体/响应 | trace_apis（CODE_SCAN） |
| 6 | 数据模型 | 表名 + 字段 + 类型 + 主键 | trace_tables（CODE_SCAN） |
| 7 | 异常与边界 | 错误码、并发、负面场景 | 06-business-rules §7 负面清单 |
| 8 | 验收标准 | 可勾选的 Given/When/Then | 功能点 + 规则推导 |
| 9 | 覆盖与缺口 | 四层覆盖数、缺哪层、为什么 | trace_relations |
| 10 | 代码证据 | Controller#method + 文件路径 + commit | trace_code_artifacts |

每个章节的每条规则/接口/字段都带 `evidence` 字段，形如
`shang-identity/.../RoleController.java#L0`、`CODE_SCAN 95`、`06-business-rules.md OT-01`。

---

## 4. 业务域规则库（Stage 4 的归因表）

AGENT 不是套空模板，而是按需求所属业务域注入真实规则。当前内置 12 个域：

| 域 | 覆盖需求 | 关键规则 |
|---|---|---|
| 认证登录 | V1-FR-001 / V2-FR-001 | BCrypt、失败5次锁15分钟、JWT 900s/7d、C端验证码123456 |
| RBAC 权限 | V1-FR-002~007 | 用户增删改查、角色权限绑定、数据范围 ALL/DEPT/SELF |
| 商品类目 | V1-FR-008~014 | 类目树、SPU+SKU、上下架校验、C端只展示 ON 且未删 |
| 库存 | V1-FR-015~017 / V2-FR-024 | physical≥locked≥0、两级低库存阈值、FOR UPDATE 锁 |
| 订单交易 | V1-FR-018/019 / V2-FR-008~011/021/022 | 五态状态机、锁库存、15分钟超时关单、幂等键 |
| 售后 | V1-FR-020/021 / V2-FR-012 | 三态状态机、仅待收货/已完成可申请、退款金额无校验缺口 |
| 支付 | V2-FR-010 | 沙箱 PAID、sold_count+=qty、无真实资金 |
| 评价 | V2-FR-015/025 / EXT-REVIEW | 仅已完成可评、1-5分、商家回复只写 reply 字段 |
| 购物车/收藏/足迹 | V2-FR-007/013/014 | skuId 合并、默认地址唯一、雪花ID字符串处理 |
| 首页运营 | V2-FR-003/018/019 | 站点品牌、运营位、推荐流 N+1 |
| AI 助手 | EXT-AI-001 | 免认证可选 token、走 Agent 子服务不落商城库 |
| 全站规范 | V1-FR-024 / V2-FR-016/026 | 弹窗/提示规范、Web/H5 双布局（无独立接口，标缺口） |

---

## 5. 运行方式

```bash
cd backend
# 生成/刷新全部 52 条需求的 PRD（幂等，可重复执行）
.venv/bin/python -m agents.prd_agent

# 只看不写（预览某条）
.venv/bin/python -m agents.prd_agent --only V1-FR-003 --dry-run
```

落库表 `requirement_prd`（`requirement_id` 主键，`doc` jsonb）。
前端通过 `GET /api/v1/requirements/{id}/prd` 读取，`GET /api/v1/requirements/prd/status` 看还原进度。

---

## 6. 质量约定

- **不编造**：没有证据的字段宁可写"源码中未见明确实现"，也不臆造业务口径。
- **缺口可见**：V1-FR-024、V2-FR-026 这类纯交互规范，链路四层为空，文档显式标注，
  而不是伪造接口。
- **负面清单必带**：订单/售后/库存相关的需求，把 NEG-S01~S13 里适用的条目写进异常章节，
  这是从代码事实反推的、测试必须覆盖的边界。
- **可复现**：同一份代码 + 同一份需求文档，AGENT 输出稳定，commit 变化时重跑即可刷新。
