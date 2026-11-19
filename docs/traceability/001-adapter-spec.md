# 扫描适配器规范（v2.1）

> 目标：把"自动发现关联"标准化。四类适配器统一接口、统一输出、统一置信度。
> 核心原则：**机器负责发现，人工只做确认**；只有高置信来源可直接 confirmed。

---

## 1. 适配器统一契约

### 1.1 接口签名（伪代码，非实现）

```
interface ScanAdapter {
  name: string                    // openapi | annotation | ddl | prd
  detect(repo_path, commit_sha) -> boolean   // 该仓库是否需要此适配器
  extract(ctx: ScanContext) -> ExtractionResult
}

ScanContext = {
  project_id, repo_path, commit_sha,
  changed_files: string[],        // 增量扫描：本次变更的文件
  config: AdapterConfig           // 适配器专属配置
}

ExtractionResult = {
  entities:  DiscoveredEntity[],  // 发现的实体
  relations: DiscoveredRelation[],// 发现的关联
  warnings:  ScanWarning[],
  stats:     { extracted, proposed, confirmed }
}
```

### 1.2 统一输出结构

```json
{
  "entity": {
    "type": "api | page | table | code_artifact",
    "id": "api:GET:/api/products/{spuId}",
    "fields": { ... },
    "evidence": { "file": "...", "line": 42, "commit": "a3f9c21" }
  },
  "relation": {
    "src": {"type":"...","id":"..."},
    "rel_type": "EXPOSED_BY",
    "dst": {"type":"...","id":"..."},
    "source": "CODE_SCAN",
    "confidence": 95,
    "evidence": { "file":"OrderController.java", "line":18, "snippet":"@GetMapping(...)" }
  }
}
```

**每个发现都带 evidence（文件+行号+commit）**——这是可验证、可回溯的关键，人工确认时能点到源代码。

---

## 2. 四类适配器详细规范

### 2.1 OpenAPI 适配器

| 项 | 内容 |
| --- | --- |
| 输入 | `openapi.yaml` / `swagger.json` |
| 发现实体 | Api（含 method/path/schema/auth） |
| 发现关联 | Requirement ↔ Api（若 spec 中带 `x-requirement-id` 扩展字段） |
| 置信度 | 95（SPEC 来源，直接 confirmed） |
| ID 生成 | `api:{METHOD}:{path}`（path 保留 `{}` 参数占位） |
| 特殊处理 | `$ref` 展开；schema 存 JSONB；`security` → auth_requirement |

```yaml
# 支持的扩展字段（约定）
paths:
  /api/products/{spuId}:
    get:
      x-requirement-id: "V2-FR-015"   # 平台读取此字段建立需求↔接口关联
      x-service: "product-service"
```

### 2.2 注解适配器（Spring Boot）

| 项 | 内容 |
| --- | --- |
| 输入 | Java 源文件（`*Controller.java`） |
| 发现实体 | CodeArtifact（接口级） |
| 发现关联 | Api ↔ CodeArtifact（EXPOSED_BY） |
| 置信度 | 90-95（CODE_SCAN，直接 confirmed） |
| 解析规则 | `@RequestMapping`/`@GetMapping` 等 → Api；类名+方法名 → CodeArtifact ID |

```
识别清单：
- @RequestMapping / @GetMapping / @PostMapping → method + path
- 类级 @RequestMapping + 方法级路径 → 拼接完整 path
- @PathVariable / @RequestBody → request_schema 线索
- @PreAuthorize / @RequiresRole → auth_requirement
```

**路径拼接**：类级 `/admin/reviews` + 方法级 `/{id}/reply` = `/admin/reviews/{id}/reply`，与 OpenAPI 的 path 匹配后建立 Api↔Code 关联。

### 2.3 DDL 适配器

| 项 | 内容 |
| --- | --- |
| 输入 | `schema.sql` / Flyway / Liquibase 迁移文件 / ORM 模型 |
| 发现实体 | Table（含 columns/indexes） |
| 发现关联 | CodeArtifact ↔ Table（READS_WRITES，需配合 Mapper 分析） |
| 置信度 | 95（SPEC，直接 confirmed） |
| ID 生成 | `table:{database}:{schema}:{name}` |

```
解析清单：
- CREATE TABLE → Table 实体 + columns JSONB
- PRIMARY KEY / UNIQUE / INDEX → indexes JSONB
- 跨库引用（多个 database 前缀）→ 标 CROSS_DB_READ 警告
```

### 2.4 PRD/原型适配器

| 项 | 内容 |
| --- | --- |
| 输入 | PRD 文档（DOCX/MD）+ 原型图说明 |
| 发现实体 | Page（产品功能页面） |
| 发现关联 | Requirement ↔ Page（SPLITS_INTO） |
| 置信度 | 60-75（DOC_PARSE，**proposed 需确认**） |
| 解析策略 | 章节标题 → 功能页面；"FR-xxx" 引用 → 需求关联 |

```
识别清单：
- 标题含"页面"/"功能"/"模块" → 候选 Page
- 文中出现 "V2-FR-015" 等需求 ID → 建立关联候选
- 原型图文件名/链接 → prototype_ref
- 无法确认归属的 → proposed，进待确认列表
```

---

## 3. 置信度规则表

| 来源 | 置信度范围 | 默认状态 | 理由 |
| --- | --- | --- | --- |
| `HUMAN` | 100 | confirmed | 人工登记最可信 |
| `SPEC`（OpenAPI/DDL） | 95 | confirmed | 机器可读契约，确定性强 |
| `CODE_SCAN`（注解） | 90-95 | confirmed | 框架注解语义明确 |
| `DOC_PARSE`（PRD） | 60-75 | proposed | 自然语言解析有歧义 |
| `AI_INFER` | 30-60 | proposed（默认关闭） | 推断成分高，风险大 |

**规则**：confidence ≥ 90 且 source ∈ {HUMAN, SPEC, CODE_SCAN} → 直接 confirmed；其余一律 proposed。

---

## 4. 增量扫描机制

### 4.1 基于 commit 的增量

```
1. 读取上次 ScanRun 的 commit_sha
2. git diff <last_sha>..<current_sha> → changed_files
3. 适配器只处理 changed_files
4. 未变更文件的关联保持不变
```

### 4.2 漂移检测（stale 机制）

| 场景 | 处理 |
| --- | --- |
| 本次扫描未再发现某 confirmed 关联的依据 | 标 `stale`，通知 Owner 复核 |
| 本次发现新的关联 | 标 `proposed`，进待确认列表 |
| 实体被删除（status=removed） | 其 confirmed 关联批量转 stale |

**关键**：不自动删除 confirmed 关联——"依据消失"可能是代码重构而非功能删除，必须由人判断。

---

## 5. 扫描流水线编排

```
触发（手动/定时CI）
   ↓
获取 commit_sha + changed_files
   ↓
并行执行 4 个适配器（detect → extract）
   ↓
合并 ExtractionResult → 去重（按 ID + 关系三元组）
   ↓
置信度判定 → confirmed / proposed
   ↓
写入 trace_relations + 记录 ScanRun 统计
   ↓
stale 通知 Owner；proposed 进待确认列表
```

---

## 6. 质量保障（避免噪音淹没）

| 措施 | 说明 |
| --- | --- |
| 默认关闭 AI_INFER | 低置信推断不启用，开启需管理员配置 |
| 扫描默认不通知 | proposed 只进待确认列表，不推送 |
| stale 才主动通知 | 因为意味着现有图谱可能错了，优先级最高 |
| 待确认页批量操作 | 支持按置信度排序、批量确认/驳回 |
| 每周清理机制 | proposed 积压超阈值时提醒负责人处理 |
| evidence 可追溯 | 每条候选带文件+行号，确认时可核对 |

---

## 7. 适配器实现清单（供下一阶段）

| 适配器 | MVP 优先级 | 依赖 |
| --- | --- | --- |
| OpenAPI | P0 | 现成 spec 文件，最快见效 |
| DDL | P0 | schema.sql，解析简单 |
| 注解（Java） | P1 | 需 Java AST 解析器 |
| PRD | P1 | 需文档解析 + 需求 ID 识别 |
| AI_INFER | P2 | 默认关闭 |

---

## 8. 验收标准

| 项 | 标准 |
| --- | --- |
| 准确率 | OpenAPI/DDL 适配器发现准确率 ≥95%；注解 ≥90% |
| 可追溯 | 每条发现带 evidence，点击可定位源文件行号 |
| 增量 | 第二次扫描只处理 changed_files，不重复全量 |
| 漂移 | 删除注解后重扫，关联转 stale 而非被删 |
| 无噪音 | proposed 不推送通知；stale 才通知 |
| 幂等 | 同一 commit 重复扫描不产生重复关联 |
