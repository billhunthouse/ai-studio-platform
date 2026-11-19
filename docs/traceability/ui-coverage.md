# UI 自动化覆盖报告

> 由 `backend/ui_coverage_report.py` 生成；feature 源 `ui_testcases/src/test/resources/features`。
> 页面归属来自 trace_relations（需求 → 页面），页面与 feature 的对应见脚本内 FEATURE_PAGES 表。

## 汇总

- 业务 feature：4 个，场景 10 条
- 页面：41 个，被 UI 覆盖 9 个（22%）
- 需求：52 条，其中 18 条有 UI 用例（35%）

## 现有 feature 覆盖的页面

| feature | 场景数 | 覆盖页面 |
| --- | ---: | --- |
| `admin-console.feature` | 3 | 登录、工作台、商品列表 |
| `mall-cart.feature` | 3 | 首页、商品详情、购物车、确认订单 |
| `mall-login.feature` | 3 | 登录 |
| `mall-order.feature` | 1 | 订单详情 |

## 缺口页面（按归属需求的最高优先级排序）

| 页面 | 路由 | 归属需求 | 优先级 |
| --- | --- | --- | --- |
| 售后管理 | `/aftersales` | V1-FR-020、V1-FR-021 | P0 |
| 类目与品牌 | `/categories` | V1-FR-008、V1-FR-009、V1-FR-010 | P0 |
| 会员管理 | `/customers` | V2-FR-017 | P0 |
| 部门管理 | `/depts` | V1-FR-005 | P0 |
| 字典管理 | `/dicts` | V1-FR-006 | P0 |
| 首页运营位 | `/home-slots` | V2-FR-019 | P0 |
| 库存管理 | `/inventory` | V1-FR-015、V1-FR-016、V1-FR-017 | P0 |
| 操作日志 | `/logs` | V1-FR-007 | P0 |
| 菜单与权限 | `/menus` | V1-FR-004 | P0 |
| 订单列表 | `/orders` | V1-FR-018、V1-FR-019、V2-FR-021、V2-FR-022 | P0 |
| 新增商品 | `/products/edit` | V1-FR-011、V1-FR-014、V2-FR-023 | P0 |
| 编辑商品 | `/products/edit/:id` | V1-FR-011、V1-FR-014、V2-FR-023 | P0 |
| 角色管理 | `/roles` | V1-FR-003 | P0 |
| 系统设置 | `/settings` | V1-FR-022、V2-FR-020 | P0 |
| 站点品牌 | `/site-brand` | V1-FR-014、V2-FR-018 | P0 |
| 用户管理 | `/users` | V1-FR-002 | P0 |
| 收货地址 | `/addresses` | V2-FR-013、V2-FR-014 | P0 |
| 我的售后 | `/after-sales` | V2-FR-012 | P0 |
| 售后详情 | `/after-sales/:id` | V2-FR-012 | P0 |
| 申请售后 | `/after-sales/apply` | V2-FR-012 | P0 |
| 分类 | `/category` | V2-FR-004、V2-FR-005、V2-FR-016 | P0 |
| 我的收藏 | `/favorites` | V2-FR-013、V2-FR-014 | P0 |
| 浏览足迹 | `/history` | V2-FR-013、V2-FR-014 | P0 |
| 个人中心 | `/me` | V2-FR-001、V2-FR-002、V2-FR-013、V2-FR-014、V2-FR-016 | P0 |
| 我的订单 | `/orders` | V2-FR-011 | P0 |
| 支付 | `/pay/:orderId` | V2-FR-008、V2-FR-009、V2-FR-010 | P0 |
| 活动专区 | `/promo/:code` | V2-FR-003 | P0 |
| 搜索 | `/search` | V2-FR-004、V2-FR-005 | P0 |
| 个人设置 | `/settings` | V2-FR-001、V2-FR-002 | P0 |
| 出入库单 | `/in-out` | V2-FR-024 | P1 |
| 评价管理 | `/reviews` | V2-FR-025、EXT-REVIEW-REPLY-001 | P1 |
| AI 助手浮窗 | `ai-assistant` | EXT-AI-001 | P1 |
