# 前端工程化脚手架（scaffold）

> 把本项目沉淀的"设计→开发→验证→沉淀"经验，固化为**下个项目复制即用**的资产。
> 这是"可复用管理经验"的实体形态——不是说明书，是可执行的文件模板 + 脚本。

---

## 一、这个脚手架解决什么问题

新项目开始时，最容易重复踩的坑：
- 颜色、字号、圆角各写各的，没有真相源；
- AI 每次生成界面都产出一套新组件，代码越来越难维护；
- 做完不知道怎么验证，只能"看着差不多"；
- 项目结束经验留不下来，下个项目从零开始。

这个脚手架把本项目验证过的最佳实践打包，让新项目**第一天就站在规范之上**。

---

## 二、目录结构

```
scaffold/
├── README.md                          # 本文档
├── init.sh                            # 一键初始化脚本（核心）
├── templates/
│   ├── DESIGN.template.md             # Agent 可读的设计系统上下文（含 Token frontmatter）
│   ├── tokens.template.json           # Design Token 真相源
│   └── component-inventory.template.md # 组件清单模板
├── prompts/
│   └── figma-ai-prompts.md            # Figma AI 五套提示词（基线/设计/Token/组件/回写）
└── scripts/
    └── verify.sh                      # 四层验证脚本（编译/单测/视觉/提示）
```

---

## 三、三步接入新项目

### 步骤 1：复制脚手架到新项目
```bash
cp -r scaffold/ /path/to/new-project/.scaffold/
cd /path/to/new-project
```

### 步骤 2：运行初始化
```bash
bash .scaffold/init.sh /path/to/new-project
```
脚本会：
- 在目标项目创建 `design/` 目录
- 把模板复制过去并替换项目名占位符
- 生成一份 `design/README.md` 使用说明
- 提示你下一步该填什么

### 步骤 3：按模板填入项目实际值
1. 编辑 `design/DESIGN.md` 的 frontmatter（改颜色/字体/项目名）
2. 编辑 `design/tokens.json`（与 DESIGN.md 保持一致）
3. 从代码现状捕获基线截图，放入 `design/baseline/screens/`
4. 用 `prompts/figma-ai-prompts.md` 推进设计

---

## 四、四层验证（verify.sh）

| 层级 | 命令 | 验证内容 |
|---|---|---|
| 编译 | `tsc --noEmit` | 类型正确 |
| 单测 | `pnpm test` | 逻辑正确 |
| 视觉 | Playwright screenshot diff | 与批准帧一致，无回归 |
| 交互 | 手动冒烟清单 | 空/加载/错误/权限状态 |

> 对后端为主的项目，把"视觉 diff"换成"API 契约测试"——真实能力比像素更重要。

---

## 五、治理原则（必须遵守，否则脚手架失效）

1. **每类信息只有一个真相源**：Token 以代码为准，视觉以 Figma 批准帧为准；
2. **Token 变更走 PR**：不在 Figma 里建"孤岛变量"；
3. **先收敛组件再批量做页面**：没有这一步，AI 会产出第二套 UI；
4. **每个批准帧有变更单**：原因/影响面/链接/负责人/日期；
5. **每步都跑验证**：不做"最后统一验证"。

---

## 六、这个脚手架来自哪里

提炼自 AI_Studio 项目的真实实践：
- `design/DESIGN.md` + `tokens.proposed.json` — 设计系统
- `design/figma-ai-prompts.md` — AI 提示词库
- `docs/设计规范.md` + `设计优化待办.md` — 规范与验收标准
- `docs/系统优化教程.md` — 落地步骤

经过两个真实项目验证后，才固化为模板。
