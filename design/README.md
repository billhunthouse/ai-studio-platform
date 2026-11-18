# 设计基线包

这是从当前代码还原的设计基线，供 Figma AI（Design / Make）做专业化改版使用。

## 目录

| 文件 | 用途 |
|---|---|
| `baseline/screens/` | 44 张 1440×900 现状截图 |
| `baseline/manifest.json` | 截图清单（路由、分组、说明、状态） |
| `baseline/contact-sheet.png` | 全部页面的总览图 |
| `baseline/contact-sheet.svg` | 可导入 Figma 的总览板 |
| `page-inventory.md` | 页面清单与待补拍状态 |
| `design-audit.md` | 现状问题、评分、专业化方向、优先级 |
| `DESIGN.md` | 目标设计系统（Precision Workspace） |
| `tokens.baseline.json` | 当前代码 Token（真相源） |
| `tokens.proposed.json` | 目标 Token（待 Figma 评审） |
| `component-inventory.md` | 组件清单、缺口、Figma 组件结构 |
| `figma-handoff.md` | Figma 文件建立、导入、批准、回写的操作手册 |
| `figma-ai-prompts.md` | 可直接粘贴的 Figma AI 提示词 |

## 当前状态

- 代码版本：`83aa7b9`（设计基线）
- 截图日期：2026-11-16
- 视口：1440×900
- 截图数量：44
- 设计阶段：**Baseline 已完成；2026-11-17 已进入代码实现第一轮**

### 2026-11-17 实现进展

- 已完成全局设计基础：Token、Button、Input、Card、Tag、Table、Modal、Drawer、Empty、Skeleton、Icon。
- 已完成全局骨架：56px 顶栏、232px 分组侧栏、26px 页面标题。
- 已完成 3 个基准页：工作台、需求列表、需求详情。
- 新版工作台截图：`after/02-dashboard.png`（旧版基线仍在 `baseline/screens/02-dashboard.png`）。
- 实现教程：`../docs/系统优化教程.md`
- 未完成清单：`../docs/设计优化待办.md`

## 推荐使用顺序

1. 读 `design-audit.md`，确认专业化方向。
2. 按 `figma-handoff.md` 建 Figma 文件、导入 Baseline。
3. 用 Tokens Studio 导入 `tokens.proposed.json`。
4. 用 `figma-ai-prompts.md` 的 Prompt 2，先做 3 个基准页。
5. 批准后，按 `component-inventory.md` 收敛组件。
6. 最后按 `figma-handoff.md` 第 7 节回写代码。

## 重要边界

- Baseline 是“现状”，不是目标稿；不要在 Baseline 上直接改。
- `tokens.proposed.json` 是待评审方案，不是当前代码真相源。
- Figma 只做视觉与组件批准；行为、数据、接口、权限仍以代码和业务文档为准。
- 当前 ZCode 的 Figma 远程 MCP OAuth 被拒绝（403），Code to canvas 需用支持的客户端或截图基线方案。
