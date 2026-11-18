# Figma 交接与操作手册

> 目标：把代码现状变成 Figma 可评审的 Baseline Snapshot，再用 Figma AI（Design / Make）完成专业化改版，最后回到代码实现。

## 0. 当前环境结论

| 项目 | 状态 |
|---|---|
| Figma 桌面端 | 已登录（bill / 17863026867@163.com） |
| Figma Dev Mode MCP | 已监听 `127.0.0.1:3845`，可读取设计 → 代码 |
| 远程 Figma MCP（Code to canvas） | ZCode 内 OAuth 被 Figma 拒绝：`Dynamic Client Registration rejected (HTTP 403)` |
| 本地基线截图 | 44 张，1440×900，已生成在 `design/baseline/screens/` |
| 设计 Token | 当前版 `design/tokens.baseline.json`；目标版 `design/tokens.proposed.json` |
| 组件清单 | `design/component-inventory.md` |
| 页面清单 | `design/page-inventory.md` |

**重要**：本地 Dev Mode MCP 只提供“Figma → 代码”的工具（`get_design_context`、`get_variable_defs`、`get_code_connect_map` 等），**没有** `generate_figma_design`。所以 Code to canvas（代码 → Figma）必须走远程 Figma MCP，或改用下面的“截图基线”方案。

## 1. 推荐执行顺序

```
① 新建 Figma 文件
② 放入 Baseline Snapshot（截图或 Code to canvas）
③ 导入目标 Tokens
④ 先重绘 3 个基准页：工作台 / 需求列表 / 需求详情
⑤ 批准 3 页后，再扩展组件和其余页面
⑥ 用 Figma Make 做 1 个交互原型验证
⑦ 标记 approved/v1.0，回写代码
```

不要一上来重绘 44 页；先把 3 个基准页做对，后面都是套模板。

## 2. 方案 A：Code to canvas（推荐，但需要支持的 MCP 客户端）

如果使用 Claude Code / Cursor 等支持 Figma 远程 MCP 的客户端：

1. 在客户端中配置 Figma Remote MCP Server：`https://mcp.figma.com/mcp`，完成 OAuth 登录。
2. 在 Figma 桌面端新建一个 Design 文件，例如 `AI Test Platform — Baseline Snapshot v1`，保持打开。
3. 在支持 MCP 的客户端中执行 `design/figma-ai-prompts.md` 的 **Prompt 1**。
4. 捕获完成后，检查：
   - 页面是否按 `00 Cover / 01 Global / 02 Project Core / 03 Automation / 04 AI & Knowledge / 05 Admin` 分组。
   - 每个 Frame 是否命名 `S01 / 登录 / default`。
   - 文件说明是否标记 `Baseline Snapshot — not a design system`。
5. 如果客户端不支持 Code to canvas，跳到方案 B。

> 当前 ZCode 的远程 MCP OAuth 失败，所以这一步可能需要在 Claude Code / Cursor 中完成，或者等 Figma 侧 OAuth 配置修复后再由我执行。

## 3. 方案 B：截图基线（现在就能做）

### 3.1 新建文件

1. Figma 桌面端 → `File` → `New design file`。
2. 命名为 `AI Test Platform — Baseline Snapshot v1`。
3. 放在 `Drafts`，不要放在团队正式文件里。
4. 在文件描述中写：
   ```
   Baseline Snapshot — not a design system.
   Captured from code on 2026-11-16, 1440×900, commit 83aa7b9.
   ```

### 3.2 建页面

在左侧 Pages 面板建立：

```
00 Cover
01 Baseline / Global
02 Baseline / Project Core
03 Baseline / Automation
04 Baseline / AI & Knowledge
05 Baseline / Admin
10 Redesign
11 Components
12 Prototype (Make)
```

### 3.3 放入截图

**封面**：

1. 打开 `00 Cover`。
2. 把 `design/baseline/contact-sheet.svg` 拖入画布，或 `File > Place image` 选择它。
3. 缩放到适合画布，命名为 `Baseline Contact Sheet`。

**分组页面**：

1. 打开 `01 Baseline / Global`。
2. 把对应截图从 Finder 拖入，或 `File > Place image` 多选。
3. 每张图：
   - 建立 Frame（`Cmd+Option+G`），尺寸保持 1440×900。
   - 图层命名：`S02 / 工作台 / default`。
   - 图片填充设为 `Fill`，不要拉伸变形。
4. 用 Auto Layout 排成网格：间距 32px，外边距 48px。
5. 每个分组页顶部加一个 28px 标题文本，例如 `Global / 10 screens`。

**分组对应关系**：

| 页面 | 截图 |
|---|---|
| 01 Baseline / Global | S01–S02、S29–S37 |
| 02 Baseline / Project Core | S03–S08 |
| 03 Baseline / Automation | S09–S19 |
| 04 Baseline / AI & Knowledge | S20–S28 |
| 05 Baseline / Admin | S38–S44 |

> 截图是扁平图层，符合文档对 Baseline Snapshot 的定义：用于评审、标注和迭代起点，不是可维护的设计系统。

### 3.4 标记

- 文件顶部放一个红色/琥珀色标签：`BASELINE — NOT APPROVED`。
- 每个 Frame 加一个小标签：`现状 / 1440×900`。
- 不要在这个文件里直接做优化；优化稿放到 `10 Redesign`。

## 4. 导入目标 Tokens

### 4.1 Tokens Studio（推荐）

1. 安装 Figma 插件 `Tokens Studio for Figma`。
2. 在插件中选择 `Import` → `JSON`，导入 `design/tokens.proposed.json`。
3. 创建 Token Set：`precision-workspace`。
4. 应用到 `10 Redesign` 页面；不要覆盖 Baseline。
5. 在 Figma 中只做 Pull / 应用，不要单方面改 Token 值；需要改先回到 `tokens.proposed.json` 走评审。

### 4.2 手动 Variables

如果不用 Tokens Studio：

1. Figma 右侧 `Variables` → `Create collection`：`Precision Workspace`。
2. 按 `tokens.proposed.json` 建立 Color / Number / String 变量。
3. 命名与 JSON 路径一致，例如 `color/brand/primary`。
4. 组件绑定 Variables，不要硬编码 Hex。

## 5. Figma AI Design 模式

### 5.1 先做 3 个基准页

在 `10 Redesign` 页面建立 3 个 1440×900 Frame：

1. `Redesign / 工作台 / default`
2. `Redesign / 需求列表 / default`
3. `Redesign / 需求详情 / default`

### 5.2 使用方式

1. 选中 Baseline 的工作台 Frame，复制到 `10 Redesign` 右侧作为参考。
2. 打开 Figma AI（Design / First Draft）。
3. 粘贴 `design/figma-ai-prompts.md` 的 **Prompt 2**。
4. 生成后不要接受整页；按区块保留/替换：
   - 顶栏 + 侧栏
   - 页面头
   - 指标卡
   - 图表卡
   - 待办/动态
5. 用 `11 Components` 里的组件替换 AI 生成的重复元素。
6. 同样的 Prompt 改页面名，重复到需求列表、需求详情。

### 5.3 批准标准

- 使用 `tokens.proposed.json` 的颜色/字号/间距。
- 有明确的页面标题、区块标题、正文、辅助文字层级。
- 主操作唯一；次要操作降级。
- 表格/列表有空、加载、错误状态。
- 1280px 下主任务可完成。
- 不改变任何业务动作。

## 6. Figma Make 模式

Make 适合做“可点击的验证原型”，不是生产代码。

1. 从批准的工作台 Frame 创建 Make 文件，或新建 Make 项目。
2. 粘贴 `design/figma-ai-prompts.md` 的 **Prompt 3**。
3. 只做 1 个流程：工作台 → 需求列表 → 需求详情 → 生成用例。
4. 用假数据，不接后端。
5. 验证：
   - 导航是否清楚。
   - 表格/详情的信息密度是否可读。
   - 空/加载/错误状态是否成立。
6. 把 Make 原型链接附在批准记录里；不要直接把 Make 代码合并进生产。

## 7. 批准与回写代码

### 7.1 命名

```
approved/v1.0 / 工作台 / default
approved/v1.0 / 需求列表 / default
approved/v1.0 / 需求详情 / empty
approved/v1.0 / 需求详情 / populated
```

### 7.2 变更单

每个批准帧记录：

- 修改原因
- 影响页面/组件/状态
- Figma 帧链接
- 负责人 / 批准日期
- 使用了哪些 Token
- 与 Baseline 的差异摘要

### 7.3 回写顺序

1. 先更新 `design/tokens.baseline.json` → 代码 Token。
2. 再改基础组件（Button / Input / Tag / Card / Table）。
3. 再改 3 个基准页。
4. 最后批量套用其余页面。
5. 每步跑 `pnpm exec tsc --noEmit`、`pnpm test`、`pnpm build`，并做截图回归。

## 8. 你现在需要做的 5 件事

1. **保持 Figma 登录**（当前已是 bill 账号）。
2. **新建一个 Design 文件**：`AI Test Platform — Baseline Snapshot v1`，放在 Drafts。
3. **选择基线方式**：
   - 有 Claude Code / Cursor：用方案 A，执行 Prompt 1 自动捕获。
   - 没有：用方案 B，把 `design/baseline/screens/` 的截图拖进 Figma，按 `00–05` 分组。
4. **导入 Tokens**：用 Tokens Studio 导入 `design/tokens.proposed.json`。
5. **先做 3 页**：工作台、需求列表、需求详情；完成后把 3 个 Frame 链接发我，我再进入代码实现。

## 9. 我可以继续替你做什么

- 你给出 Figma 文件链接后，我可以：
  - 读取 Figma 的设计上下文（当前 Dev Mode MCP 已可用）。
  - 检查 Frame 是否使用了目标 Token、组件是否复用。
  - 输出逐页的代码实现计划和差异清单。
- 你也可以把 Figma AI 生成的结果截图发我，我做设计评审（层级、密度、状态、可访问性）后再进入开发。

## 10. 常见问题

**Q：为什么不能直接用 ZCode 把页面写进 Figma？**  
A：ZCode 配置的远程 Figma MCP 在 OAuth 阶段被 Figma 拒绝（403）；本地 Dev Mode MCP 只有“读 Figma”的工具，没有 Code to canvas。需要支持的客户端完成 OAuth，或使用截图基线。

**Q：截图基线是“设计稿”吗？**  
A：它是 Baseline Snapshot，是评审和优化的起点，不是最终设计系统。最终以 `10 Redesign` 的 approved 帧为准。

**Q：Figma AI 生成后可以直接开发吗？**  
A：不行。先按 `component-inventory.md` 收敛组件和 Token，再按 `approved/v1.0` 帧开发；否则会生成第二套无法维护的 UI。

**Q：会不会改坏现有功能？**  
A：本轮只做视觉和布局，不改路由、数据、接口和业务动作。代码实现阶段会按页面逐步替换并跑回归。
