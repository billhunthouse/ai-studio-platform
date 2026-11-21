# 组件清单与 Figma 映射

> 目标：Figma 中只建立“可复用组件 + 变体”，页面由组件拼装，不要每页画一套。
> 当前代码优先复用 `src/components/ui/`，不要引入第三方 UI 库。

## 1. 基础组件（P0）

| 组件 | 代码 | 当前变体/状态 | 缺口 | Figma 目标 | 优先级 |
|---|---|---|---|---|---|
| Button | `src/components/ui/primitives.tsx` | primary / ghost / danger；disabled；focus-visible | 无 secondary、无 loading、无 icon-only、无尺寸档 | `Button`：variant=primary/secondary/ghost/danger；size=sm/md；state=default/hover/focus/disabled/loading；icon=left/right/none | P0 |
| Input | 同上 | 默认 / focus / disabled（原生） | 无 error、无 prefix/suffix、无 clear | `Input`：state=default/focus/error/disabled；prefix/suffix；size=sm/md | P0 |
| Textarea | 同上 | 默认 / focus | 无 error、无计数 | `Textarea`：state + 字数 | P1 |
| Select | 同上 | 原生 select | 无搜索、无分组、无 error | `Select`：state + 分组 + 搜索 | P1 |
| Field | 同上 | label + hint | 无必填、error、字符计数 | `Form Field`：label/required/help/error | P0 |
| Switch | 同上 | checked / unchecked | 无 disabled / loading | `Switch`：state=on/off/disabled | P1 |
| Tag | 同上 | 5 种语义色（green/red/amber/blue/gray） | 无 dot、无可关闭、无尺寸 | `Tag`：tone=success/warning/danger/info/neutral；dot；size | P0 |
| Card | 同上 | 有标题/无标题；`extra` | 无 loading、无选中、无折叠 | `Card`：state=default/loading/selected；header=title/action | P0 |
| Stat | 同上 | label/value/delta/up | 无口径、无趋势图、无 loading | `Metric Card`：value/trend/period/loading | P1 |
| Bars | 同上 | 柱状图，固定高度 | 无坐标轴/单位/空态/tooltip | `Bar Chart`：default/empty/loading | P1 |
| Empty | 同上 | 一行文字 | 无图标、无动作、无分级 | `Empty State`：icon/title/description/action | P0 |
| Progress | 同上 | 0–100 | 无分段、无状态色 | `Progress`：default/success/error | P2 |
| Table | `src/components/ui/Table.tsx` | 基础表格 + 操作列 + 自动 Tag | 无排序、选择、分页、空/加载、列配置 | `Data Table`：header/row/empty/loading/selected/sort/pagination | P0 |
| Toolbar | 同上 | 搜索 + 状态筛选 + 右侧动作 | 无筛选 chip、无批量操作、无视图切换 | `Toolbar`：search/filter/bulk/actions | P0 |
| Modal | `src/components/ui/Overlay.tsx` | 标题/内容/footer；焦点陷阱 | 无尺寸档、无危险确认、无 loading | `Modal`：size=sm/md/lg；state=default/loading/danger | P0 |
| Drawer | 同上 | 右侧 480px | 无宽度档、无多级 | `Drawer`：width=480/640；header/footer | P1 |
| Toast | 同上 | 左下角，自动消失 | 无成功/失败/警告变体 | `Toast`：tone=success/error/warning/info | P1 |
| Tabs | 布局内联 | 页面 Tab | 无 overflow、无 badge | `Tabs`：default/overflow/badge | P1 |
| Breadcrumb | `AppShell` 内联 | 文本 | 无分隔/可点击 | `Breadcrumb` | P2 |
| Pagination | 无 | 无 | 全站缺失 | `Pagination`：page/size/total | P0 |
| Tooltip | 无 | 无 | 全站缺失 | `Tooltip`：top/right/bottom/left | P1 |
| Checkbox / Radio | 原生 | 默认 | 无自定义样式 | `Checkbox` / `Radio` | P1 |
| Avatar | 布局内联 | 首字母圆形 | 无图片/状态 | `Avatar`：size/status | P2 |
| Icon | 无统一图标库 | 文字/符号 | 无图标系统 | `Icon`：16/20/24；线性 1.5px | P0 |

## 2. 业务组件（P0–P1）

| 组件 | 代码 | 当前能力 | 缺口 | Figma 目标 | 优先级 |
|---|---|---|---|---|---|
| AppShell | `src/layouts/AppShell.tsx` | 顶栏 + 侧栏 + 面包屑 + Tab + 内容区 | 入口过多、无分组、无响应式 | `App Shell`：desktop/tablet/mobile；nav group | P0 |
| ProjectSwitcher | `src/components/business/ProjectSwitcher.tsx` | 项目下拉 + 编辑/新建 | 无最近项目/搜索 | `Project Switcher`：default/open/search | P1 |
| NotificationCenter | `src/components/business/NotificationCenter.tsx` | 通知浮层 | 无分组/已读/空态 | `Notification Panel`：list/empty/unread | P1 |
| TaskDock | `src/components/business/TaskDock.tsx` | 任务浮层、进度、重试 | 遮挡内容、无收起安全区 | `Task Dock`：collapsed/expanded/empty/running | P1 |
| RequirementSplit | `src/components/business/RequirementSplit.tsx` | 拆分状态、草案弹窗、确认 | 弹窗信息密度高、无并排对比 | `Split Review`：proposal/confirm/loading/error | P0 |
| PrototypeRenderer | `src/components/business/PrototypeRenderer.tsx` | 多页原型渲染、Tab/翻页 | 无缩放/全屏/标注 | `Prototype Viewer`：page/zoom/fullscreen | P1 |
| PrototypeEditor | `src/components/business/PrototypeEditor.tsx` | 页面结构编辑 | 无拖拽/图层 | `Prototype Editor` | P2 |
| VersionDiff | `src/components/business/VersionDiff.tsx` | 文本 diff | 无并排/行内 | `Diff Viewer`：unified/split | P2 |
| DetailDrawer | `src/components/business/DetailDrawer.tsx` | 详情抽屉 | 无多级/宽度 | `Detail Drawer` | P2 |
| MonacoEditor | `src/components/business/MonacoEditor.tsx` | YAML/JSON/脚本编辑 | 无主题/工具栏 | `Code Editor`：light/dark/toolbar | P2 |
| AgentTraceTimeline | `src/components/business/AgentTraceTimeline.tsx` | Agent 轨迹 | 无折叠/耗时 | `Trace Timeline` | P2 |
| AgentEvalVerify | `src/components/business/AgentEvalVerify.tsx` | 评测校验 | 无空/错误态 | `Eval Result` | P2 |
| AgentRunPanel | `src/components/business/AgentRunPanel.tsx` | 运行面板 | 无状态机可视化 | `Run Panel` | P2 |

## 3. 需要新增的组件（按页面模板）

| 组件 | 用途 | 优先级 |
|---|---|---|
| `PageHeader` | 页面标题 + 描述 + 主操作 + 面包屑，统一所有页面头部 | P0 |
| `FilterBar` | 搜索 + 筛选 chip + 视图切换 + 批量操作 | P0 |
| `DataTable` 增强 | 排序、选择、分页、列配置、空/加载 | P0 |
| `StatusBadge` | 圆点 + 文案 + 语义色，替代大面积 Tag | P0 |
| `EmptyState` | 图标 + 标题 + 说明 + 主/次操作 | P0 |
| `Skeleton` | 表格/卡片/图表骨架 | P0 |
| `ErrorState` | 原因 + 重试 + 联系管理员 | P0 |
| `ConfirmDialog` | 破坏性操作二次确认，含影响说明 | P0 |
| `PageTabs` | 支持 overflow、badge、键盘 | P1 |
| `MetricCard` | 数值 + 口径 + 趋势 + 更新时间 | P1 |
| `ChartCard` | 标题 + 时间范围 + 图表 + 空/加载 | P1 |
| `SplitLayout` | 详情页 320px + 自适应 | P1 |
| `BuilderLayout` | 节点库/画布/配置三栏 | P1 |
| `ChatLayout` | 会话/消息/引用三栏 | P1 |
| `CommandMenu` | 全局搜索/快捷跳转（可选） | P2 |
| `ResizablePanel` | 详情/编排可拖拽分栏 | P2 |

## 4. Figma 组件库结构建议

```
00 Foundations
  Colors / Type / Spacing / Radius / Shadow / Icons
01 Primitives
  Button / Input / Select / Checkbox / Radio / Switch / Tag / Avatar / Tooltip
02 Containers
  Card / Panel / Modal / Drawer / Toast / Tabs / Pagination
03 Data
  DataTable / Toolbar / FilterBar / EmptyState / Skeleton / ErrorState / MetricCard / ChartCard
04 Navigation
  AppShell / Sidebar / TopBar / Breadcrumb / ProjectSwitcher / NotificationPanel / TaskDock
05 Business
  RequirementTree / SplitReview / PrototypeViewer / CaseEditor / ApiRequestBuilder / KnowledgeChunks / WorkflowCanvas
06 Page Templates
  Dashboard / List / Detail / Generate / Builder / Chat / Report
```

## 5. Code Connect 优先级

先建立 5 个高频组件的映射，等 Figma 组件稳定后再扩展：

1. `Button` → `src/components/ui/primitives.tsx`
2. `Input` → `src/components/ui/primitives.tsx`
3. `Tag` → `src/components/ui/primitives.tsx`
4. `Card` → `src/components/ui/primitives.tsx`
5. `Table` → `src/components/ui/Table.tsx`

映射要求：

- 使用 Figma 组件节点的精确 URL（含 `node-id`），不要用页面/Frame URL。
- 映射 variant / size / state 到代码 props。
- `Code Connect sync` 退出码为 0 才算完成。
- 组件 API 以代码为准；Figma 不单方面定义新 props。

## 6. 现状组件问题清单

- `Button` 没有 loading，异步操作只能靠文字变化。
- `Input` 没有 error 状态，表单校验只能弹 toast。
- `Tag` 的颜色由字符串正则自动推断，容易出现语义误判。
- `Table` 用数组下标作为 key，行选择/排序会出问题。
- `Modal` / `Drawer` 没有尺寸体系和危险操作变体。
- `Empty` 只有一行文字，无法引导下一步。
- 没有 `Skeleton` / `Pagination` / `Tooltip` / `ConfirmDialog` 统一组件。
- 业务组件与页面耦合较深，Figma 映射前建议先抽 props。
