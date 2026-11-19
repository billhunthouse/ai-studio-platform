"""【已废弃】v0.5 的演示数据导入脚本，不要再用。

它的需求（REQ-018~021）、页面（8 个）、数据表（5 张优惠券/会员表）、接口（6 个）都是
按演示需要编的，与真实仓库对不上——例如系统里根本没有优惠券模块，也没有 /member 页面。
继续跑会把假数据重新写回库里，污染覆盖率统计。

现在数据来源拆成两个脚本，各自负责一类事实：
  - seed_prd.py      ：从 llm-wiki 的 02-requirements.md / 04-page-map.md 导入真实需求与页面；
  - scanners/java_scanner.py：从真实源码扫描接口、代码实体、数据表与读写关系。
保留本文件仅作历史对照。

原始说明：追溯平台真实数据导入（ecommerce 项目）。

数据来源：shang-pivot-master/docs/llm-wiki 的
  - 03-需求与页面地图.md   → 页面路由
  - 04-接口契约与鉴权.md   → 接口路径与鉴权要求
  - 05-数据模型与业务规则.md → schema 与核心表

幂等：已存在的实体/关联跳过（409 视为成功）。
用法：.venv/bin/python seed_traceability.py
"""
from __future__ import annotations

import os
import sys

import httpx

BASE = os.getenv("TRACE_API", "http://127.0.0.1:8000/api/v1")
PROJECT = os.getenv("TRACE_PROJECT", "ecommerce")
ADMIN_EMAIL = os.getenv("TRACE_EMAIL", "zhangwei@corp.com")

# ---------------------------------------------------------------- 数据定义

PAGES = [
    # code, name, feature_domain, route, prd_section
    ("mall-checkout", "确认订单", "交易", "/checkout", "V2-FR-003"),
    ("mall-order-detail", "订单详情", "交易", "/orders/:id", "V2-FR-005"),
    ("mall-aftersale-apply", "申请售后", "售后", "/after-sales/apply", "V1-FR-018"),
    ("admin-aftersale", "售后管理", "售后", "/admin/aftersales", "V1-FR-019"),
    ("mall-login", "登录", "用户", "/login", "V2-FR-001"),
    ("mall-member", "会员中心", "会员", "/member", "V2-FR-012"),
    ("mall-orders", "我的订单", "交易", "/orders", "V2-FR-004"),
    ("admin-coupon", "优惠券管理", "营销", "/admin/coupons", "V1-FR-022"),
]

APIS = [
    # method, path, service, summary, auth
    ("GET", "/api/coupons/available", "commerce-service", "查询用户可用优惠券", "member"),
    ("POST", "/api/orders", "commerce-service", "创建订单并计算优惠", "member"),
    ("GET", "/api/orders/{id}", "commerce-service", "订单详情", "member"),
    ("POST", "/api/after-sales", "commerce-service", "提交退款/退货申请", "member"),
    ("POST", "/admin/after-sales/{id}/audit", "commerce-service", "售后审核", "admin"),
    ("POST", "/api/auth/sms-code", "member-service", "发送短信验证码", "public"),
    ("POST", "/api/auth/login-by-sms", "member-service", "手机号验证码登录", "public"),
    ("GET", "/api/member/profile", "member-service", "会员资料与等级", "member"),
    ("GET", "/api/member/benefits", "member-service", "会员权益列表", "member"),
    ("GET", "/api/orders", "commerce-service", "我的订单列表", "member"),
    ("POST", "/admin/coupons", "commerce-service", "后台创建优惠券", "admin"),
]

CODES = [
    # 代码实体不再由种子脚本编造：类名、文件路径、commit 都必须来自真实仓库，
    # 现在统一由 scanners/java_scanner.py 扫描 Spring 控制器生成（source=CODE_SCAN）。
]


TABLES = [
    # database, schema, name, service, primary_key, columns
    ("shang_mall", "commerce", "order", "commerce-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "user_id", "type": "bigint"},
      {"name": "status", "type": "varchar(20)"}, {"name": "total_amount", "type": "decimal(12,2)"},
      {"name": "discount_amount", "type": "decimal(12,2)"}, {"name": "paid_at", "type": "datetime"}]),
    ("shang_mall", "commerce", "order_item", "commerce-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "order_id", "type": "bigint"},
      {"name": "sku_id", "type": "bigint"}, {"name": "qty", "type": "int"},
      {"name": "price", "type": "decimal(12,2)"}]),
    ("shang_mall", "commerce", "after_sale", "commerce-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "order_id", "type": "bigint"},
      {"name": "type", "type": "varchar(20)"}, {"name": "status", "type": "varchar(20)"},
      {"name": "reason", "type": "varchar(500)"}, {"name": "refund_amount", "type": "decimal(12,2)"}]),
    ("shang_mall", "commerce", "payment", "commerce-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "order_id", "type": "bigint"},
      {"name": "channel", "type": "varchar(20)"}, {"name": "amount", "type": "decimal(12,2)"},
      {"name": "paid_at", "type": "datetime"}]),
    ("shang_mall", "commerce", "coupon", "commerce-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "name", "type": "varchar(80)"},
      {"name": "type", "type": "varchar(20)"}, {"name": "amount", "type": "decimal(12,2)"},
      {"name": "scope", "type": "varchar(20)"}, {"name": "stackable", "type": "tinyint"}]),
    ("shang_mall", "member", "member", "member-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "phone", "type": "varchar(20)"},
      {"name": "level_id", "type": "bigint"}, {"name": "points", "type": "int"},
      {"name": "growth", "type": "int"}]),
    ("shang_mall", "member", "member_level", "member-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "name", "type": "varchar(30)"},
      {"name": "min_growth", "type": "int"}]),
    ("shang_mall", "member", "points_log", "member-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "member_id", "type": "bigint"},
      {"name": "change", "type": "int"}, {"name": "reason", "type": "varchar(80)"}]),
    ("shang_mall", "member", "sms_code", "member-service", "id",
     [{"name": "id", "type": "bigint"}, {"name": "phone", "type": "varchar(20)"},
      {"name": "code", "type": "varchar(10)"}, {"name": "expires_at", "type": "datetime"},
      {"name": "used", "type": "tinyint"}]),
]

# (src_type, src_key, rel_type, dst_type, dst_key)
RELATIONS = [
    # 需求 → 页面
    ("requirement", "REQ-018", "SPLITS_INTO", "page", "mall-checkout"),
    ("requirement", "REQ-018", "SPLITS_INTO", "page", "admin-coupon"),
    ("requirement", "REQ-019", "SPLITS_INTO", "page", "mall-aftersale-apply"),
    ("requirement", "REQ-019", "SPLITS_INTO", "page", "admin-aftersale"),
    ("requirement", "REQ-019", "SPLITS_INTO", "page", "mall-order-detail"),
    ("requirement", "REQ-020", "SPLITS_INTO", "page", "mall-login"),
    ("requirement", "REQ-021", "SPLITS_INTO", "page", "mall-member"),
    ("requirement", "REQ-021", "SPLITS_INTO", "page", "mall-orders"),
    # 页面 → 接口
    ("page", "mall-checkout", "TRIGGERS", "api", "GET:/api/coupons/available"),
    ("page", "mall-checkout", "TRIGGERS", "api", "POST:/api/orders"),
    ("page", "admin-coupon", "TRIGGERS", "api", "POST:/admin/coupons"),
    ("page", "mall-order-detail", "TRIGGERS", "api", "GET:/api/orders/{id}"),
    ("page", "mall-aftersale-apply", "TRIGGERS", "api", "POST:/api/after-sales"),
    ("page", "admin-aftersale", "TRIGGERS", "api", "POST:/admin/after-sales/{id}/audit"),
    ("page", "mall-login", "TRIGGERS", "api", "POST:/api/auth/sms-code"),
    ("page", "mall-login", "TRIGGERS", "api", "POST:/api/auth/login-by-sms"),
    ("page", "mall-member", "TRIGGERS", "api", "GET:/api/member/profile"),
    ("page", "mall-member", "TRIGGERS", "api", "GET:/api/member/benefits"),
    ("page", "mall-orders", "TRIGGERS", "api", "GET:/api/orders"),
    # 接口 → 代码
    # 接口 → 表
    ("api", "POST:/api/orders", "READS_WRITES", "table", "commerce.order"),
    ("api", "POST:/api/orders", "READS_WRITES", "table", "commerce.order_item"),
    ("api", "POST:/api/orders", "READS_WRITES", "table", "commerce.coupon"),
    ("api", "GET:/api/coupons/available", "READS_WRITES", "table", "commerce.coupon"),
    ("api", "GET:/api/orders/{id}", "READS_WRITES", "table", "commerce.order"),
    ("api", "GET:/api/orders", "READS_WRITES", "table", "commerce.order"),
    ("api", "POST:/api/after-sales", "READS_WRITES", "table", "commerce.after_sale"),
    ("api", "POST:/api/after-sales", "READS_WRITES", "table", "commerce.order"),
    ("api", "POST:/admin/after-sales/{id}/audit", "READS_WRITES", "table", "commerce.after_sale"),
    ("api", "POST:/admin/after-sales/{id}/audit", "READS_WRITES", "table", "commerce.payment"),
    ("api", "POST:/api/auth/sms-code", "READS_WRITES", "table", "member.sms_code"),
    ("api", "POST:/api/auth/login-by-sms", "READS_WRITES", "table", "member.sms_code"),
    ("api", "POST:/api/auth/login-by-sms", "READS_WRITES", "table", "member.member"),
    ("api", "GET:/api/member/profile", "READS_WRITES", "table", "member.member"),
    ("api", "GET:/api/member/profile", "READS_WRITES", "table", "member.member_level"),
    ("api", "GET:/api/member/benefits", "READS_WRITES", "table", "member.member_level"),
    ("api", "POST:/admin/coupons", "READS_WRITES", "table", "commerce.coupon"),
    # 代码 → 表
]

# ---------------------------------------------------------------- 客户端


class Client:
    def __init__(self) -> None:
        self.http = httpx.Client(base_url=BASE, timeout=20.0)
        self.token = ""
        self.stats = {"created": 0, "skipped": 0, "failed": 0}

    def _headers(self) -> dict[str, str]:
        return {"Authorization": f"Bearer {self.token}", "X-Project-Id": PROJECT}

    def login(self) -> None:
        pw = os.getenv("SEED_ADMIN_PASSWORD", "")
        if not pw:
            sys.exit("缺少环境变量 SEED_ADMIN_PASSWORD（可从 backend/.env 读取）")
        r = self.http.post("/auth/login", json={"email": ADMIN_EMAIL, "password": pw})
        body = r.json()
        if body.get("code") != 0:
            sys.exit(f"登录失败: {body}")
        self.token = body["data"]["accessToken"]

    def call(self, method: str, path: str, **kw):
        r = self.http.request(method, path, headers=self._headers(), **kw)
        try:
            return r.status_code, r.json()
        except Exception:
            return r.status_code, {"raw": r.text[:200]}

    def upsert(self, label: str, path: str, payload: dict) -> str | None:
        code, body = self.call("POST", path, json=payload)
        if code in (200, 201):
            self.stats["created"] += 1
            return body["data"]["id"]
        if code == 409:
            self.stats["skipped"] += 1
            return None
        self.stats["failed"] += 1
        print(f"  ! {label} 失败 {code}: {body}")
        return None


# ---------------------------------------------------------------- 主流程


def main() -> None:
    c = Client()
    c.login()
    print(f"已登录，项目={PROJECT}\n")

    code_ep_to_id: dict[str, str] = {}

    print("① 功能页面")
    for code, name, domain, route, prd in PAGES:
        c.upsert(f"page {name}", "/trace/pages", {
            "name": name, "feature_domain": domain, "code": code,
            "route": route, "prd_section": prd,
        })
    pages = c.call("GET", "/trace/pages")[1].get("data") or []
    page_id_by_code = {}
    for p in pages:
        for code, name, domain, _, _ in PAGES:
            if p["name"] == name and p.get("featureDomain", p.get("feature_domain")) == domain:
                page_id_by_code[code] = p["id"]
    print(f"   {len(page_id_by_code)}/{len(PAGES)} 个页面就绪\n")

    print("② 接口")
    for method, path, service, summary, auth in APIS:
        c.upsert(f"api {method} {path}", "/trace/apis", {
            "method": method, "path": path, "service": service,
            "summary": summary, "auth_requirement": auth,
        })
    apis = c.call("GET", "/trace/apis")[1].get("data") or []
    api_id_by_key = {f'{a["method"]}:{a["path"]}': a["id"] for a in apis}
    print(f"   {len(api_id_by_key)} 个接口就绪\n")

    print("③ 代码实体")
    for repo, service, entry, fpath, api_key in CODES:
        api_id = api_id_by_key.get(api_key)
        c.upsert(f"code {entry}", "/trace/code-artifacts", {
            "repo": repo, "service": service, "entry_point": entry,
            "file_path": fpath, "api_id": api_id, "commit_sha": "3f9c1ab",
        })
    codes = c.call("GET", "/trace/code-artifacts")[1].get("data") or []
    code_ep_to_id = {x["entryPoint"]: x["id"] for x in codes if x.get("entryPoint")}
    print(f"   {len(code_ep_to_id)} 个代码实体就绪\n")

    print("④ 数据表")
    for db, schema, name, service, pk, cols in TABLES:
        c.upsert(f"table {schema}.{name}", "/trace/tables", {
            "database_name": db, "schema_name": schema, "name": name,
            "service": service, "primary_key": pk, "columns": cols,
        })
    tables = c.call("GET", "/trace/tables")[1].get("data") or []
    table_id_by_key = {f'{t["schema"]}.{t["name"]}': t["id"] for t in tables}
    print(f"   {len(table_id_by_key)} 张表就绪\n")

    print("⑤ 关联关系")
    ok_cnt = skip_cnt = fail_cnt = 0
    for src_type, src_key, rel_type, dst_type, dst_key in RELATIONS:
        if src_type == "requirement":
            src_id = src_key
        elif src_type == "page":
            src_id = page_id_by_code.get(src_key)
        elif src_type == "api":
            src_id = api_id_by_key.get(src_key)
        else:
            src_id = code_ep_to_id.get(src_key)

        if dst_type == "page":
            dst_id = page_id_by_code.get(dst_key)
        elif dst_type == "api":
            dst_id = api_id_by_key.get(dst_key)
        elif dst_type == "table":
            dst_id = table_id_by_key.get(dst_key)
        else:
            dst_id = code_ep_to_id.get(dst_key)

        if not src_id or not dst_id:
            fail_cnt += 1
            print(f"  ! 端点缺失 {src_type}:{src_key} -{rel_type}-> {dst_type}:{dst_key}")
            continue

        code, body = c.call("POST", "/trace/relations", json={
            "src_type": src_type, "src_id": src_id, "rel_type": rel_type,
            "dst_type": dst_type, "dst_id": dst_id,
            "note": "来源: llm-wiki 页面地图/接口契约/数据模型（代码层由扫描器提供）",
        })
        if code in (200, 201):
            ok_cnt += 1
        elif code == 409:
            skip_cnt += 1
        else:
            fail_cnt += 1
            print(f"  ! 关联失败 {code}: {body}")
    print(f"   新建 {ok_cnt} / 已存在 {skip_cnt} / 失败 {fail_cnt}\n")

    print("⑥ 结果总览")
    ov = c.call("GET", "/trace/overview")[1].get("data") or {}
    for k, v in ov.items():
        print(f"   {k}: {v}")


if __name__ == "__main__":
    main()
