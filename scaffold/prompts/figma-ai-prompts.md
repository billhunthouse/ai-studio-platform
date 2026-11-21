# Figma AI 提示词

> 使用顺序：Prompt 1 → Prompt 2（逐页）→ Prompt 3 → Prompt 4 → Prompt 5。  
> 每次只喂一个页面或一个组件，不要把 44 页一次性丢给模型。

---

## Prompt 1：代码 → Figma 基线捕获

用于支持 Figma Remote MCP / Code to canvas 的客户端（Claude Code、Cursor 等）。

```text
Start the local app at http://127.0.0.1:8443 and capture the current UI into a new Figma design file named "AI Test Platform — Baseline Snapshot v1".

Capture at a fixed viewport of 1440×900. Capture each screen as a separate frame with semantic layer naming: "S01 / 登录 / default", "S02 / 工作台 / default", etc.

Group frames into pages:
- 00 Cover
- 01 Baseline / Global
- 02 Baseline / Project Core
- 03 Baseline / Automation
- 04 Baseline / AI & Knowledge
- 05 Baseline / Admin

Screens to capture:
Login; Dashboard; Project Overview; Requirements List; Requirement Detail; Test Case List; AI Generate Cases; Case Review; API Manage; API Debug; API Suites; API Reports; WebUI Elements; WebUI Scripts; Recorder; WebUI Runs; App Devices; App UI Flow; App Runs; AI Chat; AI Workflow; Knowledge List; Knowledge Documents; Knowledge Recall; Learning Center; Task List; Agent Eval; Version Compare; Skills; MCP Servers; Team Members; Team Roles; Team Assignments; Profile Info; Profile Security; Profile Assets; Profile Keys; Admin Providers; Admin Routing; Admin Connection Test; Admin Users; Admin Health; Admin Notifications; Admin Audit.

Mark the file description exactly: "Baseline Snapshot — not a design system. Captured from code, 1440×900, 2026-11-16."

Rules:
- Do not modify any existing frames or files.
- Do not redesign yet; capture the current state faithfully.
- If login is required, stop and ask me to log in; do not guess credentials.
- Keep the original spacing, typography, colors, and table density.
- Name layers by screen and state, not by DOM element.
```

**如果当前端没有 Code to canvas 工具**，跳过此 Prompt，改用 `design/figma-handoff.md` 的方案 B（截图拖入 Figma）。

---

## Prompt 2：Figma AI Design 模式，逐页重绘

一次只替换 `{PAGE_NAME}` 和 `{SCREEN_REF}`。先做工作台、需求列表、需求详情。

```text
You are a senior product designer redesigning an enterprise AI test platform.

Target page: {PAGE_NAME}
Baseline reference: {SCREEN_REF} (keep it visible on the left; do not edit it)
Output: one 1440×900 frame named "Redesign / {PAGE_NAME} / default"

Design direction: "Precision Workspace"
- Calm, precise, high-signal; a control room for test engineers, not a consumer SaaS dashboard.
- Dark graphite top bar (#0B1220), cool off-white canvas (#F5F7FB), white surfaces.
- Primary cobalt #2D5BFF; AI accent cyan #0891B2 used only for AI-generated actions; status colors only for status.
- Typography: Inter/Geist + PingFang SC. Page title 28px/600; section title 16–20px/600; body 14px/400; table 13px; caption 12px. Use tabular numerals for metrics.
- Spacing: 8pt system; 24px page padding; 16px card gap; 10–12px radii; subtle 1px borders; almost invisible shadows.
- Cards: white, 1px #E2E8F0 border, 10px radius, no heavy shadow.

Keep the existing information architecture and every business action. Do not add or remove features. Do not change routes, fields, permissions, or data.

Required layout:
- Page header: breadcrumb, 28px title, one-line description, one primary action (max), secondary actions as ghost/text.
- A clear filter/context row if the page is a list.
- Main content in a 12-column grid, max width 1600px.
- Right-side context or summary where the baseline has one.

Required states:
- default
- empty (icon + explanation + one action)
- loading (skeleton rows/cards, not a full-page spinner)
- error (reason + retry + contact admin)
- disabled/permission-denied where relevant

Quality bar:
- No gradients, glassmorphism, neon, or decorative blobs.
- No more than 2 colored tags per row.
- Primary action must be visually unique.
- All text must remain readable at 1280px width.
- Use the provided components and tokens; do not invent a new visual language.

Deliver:
1. The redesigned frame.
2. A short list of the components used.
3. Any state that is missing from the baseline and needs a new frame.
```

### 逐页替换表

| 轮次 | `{PAGE_NAME}` | `{SCREEN_REF}` |
|---|---|---|
| 1 | 工作台 | S02 |
| 2 | 需求列表 | S04 |
| 3 | 需求详情 | S05 |
| 4 | 用例列表 | S06 |
| 5 | AI 生成用例 | S07 |
| 6 | 用例评审 | S08 |
| 7 | AI 对话 | S20 |
| 8 | API 管理 | S09 |
| 9 | 知识库文档 | S23 |

> 3 个基准页批准前，不要继续扩展。每轮只改一个页面。

---

## Prompt 3：Figma Make 交互原型

```text
Create a clickable prototype for the "Precision Workspace" redesign of the AI test platform.

Scope: one flow only —
Dashboard → Requirements List → Requirement Detail → Generate Test Cases.

Use the approved redesign frames as the visual source. Use realistic sample data for the 物业小程序 project:
- 8 business modules, 65 sub-requirements, 36 test cases.
- One module: 楼栋管理 with 12 sub-requirements.
- One requirement: 登录与初始化 with 5 sub-requirements.

Interactions:
- Dashboard: click "新建需求" → Requirements List; click a project card → Project Overview.
- Requirements List: expand/collapse a module; search by title/ID; filter by module and status; click "详情" → Requirement Detail.
- Requirement Detail: switch tabs 原型图 / 接口设计; click "生成测试用例" → Generate Test Cases; show a loading state and a result state.
- Generate Test Cases: show input source, model, scope; click "生成" → progress → result list; click "保存" → success toast.

Rules:
- Desktop 1440×900; also show a 1024px layout note.
- Use the design tokens; do not hardcode new colors.
- Do not connect to the backend; use local mock data.
- Show empty, loading, error, and success states.
- Keep all labels in Chinese.

Deliver: a runnable Make prototype link plus a one-paragraph note on what to validate with users.
```

---

## Prompt 4：组件与 Token 一致性审查

```text
Audit the "10 Redesign" page against the design system.

Reference files:
- design/tokens.proposed.json
- design/DESIGN.md
- design/component-inventory.md

For every frame on the page, report:
1. Hardcoded colors, font sizes, spacing, radii, shadows that should be tokens.
2. Components that are duplicated instead of instantiated from the component library.
3. Missing states: empty, loading, error, disabled, permission-denied, long content.
4. Table issues: row height, alignment, action column, pagination, overflow.
5. Typography hierarchy issues: page title vs section title vs body vs caption.
6. Accessibility issues: contrast, focus ring, click target, label/ARIA.
7. Any place where the redesign changed business behavior or removed an action.

Output a table: Frame / Issue / Severity (P0/P1/P2) / Fix / Token or component to use.
Do not edit the file; report only.
```

---

## Prompt 5：批准后的开发交接

```text
You are handing off approved Figma frames to the engineering team.

For each approved/v1.0 frame, produce an implementation spec:
- Frame name and link
- Page route
- Components used (map to src/components/ui and src/components/business)
- Tokens used (color/type/spacing/radius)
- Layout rules (grid, breakpoints, min/max widths)
- States (default/empty/loading/error/disabled/permission)
- Data fields and API endpoints (do not invent)
- Responsive behavior at 1280 / 1024 / 768 / 390
- Accessibility notes
- Visual regression screenshot pair (baseline vs approved)

Also produce a change record:
- What changed vs baseline
- Which pages/components/tokens are affected
- Risk and rollback plan
- Open questions

Do not write code. Do not change the approved frames. Output a Markdown spec and a checklist for the implementation PR.
```

---

## Prompt 6（可选）：只做视觉探索，不改结构

用于前期风格对比，不进入开发。

```text
Generate 3 visual directions for the same Dashboard frame, keeping the exact same layout and content:
A. Precision Workspace (recommended): graphite nav, cool white canvas, cobalt primary, cyan AI accent.
B. Soft Industrial: warm off-white canvas, ink text, olive/lime accent, editorial spacing.
C. Deep Tech: dark canvas, cyan accent, high contrast, for comparison only.

For each direction, show only the visual language: color, type, surface, border, shadow, tag style. Do not change layout or add features.
Label each frame "EXPLORATION — NOT APPROVED".
```
