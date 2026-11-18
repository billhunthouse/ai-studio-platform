# 页面基线清单

- 生成日期：2026-11-16
- 代码版本：`83aa7b9`
- 视口：1440×900
- 截图目录：`design/baseline/screens/`

> 当前截图记录的是“实现现状”，不是目标设计。优化稿请放在 Figma，并以 approved 帧为准。

## 认证

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S01 | 登录 | `/login` | `screens/01-login.png` | 邀请制登录入口，邮箱 + 密码；需补拍错误提示、禁用态 |

## 全局层

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S02 | 工作台 | `/dashboard` | `screens/02-dashboard.png` | 全局指标、待办、告警、近期动态；图表区为当前实现状态 |

## 项目层 · 核心流程

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S03 | 项目概览 | `/project/:pid/overview` | `screens/03-project-overview.png` | 项目健康度、用例与执行统计 |
| S04 | 需求列表 | `/project/:pid/requirements` | `screens/04-requirements-list.png` | 按业务模块分组的需求树、筛选、上传；当前项目数据 77 条 |
| S05 | 需求详情 | `/project/:pid/requirements/:rid` | `screens/05-requirement-detail.png` | 需求信息 + AI 设计生成/原型/接口；右侧工作区为空态 |
| S06 | 用例列表 | `/project/:pid/testcases` | `screens/06-testcases-list.png` | 测试用例表格、导入导出 |
| S07 | AI 生成用例 | `/project/:pid/testcases/generate` | `screens/07-testcases-generate.png` | 配置生成输入、生成结果 |
| S08 | 用例评审 | `/project/:pid/testcases/review` | `screens/08-testcases-review.png` | 可编辑评审、通过保存 |

## 项目层 · 自动化

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S09 | 接口管理 | `/project/:pid/api` | `screens/09-api-manage.png` | 接口目录 + 接口表格；当前为空状态，需要补拍有数据状态 |
| S10 | 调试面板 | `/project/:pid/api/debug` | `screens/10-api-debug.png` | 请求编辑、响应与断言 |
| S11 | 套件与定时任务 | `/project/:pid/api/suites` | `screens/11-api-suites.png` | 套件、定时计划与执行 |
| S12 | 执行报告 | `/project/:pid/api/reports` | `screens/12-api-reports.png` | 报告列表与结果 |
| S13 | 元素库 | `/project/:pid/webui` | `screens/13-webui-elements.png` | WebUI 元素与定位器 |
| S14 | 用例脚本 | `/project/:pid/webui/scripts` | `screens/14-webui-scripts.png` | 脚本列表与编辑器入口 |
| S15 | 录制回放 | `/project/:pid/webui/recorder` | `screens/15-webui-recorder.png` | 录制器与步骤回放 |
| S16 | 执行记录 | `/project/:pid/webui/runs` | `screens/16-webui-runs.png` | WebUI 运行记录 |
| S17 | 设备管理 | `/project/:pid/app` | `screens/17-app-devices.png` | App 设备与状态 |
| S18 | UI Flow 编排 | `/project/:pid/app/flow` | `screens/18-app-flow.png` | 节点画布与配置；画布空态 |
| S19 | 执行记录 | `/project/:pid/app/runs` | `screens/19-app-runs.png` | App 运行记录 |

## 项目层 · AI 与知识

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S20 | 对话助手 | `/project/:pid/ai/chat` | `screens/20-ai-chat.png` | 知识库问答、引用与工具调用；已有会话数据 |
| S21 | 工作流编排器 | `/project/:pid/ai/workflow` | `screens/21-ai-workflow.png` | 节点库、画布、节点配置 |
| S22 | 知识库列表 | `/project/:pid/knowledge` | `screens/22-knowledge-list.png` | 知识库与文档数量 |
| S23 | 文档管理 | `/project/:pid/knowledge/documents` | `screens/23-knowledge-documents.png` | 文档上传、解析、切片 |
| S24 | 召回测试 | `/project/:pid/knowledge/recall` | `screens/24-knowledge-recall.png` | 检索查询与召回结果 |
| S25 | 学习中心 | `/project/:pid/knowledge/learning` | `screens/25-knowledge-learning.png` | 课程内容与学习进度 |
| S26 | 任务列表 | `/project/:pid/tasks` | `screens/26-task-list.png` | 后台任务、进度与重试 |
| S27 | Agent 评测 | `/project/:pid/tasks/agent-eval` | `screens/27-agent-eval.png` | 评测集与结果 |
| S28 | 版本对比 | `/project/:pid/tasks/compare` | `screens/28-version-compare.png` | 版本差异与变更 |

## 全局层

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S29 | 技能市场 | `/skills/list` | `screens/29-skills-list.png` | 技能列表、导入、编辑 |
| S30 | MCP 服务 | `/mcp` | `screens/30-mcp-servers.png` | MCP 服务登记、连接测试、工具列表 |
| S31 | 团队成员 | `/team/members` | `screens/31-team-members.png` | 成员列表、邀请、角色 |
| S32 | 角色权限 | `/team/roles` | `screens/32-team-roles.png` | 角色权限矩阵 |
| S33 | 项目分配 | `/team/assignments` | `screens/33-team-assignments.png` | 成员与项目关系 |
| S34 | 个人信息 | `/profile/info` | `screens/34-profile-info.png` | 个人资料与偏好 |
| S35 | 安全设置 | `/profile/security` | `screens/35-profile-security.png` | 密码、会话与安全 |
| S36 | 我的资产 | `/profile/assets` | `screens/36-profile-assets.png` | 产物与资产 |
| S37 | API Key | `/profile/keys` | `screens/37-profile-keys.png` | 个人密钥管理 |

## 管理员层

| ID | 页面 | 路由 | 截图 | 说明 |
|---|---|---|---|---|
| S38 | 模型供应商 | `/admin/models/providers` | `screens/38-admin-providers.png` | 模型供应商与密钥 |
| S39 | 模型路由规则 | `/admin/models/routing` | `screens/39-admin-routing.png` | 模型路由与规则 |
| S40 | 连接测试 | `/admin/models/test` | `screens/40-admin-connection-test.png` | 模型连通性测试 |
| S41 | 用户管理 | `/admin/system/users` | `screens/41-admin-users.png` | 平台用户与角色 |
| S42 | 环境检测 | `/admin/system/health` | `screens/42-admin-health.png` | 服务与依赖健康 |
| S43 | 通知配置 | `/admin/system/notifications` | `screens/43-admin-notifications.png` | 通知渠道与规则 |
| S44 | 审计日志 | `/admin/audit/logs` | `screens/44-admin-audit.png` | 操作审计与筛选 |

## 待补拍状态

- 登录错误提示 / 禁用态
- 需求上传弹窗、拆分草案弹窗
- 用例评审保存成功 / 失败
- 接口管理的“有数据”状态
- 各类空状态、加载骨架、权限不足、网络错误
- 1024px 与 390px 响应式基线
