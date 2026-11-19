# API 契约（v2.1）

> 风格对齐 AI_Studio：FastAPI + 响应封装 `{code, message, data}` + `X-Project-Id` 请求头 + RBAC。
> 本文是接口契约，不含实现代码。

---

## 0. 通用约定

### 0.1 请求头

| Header | 必填 | 说明 |
| --- | --- | --- |
| `Authorization` | 是 | Bearer JWT（沿用现有） |
| `X-Project-Id` | 是 | 项目 ID，所有追溯接口必带 |

### 0.2 响应封装

```json
{ "code": 0, "message": "success", "data": { ... } }
```
错误码：`code=0` 成功；`40001` 参数错误；`40301` 无权限；`40401` 不存在；`40901` 冲突；`50301` 依赖不可用。

### 0.3 错误状态

| code | HTTP | 说明 |
| --- | --- | --- |
| 40001 | 400 | 关联两端类型组合非法 / ID 格式错误 |
| 40301 | 403 | 非项目成员 / 角色权限不足 |
| 40401 | 404 | 实体不存在或不属于本项目 |
| 40901 | 409 | 关联已存在（唯一约束冲突） |
| 50301 | 503 | 扫描器/LLM 不可用 |

### 0.4 权限矩阵速查

| 操作 | 只读 | 评审者 | 开发者 | 管理员 |
| --- | --- | --- | --- | --- |
| 查询实体/关联/影响 | ✅ | ✅ | ✅ | ✅ |
| 创建/编辑实体 | ❌ | ❌ | ✅ | ✅ |
| 创建人工关联 | ❌ | ❌ | ✅ | ✅ |
| 确认/驳回 proposed | ❌ | ✅ | ✅ | ✅ |
| 触发扫描 | ❌ | ❌ | ✅ | ✅ |
| 管理 Release / 版本快照 | ❌ | ❌ | ❌ | ✅ |
| 查看审计 | ❌ | ❌ | ❌ | ✅ |

---

## 1. 实体 CRUD（五类统一模式）

以 Api 为例，其他实体同构。

### 1.1 列表查询

```
GET /api/trace/apis
Query: page, page_size(默认20), method, service, status, source, keyword
Response.data:
{
  "total": 128,
  "items": [
    { "id": "api:GET:/api/products/{spuId}", "method": "GET",
      "path": "/api/products/{spuId}", "summary": "商品详情",
      "service": "product-service", "auth_requirement": "public",
      "status": "active", "source": "SPEC",
      "upstream_requirement_count": 3,   // 反查聚合
      "calling_page_count": 2,
      "read_tables_count": 4,
      "updated_at": "2026-11-19T10:00:00Z" }
  ]
}
```

### 1.2 详情查询（含双向关联）

```
GET /api/trace/apis/{id}
Response.data:
{
  "entity": { ...完整字段... },
  "relations": {
    "upstream": [   // 谁指向我（反向）
      { "rel_type": "TRIGGERS", "from_type": "page",
        "from_id": "page:shang:product-detail-01", "from_name": "商品详情页" },
      { "rel_type": "SPLITS_INTO", "from_type": "requirement",
        "from_id": "V2-FR-015", "from_name": "发表评价" }
    ],
    "downstream": [ // 我指向谁（正向）
      { "rel_type": "EXPOSED_BY", "to_type": "code_artifact", "to_id": "code:..." },
      { "rel_type": "READS_WRITES", "to_type": "table", "to_id": "table:mall:review" }
    ]
  }
}
```

> 关键：详情接口**同时返回 upstream 和 downstream**，这是"双向可查"的接口层保证。

### 1.3 创建 / 更新 / 废弃

```
POST   /api/trace/apis         body: {id, method, path, service, ...}
PUT    /api/trace/apis/{id}    body: 部分字段
DELETE /api/trace/apis/{id}    → 软废弃 status=removed，不物理删除
```

其他实体端点：
| 实体 | 端点 |
| --- | --- |
| Page | `/api/trace/pages` |
| CodeArtifact | `/api/trace/artifacts` |
| Table | `/api/trace/tables` |
| Requirement | 复用现有 `/api/requirements`，扩展字段通过 PUT |

---

## 2. 关联接口（核心）

### 2.1 双向查询（通用）

```
GET /api/trace/relations
Query:
  direction = forward | backward | both
  entity_type = requirement|page|api|code_artifact|table
  entity_id  = <ID>
  rel_type   = 可选过滤
  status     = confirmed(默认) | proposed | stale | all
  release    = 可选，按版本区间过滤
Response.data:
{
  "items": [ { "relation_id", "rel_type", "direction",
               "src": {type,id,name}, "dst": {type,id,name},
               "source", "confidence", "status",
               "valid_from_release", "valid_to_release" } ],
  "total": 8
}
```

### 2.2 创建人工关联

```
POST /api/trace/relations
Body:
{
  "src": {"type":"requirement","id":"EXT-REVIEW-REPLY-001"},
  "rel_type": "SPLITS_INTO",
  "dst": {"type":"page","id":"page:shang:review-reply-01"},
  "note": "人工登记：回复功能对应管理端页面"
}
校验：类型组合合法 + 两端存在 + 同 project → 直接 confirmed（HUMAN 来源）
Response: { relation_id, status: "confirmed" }
```

### 2.3 确认 / 驳回 proposed

```
POST /api/trace/relations/{id}/confirm   → status=confirmed, confirmed_by=当前用户
POST /api/trace/relations/{id}/reject    body:{reason} → status=rejected
POST /api/trace/relations/batch-confirm  body:{ids:[...]} → 批量确认（待确认页用）
权限：评审者 / 开发者 / 管理员（只读不可）
```

### 2.4 待确认列表

```
GET /api/trace/relations/pending
Query: page, page_size, source, status(proposed|stale), sort=confidence_desc|created_desc
Response.data:
{
  "total": 23,
  "stale_count": 4,
  "items": [
    { "relation_id", "rel_type", "src":{...}, "dst":{...},
      "source": "DOC_PARSE", "confidence": 72, "status": "proposed",
      "first_seen_scan": "...", "created_at": "..." }
  ]
}
```

---

## 3. 影响分析接口

### 3.1 正向影响（给定实体，看影响范围）

```
GET /api/trace/impact/forward
Query: entity_type, entity_id, max_hops(默认3), release(可选)
Response.data:
{
  "root": {"type":"requirement","id":"EXT-REVIEW-REPLY-001"},
  "hops": [
    { "hop":1, "items":[ {type:"page", id:"...", name:"..."} ] },
    { "hop":2, "items":[ {type:"api",  id:"...", name:"..."} ] },
    { "hop":3, "items":[ {type:"table",id:"...", name:"..."} ] }
  ],
  "all_affected_count": 9,
  "cross_database_warning": false
}
```

### 3.2 反向追溯（给定表/接口，看上游需求）

```
GET /api/trace/impact/backward
Query: entity_type, entity_id, max_hops(默认3)
Response.data:
{
  "root": {"type":"table","id":"table:mall:review"},
  "upstream_requirements": [
    { "id":"V2-FR-015", "title":"发表评价", "hops":2, "path":["table","api","page","requirement"] },
    { "id":"EXT-REVIEW-REPLY-001", "title":"商家回复评价", "hops":3, "path":[...] }
  ]
}
```

### 3.3 按发布版本的影响

```
GET /api/trace/impact/release/{version}
Response.data:
{
  "version": "v2.3.0",
  "affected_requirements": [...],
  "relation_changes": { "added": [...], "removed": [...], "deprecated": [...] }
}
```

---

## 4. 扫描接口

### 4.1 触发扫描

```
POST /api/trace/scans/trigger
Body:
{
  "adapter": "openapi|annotation|ddl|prd",
  "repo": "shang-product-service",   // 可选，不填扫全部
  "commit_sha": "abc123"             // 可选，增量扫描基准
}
权限：开发者 / 管理员
Response: { scan_run_id, status: "running" }（异步）
```

### 4.2 扫描结果

```
GET /api/trace/scans/{scan_run_id}
Response.data:
{
  "adapter": "annotation", "status": "success",
  "extracted_count": 42, "proposed_count": 18,
  "confirmed_count": 24, "stale_count": 3,
  "started_at": "...", "finished_at": "..."
}
```

### 4.3 扫描历史

```
GET /api/trace/scans
Query: page, page_size, adapter, status, trigger
```

---

## 5. 版本接口

```
GET    /api/trace/releases                        # 列表
GET    /api/trace/releases/{version}              # 详情（含快照）
POST   /api/trace/releases                        # 创建发布版本（管理员）
POST   /api/trace/releases/{version}/snapshot     # 冻结当前 confirmed 关联为快照（管理员）
GET    /api/trace/releases/compare?from=v2.2.0&to=v2.3.0   # 版本对比
```

---

## 6. 总览与矩阵接口

### 6.1 需求总览统计

```
GET /api/trace/overview
Response.data:
{
  "requirement_total": 64,
  "coverage_rate": 0.87,          // 五层关联完整率
  "pending_relation_count": 23,   // 待确认
  "stale_relation_count": 4,
  "by_status": {...},
  "by_domain": {...}
}
```

### 6.2 追踪矩阵

```
GET /api/trace/matrix
Query: release, domain, page, page_size
Response.data:
{
  "columns": ["requirement","page","api","code","table","coverage"],
  "rows": [
    { "requirement": {"id":"...","title":"..."},
      "page": 2, "api": 3, "code": 3, "table": 1,
      "coverage": 100, "missing": [] }
  ]
}
```

---

## 7. 审计接口

```
GET /api/trace/audit
Query: page, page_size, actor, action, entity_type, date_from, date_to
权限：管理员
Response.data: { total, items:[{actor_name,action,entity_type,entity_id,before,after,created_at}] }
```

---

## 8. 接口清单速查表

| 分组 | 接口数 | 说明 |
| --- | --- | --- |
| 实体 CRUD | 5 组 × 5 = 25 | 五类实体统一模式 |
| 关联管理 | 6 | 双向查询/创建/确认/驳回/批量/待确认 |
| 影响分析 | 3 | 正向/反向/按版本 |
| 扫描 | 3 | 触发/结果/历史 |
| 版本 | 6 | 列表/详情/创建/快照/对比 |
| 总览矩阵 | 2 | 统计/矩阵 |
| 审计 | 1 | 日志 |
| **合计** | **约 46** | |

---

## 9. 实现注意事项（供下一阶段）

1. 所有接口强制 `project_id` 过滤，从 `X-Project-Id` 读取并校验成员身份
2. `GET relations` 的 `direction=both` 用 UNION 或两次查询合并，避免重复
3. 影响分析用 PostgreSQL 递归 CTE，`max_hops` 限制防止深图爆炸
4. 扫描触发异步（后台任务），接口立即返回 scan_run_id
5. 软删除实体时，其 confirmed 关联批量转 stale
6. 批量确认需注意事务与并发（同一 relation 被两人确认）
