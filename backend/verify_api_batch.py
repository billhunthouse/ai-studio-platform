"""验证"系统（平台）驱动 UI 自动化"：完全走 HTTP 接口，不碰 CLI。

流程：
1. 登录平台拿 token
2. POST /api/v1/ui/run-batch 启动后台批量真实执行
3. 轮询 GET /api/v1/ui/run-batch/{jobId} 看进度
4. 结束后打印汇总，并把结果落盘作为证据

这验证的是"平台能不能执行 UI 自动化"，而不是"脚本能不能跑"。
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8000/api/v1"
HEADERS_COMMON = {"X-Project-Id": "ecommerce"}
LIMIT = int(sys.argv[1]) if len(sys.argv) > 1 else 30
MAX_WRITE = int(sys.argv[2]) if len(sys.argv) > 2 else 2
CASE_IDS = sys.argv[3].split(",") if len(sys.argv) > 3 else []


def main() -> int:
    with httpx.Client(timeout=60, headers=HEADERS_COMMON) as c:
        r = c.post(f"{BASE}/auth/login", json={"email": "zhangwei@corp.com", "password": "Admin@12345"})
        r.raise_for_status()
        token = r.json()["data"]["accessToken"]
        h = {**HEADERS_COMMON, "Authorization": f"Bearer {token}"}
        print(f"登录成功 token={token[:16]}…")

        # 1. 编译全部（v2 PO + 断言）
        t0 = time.time()
        r = c.post(f"{BASE}/ui/compile-all", headers=h)
        r.raise_for_status()
        print(f"编译完成 {time.time() - t0:.1f}s：{r.json()['data']['stats']}")

        # 2. 启动批量真实执行
        r = c.post(f"{BASE}/ui/run-batch", headers=h, json={"limit": LIMIT, "maxWrite": MAX_WRITE, "delayMs": 300, "caseIds": CASE_IDS})
        r.raise_for_status()
        job_id = r.json()["data"]["jobId"]
        print(f"任务已启动：{job_id}（limit={LIMIT}, maxWrite={MAX_WRITE}）")

        # 3. 轮询
        last = -1
        summary = None
        while True:
            time.sleep(4)
            s = c.get(f"{BASE}/ui/run-batch/{job_id}", headers=h).json()["data"]
            if s["index"] != last:
                last = s["index"]
                print(f"  进度 {s['index']}/{s['total']}  {s.get('current', '')}", flush=True)
            if s["status"] != "running":
                if s["status"] == "failed":
                    print(f"任务失败：{s.get('error')}")
                    return 1
                summary = s["result"]
                break

    print("\n=== 接口驱动执行汇总 ===")
    for k in ("executed", "passed", "failed", "partial", "skippedCount", "passRate", "totalSeconds", "writeExecuted"):
        print(f"  {k}: {summary.get(k)}")
    print("  按 PO：")
    for name, v in summary["byPageObject"].items():
        print(f"    {name}: {v}")
    orders = [(r["caseId"], n) for r in summary["results"] for n in r.get("orderNos", [])]
    print(f"  真实落库订单：{orders}")
    print(f"  失败：{len(summary['failures'])}")

    out = Path("/Users/imac/Desktop/AI_Studio/方案交互页面设计/docs/traceability/ui-real-run-api.json")
    out.write_text(json.dumps({"jobId": job_id, **summary}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n→ {out}")
    return 0 if summary["failed"] == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
