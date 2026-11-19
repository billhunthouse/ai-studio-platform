"""追溯平台扫描器集合。

每个扫描器负责把一种"事实来源"翻译成追溯实体与关联：

- java_entity_scanner  : MyBatis-Plus 实体 → 数据表 + 字段（CODE_SCAN）
- java_api_scanner     : Spring Controller 注解 → 接口 + 参数 + 实现类（CODE_SCAN）
- 后续：openapi_scanner / ddl_scanner / prd_scanner

约定（与 001-adapter-spec.md 一致）：
1. 扫描结果只做 upsert，不删除人工登记的数据
2. 每个实体带 source（SPEC / CODE_SCAN / DOC_PARSE / HUMAN）与置信度
3. 一次扫描写一条 trace_scan_runs 记录，便于审计与增量对比
"""
