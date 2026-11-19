"""抽样验证用例预期是否被真实实现满足（只读，不改数据）。

只跑 GET 类正向用例：这类用例的预期是确定值（HTTP/code/字段），可以机器判定，
且不会污染数据库。写操作的正向用例需要造数与清理，不在此脚本内。

判定口径（rule.md §3.6 三要素）：
  协议层  HTTP 状态码相等
  业务层  响应 code 与预期业务码相等（词条按领域词典映射成数值）
  数据层  data 非空 / 命中断言里提到的字段路径

用法：
  .venv/bin/python verify_cases_sample.py \
      --inventory /path/to/test_cases_inventory.md \
      --base http://127.0.0.1:8086 \
      --token-file /tmp/shang_tok.txt [--limit 60]
"""
from __future__ import annotations

import argparse
import json
import re
import urllib.error
import urllib.request
from pathlib import Path

# 领域词典 §9：词条 → 数值
CODE_MAP = {
    "SUCCESS": 0, "BAD_REQUEST": 40000, "UNAUTHORIZED": 40100, "LOGIN_FAILED": 40101,
    "TOKEN_EXPIRED": 40102, "TOKEN_INVALID": 40103, "ACCOUNT_LOCKED": 40104,
    "FORBIDDEN": 40300, "CUSTOMER_FROZEN": 40310, "NOT_FOUND": 40400,
    "PRODUCT_UNAVAILABLE": 40410, "CONFLICT": 40900, "STOCK_INSUFFICIENT": 40901,
    "ORDER_STATUS_INVALID": 40902, "AFTER_SALE_STATUS_INVALID": 40903,
    "REVIEW_EXISTS": 40904, "SYSTEM_ERROR": 50000,
}
CASE_ID = re.compile(r"^[A-Z][A-Z0-9_]*-\d{3}$")


def parse_cases(path: Path) -> list[dict]:
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("|"):
            continue
        c = [x.strip() for x in line.strip().strip("|").split("|")]
        if len(c) < 14 or not CASE_ID.match(c[0]):
            continue
        m = re.match(r"(GET|POST|PUT|DELETE|PATCH)\s+(\S+)", c[5])
        if not m:
            continue
        out.append({"id": c[0], "type": c[2], "http": c[9], "code": c[10],
                    "method": m.group(1), "path": m.group(2),
                    "param": c[7], "assert": c[11]})
    return out


def call(base: str, method: str, path: str, token: str, query: str = "") -> tuple[int, dict]:
    url = f"{base}{path}{query}"
    req = urllib.request.Request(url, method=method)
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=8) as r:
            body = r.read().decode("utf-8", "ignore")
            return r.status, json.loads(body) if body.startswith("{") else {}
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "ignore")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {}


def list_probe(base: str, path: str, token: str) -> str:
    """把 {id} 换成真实 id：去掉末段占位符，取列表接口第一条。"""
    parent = path.rsplit("/", 1)[0]
    status, data = call(base, "GET", parent, token, "?page=1&size=1")
    if status != 200 or not isinstance(data.get("data"), dict):
        return ""
    records = data["data"].get("records") or data["data"].get("items") or []
    if records and isinstance(records[0], dict):
        for key in ("id", "afterSaleId", "orderId", "spuId", "userId", "roleId"):
            if key in records[0]:
                return str(records[0][key])
    return ""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--inventory", required=True)
    ap.add_argument("--base", default="http://127.0.0.1:8086")
    ap.add_argument("--token-file", default="/tmp/shang_tok.txt",
                    help="管理员 token")
    ap.add_argument("--ctoken-file", default="/tmp/shang_ctok.txt",
                    help="C 端（会员）token，用于 /api/** 端点")
    ap.add_argument("--limit", type=int, default=80)
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    admin_token = Path(args.token_file).read_text().strip()
    ctoken_path = Path(args.ctoken_file)
    ctoken = ctoken_path.read_text().strip() if ctoken_path.exists() else ""

    def token_for(path: str) -> str:
        """管理端与 C 端是两个身份体系，用错一律 401（Token 无效并非用例问题）。"""
        return ctoken if path.startswith("/api/") and ctoken else admin_token

    cases = [c for c in parse_cases(Path(args.inventory))
             if c["type"] == "正向" and c["method"] == "GET"]
    print(f"GET 正向用例 {len(cases)} 条，抽样执行前 {min(args.limit, len(cases))} 条\n")

    results = []
    for c in cases[: args.limit]:
        path = c["path"]
        if "{" in path:
            real = list_probe(args.base, path, token_for(path))
            if not real:
                results.append({**c, "verdict": "无法执行", "detail": "取不到样本 id"})
                continue
            path = re.sub(r"\{[^}]+\}", real, path, count=1)
        query = "?page=1&size=5" if path.endswith(("/orders", "/products", "-sales", "/reviews",
                                                  "/users", "/roles", "/logs", "/stocks")) else ""
        status, body = call(args.base, "GET", path, token_for(path), query)
        exp_http = int(c["http"]) if c["http"].isdigit() else None
        exp_code = CODE_MAP.get(c["code"])
        if exp_code is None and c["code"].isdigit():
            exp_code = int(c["code"])
        ok_http = exp_http is None or status == exp_http
        actual_code = body.get("code")
        ok_code = exp_code is None or actual_code == exp_code
        data = body.get("data")
        ok_data = data is not None if exp_code == 0 else True

        verdict = "通过" if (ok_http and ok_code and ok_data) else "不符"
        detail = ""
        if verdict == "不符":
            detail = (f"预期 HTTP={exp_http}/code={exp_code}，"
                      f"实际 HTTP={status}/code={actual_code}/msg={str(body.get('msg'))[:40]}")
        results.append({**c, "verdict": verdict, "detail": detail,
                        "actualHttp": status, "actualCode": actual_code})

    ok = [r for r in results if r["verdict"] == "通过"]
    bad = [r for r in results if r["verdict"] == "不符"]
    skip = [r for r in results if r["verdict"] == "无法执行"]
    print(f"通过 {len(ok)} / 不符 {len(bad)} / 跳过 {len(skip)} "
          f"（通过率 {len(ok)/max(1,len(results)):.0%}）\n")
    for r in bad:
        print(f"  ✗ {r['id']:40} {r['method']} {r['path']}")
        print(f"     {r['detail']}")
    for r in skip:
        print(f"  - {r['id']:40} 跳过：{r['detail']}")

    if args.out:
        Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print("\n明细已写出", args.out)


if __name__ == "__main__":
    main()
