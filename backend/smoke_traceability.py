"""追溯平台端到端冒烟测试（对运行中的服务）。

用法: .venv/bin/python smoke_traceability.py
前置: uvicorn 已启动于 8011 端口。
"""
from __future__ import annotations

import json
import os

import httpx

requests = httpx  # httpx 的 request/post 接口与本脚本用法兼容

BASE = "http://127.0.0.1:8011/api/v1"
PID = "ecommerce"


def call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    r = requests.request(
        method, BASE + path,
        headers={"Authorization": f"Bearer {token}", "X-Project-Id": PID},
        json=body, timeout=15,
    )
    try:
        return r.json()
    except Exception:
        return {"code": -1, "http": r.status_code, "text": r.text[:200]}


def main() -> None:
    pw = os.environ.get("SEED_ADMIN_PASSWORD", "")
    if not pw:
        from dotenv import load_dotenv
        load_dotenv(".env")
        pw = os.environ["SEED_ADMIN_PASSWORD"]
    login = requests.post(BASE + "/auth/login", json={
        "email": "zhangwei@corp.com", "password": pw}, timeout=15).json()
    token = login["data"]["accessToken"]
    print("[0] 登录成功")

    print("[1] 创建页面")
    page = call("POST", "/trace/pages", token, {
        "name": "冒烟测试页面", "feature_domain": "商品", "prd_section": "TEST-1.1"})
    print("   ", page["code"], page.get("data"))
    if page["code"] != 0:
        existing = call("GET", "/trace/pages", token)
        page_id = next((x["id"] for x in existing.get("data", []) if x["name"] == "冒烟测试页面"), None)
        if not page_id:
            raise RuntimeError("创建页面失败且无已有")
    else:
        page_id = page["data"]["id"]

    print("[2] 创建接口")
    api = call("POST", "/trace/apis", token, {
        "method": "GET", "path": "/api/smoke/{id}", "summary": "冒烟接口", "service": "smoke-service"})
    print("   ", api["code"], api.get("data"))
    if api["code"] != 0:
        existing = call("GET", "/trace/apis", token)
        api_id = next((x["id"] for x in existing.get("data", []) if x["path"] == "/api/smoke/{id}"), None)
        if not api_id:
            raise RuntimeError("创建接口失败且无已有")
    else:
        api_id = api["data"]["id"]

    print("[3] 创建表")
    tbl = call("POST", "/trace/tables", token, {
        "database_name": "smoke_db", "service": "smoke-service", "name": "smoke_table",
        "columns": [{"name": "id", "type": "bigint"}]})
    print("   ", tbl["code"], tbl.get("data"))
    if tbl["code"] != 0:
        existing = call("GET", "/trace/tables", token)
        tbl_id = next((x["id"] for x in existing.get("data", []) if x["name"] == "smoke_table"), None)
        if not tbl_id:
            raise RuntimeError("创建表失败且无已有")
    else:
        tbl_id = tbl["data"]["id"]

    print("[4] 建立关联：requirement -> page")
    rel1 = call("POST", "/trace/relations", token, {
        "src_type": "requirement", "src_id": "REQ-018",
        "rel_type": "SPLITS_INTO", "dst_type": "page", "dst_id": page_id})
    print("   ", rel1["code"], rel1.get("data"), "(409=已存在，OK)" if rel1["code"]==409 else "")

    print("[5] 建立关联：page -> api")
    rel2 = call("POST", "/trace/relations", token, {
        "src_type": "page", "src_id": page_id,
        "rel_type": "TRIGGERS", "dst_type": "api", "dst_id": api_id})
    print("   ", rel2["code"], rel2.get("data"), "(409=已存在，OK)" if rel2["code"]==409 else "")

    print("[6] 建立关联：api -> table")
    rel3 = call("POST", "/trace/relations", token, {
        "src_type": "api", "src_id": api_id,
        "rel_type": "READS_WRITES", "dst_type": "table", "dst_id": tbl_id})
    print("   ", rel3["code"], rel3.get("data"), "(409=已存在，OK)" if rel3["code"]==409 else "")

    print("[7] 正向影响：从需求出发（应看到 page/api/table 三跳）")
    fwd = call("GET", f"/trace/impact/forward?entity_type=requirement&entity_id=REQ-018&max_hops=3", token)
    print("   code:", fwd["code"], "affected:", fwd.get("data", {}).get("affectedCount"))
    for it in fwd.get("data", {}).get("items", [])[:6]:
        print(f"     hop{it['hop']} {it['type']}: {it['id'][:50]}")

    print("[8] 反向追溯：从表出发（应看到上游需求）")
    bwd = call("GET", f"/trace/impact/backward?entity_type=table&entity_id={tbl_id}&max_hops=3", token)
    print("   code:", bwd["code"], "upstream reqs:",
          len(bwd.get("data", {}).get("upstreamRequirements", [])))

    print("[9] 实体详情双向关联：接口详情")
    import urllib.parse
    detail = call("GET", f"/trace/entity?entity_type=api&entity_id={urllib.parse.quote(api_id, safe='')}", token)
    d = detail.get("data", {})
    print("   code:", detail["code"],
          "upstream:", len(d.get("relations", {}).get("upstream", [])),
          "downstream:", len(d.get("relations", {}).get("downstream", [])))

    print("[10] 总览 / 矩阵")
    ov = call("GET", "/trace/overview", token)
    print("   overview:", ov.get("data"))
    mx = call("GET", "/trace/matrix", token)
    print("   matrix rows:", len(mx.get("data", {}).get("rows", [])))

    print("\n冒烟测试完成。")


if __name__ == "__main__":
    main()
