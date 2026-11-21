---
version: alpha
name: AI Test Platform — Precision Workspace
description: 面向测试开发团队的企业级 AI 工作台。核心气质是冷静、精确、高信号密度；不是消费级 SaaS 的轻快风格，也不是传统后台的灰色表格堆叠。
colors:
  primary: "#2D5BFF"
  primary-hover: "#1F46E0"
  primary-subtle: "#EEF3FF"
  ai-accent: "#0891B2"
  canvas: "#F5F7FB"
  surface: "#FFFFFF"
  nav: "#0B1220"
  text-primary: "#0F172A"
  text-secondary: "#475569"
  text-muted: "#64748B"
  border: "#E2E8F0"
  success: "#0E9F6E"
  warning: "#D97706"
  danger: "#E11D48"
typography:
  body:
    fontFamily: Inter, Geist, PingFang SC, Microsoft YaHei, sans-serif
    fontSize: 14px
    fontWeight: 400
    lineHeight: 1.5
  table:
    fontFamily: Inter, Geist, PingFang SC, Microsoft YaHei, sans-serif
    fontSize: 13px
    fontWeight: 400
    lineHeight: 1.4
  label:
    fontFamily: Inter, Geist, PingFang SC, Microsoft YaHei, sans-serif
    fontSize: 12px
    fontWeight: 500
    lineHeight: 1.4
  page-title:
    fontFamily: Inter, Geist, PingFang SC, Microsoft YaHei, sans-serif
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.2
  metric:
    fontFamily: Inter, Geist, PingFang SC, Microsoft YaHei, sans-serif
    fontSize: 28px
    fontWeight: 600
    lineHeight: 1.2
rounded:
  sm: 6px
  md: 8px
  lg: 10px
  xl: 12px
  full: 9999px
spacing:
  xs: 4px
  sm: 8px
  md: 12px
  lg: 16px
  xl: 24px
  2xl: 32px
  3xl: 48px
components:
  button-primary:
    backgroundColor: "{colors.primary}"
    textColor: "#FFFFFF"
    rounded: "{rounded.md}"
    height: 32px
    padding: 0 12px
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-secondary}"
    border: "1px solid {colors.border}"
    rounded: "{rounded.md}"
    height: 32px
  card:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.border}"
    rounded: "{rounded.lg}"
    padding: 20px
  input:
    backgroundColor: "{colors.surface}"
    border: "1px solid {colors.border}"
    rounded: "{rounded.md}"
    height: 32px
  tag:
    rounded: "{rounded.sm}"
    padding: 2px 6px
---

# AI 测试开发平台 — Precision Workspace

## 1. 设计意图

这是一个每天要被测试开发、评审、管理者使用数小时的**工作台**。设计目标不是“看起来像 AI 产品”，而是：

1. **高信号**：用户 3 秒内知道当前项目、当前任务、下一步动作。
2. **可扫描**：表格、需求树、执行报告在 1280–1600px 宽度下保持清晰。
3. **可信**：AI 生成、自动执行、审计、权限这些能力要显得可控，而不是炫技。
4. **一致**：页面骨架、状态语义、组件行为统一，降低学习成本。

关键词：**冷静、精确、克制、可追溯**。

## 2. 品牌与视觉方向

### 推荐方向：Precision Workspace

- **深石墨顶栏 + 冷白画布 + 钴蓝主色**。顶栏承担品牌和全局导航，内容区保持高对比与低噪声。
- **AI 能力用青色作为辅助强调**，只出现在生成、自动化、智能建议相关入口，不大面积铺色。
- **数据用等宽数字**，指标、耗时、Token、通过率使用 `font-variant-numeric: tabular-nums`。
- **弱化渐变**。主视觉可以用一次低饱和度渐变或网格纹理，但页面内不重复使用。
- **图标线性、1.5px 描边、16/20px 两档**；不要用 emoji。

### 不建议

- 全站深色霓虹风：长时间阅读疲劳，且与“企业测试平台”的信任感冲突。
- 大面积紫色 AI 渐变：容易变成模板化 AI 产品。
- 过度圆角、玻璃拟态、悬浮光晕。

## 3. 色彩系统

| 角色 | Token | 值 | 用法 |
|---|---|---|---|
| 主色 | `color.brand.primary` | `#2D5BFF` | 主按钮、选中、链接、焦点 |
| 主色悬停 | `color.brand.primaryHover` | `#1F46E0` | hover / pressed |
| 主色浅底 | `color.brand.primarySubtle` | `#EEF3FF` | 选中背景、信息提示 |
| AI 强调 | `color.brand.ai` | `#0891B2` | AI 生成、自动化、智能建议 |
| 画布 | `color.surface.canvas` | `#F5F7FB` | 页面背景 |
| 卡片 | `color.surface.default` | `#FFFFFF` | 内容容器 |
| 顶栏 | `color.surface.nav` | `#0B1220` | 全局导航 |
| 主文本 | `color.text.primary` | `#0F172A` | 标题、关键数字 |
| 次文本 | `color.text.secondary` | `#475569` | 正文、说明 |
| 弱文本 | `color.text.muted` | `#64748B` | 辅助信息、占位 |
| 边框 | `color.border.default` | `#E2E8F0` | 卡片、输入、分隔 |
| 成功 | `color.status.successFg` | `#0E9F6E` | 通过、完成、在线 |
| 警告 | `color.status.warningFg` | `#D97706` | 待处理、风险 |
| 危险 | `color.status.dangerFg` | `#E11D48` | 失败、删除、P0 |

规则：

- 一个视图内最多出现 **1 个主色按钮**；其他操作使用 secondary / ghost / text。
- 状态色只用于状态，不用于装饰。`P0` 用危险色，`P1` 用警告色，`P2` 用信息色或中性色。
- 正文对比度至少 4.5:1；弱文本不低于 `#64748B`，不要使用 `slate-400` 作为正文。

## 4. 字体与排版

- 字体：`Inter` / `Geist`，中文回落 `PingFang SC` / `Microsoft YaHei`。
- 代码、ID、路径、JSON：`JetBrains Mono` / `SFMono-Regular`。
- 基础字号从当前的 12px 提升到 **14px 正文 / 13px 表格 / 12px 标签**。这是“专业化”最直接的一步。
- 页面标题 28px，区块标题 16–20px，指标 28–36px；不要用 16px 冒充页面标题。
- 行高：正文 1.5，表格 1.4，标题 1.2–1.3。
- 数字使用 tabular-nums，保证表格纵向对齐。

## 5. 布局

### 桌面基准（1440×900）

- 顶栏 56px；侧栏 232px；内容区内边距 24px；宽屏 32px。
- 内容最大宽度 1600px，超出后居中，不要让表格无限拉伸。
- 12 列网格，间距 16/24px；卡片间距 16px；页面区块间距 24px。
- 列表页：页面头（标题 + 描述 + 主操作）→ 筛选条 → 表格/卡片。
- 详情页：左侧 320px 固定信息栏 + 右侧自适应工作区；移动端折叠为顶部摘要。
- 编排页：节点库 240px | 画布自适应 | 配置面板 320px。
- 对话页：会话列表 280px | 消息区自适应 | 可选知识库上下文 300px。

### 响应式

- `>= 1440`：完整三栏/双栏。
- `1024–1439`：侧栏收窄到 200px，隐藏次要列。
- `768–1023`：侧栏抽屉化，表格横向滚动，详情页上下堆叠。
- `< 768`：单列；表格转卡片列表；主操作固定在底部安全区。

## 6. 组件规则

### Button

- `primary`：钴蓝实底，白字，32px 高；一个区域最多一个。
- `secondary`：白底、1px 边框；用于取消、次要操作。
- `ghost`：无边框，hover 浅底；用于表格行内、工具栏。
- `danger`：危险色文字或浅底；删除必须二次确认。
- 状态：default / hover / active / focus-visible / disabled / loading。loading 时保留宽度，左侧 14px spinner。

### Input / Select / Textarea

- 高度 32px（大号 36/40px）；圆角 8px；边框 `#E2E8F0`。
- focus：边框主色 + 3px 主色 18% 外发光。
- error：危险色边框 + 12px 错误文案；不要只靠颜色。
- 必填、帮助文本、字符计数放在固定位置，避免布局跳动。

### Table

- 行高 48px；表头 40px；表头背景 `#F8FAFC`；分隔线 `#F1F5F9`。
- 首列左对齐，数字右对齐，状态居中或左对齐；操作列固定在右侧。
- 行 hover 使用主色 4% 背景；选中行使用主色 8%。
- 空状态：插图/图标 + 一句解释 + 一个主操作；不要只写“暂无数据”。
- 加载：5–8 行骨架，不要整页 spinner。
- 分页：默认 20 条/页；超过 20 条必须分页或虚拟滚动。

### Tag / Badge

- 5 种语义：success / warning / danger / info / neutral。
- 形态：浅底 + 同色文字 + 1px 同色边框；圆角 6px；字号 12px。
- 状态点 + 文案优先于纯色块，例如 `● 已解析`。

### Card / Panel

- 白底、1px 边框、10px 圆角、极轻阴影；不要用大阴影堆叠。
- 卡片头 48px，标题 16px/600；右上角放一个次要操作或筛选。
- 卡片内边距 20px；紧凑表格卡可 16px。

### Modal / Drawer

- Modal 最大宽度 640px；Drawer 480/640px；圆角 12px。
- 标题、说明、内容、footer 四段式；危险操作使用危险色按钮。
- 打开时焦点进入第一个可操作元素；Esc 关闭；关闭后焦点回到触发点。

### TaskDock / Notification

- 默认收起为 40px 高的小条；有新任务时自动展开，任务完成后不自动弹回。
- 不遮挡表格操作列：内容区底部保留 64px 安全区；窄屏改为底部抽屉。

### 图表

- 折线/柱状图使用主色 + AI 青色；网格线 `#F1F5F9`；坐标轴文字 11px。
- 每个图表必须有标题、时间范围、空状态、加载状态。
- 指标卡必须带“对比口径”（环比/同比/时间范围），不能只给一个数字。

## 7. 页面模板

1. **工作台**：欢迎区（弱化）→ 4 个指标卡 → 趋势图 + 告警 → 项目/待办/动态三栏。
2. **列表页**：页面头 → 搜索/筛选/批量操作 → 表格 → 分页。
3. **详情页**：左侧摘要（状态、负责人、优先级、版本）→ 右侧 Tab 工作区（原型/接口/用例/文件）。
4. **生成页**：左侧配置（输入源、模型、范围）→ 右侧结果预览 → 底部生成/保存。
5. **编排页**：节点库 | 画布 | 配置面板；顶部工具栏放运行/保存/版本。
6. **对话页**：会话列表 | 消息流 | 引用/工具调用折叠面板。
7. **报告页**：摘要指标 → 失败分布 → 明细表 → 导出/重跑。

## 8. 交互与状态

每个页面必须定义：

- 空状态：为什么空、下一步做什么。
- 加载状态：骨架屏，不用全屏 spinner。
- 错误状态：错误原因 + 重试 + 联系管理员。
- 权限不足：说明缺什么权限、找谁开通。
- 长内容：截断 + tooltip；表格列可配置。
- 破坏性操作：二次确认 + 影响说明。
- 键盘：Tab 顺序、Enter 提交、Esc 关闭、焦点可见。

## 9. 文案

- 用动词开头：`新建需求`、`生成用例`、`重新解析`。
- 不用“确定/提交”这种含糊词；用具体动作。
- 错误文案说明“发生了什么 + 怎么解决”，不要只抛后端 message。
- 中文标点统一全角；英文/数字与中文之间加空格。

## 10. 可访问性

- 正文对比度 ≥ 4.5:1；大字号 ≥ 3:1。
- 可点击目标 ≥ 32×32px；移动端 ≥ 44×44px。
- 所有图标按钮有 `aria-label`；表格有表头关联；表单有 label。
- 焦点环 2px 主色 + 2px offset；不要移除 outline。
- 动效 150–200ms，尊重 `prefers-reduced-motion`。

## 11. Figma 使用方式

1. 先导入 `tokens.proposed.json` 到 Figma Variables（或 Tokens Studio）。
2. 以 `design/baseline/screens/` 的截图作为 Baseline Snapshot，不要直接在上面改。
3. 新建 `10 Redesign` 页面，按页面模板逐页重绘；不要一次重绘全部 44 页。
4. 先做 3 个基准页：工作台、需求列表、需求详情；批准后再扩展。
5. 组件先做 Button / Input / Table / Tag / Card / Modal 六个，再拼页面。
6. 批准帧命名：`approved/v1.0 / <page> / <state>`。
7. 任何视觉变更都要记录：改了什么、影响哪些页面/组件、对应 Token。

> 本文件是目标设计规范，不代表当前代码已实现。代码落地的唯一真相源仍是 `src/` 与 `tokens.baseline.json`；Figma 批准后再同步回代码。

---

## 实施状态（2026-11-17）

- 已落地：`brand-*` / `ink-*` / `surface` / `line` Token、Button/Input/Card/Tag/Table/Modal/Drawer/Empty/Skeleton/Icon、56px 顶栏 + 232px 侧栏、工作台/需求列表/需求详情。
- 部分落地：CaseList / ApiManage 的 loading 与空状态。
- 未落地：其余 30+ 页面、分页/排序、完整响应式、全站错误/权限状态、Code Connect。
- 详情见 `../docs/设计优化待办.md`。
