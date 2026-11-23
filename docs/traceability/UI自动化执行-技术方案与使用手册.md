# UI 自动化执行 · 技术方案与使用手册

> 面向三类读者：**使用者**（怎么跑、怎么看结果）、**维护者**（代码在哪、怎么改）、**评审者**（为什么这么设计）。
> 架构演进过程与踩坑记录见同目录 `UI自动化执行架构-设计说明.md`，本文只讲**是什么、怎么用、为什么**。

---

## 0. 一页速览

| 维度 | 现状 |
|---|---|
| 被测对象 | 尚品汇 C 端前端 `http://127.0.0.1:5174`（真实站点，非 mock） |
| 驱动技术 | Playwright 1.65.2（Python Sync API）+ Chromium headless |
| 用例来源 | 平台「测试用例」里的功能用例，中文自然语言步骤 |
| 可执行规模 | 363 条功能用例，**289 条**可直接执行，60 条为写操作（下单/支付），74 条无对应 UI 流程 |
| 执行方式 | 单条同步执行（5~15s）／批量后台任务（页面默认 120 条，接口上限 500）／CLI |
| 证据留存 | 每步 1 张 1440×900 截图 + 整段 800×500 webm 视频，HMAC 签名 URL 访问，5 GiB 滚动淘汰 |
| 判定 | 通过 / 部分可执行 / 失败 / 未执行，断言失败带**实际值** |

**三个常用入口**

| 想做的事 | 去哪 |
|---|---|
| 快速跑一条看效果 | 测试用例列表 → 「运行」（已自动化的用例） |
| 选一条 / 勾多条跑，看逐步回放 | WebUI 自动化 → **用例脚本** |
| 看历史结果、截图、视频、批次明细 | WebUI 自动化 → **执行记录** |

---

## 1. 要解决的问题

平台里有几百条中文测试用例，例如：

```
步骤：1. 进入登录页  2. 输入手机号 13800000001  3. 输入验证码 123456
     4. 点击登录  5. 进入商品详情并加入购物车
预期：登录成功、购物车角标变为 1
```

传统做法是人工把这些句子翻译成 Selenium/Playwright 脚本，成本高、易腐化；更常见的偷懒做法是“点一下执行，直接返回成功”——**接口是通的，但没有一行代码碰过浏览器**。本项目要实现的是：

1. **中文步骤能跑起来**：不要求测试同学写代码，也能在真实浏览器里执行；
2. **结果是可信的**：断言必须基于真实页面（URL／文本／元素数量），失败要说清“实际是什么”；
3. **有证据**：每一步的截图、整段录屏，能回答“这一步到底发生了什么”；
4. **不假装**：不能执行的步骤如实标注，而不是混进“通过率”里。

---

## 2. 技术栈

### 2.1 分层清单

| 层 | 技术 | 版本 | 用在哪 | 落地文件 |
|---|---|---|---|---|
| 浏览器自动化 | **Playwright**（Python Sync API） | 1.65.2 | 驱动 Chromium 执行、截图、录屏、断言 | `backend/app/ui_executor.py` |
| 浏览器 | Chromium（headless） | 随 Playwright | 每用例一个独立 context | 同上 |
| 语言 | Python | 3.12.14 | 编译、执行、批处理 | `backend/app/ui_*.py` |
| Web 框架 | FastAPI + Uvicorn | ≥0.115 / ≥0.30 | 执行接口、进度轮询、媒体下发 | `backend/app/routers/testing.py` |
| 数据校验 | Pydantic v2 | ≥2.8 | 请求模型（limit / maxWrite / caseIds / force） | `backend/app/schemas.py` |
| 存储 | PostgreSQL **JSONB 文档表** | 16（:55432） | `uiScripts` / `uiRuns` / `uiBatches` 集合 | `backend/app/store.py` |
| 业务库取证 | psycopg3 | ≥3.2 | 用 `/pay/{id}` 回查 `commerce.order.order_no` | `ui_batch_runner.py` |
| 媒体存储 | 本地文件系统 | — | `/tmp/ui-auto-media/{runId}/` | `backend/app/ui_media.py` |
| 媒体鉴权 | **HMAC-SHA256 签名 URL** | 标准库 | `<img>/<video>` 免 Header 加载 | 同上 |
| 并发 | `threading` + 进程内任务表 | 标准库 | 批量任务后台跑、前端轮询 | `ui_batch_runner.py` |
| 前端 | React 19 + Vite 8 + TS + Tailwind | — | 执行台、执行记录、批次详情 | `src/pages/project/Ui*.tsx` |
| 路由 | React Router | 7 | `webui/scripts`、`webui/runs/:runId` | `src/config/menu.ts` |
| 验收脚本 | Playwright + Python | 1.65.2 | 真实登录点页面，抓运行时异常 | `backend/probe_*.py` |

### 2.2 三个关键技术决策

**① 为什么是 Playwright，不是 Selenium / Cypress**

| 能力 | Playwright | Selenium | 说明 |
|---|---|---|---|
| 自动等待 | 内置（actionability 检查） | 需手写 `WebDriverWait` | 中文用例大多没有精确 wait，自动等待是刚需 |
| 定位语义 | `text=` / `has-text()` / `:has()` | 基本只有 CSS/XPath | “点击登录按钮”可直接映射文本定位 |
| 录屏 | `record_video_dir` 原生支持 | 需第三方（FFmpeg 拼帧） | 本项目的逐步回放靠它 |
| 多 context 隔离 | `browser.new_context()` 轻量 | 每会话一个 driver 进程 | 决定“1 浏览器 + N context”是否经济 |
| 失败现场 | 自动截图 + trace | 需自行补齐 | 失败归因成本差异明显 |

**② 为什么用 Sync API，而不是 async**

执行是**长阻塞**任务（一条用例 5~15s），放在 FastAPI 的 async 事件循环里会卡住其他请求。当前做法：接口层用同步函数（FastAPI 自动丢到线程池），批量任务再单独开线程，每个任务**独占**一个浏览器池。

> 踩过的坑：Playwright sync API 与创建它的线程绑定。若多个请求复用同一个 `Browser`，会抛 greenlet 跨线程错误。所以 `BrowserPool(isolated=True)` 为每个后台任务建独立池，任务结束即 `close()`。这条约束写在代码注释里，改并发逻辑前必须先读。

**③ 为什么中间要有一层「关键字 IR」，而不是直接生成代码 / 让 LLM 直接操作浏览器**

- **安全**：执行器只认 9 个白名单关键字（`nav/click/fill/select/check/assert/wait/scroll/screenshot`），不 `eval` 任何用户文本；
- **可审计**：编译结果是结构化 JSON，能存库、能看、能人工改，也能一键导出成可独立运行的 Python 脚本；
- **可移植**：IR 与框架解耦，将来换 JS 版 Playwright 或别的引擎，只需换一层 `to_playwright_script()`。

---

## 3. 设计思路（六条原则）

| # | 原则 | 具体表现 |
|---|---|---|
| 1 | **一次编译、处处复用** | 编译结果存 `uiScripts`（IR + 脚本），执行时不再“翻译”中文；页面刷新、批量重跑都复用同一份 |
| 2 | **关键字白名单** | 执行器只执行有限指令；未知关键字标记 `blocked` 并跳过，绝不“猜着点” |
| 3 | **诚实降级** | 抽象步骤（“按验收标准逐项核对”）编译为 `design_check`，明确说“这需要人工/API 断言”，不计入通过 |
| 4 | **资源复用 + 隔离** | 全局 1 个 Chromium 进程，每用例 1 个 context（cookie/localStorage 隔离），用完即关；空闲 300s 自动回收 |
| 5 | **默认留证** | 每步截图 + 整段视频 + 最终 URL + 页面文本摘要，失败还要保留失败瞬间的截图 |
| 6 | **有边界的执行** | 写操作配额（默认 3，页面默认 8）、5 GiB 媒体预算、失败快速终止、批量每 10 条落库一次 |

---

## 4. 执行链路

### 4.1 全景

```
┌─────────────────────── 平台前端 React 19（:8443）───────────────────────┐
│ 用例列表「运行」     用例脚本「单条执行 / 执行台」     执行记录「截图·视频」   │
└──────────┬─────────────────────────┬──────────────────────────────┬──────┘
           │ POST /ui/run-one        │ POST /ui/run-batch           │ GET /ui/runs
           │ （同步，5~15s）          │ + GET /ui/run-batch/{jobId}  │ /ui/batches/{id}
┌──────────▼─────────────────────────▼──────────────────────────────▼──────┐
│ FastAPI（:8000，前缀 /api/v1，Header 需 X-Project-Id: ecommerce）           │
│  ├─ run-one   ：编译一条 → 独占池执行 → 返回逐步证据                        │
│  └─ run-batch ：start_job() 起后台线程 → JOBS 内存表 → 前端 2.5s 轮询        │
└──────────┬───────────────────────────────────────────────────────────────┘
           │ 同一套内核：ui_batch_runner.execute_batch()
┌──────────▼─────────────┬──────────────────────┬──────────────────────────┐
│ 编译                    │ 执行                  │ 留证                      │
│ ui_step_compiler.py     │ ui_executor.py        │ ui_media.py               │
│ 中文 → IR → PO 展开     │ BrowserPool + 关键字   │ step_NN.png + video.webm  │
└─────────────────────────┴──────────┬───────────┴──────────────────────────┘
                                     │ Playwright 1.65（Chromium headless）
                          ┌──────────▼──────────┐    ┌───────────────────────┐
                          │ 尚品汇前端 :5174     │    │ shang-postgres :55434 │
                          │ （被测系统）          │    │ （订单号取证）          │
                          └─────────────────────┘    └───────────────────────┘
```

### 4.2 编译阶段：中文 → IR

`compile_case(case)` 做四件事：

1. **抽象步骤先拦截**（避免误编译）

   | 正则特征 | 归类 | 处理 |
   |---|---|---|
   | 按验收标准／逐项核对／构造场景 | `design_check` | 需业务专家给定位器 |
   | 查询总金额／核对库存／手工计算 | `db_verify` | 建议 API/DB 断言，非 UI 操作 |
   | 敏感字段／绕过／越权 | `security_probe` | 需专用数据与权限环境 |
   | 下单／支付／发货／完整业务操作 | `business_flow` | 建议拆成多个 PO 步骤 |

2. **Page Object 匹配**（命中就整体替换）

   `match_po(module, title)` 先按标题关键词、再按模块兜底，共 **14 个**可复用流程：
   登录 / 首页 / 商品搜索 / 商品详情 / 加购 / 购物车 / 结算 / 完整下单 / 收银台支付 / 订单列表 / 订单详情 / 售后 / 地址 / 收藏。

   命中后**整条用例的步骤被 PO 的真实操作序列替换**（含业务断言），原中文步骤保留在 `originalSteps` 里作为“测试意图”。
   原因：如果只把 PO 步骤追加在中文步骤后面，前面那些“输入正确账号密码”会编译成 `{{TEST_VALUE}}` 占位，永远处于“部分可执行”。

3. **未命中 PO 的用例走关键字编译**

   ```
   点击登录        → {"keyword":"click","args":{"locator":"button:has-text('登录')"}}
   输入手机号 xxx  → {"keyword":"fill","args":{"locator":"input[name='phone']","value":"xxx"}}
   验证登录成功    → {"keyword":"assert","args":{"expectation":"登录成功"}}
   ```

   语义定位器词典（`LOCATOR_HINTS`）把“登录按钮/用户名/密码/验证码/加入购物车/结算/提交…”映射成具体 selector，未识别的退化为 `text=` 匹配。

4. **产出四维统计**

   ```json
   {"total": 9, "executable": 9, "designChecks": 0, "unknown": 0,
    "ready": true, "uiRunnable": true,
    "pageObject": "登录流程", "writeFlow": false, "assertions": 2}
   ```

   `ready` 是“能直接跑且全部步骤可执行”，页面上「可直接执行」就是这个口径。

### 4.3 执行阶段：BrowserPool + 关键字

```python
browser, page, release = pool.acquire(video_dir=media_dir)   # 每用例一个 context
for i, step in enumerate(steps, 1):
    r = execute_step(page, step, i, base_url, delay_ms=300)  # 步骤间节流 300ms
    capture(page, media_dir, f"step_{i:02d}.png")            # 每步截图
    if r.status == "failed":
        break                                                 # 快速失败，不留无用截图
release()                                                     # 关 context，视频落盘
```

**定位策略（宽容）**：`page.locator(sel)` 先数一下 `count()`，为 0 直接判“找不到元素”，不抛框架异常；点击被浮层遮挡时（`intercepts pointer events`）自动降级为 `force=True` 再试一次——这是真实站点（抽屉、toast）最常见的失败原因。

**断言引擎（7 种 + 1 个降级）**

| kind | 判定 | 失败时的 detail（实际值） |
|---|---|---|
| `url` | 当前 URL 包含目标串 | `URL 应包含「/pay」，实际 http://…/cart` |
| `url_not` | 不包含 | `URL 不应包含「/login」，实际 …` |
| `text` | body 文本包含 | `页面未出现预期文本「下单成功」` |
| `no_text` | 不包含 | `页面出现了不应存在的文本「错误」` |
| `count` | 选择器数量 ≥ min | `元素「.item」数量 0 < 期望 1` |
| `regex` | 正则命中 | `页面未匹配到正则「订单号：\d+」` |
| `text_not_empty` | 正文 > 30 字 | `页面内容为空或过短` |
| （无 kind） | 语义断言降级 | 只校验页面存活，并在脚本里注明“需人工核对” |

**判定规则**

```
有 failed            → 失败（并保留失败步骤截图）
无 failed 有 blocked → 部分可执行（设计核对项 / {{TEST_VALUE}} 未填）
全部 passed          → 通过
```

### 4.4 留证阶段：截图、视频、签名 URL、5 GiB 淘汰

```
/tmp/ui-auto-media/
├── UR-1795258587/            ← 单条执行
│   ├── step_01.png … step_07.png   （1440×900，40~300 KB）
│   └── video.webm                  （800×500，0.1~0.3 MB/s）
└── UIJOB-1795255936084__TC-1001/   ← 批次里的某条用例
```

- **视频落盘时机**：Playwright 只有在 `context.close()` 后才把 webm 写盘，所以执行器在 `release()` 之后把随机文件名改成固定的 `video.webm`；
- **访问控制**：`<img>` / `<video>` 无法带 `Authorization` 头。用 `HMAC-SHA256(app_secret, "{runId}/{name}:{exp}")` 生成 12 小时有效的签名 URL；无签名/过期 403，文件不存在 404，`../` 穿越被拦；
- **容量策略**：`BUDGET_BYTES = 5 GiB`。每次执行结束按目录 mtime 从旧到新删，直到回到预算内；被删的 runId 在库里打 `mediaPruned=true`——**记录和结论保留，只是媒体没了**，前端显示“媒体已清理”而不是报错。

### 4.5 三个入口，一套内核

| 入口 | 接口 | 特点 |
|---|---|---|
| 单条执行 | `POST /ui/run-one` | 同步返回，编译一条 → 独占池跑完 → 直接带 stepShots/videoUrl；**写操作必须 `force=true`**，否则 409 |
| 批量执行 | `POST /ui/run-batch` → `GET /ui/run-batch/{jobId}` | 后台线程，返回 jobId 轮询；批次结束落 `uiBatches`，媒体目录名 `{batchId}__{caseId}` |
| CLI | `backend/run_ui_batch.py` | 与批量接口共用 `execute_batch()`，可出 JSON/Markdown 报告 |

批量执行的三个细节：

1. **轮转取样**：勾选/不限量时会按 Page Object 分桶轮转（`round_robin`），让有限条数覆盖多种真实路径，而不是同一流程刷 20 次；
2. **写操作配额**：`max_write` 用尽后，后续写操作用例进 `skipped`，理由写“写操作配额保护（避免耗尽演示库存/污染订单表）”；
3. **分段落库**：第 1 条、每满 10 条、最后一条各写一次 `uiBatches`，进程被杀也能留下已完成部分。

---

## 5. 使用手册

### 5.1 前置条件

| 服务 | 地址 | 说明 |
|---|---|---|
| 平台前端 | `http://127.0.0.1:8443` | Vite dev server |
| 平台后端 | `http://127.0.0.1:8000/api/v1` | 需 Header `X-Project-Id: ecommerce` |
| 被测站点 | `http://127.0.0.1:5174` | 尚品汇 C 端，**必须可访问**，否则全部步骤失败 |
| 平台库 | `127.0.0.1:55432/ai_test_platform` | JSONB 文档表 |
| 真实业务库 | `127.0.0.1:55434/shang` | 仅用于下单后回查订单号 |

```bash
# 后端（注意：改代码后要重启，当前未开 --reload）
cd backend && .venv/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
npm run dev

# 登录账号
zhangwei@corp.com / Admin@12345
```

### 5.2 入口 A：测试用例列表直接跑（最快验证）

1. 进入 **测试用例 → 用例列表**；
2. 看「自动化」列：`是`（绿）= 已转成脚本可执行，`否`（灰）= 无 UI 流程，运行按钮置灰；
3. 点某行「运行」→ 弹出执行窗 → 逐步显示每步状态 + 断言数；
4. 写操作用例（下单/支付）需先勾「允许真实写操作」。

> 这条路径背后调用的就是 `/ui/run-one`，与你写代码调 API 完全等价。

### 5.3 入口 B：用例脚本页（主力工作台）

页面分两块：

**① 单条用例执行**

- 搜索框支持 `TC-1001` / 标题 / 模块；
- 列表每行显示：`可执行步数/总步数`、`断言数`、`无 UI 流程`、`需补全`、`写操作` 标签；
- 选中一条 → 「运行这条用例」；勾选多条 → 「执行选中 N 条」（1 条同步、多条转批次）；
- 结果区出现「单条执行回放」：每步截图（点开放大）+ 视频播放器 + 断言明细 + 本次生成的脚本。

**② UI 自动化执行台**

| 控件 | 作用 |
|---|---|
| 编译功能测试用例 | 把功能用例编译成 IR + 脚本，落 `uiScripts`（已有则跳过） |
| 重新编译全部 | 覆盖重编（改了 PO/定位器后点这个） |
| 条数 / 写操作配额 | 批量上限（默认 120）/ 允许真实下单的条数（默认 8） |
| 批量真实执行 | 起后台任务，显示进度条 + `已完成/总数` + 当前用例 |
| 完成后 | 出现「查看批次详情」，跳到 `/webui/runs/{jobId}` 看逐条截图与视频 |

右上角有共享浏览器池状态灯：`运行中 / 空闲 / 未启动（首次执行自动拉起）`。

### 5.4 入口 C：执行记录页（看历史与证据）

- 5 张统计卡：执行总数、成功、失败、平均耗时、**媒体占用**（`x MB / 5.0 GB`）；
- 列表按开始时间**倒序**，一条批次只占一行：`批量执行 · 3 条 · 17 张 / 1 段`；
- 单条行 → 「详情」抽屉：逐步截图 + 视频 + 最终 URL + 页面文本摘要；
- 批次行 → 「查看批次」子页 `/webui/runs/{batchId}`：批次统计、用例表、失败明细、未执行原因。

### 5.5 入口 D：命令行（CI/回归）

```bash
# 批量跑 120 条，允许 8 条真实下单
backend/.venv/bin/python backend/run_ui_batch.py --limit 120 --max-write 8 --tag full

# 小样本验证（挑 8 条覆盖不同流程）
backend/.venv/bin/python backend/run_ui_sample.py

# 生成人类可读报告
backend/.venv/bin/python backend/gen_ui_run_report.py docs/traceability/ui-real-run-full.json
```

### 5.6 读结果：五种状态

| 状态 | 含义 | 该做什么 |
|---|---|---|
| 通过 | 所有步骤 passed，断言全过 | — |
| 部分可执行 | 没有失败，但有 `blocked` 步骤（设计核对项 / `{{TEST_VALUE}}` 未填） | 补定位器或测试数据，或在用例里写清具体值 |
| 失败 | 某步 `failed`，已快速终止 | 看该步截图 + `detail`（含实际值），先判断是脚本问题还是真 bug |
| 未执行 | 批次里 `executed == 0`（如只勾了不可自动化的用例） | 看「未执行」卡片的 reason |
| 执行中 | 批次 status=running | 刷新看进度；进程被杀则保留已完成部分 |

### 5.7 常见提示与处理

| 现象 | 原因 | 处理 |
|---|---|---|
| `409 这条用例会真实下单/支付，请勾选「允许真实写操作」` | 写操作用例未加 `force` | 勾选允许写操作，或改用只读用例 |
| `400 这条用例没有可执行的 UI 步骤` | 该用例只有业务规则描述，无 PO 匹配 | 在 `ui_page_objects.py` 补一个流程，或补全定位器 |
| `找不到元素：text=xxx` | 定位器不匹配当前前端 | 查截图确认页面结构 → 改 PO 定位器 → 重新编译 |
| `点击失败（元素存在但不可交互）` | 被抽屉/遮罩挡住，`force` 也没成 | 在 PO 里先关弹窗（通常是作者漏了一步“关闭规格抽屉”） |
| 执行记录显示「媒体已清理」 | 超过 5 GiB，旧目录被淘汰 | 正常行为；结论仍保留。需要证据请重跑 |
| 截图/视频打不开，403 | 签名 URL 过期（12 小时） | 刷新执行记录页重新签名 |
| 批次显示「未执行」 | 勾选的用例都没转成自动化 | 看批次详情里的「未执行」卡片，按 reason 处理 |

---

## 6. 代码地图

| 文件 | 职责 | 改这里会影响到 |
|---|---|---|
| `backend/app/ui_step_compiler.py` | 中文 → 关键字 IR；抽象步骤分类；导出 Python 脚本 | 编译结果、`ready` 统计 |
| `backend/app/ui_page_objects.py` | 12 个可复用流程 + 演示数据；`match_po()` 匹配规则 | 用例命中率与真实路径 |
| `backend/app/ui_executor.py` | `BrowserPool`、关键字执行、断言引擎、逐步截图/录屏 | 所有执行行为 |
| `backend/app/ui_media.py` | 媒体落盘、签名 URL、5 GiB 淘汰、`mediaPruned` 标记 | 证据访问与磁盘占用 |
| `backend/app/ui_batch_runner.py` | 编译落库、轮转取样、写配额、批次落库、后台任务 | 批量行为与批次数据 |
| `backend/app/routers/testing.py` | `/ui/*` 全部接口（run-one / run-batch / runs / batches / media） | 前端契约 |
| `src/pages/project/UiScripts.tsx` | 单条执行 + 执行台 + 脚本查看 | 工作台交互 |
| `src/pages/project/UiRuns.tsx` | 执行记录列表 + 单条抽屉 | 结果查看 |
| `src/pages/project/UiRunBatch.tsx` | 批次详情子页 | 批次下钻 |
| `src/pages/project/CaseList.tsx` | 自动化列 + 运行门控 + 执行弹窗 | 用例列表入口 |

---

## 7. 扩展指南

**① 加一个关键字（例如 `hover`）**

1. `ui_step_compiler.py::RULES` 加一条中文规则并产出 `keyword="hover"`；
2. `ui_executor.py::execute_step` 加分支（`loc.first.hover(timeout=6000)`）；
3. `to_playwright_script()` 加对应代码生成；
4. 跑 `probe_single_run_ui.py` 回归一条用例。

**② 加一个业务流程图（PO）**

```python
def flow_coupon() -> list[PoStep]:
    return [
        *flow_login(),
        nav("/coupons", "进入优惠券页"),
        click(".coupon-claim", "领取优惠券"),
        assert_text("领取成功", "断言领取提示"),
    ]

# 再在 TITLE_RULES 最前面加规则（注意：先具体后宽泛）
(["优惠券", "领券"], "优惠券流程", flow_coupon),
```

改完点执行台「重新编译全部」，再到 `/ui/cases` 确认该用例 `ready=true`。

**③ 加一种断言**

`_run_assert()` 增加 `kind` 分支 + `to_playwright_script()` 同步生成 `assert` 语句（两处必须一致，否则“页面能跑、导出脚本跑不了”）。

**④ 换被测系统**

改 `ui_page_objects.py::BASE_URL` 与各 PO 的定位器；`ui_media` / 执行器无需改动。

---

## 8. 边界与已知限制（诚实清单）

| # | 限制 | 影响 | 备注 |
|---|---|---|---|
| 1 | 74/363 条功能用例没有 PO，无法执行 | 「自动化」列显示“否” | 因为它们是业务规则/权限/数据一致性用例，本就不该用 UI 跑 |
| 2 | 「元素库」未参与编译 | 改了元素库不会影响执行 | 目前只是登记与浏览；PO 用硬编码 locator。要打通需在 `_locator_for()` 里接 `uiElements` |
| 3 | 「录制回放」是前端模拟 | 不会生成真实脚本 | 页面用定时器回放固定 5 条示例；真实链路是「用例 → 编译 → 执行」。接 Playwright `codegen` 是后续可选项 |
| 4 | 任务表在进程内存（`JOBS`） | 后端重启丢进度；多实例不共享 | 单机演示够用；上多实例需换 Redis/DB |
| 5 | 媒体放 `/tmp` | 系统清理/重启后丢失 | 只保留 5 GiB，结论与步骤状态不受影响 |
| 6 | 串行执行 | 120 条约 15~20 分钟 | `max_concurrency` 已预留但默认 1；并发要考虑站点承受力与写操作互斥 |
| 7 | 无重试、无 CI 集成 | 抖动失败需人工重跑 | 失败详情足够定位；必要时接 Jenkins/GitLab CI 跑 CLI |
| 8 | 写操作真实落库 | 会产生真实订单、消耗库存 | 配额保护 + `force` 双闸；演示环境可接受 |
| 9 | 语义断言只校验“页面存活” | 中文预期结果无法精确验证 | 精确断言需 PO 里写成 `text/url/count` |

---

## 9. 附录

### 9.1 接口一览

| 方法 | 路径 | 说明 |
|---|---|---|
| POST | `/ui/compile` | 编译指定/全部功能用例，落 `uiScripts`（`overwrite` 控制覆盖） |
| POST | `/ui/compile-all` | 重新编译全部（PO 改动后用） |
| GET | `/ui/compile/{caseId}` | 看单条编译结果（IR + 脚本） |
| GET | `/ui/cases` | 用例索引：`ready` / `uiRunnable` / `writeFlow` / 步数 / 断言数 |
| POST | `/ui/run-one` | 单条同步执行（写操作需 `force`） |
| POST | `/ui/run-cases` | 已编译脚本批量执行（同步，少量） |
| POST | `/ui/run-batch` | 批量后台任务，返回 `jobId` |
| GET | `/ui/run-batch/{jobId}` | 轮询进度 / 取完整结果 |
| GET | `/ui/runs` | 执行记录（单条 + 批次合并倒序）+ `stats` + `media` |
| GET | `/ui/batches/{batchId}` | 批次明细（逐条用例 + 媒体 URL） |
| GET | `/ui/media/{runId}/{name}?k=` | 截图/视频（签名 URL，支持 Range） |
| GET | `/ui/media-stats` | 媒体占用 / 预算 |
| GET | `/ui/pool-status` | 浏览器池状态（`browserAlive` / `activeContexts` / `idleSeconds`） |
| GET | `/ui/scripts` | 已编译脚本库 |

### 9.2 数据模型（JSONB 文档）

**`uiScripts`**：`id=US-{caseId}`、`caseId`、`ir`（编译结果）、`content`（可导出脚本）、`status`（启用/部分可执行/待补全）。

**`uiRuns`（单条）**：`id`、`caseId`、`verdict`、`steps[]`（`index/raw/keyword/status/detail/durationMs/shot`）、`assertions/assertionsPassed`、`finalUrl`、`pageText`、`orderNo`、`media{dir,video,bytes,steps[]}`、`startedAtMs`、`durationMs`、`mediaPruned`。

**`uiBatches`（批次）**：`id`、`status(running/finished)`、`total/executed/passed/failed/partial/skippedCount`、`passRate`、`writeExecuted`、`mediaBytes`、`results[]`、`failures[]`、`skippedCases[]`、`byPageObject{}`、`startedAtMs/finishedAtMs`。

### 9.3 术语

| 术语 | 含义 |
|---|---|
| **IR** | 中间表示，`{keyword, args, raw, confidence, note}`，执行器唯一认识的格式 |
| **PO / Page Object** | 可复用业务流程（如“登录流程”），由多步真实 UI 操作 + 断言组成 |
| **design_check** | 抽象步骤的分类结果：不是 UI 操作，不计入可执行步数 |
| **runId** | 一次执行（单条或批次中的一条）的目录名，也是媒体寻址键 |
| **写操作配额** | 允许真实下单/支付的条数上限，防止污染订单表与库存 |
| **签名 URL** | 带过期时间与 HMAC 校验的媒体地址，供 `<img>/<video>` 免 Header 访问 |

---

## 10. 当前实测基线（2026-11-21）

| 指标 | 数值 |
|---|---|
| 功能用例总数 | 363 |
| 可直接执行（`ready`） | 289 |
| 写操作用例 | 60 |
| 无 UI 流程用例 | 74 |
| 历史执行记录 | 295 条（单条 292 + 批次 3），通过 283 / 失败 7，平均 6.9s |
| 媒体占用 | 13.7 MB / 5.0 GB |
| PO 覆盖 Top5 | 商品详情 76、订单列表 55、收银台支付 37、商品搜索 28、完整下单 23 |

> 复现方式：`GET /ui/cases`、`GET /ui/runs`、`GET /ui/media-stats`（Header 带 `X-Project-Id: ecommerce`）。
