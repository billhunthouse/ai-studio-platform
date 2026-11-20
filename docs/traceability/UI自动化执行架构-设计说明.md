# UI 自动化执行架构设计说明

> 目标：把功能测试用例的中文步骤转化为可复用、可真实执行的 Playwright 脚本；
> 点击执行即在真实前端（尚品汇 127.0.0.1:5174）上跑，步骤间 300ms 延时。
> 架构原则：**一次编译、处处复用；共享资源、按需回收；诚实标注、不伪造自动化**。

---

## 1. 现状与目标

### 1.1 改造前的假实现
- `POST /ui/runs` 永远返回 `result="成功", shots=3, duration="36s"`——纯造假，不接触浏览器。
- 元素库只有 4 个名字、locator 全空，无法作为定位来源。
- 399 条功能测试用例步骤是中文自然语言，其中 350 条来自测试工程师 AGENT，
  步骤多为抽象描述（"按验收标准构造场景"、"逐项核对验收标准"），
  **本质上不是 UI 操作指令**。

### 1.2 目标
| 维度 | 要求 | 实现 |
|---|---|---|
| 真实执行 | 点击执行跑真实浏览器 | Playwright Chromium → 尚品汇前端 |
| 节流 | 步骤间 300ms | 执行器统一 `wait_for_timeout(300)` |
| 不浪费资源 | 避免每用例启停浏览器 | 共享浏览器池：1 browser + N 临时 context |
| 可复用 | 脚本可编辑、导出、重跑 | 编译产物落 `uiScripts`，IR 与实现解耦 |
| 诚实 | 不能执行的明确标注 | 抽象步骤分类为 design_check，不伪装成通过 |

---

## 2. 分层架构

```
功能测试用例（中文步骤 + 预期）
        ↓ 编译一次
步骤编译器 ui_step_compiler.py
   中文 → 关键字 IR（nav/click/fill/assert…）
        ↓ 生成
Playwright 脚本 → uiScripts（可编辑/导出/复用）
        ↓ 执行
执行引擎 ui_executor.py
   ├─ 关键字执行器：只认有限关键字，不 eval 任意代码
   ├─ BrowserPool：1 browser + N context（共享、空闲回收）
   └─ 节流：步骤间 300ms，失败快速终止 + 截图
        ↓ 回写
uiRuns 执行记录 + 用例 lastRun + 详情页步骤轨迹
```

### 2.1 步骤编译器（`backend/app/ui_step_compiler.py`）
- **关键字 IR** 是中间层：与具体浏览器框架解耦，同一 IR 未来可生成 JS/其他框架脚本。
- 12 类关键字：`nav / click / fill / select / check / assert / wait / scroll / screenshot / design_check`。
- 中文规则匹配：正则 + 语义定位器词典（"登录按钮" → `button:has-text('登录')`）。
- **抽象步骤分类**（关键设计）：不把"按验收标准核对"硬转成假点击，而是分四类标注：
  - `design_check`：验收核对项，需业务专家补全定位器；
  - `db_verify`：数据校验项，建议 API/DB 断言（非 UI 操作）；
  - `security_probe`：安全探测项，需专用数据与权限环境；
  - `business_flow`：业务主流程，建议拆成多个页面对象步骤。
- 编译结果含 `ready / uiRunnable / designChecks / unknown` 四维统计，诚实反映可执行度。

### 2.2 共享浏览器池（`backend/app/ui_executor.py::BrowserPool`）
- **单例**：全局 1 个 Chromium 进程，避免最昂贵的启停操作。
- **context 隔离**：每条用例一个独立 `browser.new_context()`（cookie/localStorage 隔离），
  用完立即 `close()`，`activeContexts` 计数受控。
- **空闲回收**：`idle_ttl=300s`，空闲超时且无活动 context 时自动关浏览器。
- **可观测**：`GET /ui/pool-status` 返回 `browserAlive / activeContexts / idleSeconds`。
- 失败自动截图（仅失败时写盘），成功不产生文件。

### 2.3 关键字执行器
- 只执行编译后的有限关键字，不执行用户自由输入的任意代码（安全边界）。
- 每个关键字超时受控（click 5s / nav 10s），失败快速终止当前用例，不浪费后续步骤。
- 步骤间统一 `waitForTimeout(300)`；`wait` 关键字自身已等待时不重复。
- 定位失败返回 `failed` 并给出具体 locator，便于补全。

---

## 3. 数据模型

| 集合 | 新增字段 | 用途 |
|---|---|---|
| `uiScripts` | `caseId`, `caseTitle`, `ir`, `framework="Playwright · 关键字驱动"`, `status` | 编译产物，可编辑复用 |
| `uiRuns` | `caseId`, `verdict`, `steps[]`, `screenshot`, `duration` | 真实执行记录（替代原假数据） |
| `testCases` | `lastRun{mode:"ui", verdict, at}` | 用例页展示最近一次 UI 执行结果 |

---

## 4. API 设计

| 端点 | 方法 | 说明 |
|---|---|---|
| `/ui/compile` | POST | 批量编译功能用例→IR+脚本；`caseIds` 空=全部，`overwrite` 控制重编译 |
| `/ui/compile/{case_id}` | GET | 查看单条编译结果（IR + 脚本源码） |
| `/ui/run-cases` | POST | 共享浏览器池执行；`caseIds` 指定用例，`delayMs` 默认 300 |
| `/ui/pool-status` | GET | 浏览器池资源状态 |

---

## 5. 前端交互

- **Web UI 自动化 → 用例脚本页**：新增执行台（编译按钮 / 执行按钮 / 四类统计 / 用例列表 / 步骤轨迹 / 脚本编辑器），
  替换原"运行永远成功"的假逻辑。
- **测试用例详情页**：功能用例执行面板新增「编译并自动执行」按钮，
  展示每个步骤的关键字与状态（通过/失败/待补全），并把结果回写 `lastRun`。

---

## 6. 实测结论（2026-11-20）

- Playwright 1.65.2 + Chromium Headless Shell 159 安装完成（用清华 PyPI 镜像 + npmmirror 浏览器镜像）。
- 真实打开尚品汇首页成功（标题"首页"，正文含"亲，请登录/购物车/我的订单"等）。
- 全量编译 **363 条**功能用例：363 条都有 UI 可执行步骤；
  其中 191 条为 AGENT 生成的"验收标准核对"类，步骤本身是检查清单，
  标注为 `design_check`，**不伪造为可执行 UI 脚本**。
- 批量执行 TC-1001/TC-1002：真实浏览器执行，步骤级结果如实返回
  （TC-1001 部分可执行——"输入正确账号密码"缺具体值；TC-1002 失败——click 前无导航步骤）。
- 导出的脚本可独立 `python xxx.py` 运行，输出 `{"caseId":…, "verdict":…}` JSON。
- 浏览器池：执行后 `browserAlive=true, activeContexts=0`——浏览器进程复用、context 已释放。

## 7. 后续增强方向
1. 元素库补全 locator（当前为空），让 `design_check` 用例可逐步转为可执行；
2. 引入 Page Object 层，把"登录/下单/结算"等高频流程沉淀为可复用页面对象；
3. `db_verify` 类步骤接入 API/DB 断言执行器，与 UI 执行器并列；
4. 并发执行：在共享池基础上增加 `max_concurrency`，用 `asyncio` + 多 context 并行。
