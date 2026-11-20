"""用例运行引擎：把用例真正打到真实 shang-pivot 后端（127.0.0.1:8086）上执行。

双身份体系（与 verify_cases_sample.py 口径一致）：
  管理端 /admin/**  → admin / Admin@123（V1__init.sql 种子）
  C 端    /api/**   → 手机号 13800000001 + 演示万能验证码 123456

判定口径（三要素）：
  协议层 HTTP 状态码；业务层响应 code（0 成功 / 非 0 失败）；数据层 data 非空。
预期从用例 expected 文本解析：HTTP 200 / HTTP 4xx / 业务码为 0 / 业务码非 0。

安全策略：GET/POST/PUT 真实执行；DELETE 为保护演示库默认跳过（可 force）。
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from typing import Any

BASE = "http://127.0.0.1:8086"
ADMIN_USER, ADMIN_PASS = "admin", "Admin@123"
C_PHONE, C_SMS = "13800000001", "123456"
TIMEOUT = 8

CODE_HINTS = {  # 业务词条 → 数值（领域词典）
    "SUCCESS": 0, "UNAUTHORIZED": 40100, "FORBIDDEN": 40300, "NOT_FOUND": 40400,
}


# ---------------------------------------------------------------- HTTP 基础
def _call(method: str, path: str, token: str = "", body: dict | None = None,
          query: str = "") -> tuple[int, dict]:
    url = f"{BASE}{path}{query}"
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            text = r.read().decode("utf-8", "ignore")
            return r.status, json.loads(text) if text.startswith("{") else {}
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(text)
        except Exception:
            return e.code, {}
    except Exception as e:  # 连接失败等
        return -1, {"msg": str(e)}


# ---------------------------------------------------------------- 身份
class _Tokens:
    """惰性登录并缓存两类身份的 JWT。"""

    def __init__(self) -> None:
        self._admin = ""
        self._c = ""

    def admin(self) -> str:
        if not self._admin:
            _, d = _call("POST", "/admin/auth/login",
                         body={"username": ADMIN_USER, "password": ADMIN_PASS})
            self._admin = self._extract(d)
        return self._admin

    def c(self) -> str:
        if not self._c:
            _, d = _call("POST", "/api/auth/login",
                         body={"phone": C_PHONE, "code": C_SMS, "clientType": "web"})
            self._c = self._extract(d)
        return self._c

    @staticmethod
    def _extract(d: dict) -> str:
        data = d.get("data") or {}
        if isinstance(data, dict):
            return str(data.get("accessToken") or data.get("token") or "")
        return ""

    def for_path(self, path: str) -> str:
        return self.c() if path.startswith("/api/") else self.admin()


TOKENS = _Tokens()


# ---------------------------------------------------------------- 预期解析
def parse_expectation(expected: str) -> dict:
    """从预期文本提取机器可判定条件。"""
    exp: dict[str, Any] = {"http": None, "code": None, "dataNonEmpty": None}
    if not expected:
        return exp
    m = re.search(r"HTTP\s*(\d{3})", expected)
    if m:
        exp["http"] = int(m.group(1))
    elif re.search(r"HTTP\s*4xx|4xx", expected):
        exp["http"] = "4xx"
    elif re.search(r"HTTP\s*2xx|2xx", expected):
        exp["http"] = "2xx"
    if re.search(r"业务码为?0|业务码.{0,4}为\s*0|code\s*=?\s*0(?!0)", expected):
        exp["code"] = 0
    elif re.search(r"业务码非?0|业务码.{0,6}非\s*0|非\s*0", expected):
        exp["code"] = "nonzero"
    if re.search(r"data.{0,6}非空|返回.{0,8}(数据|列表|记录)", expected):
        exp["dataNonEmpty"] = True
    return exp


def _judge(exp_http: Any, exp_code: Any, exp_data: Any, status: int, body: dict) -> tuple[bool, str]:
    """返回 (通过, 不通过原因)。"""
    actual_code = body.get("code")
    if exp_http is not None:
        if exp_http == "4xx":
            if not (400 <= status < 500 or (isinstance(actual_code, int) and 40000 <= actual_code < 50000)):
                return False, f"预期 4xx 类拒绝，实际 HTTP={status}/code={actual_code}"
        elif exp_http == "2xx":
            if not (200 <= status < 300):
                return False, f"预期 2xx，实际 HTTP={status}"
        elif status != exp_http:
            return False, f"预期 HTTP={exp_http}，实际 HTTP={status}"
    if exp_code == 0:
        if actual_code != 0:
            return False, f"预期业务码 0，实际 code={actual_code}/msg={str(body.get('msg'))[:40]}"
        if exp_data and not body.get("data"):
            return False, "预期返回非空数据，实际 data 为空"
    elif exp_code == "nonzero":
        if actual_code in (0, None) and status < 400:
            return False, f"预期失败（业务码非 0），实际 HTTP={status}/code={actual_code}"
    return True, ""


# ---------------------------------------------------------------- 造数
def _probe_id(path: str) -> str:
    """把 {id} 换成真实样本：取最近一个无占位符的资源列表接口第一条记录 id。"""
    parent = path.rsplit("/", 1)[0]
    if "{" in parent:  # /admin/orders/{id}/ship → 探测 /admin/orders
        parent = re.sub(r"\{[^}]+\}.*$", "", parent).rstrip("/")
    token = TOKENS.for_path(parent)
    status, d = _call("GET", parent, token, query="?page=1&size=1")
    if status != 200 or not isinstance(d.get("data"), dict):
        return ""
    records = d["data"].get("records") or d["data"].get("items") or []
    if records and isinstance(records[0], dict):
        for key in ("id", "afterSaleId", "orderId", "spuId", "userId", "roleId", "permissionId"):
            if key in records[0]:
                return str(records[0][key])
    return ""


def _sample_value(ftype: str, desc: str, name: str) -> Any:
    """按字段类型/描述造一个合法值。"""
    enums = re.findall(r"[A-Z][A-Z_]{2,}", desc or "")
    if enums and re.search(r"[:：]", desc or ""):
        return enums[0]
    if ftype in ("Long", "Integer", "int", "long"):
        return 1 if "id" not in name.lower() else 1
    if ftype in ("Boolean", "boolean"):
        return True
    if ftype in ("List", "Array"):
        return []
    return "测试数据" if any(k in name.lower() for k in ("name", "title", "nick")) else "test-case"


def build_body(schema: dict | None, negative: bool) -> dict:
    """从 trace_apis 的 bodyFields 构造请求体；negative=True 时构造缺参/非法体。"""
    fields = ((schema or {}).get("bodyFields")) or []
    if negative:
        return {}  # 缺失全部必填 → 触发参数校验
    body: dict[str, Any] = {}
    for f in fields:
        name = f.get("name") or ""
        if not f.get("required", False):
            continue
        body[name] = _sample_value(f.get("type", "String"), f.get("description", ""), name)
    return body


# ---------------------------------------------------------------- 样本探测（调试面板用）
def probe_sample(method: str, path: str, schema: dict | None) -> dict:
    """为调试面板生成真实样本：替换 {id} 占位、构造合法请求体、建议分页参数。

    只做探测与造数，不发起被测请求本身（探测内部会调一次父列表接口取样本 id）。
    """
    negative = False
    filled = path
    notes: list[str] = []
    if "{" in path:
        real = _probe_id(path)
        if real:
            filled = re.sub(r"\{[^}]+\}", real, path)
            notes.append(f"路径参数已替换为真实样本 id：{real}")
        else:
            notes.append("未能取到真实样本 id（父列表接口无数据），占位符保留待手动填写")
    query = ""
    if method == "GET" and re.search(
        r"/(orders|products|-sales|reviews|users|roles|logs|stocks|permissions|dict|depts|files|addresses|favorites)$", filled):
        query = "?page=1&size=5"
        notes.append("列表类接口自动附加分页参数")
    body = None
    if method in ("POST", "PUT", "PATCH"):
        body = build_body(schema, negative)
        if body:
            notes.append("请求体已按接口契约必填字段自动构造")
        else:
            notes.append("契约中无必填字段，请求体为空")
    auth = "customer" if path.startswith("/api/") else "admin"
    return {"filledPath": filled, "query": query, "body": body, "auth": auth, "notes": notes}


# ---------------------------------------------------------------- 主入口
def run_case(case: dict, schema_lookup=None, force: bool = False) -> dict:
    """执行一条用例，返回运行报告。schema_lookup(path,method)->schema|None 由调用方注入。"""
    related = (case.get("relatedApi") or "").strip()
    if not related:
        return {"verdict": "不支持", "detail": "功能测试用例无被测接口，请使用人工执行并按步骤记录结果"}

    m = re.match(r"(GET|POST|PUT|DELETE|PATCH)\s+(\S+)", related)
    if not m:
        return {"verdict": "无法执行", "detail": f"被测接口格式无法解析：{related}"}
    method, path = m.group(1), m.group(2)
    template_path = path  # trace_apis 里存的是带 {id} 的模板，查契约用

    if method == "DELETE" and not force:
        return {"verdict": "跳过", "detail": "删除类写操作为保护演示数据默认不执行，可勾选「强制执行」后重跑"}

    # 占位符替换
    query = ""
    if "{" in path:
        real = _probe_id(path)
        if not real:
            return {"verdict": "无法执行", "detail": f"取不到 {path} 的样本 id（父列表无数据）"}
        path = re.sub(r"\{[^}]+\}", real, path, count=1)
    if method == "GET" and re.search(r"/(orders|products|-sales|reviews|users|roles|logs|stocks|permissions|dict|depts|files|addresses|favorites)$", path):
        query = "?page=1&size=5"

    # 请求体
    body = None
    if method in ("POST", "PUT", "PATCH"):
        negative = bool(re.search(r"缺失|未传|不传|非法|为空|缺参", (case.get("title") or "") + (case.get("designMethod") or "")))
        schema = schema_lookup(template_path, method) if schema_lookup else None
        body = build_body(schema, negative)
        if not body:
            body = None if negative else None

    token = TOKENS.for_path(path)
    status, resp = _call(method, path, token, body, query)

    exp = parse_expectation(case.get("expected") or "")
    has_expectation = exp["http"] is not None or exp["code"] is not None
    if has_expectation:
        passed, reason = _judge(exp["http"], exp["code"], exp["dataNonEmpty"], status, resp)
        verdict = "通过" if passed else "不符"
        detail = "" if passed else reason
    else:
        verdict = "已执行"
        detail = "用例预期无机器可判定条件，请人工核对响应"
    if status == -1:
        verdict, detail = "无法执行", f"请求失败：{resp.get('msg', '网络错误')}"

    return {
        "verdict": verdict, "detail": detail,
        "request": {"method": method, "path": path + query, "body": body},
        "actual": {
            "http": status, "code": resp.get("code"), "msg": str(resp.get("msg") or "")[:80],
            "dataPreview": json.dumps(resp.get("data"), ensure_ascii=False)[:300] if resp.get("data") is not None else "",
        },
        "expectation": {k: v for k, v in exp.items() if v is not None},
    }
