"""数据表字段中文语义库 · 表/字段说明的统一权威来源.

三层来源（按优先级）：
1. DDL 真实注释：解析 shang-pivot 仓库 migration 里的 `COMMENT ON COLUMN`
   （数据库设计者的原话，最权威）；
2. 知识字典：源码无注释的表（购物车/评价/运营位/地址等），
   按字段名语义 + 真实代码证据（枚举赋值处）撰写；
3. 通用字段规则：id/created_at/updated_at/deleted/trace_id 等平台公共字段。

用途：
- backend/enrich_field_comments.py —— 批量补全 trace_tables.columns 中缺失的 comment；
- scanners/java_scanner.parse_entity —— 重扫兜底，保证重扫不丢说明。

证据分级遵循平台规范：DDL 注释 > 代码枚举推导 > 语义知识。
"""

from __future__ import annotations

import re
from pathlib import Path

# ---------------------------------------------------------------- 真实库精确类型

REAL_DB_DSN = "postgresql://shang:shang@127.0.0.1:55434/shang"


def real_column_types(schema: str, table: str) -> dict[str, str]:
    """从真实业务库读列的精确 PostgreSQL 类型（含长度/精度），用于重扫时覆盖 Java 推断。

    Java 实体字段只有 String/Integer 等粗粒度类型，扫描器只能给出 varchar(255) 默认值；
    真实库 information_schema 才是 DDL+所有 ALTER 后的最终状态（如 phone varchar(20)）。
    库不可达时返回空字典，调用方保留 Java 推断值。
    """
    try:
        import psycopg
        with psycopg.connect(REAL_DB_DSN, connect_timeout=2) as conn:
            rows = conn.execute("""
                SELECT column_name, data_type, character_maximum_length,
                       numeric_precision, numeric_scale
                FROM information_schema.columns
                WHERE table_schema = %s AND table_name = %s
            """, (schema, table)).fetchall()
    except Exception:
        return {}

    out: dict[str, str] = {}
    for name, dtype, maxlen, prec, scale in rows:
        dt = dtype.lower()
        if dt == "character varying":
            t = f"varchar({maxlen})" if maxlen else "varchar"
        elif dt == "timestamp with time zone":
            t = "timestamptz"
        elif dt == "double precision":
            t = "float8"
        elif dt == "numeric":
            t = f"numeric({prec},{scale})" if prec else "numeric"
        elif dt == "integer":
            t = "int4"
        elif dt == "smallint":
            t = "int2"
        elif dt == "boolean":
            t = "bool"
        else:
            t = dt
        out[name] = t
    return out


# ---------------------------------------------------------------- DDL 真实注释

SHANG_REPO = Path("/Users/imac/Desktop/shang-pivot/backend")
MIGRATION_GLOB = "shang-server/src/main/resources/db/migration/*.sql"

COMMENT_RE = re.compile(
    r"COMMENT\s+ON\s+COLUMN\s+(?P<schema>[\w\"]+)\.(?P<table>[\w\"]+)\.(?P<col>[\w\"]+)"
    r"\s+IS\s+'(?P<text>(?:[^']|'')*)'",
    re.IGNORECASE,
)


def parse_ddl_comments(repo: Path = SHANG_REPO) -> dict[tuple[str, str], str]:
    """解析全部 migration SQL 中的 COMMENT ON COLUMN，返回 {(table, column): 说明}.

    说明会追加「〔DDL〕」证据标记，与 PRD 业务规则的证据链风格一致。
    """
    out: dict[tuple[str, str], str] = {}
    if not repo.exists():
        return out
    for sql_file in sorted(repo.glob(MIGRATION_GLOB)):
        text = sql_file.read_text(encoding="utf-8", errors="ignore")
        for m in COMMENT_RE.finditer(text):
            table = m.group("table").strip('"')
            col = m.group("col").strip('"')
            body = m.group("text").replace("''", "'").strip()
            if body:
                out[(table, col)] = body
    return out


# ---------------------------------------------------------------- 知识字典
# 源码无 DDL 注释的表：按字段名语义 + 真实代码证据撰写。
# 枚举值均来自真实代码（见各条目内标注的代码位置）。

KNOWLEDGE_GLOSSARY: dict[str, dict[str, str]] = {
    # 收货地址（commerce.address）
    "address": {
        "customer_id": "顾客 ID",
        "name": "收货人姓名",
        "phone": "收货人手机号",
        "province": "省份",
        "city": "城市",
        "district": "区/县",
        "detail": "详细地址",
        "is_default": "是否默认地址",
    },
    # 浏览足迹（commerce.browse_history）
    "browse_history": {
        "customer_id": "顾客 ID",
        "spu_id": "浏览的商品 SPU ID",
        "last_at": "最近一次浏览时间",
    },
    # 购物车（一顾客一车）
    "cart": {
        "customer_id": "顾客 ID（一顾客一车）",
    },
    # 购物车明细
    "cart_item": {
        "cart_id": "所属购物车 ID",
        "sku_id": "SKU ID",
        "quantity": "加入数量",
        "selected": "是否勾选参与结算",
    },
    # C 端顾客账号（identity.customer）
    "customer": {
        "nickname": "会员昵称",
        "avatar": "头像图片 objectKey",
        # status 取值证据：CustomerController「C 端会员查询与冻结」
        "status": "会员状态：NORMAL 正常 / FROZEN 冻结（冻结后不可下单）",
        "openid": "微信 openid（微信登录扩展用，手机号登录时可空）",
        "union_id": "微信 unionId（跨小程序/公众号识别同一用户）",
        "last_login_at": "最近登录时间",
    },
    # 商品收藏（commerce.favorite）
    "favorite": {
        "customer_id": "顾客 ID",
        "spu_id": "收藏的商品 SPU ID",
        "created_at": "收藏时间",
    },
    # 首页运营位槽位（commerce.home_slot）
    "home_slot": {
        "code": "槽位编码（唯一，如 banner / hot_products）",
        "title": "槽位标题",
        # status 取值证据：HomeSlotService + @Parameter「状态：ENABLED / DISABLED」
        "status": "状态：ENABLED / DISABLED（C 端仅展示 ON 且在时间窗内）",
        "sort": "排序，越小越靠前",
        "valid_from": "生效开始时间（时间窗起点）",
        "valid_to": "生效结束时间（时间窗终点）",
    },
    # 运营位内容项（Banner/选品/热搜词）
    "home_slot_item": {
        "slot_id": "所属槽位 ID",
        "spu_id": "关联商品 SPU ID（选品类内容）",
        "title": "内容标题",
        "image_key": "内容图片 objectKey",
        # link_type 证据：HomeSlotService 默认 "NONE"
        "link_type": "点击跳转类型（如 SPU 商品详情；无跳转为 NONE）",
        "link_value": "跳转目标值（如 SPU ID）",
        "extra": "扩展信息 JSONB（如热搜词配置）",
        # status 证据：HomeSlotService 默认 "ON"
        "status": "状态：ON 展示 / OFF 隐藏",
        "sort": "排序，越小越靠前",
    },
    # 订单项评价（commerce.review）
    "review": {
        "customer_id": "评价人顾客 ID",
        "order_item_id": "关联订单明细 ID（一单一评）",
        "spu_id": "评价的商品 SPU ID",
        "rating": "评分 1-5 星",
        "content": "评价内容",
        "pics": "评价图 objectKey 列表 JSONB",
        # status 证据：StorefrontController 发表即 VISIBLE；ReviewAdminService 后台可改
        "status": "状态：VISIBLE 可见 / HIDDEN 后台隐藏",
        "merchant_reply": "商家回复内容",
        "replied_at": "商家回复时间",
    },
    # 站点品牌（commerce.site_brand，推荐单行 id=1）
    "site_brand": {
        "name": "站点名称",
        "slogan": "站点标语",
        "logo_key": "Logo 图片 objectKey",
        "favicon_key": "浏览器标签页图标 objectKey",
        "updated_by": "最后更新人用户 ID",
    },
    # 订单事件日志（commerce.order_event_log，状态机事件流水）
    "order_event_log": {
        "order_id": "订单 ID",
        # 事件类型对应订单状态机各节点（下单/支付/发货/收货/关单）
        "event_type": "订单事件类型（状态机节点事件，如支付成功/发货/确认收货/关单）",
        "payload": "事件附加内容（发生时的上下文快照）",
    },
    # 出入库单（commerce.in_out_order）
    "in_out_order": {
        "bill_no": "出入库单号（唯一，含类型前缀）",
        "warehouse_id": "仓库 ID",
        "operator_id": "经办人用户 ID（定时任务写入时为空）",
        "related_order_no": "关联业务单号（如销售出库关联订单号）",
        "remark": "备注",
    },
    # 出入库明细（commerce.in_out_item）
    "in_out_item": {
        "bill_id": "所属出入库单 ID",
        "sku_id": "SKU ID",
        "remark": "明细备注",
    },
}


# ---------------------------------------------------------------- 通用字段

COMMON_FIELDS: dict[str, str] = {
    "id": "主键（雪花 ID）",
    "created_at": "创建时间",
    "updated_at": "更新时间",
    "deleted": "逻辑删除标记",
    "trace_id": "请求 traceId（链路追踪）",
}


# ---------------------------------------------------------------- 统一入口


def comment_for(table: str, column: str, ddl: dict[tuple[str, str], str] | None = None) -> tuple[str, str] | None:
    """返回 (中文说明, 来源)。来源 ∈ {DDL, KNOWLEDGE, COMMON}；无合适说明返回 None.

    优先级：DDL 真实注释 > 知识字典 > 通用字段。已有说明不覆盖（由调用方保证）。
    """
    ddl = ddl if ddl is not None else parse_ddl_comments()
    if (table, column) in ddl:
        return ddl[(table, column)], "DDL"
    hit = KNOWLEDGE_GLOSSARY.get(table, {}).get(column)
    if hit:
        return hit, "KNOWLEDGE"
    if column in COMMON_FIELDS:
        return COMMON_FIELDS[column], "COMMON"
    return None
