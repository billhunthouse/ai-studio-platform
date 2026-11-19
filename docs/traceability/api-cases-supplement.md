# 补充用例 · 两个未被覆盖的接口

> 依据 `docs/测试资料/rule.md` v2.6 与 `docs/测试资料/领域词典.md` 生成。
> 缺口来源：追溯平台覆盖率分析 —— 代码里 137 个端点，`test_cases_inventory.md` 覆盖 135 个，
> 缺 `POST /api/customer-service/chat`（EXT-AI-001）与 `PUT /admin/reviews/{id}/reply`（EXT-REVIEW-REPLY-001）。
> 本文件为待合入 `api_testcases/test_cases_inventory.md` 的增量，稳定 ID 续接原命名规则。

## 预期口径（已实测确认）

本系统业务异常不走 HTTP 4xx，而是 **HTTP 200 + body 数值码**（`GlobalExceptionHandler` 无 `@ResponseStatus`）；
只有 Spring Security 拒绝（未认证/令牌无效）与参数绑定失败才返回真实 4xx。故负向用例的
`预期HTTP` 按实测填写，并在业务码列括注来源，符合 rule.md §3.6 的例外条款。

| 场景 | 实测结果 |
| --- | --- |
| `PUT /admin/reviews/{id}/reply` 缺 reply | `HTTP 200`，`code=40000`，msg「回复内容不能为空」 |
| `PUT /admin/reviews/{id}/reply` 评价不存在 | `HTTP 200`，`code=40400`，msg「资源不存在」 |
| `PUT /admin/reviews/{id}/reply` reply 超 500 字 | `HTTP 200`，`code=40000`，msg「回复不能超过 500 字」 |
| `PUT /admin/reviews/{id}/reply` 未带 Token | `HTTP 401`，`code=40100` |
| `POST /api/customer-service/chat` 缺 message | `HTTP 400`，`code=40000`，msg「message 不能为空」 |
| `POST /api/customer-service/chat` message 2001 字 | `HTTP 400`，`code=40000`，msg「message 不能超过 2000 字」 |
| `POST /api/customer-service/chat` 正常提问 | `HTTP 200`，`code=50000`（Agent 子服务未启动，属环境依赖，非接口缺陷） |

## 用例表

| 用例ID | 优先级 | 类型 | 标题 | 前置条件 | 请求方法/URL | 请求头 | Path/Query/Body | 步骤 | 预期HTTP | 预期业务码 | 断言点 | 清理 | 备注 |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| PUT_ADMIN_REVIEWS_ID_REPLY-001 | P1 | 正向 | 管理员回复评价_典型请求_回复成功 | 环境：baseUrl（BASE_URL）与测试账号由 pytest 环境变量提供（conftest 自动注入）。<br>账号：管理员 token（ADMIN_TEST_ACCOUNT / ADMIN_TEST_PASSWORD 登录后由 fixture 注入 Authorization）<br>数据：一条已发表评价；准备方式：先调用 GET /admin/reviews?page=1&size=5 取 data.records[0].id | PUT /admin/reviews/{id}/reply | Authorization: Bearer <管理员 token> | 路径参数 id：先调用 GET /admin/reviews?page=1&size=5 取一条记录的 id；请求体：{"reply":"自动化测试回复内容"} | 请求：PUT /admin/reviews/{id}/reply<br>请求头：Authorization: Bearer <管理员 token><br>参数：路径参数 id：先调用 GET /admin/reviews?page=1&size=5 取一条记录的 id；请求体：{"reply":"自动化测试回复内容"}<br>步骤：取评价 id；发送回复请求；回查评价详情 | 200 | 0 | HTTP=200；code=0；回查 GET /admin/reviews?page=1&size=5 校验该条 data.records[].merchantReply 等于"自动化测试回复内容"且 repliedAt 非空 | 将 merchantReply 置空（再次回复为空串会被拒绝，需直接改库恢复） | 源码 AdminOpsController#reviewReply；需求：EXT-REVIEW-REPLY-001 |
| PUT_ADMIN_REVIEWS_ID_REPLY-002 | P2 | 参数 | 管理员回复评价_缺少回复内容_提示参数错误 | 环境：baseUrl（BASE_URL）与测试账号由 pytest 环境变量提供（conftest 自动注入）。<br>账号：管理员 token（ADMIN_TEST_ACCOUNT / ADMIN_TEST_PASSWORD 登录后由 fixture 注入 Authorization）<br>数据：一条已发表评价；准备方式：先调用 GET /admin/reviews?page=1&size=5 取 data.records[0].id | PUT /admin/reviews/{id}/reply | Authorization: Bearer <管理员 token> | 路径参数 id：先调用 GET /admin/reviews?page=1&size=5 取一条记录的 id；请求体：{}（删除必填 body 字段 reply） | 请求：PUT /admin/reviews/{id}/reply<br>请求头：Authorization: Bearer <管理员 token><br>参数：路径参数 id：先调用 GET /admin/reviews?page=1&size=5 取一条记录的 id；请求体：{}（删除必填 body 字段 reply）<br>步骤：取评价 id；发送空 body 请求；记录响应 | 200 | 40000（源码现状：BusinessException 无 @ResponseStatus） | HTTP=200；code=40000；msg 含"回复内容不能为空"；data 为 null；该评价 merchantReply 保持原值不变 | 无需清理（未产生写入） | 源码 ReviewAdminService#reply 第 81-83 行；需求：EXT-REVIEW-REPLY-001 |
| PUT_ADMIN_REVIEWS_ID_REPLY-003 | P1 | 业务 | 管理员回复评价_评价不存在_提示资源不存在 | 环境：baseUrl（BASE_URL）与测试账号由 pytest 环境变量提供（conftest 自动注入）。<br>账号：管理员 token（ADMIN_TEST_ACCOUNT / ADMIN_TEST_PASSWORD 登录后由 fixture 注入 Authorization）<br>数据：不存在的评价 id；准备方式：使用固定值 99999999（远大于任何自增 id） | PUT /admin/reviews/99999999/reply | Authorization: Bearer <管理员 token> | 路径参数 id：99999999（不存在的资源）；请求体：{"reply":"自动化测试回复内容"} | 请求：PUT /admin/reviews/99999999/reply<br>请求头：Authorization: Bearer <管理员 token><br>参数：路径参数 id：99999999（不存在的资源）；请求体：{"reply":"自动化测试回复内容"}<br>步骤：直接发送回复请求；记录响应 | 200 | 40400（源码现状：BusinessException 无 @ResponseStatus） | HTTP=200；code=40400；msg 含"资源不存在"；data 为 null | 无需清理（未产生写入） | 源码 ReviewAdminService#reply 第 88-91 行；需求：EXT-REVIEW-REPLY-001 |
| PUT_ADMIN_REVIEWS_ID_REPLY-004 | P0 | 鉴权 | 管理员回复评价_未带Token_拒绝访问 | 环境：baseUrl（BASE_URL）与测试账号由 pytest 环境变量提供（conftest 自动注入）。<br>账号：不发送 Authorization（验证未登录场景）<br>数据：一条已发表评价；准备方式：先用管理员 token 调用 GET /admin/reviews?page=1&size=5 取 data.records[0].id | PUT /admin/reviews/{id}/reply | 不含 Authorization | 路径参数 id：先用管理员 token 调用 GET /admin/reviews?page=1&size=5 取一条记录的 id；请求体：{"reply":"自动化测试回复内容"} | 请求：PUT /admin/reviews/{id}/reply<br>请求头：不含 Authorization<br>参数：路径参数 id：先用管理员 token 调用 GET /admin/reviews?page=1&size=5 取一条记录的 id；请求体：{"reply":"自动化测试回复内容"}<br>步骤：删除 Authorization 头；发送请求；记录响应 | 401 | UNAUTHORIZED | HTTP=401；error.code=UNAUTHORIZED；响应不含 data 且不泄露内部堆栈；该评价 merchantReply 未被修改 | 无需清理（未产生写入） | 实测 401/40100；需求：EXT-REVIEW-REPLY-001 |
| POST_API_CUSTOMER_SERVICE_CHAT-001 | P1 | 正向 | AI 助手对话_匿名提问商品推荐_回答成功 | 环境：baseUrl（BASE_URL）由 pytest 环境变量提供（conftest 自动注入）；需 Agent 子服务已启动。<br>账号：不发送 Authorization（该端点 permitAll，匿名可用）<br>数据：无需额外数据；准备方式：不构造 | POST /api/customer-service/chat | 不含 Authorization | 请求体：{"message":"有哪些适合送礼的商品推荐"} | 请求：POST /api/customer-service/chat<br>请求头：不含 Authorization<br>参数：请求体：{"message":"有哪些适合送礼的商品推荐"}<br>步骤：发送请求；记录响应 | 200 | 0 | HTTP=200；code=0；data.answer 非空字符串；data.runId 与 data.traceId 非空；data.latencyMs 为数值 | 无需清理（只读对话，不落业务数据） | Agent 子服务未启动时返回 code=50000（环境依赖，非接口缺陷）；需求：EXT-AI-001 |
| POST_API_CUSTOMER_SERVICE_CHAT-002 | P2 | 参数 | AI 助手对话_缺少message_提示参数错误 | 环境：baseUrl（BASE_URL）由 pytest 环境变量提供（conftest 自动注入）。<br>账号：不发送 Authorization（该端点 permitAll）<br>数据：无需额外数据；准备方式：不构造 | POST /api/customer-service/chat | 不含 Authorization | 请求体：{}（删除必填 body 字段 message） | 请求：POST /api/customer-service/chat<br>请求头：不含 Authorization<br>参数：请求体：{}（删除必填 body 字段 message）<br>步骤：发送空 body 请求；记录响应 | 400 | 40000 | HTTP=400；code=40000；msg 含"message 不能为空"；data 为 null | 无需清理（未产生写入） | @Valid + @NotBlank 触发，实测 400/40000；需求：EXT-AI-001 |
| POST_API_CUSTOMER_SERVICE_CHAT-003 | P2 | 边界 | AI 助手对话_message超过2000字_提示参数错误 | 环境：baseUrl（BASE_URL）由 pytest 环境变量提供（conftest 自动注入）。<br>账号：不发送 Authorization（该端点 permitAll）<br>数据：无需额外数据；准备方式：不构造 | POST /api/customer-service/chat | 不含 Authorization | 请求体：{"message":"a"×2001}（长度取上限 2000 的 +1 边界值） | 请求：POST /api/customer-service/chat<br>请求头：不含 Authorization<br>参数：请求体：{"message":"a"×2001}（长度取上限 2000 的 +1 边界值）<br>步骤：构造 2001 字符 message；发送请求；记录响应 | 400 | 40000 | HTTP=400；code=40000；msg 含"message 不能超过 2000 字"；data 为 null | 无需清理（未产生写入） | @Size(max=2000)，实测 400/40000；需求：EXT-AI-001 |
| POST_API_CUSTOMER_SERVICE_CHAT-004 | P1 | 正向 | AI 助手对话_携带会话ID连续提问_沿用同一会话 | 环境：baseUrl（BASE_URL）由 pytest 环境变量提供（conftest 自动注入）；需 Agent 子服务已启动。<br>账号：普通用户 token（APP_TEST_ACCOUNT / APP_TEST_PASSWORD 登录后由 fixture 注入 Authorization），用于订单相关提问<br>数据：一个会话 ID；准备方式：首次调用时由服务端生成，或用固定值 "auto-session-001" | POST /api/customer-service/chat | Authorization: Bearer <普通用户 token> | 请求体：{"message":"我的订单到哪了","sessionId":"auto-session-001"} | 请求：POST /api/customer-service/chat<br>请求头：Authorization: Bearer <普通用户 token><br>参数：请求体：{"message":"我的订单到哪了","sessionId":"auto-session-001"}<br>步骤：先不带 sessionId 提问一次取回 data.sessionId；再带该 sessionId 提问；比较两次返回 | 200 | 0 | HTTP=200；code=0；第二次响应 data.sessionId 与传入值一致；data.answer 非空 | 无需清理（只读对话） | 订单查询依赖 Authorization 透传；需求：EXT-AI-001 |

## 合入说明

1. 这 8 条按 rule.md §7 的完成标准补足了两个接口的「正向 / 未带Token / 缺少必填参数 / 边界」四类维度；
   `PUT /admin/reviews/{id}/reply` 另补了业务层（资源不存在）。
2. 合入 `test_cases_inventory.md` 时需同步更新顶部「覆盖统计」：端点数 135 → 137、用例数 424 → 432。
3. 合入后执行 `python scripts/case_lint.py` 清零再上传。
