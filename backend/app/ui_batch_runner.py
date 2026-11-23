"""UI 自动化批量执行内核：CLI 与 HTTP 接口共用同一套逻辑。

为什么要抽出来：
- CLI（run_ui_batch.py）与接口（POST /ui/run-batch）如果各写一份编译/排序/执行逻辑，
  两边行为必然漂移（真实执行最怕这个）。这里保持单一实现。
- 接口侧同步执行 100+ 条会 HTTP 超时，因此接口用后台线程跑本模块，前端轮询进度。
"""
from __future__ import annotations

import re
import threading
import time
from collections import defaultdict
from pathlib import Path
from typing import Any, Callable

from .store import store
from .ui_step_compiler import compile_batch, to_playwright_script
from .ui_executor import BrowserPool, run_compiled

# 进程内任务表（单实例部署；多实例需换 Redis/DB）
JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()


def _pay_id(url: str) -> str:
    """从收银台 URL 提取订单主键：/pay/2124058521924726786 → 2124058521924726786"""
    m = re.search(r"/pay/(\d{10,})", url or "")
    return m.group(1) if m else ""


def _order_no_for(pay_id: str) -> str:
    """用订单主键回查真实订单号（证据链：UI 操作 → /pay/{id} → commerce.order.order_no）。"""
    if not pay_id:
        return ""
    try:
        import os
        import psycopg
        dsn = os.getenv("REAL_DB_DSN", "postgresql://shang:shang@127.0.0.1:55434/shang")
        with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
            cur.execute('select order_no from commerce."order" where id = %s', (int(pay_id),))
            row = cur.fetchone()
            return row[0] if row else ""
    except Exception:  # noqa: BLE001
        return ""


def _functional_cases(project_id: str, include_archived: bool = False) -> list[dict]:
    """功能用例（默认排除已合并归档的副本）。

    去重合并后 363 条里 294 条是副本，它们带 `archived/duplicateOf` 标记。
    统计、编译、执行都必须只看在册的 69 条，否则"同一条用例跑 23 次"的虚高会回来。
    """
    return [c for c in store.all("testCases", project_id)
            if (c.get("caseType") or ("api" if c.get("relatedApi") else "functional")) == "functional"
            and (include_archived or not c.get("archived"))]


def round_robin(compiled: list[dict]) -> list[dict]:
    """按 Page Object 分桶轮转，让有限样本覆盖多种真实路径，而不是同一流程刷 N 次。"""
    buckets: dict[str, list[dict]] = defaultdict(list)
    for c in compiled:
        buckets[c["summary"]["pageObject"] or "（无 PO）"].append(c)
    order = sorted(buckets, key=lambda k: (k == "（无 PO）", k))
    out: list[dict] = []
    idx = 0
    while len(out) < len(compiled):
        for name in order:
            if idx < len(buckets[name]):
                out.append(buckets[name][idx])
        idx += 1
        if all(idx >= len(buckets[n]) for n in order):
            break
    return out


def compile_and_store(project_id: str) -> dict:
    """编译全部功能用例并落库 uiScripts，返回统计。"""
    cases = _functional_cases(project_id)
    result = compile_batch(cases)
    for ir_case in result["compiled"]:
        store.put("uiScripts", f"US-{ir_case['caseId']}", {
            "id": f"US-{ir_case['caseId']}", "projectId": project_id,
            "caseId": ir_case["caseId"], "caseTitle": ir_case["caseTitle"],
            "name": ir_case["caseTitle"][:80], "framework": "Playwright · 关键字驱动",
            "content": to_playwright_script(ir_case), "ir": ir_case,
            "status": "启用" if ir_case["summary"]["ready"] else "部分可执行",
            "updatedAt": time.strftime("%Y/%m/%d %H:%M:%S"),
        })
    return {"stats": result["stats"], "compiled": result["compiled"]}


def execute_batch(
    project_id: str,
    limit: int = 20,
    max_write: int = 3,
    delay_ms: int = 300,
    case_ids: list[str] | None = None,
    progress: Callable[[dict], None] | None = None,
    duration_fn: Callable[[dict], list[dict]] | None = None,
    batch_id: str = "",
    only_confirmed: bool = False,
) -> dict:
    """编译 + 轮转选择 + 真实执行 + 落库 + 汇总。

    一次批量执行在「执行记录」里只显示为一 条批次记录（uiBatches），
    每个用例的步骤截图/视频落在批次目录下（媒体目录名 {batchId}__{caseId}）。

    only_confirmed=True 时只跑"页面已人工确认绑定"的用例：
    这是把质量指标落到执行上的开关——不确定测哪个页面的用例不跑，
    避免用无关流程刷出好看的通过率。
    """
    from . import ui_media

    batch_id = batch_id or f"UB-{int(time.time() * 1000)}"
    started_ms = int(time.time() * 1000)
    compiled_result = compile_and_store(project_id)
    compiled = compiled_result["compiled"]
    ready = [c for c in compiled if c["summary"]["ready"]]
    not_ready: list[dict] = []
    unconfirmed: list[dict] = []
    if only_confirmed:
        def _confirmed(c: dict) -> bool:
            return ((c["summary"].get("binding") or {}).get("risk") == "confirmed")
        unconfirmed = [{
            "caseId": c["caseId"], "caseTitle": c["caseTitle"],
            "pageObject": c["summary"].get("pageObject", ""),
            "reason": "绑定未人工确认（仅规则推断），本次限定只跑已确认绑定的用例",
        } for c in ready if not _confirmed(c)]
        ready = [c for c in ready if _confirmed(c)]
    if case_ids:
        wanted = set(case_ids)
        by_id = {c["caseId"]: c for c in compiled}
        ready = [c for c in ready if c["caseId"] in wanted]
        # 明确告知"勾选了但还没转成自动化脚本"的用例，而不是静默丢掉
        not_ready = [{
            "caseId": cid,
            "caseTitle": (by_id.get(cid) or {}).get("caseTitle", cid),
            "pageObject": "",
            "reason": "尚未转化为自动化脚本（缺少 Page Object / 可执行步骤）",
        } for cid in case_ids if not (by_id.get(cid) or {}).get("summary", {}).get("ready")]
    pool = (round_robin(ready) if not case_ids else ready)[:limit]

    results: list[dict] = []
    skipped: list[dict] = list(not_ready) + list(unconfirmed)
    write_used = 0
    started = time.time()
    # 后台任务独占浏览器池：Playwright sync API 与线程绑定，跨线程复用同一 browser 会崩
    browser_pool = BrowserPool(isolated=True)
    store.put("uiBatches", batch_id, {
        "id": batch_id, "projectId": project_id, "kind": "batch",
        "title": f"批量执行 · {len(pool)} 条", "status": "running",
        "startedAtMs": started_ms,
        "startedAt": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(started_ms / 1000)),
        "total": len(pool), "executed": 0, "passed": 0, "failed": 0, "partial": 0,
        "caseIds": [c["caseId"] for c in pool], "results": [],
    })

    for i, ir_case in enumerate(pool, 1):
        is_write = bool(ir_case["summary"].get("writeFlow"))
        if is_write and write_used >= max_write:
            skipped.append({"caseId": ir_case["caseId"], "caseTitle": ir_case["caseTitle"],
                            "pageObject": ir_case["summary"]["pageObject"],
                            "reason": "写操作配额保护（避免耗尽演示库存/污染订单表）"})
            continue
        if is_write:
            write_used += 1

        report = run_compiled(ir_case, delay_ms=delay_ms, pool=browser_pool,
                              run_id=f"{batch_id}__{ir_case['caseId']}")
        # 只有写操作用例才产生新订单；用 /pay/{id} 回查订单号，避免把订单列表里看到的历史单号当成"新单"
        pay_id = _pay_id(report.get("finalUrl", "")) if is_write else ""
        order_nos = [n for n in [_order_no_for(pay_id)] if n]
        item = {
            "caseId": ir_case["caseId"], "caseTitle": ir_case["caseTitle"],
            "module": ir_case["module"], "pageObject": ir_case["summary"]["pageObject"],
            "writeFlow": is_write, "verdict": report["verdict"],
            "steps": report["steps"],
            "assertions": report.get("assertions", 0),
            "assertionsPassed": report.get("assertionsPassed", 0),
            "finalUrl": report.get("finalUrl", ""),
            "pageText": (report.get("pageText") or "")[:120],
            "orderNos": order_nos,
            "screenshot": report["screenshot"],
            "media": report.get("media") or {},
            "durationMs": report["durationMs"],
            "seconds": round(report["durationMs"] / 1000, 1),
        }
        results.append(item)
        # 进度里带上已完成的判定，批次文档定期落库（防止进程被杀导致整批丢失）；
        # 每 10 条写一次，避免 120 条时把逐条结果反复写库拖慢执行
        if i % 10 == 0 or i == 1 or i == len(pool):
            store.put("uiBatches", batch_id, {
                "id": batch_id, "projectId": project_id, "kind": "batch",
                "title": f"批量执行 · {len(pool)} 条", "status": "running",
                "startedAtMs": started_ms,
                "startedAt": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(started_ms / 1000)),
                "total": len(pool), "executed": len(results),
                "passed": sum(1 for r in results if r["verdict"] == "通过"),
                "failed": sum(1 for r in results if r["verdict"] == "失败"),
                "partial": sum(1 for r in results if r["verdict"] == "部分可执行"),
                "caseIds": [c["caseId"] for c in pool], "results": results,
            })
        if progress:
            progress({"index": i, "total": len(pool), "caseId": item["caseId"],
                      "verdict": item["verdict"], "pageObject": item["pageObject"]})

    passed = [r for r in results if r["verdict"] == "通过"]
    failed = [r for r in results if r["verdict"] == "失败"]
    partial = [r for r in results if r["verdict"] == "部分可执行"]
    by_po: dict[str, dict] = defaultdict(lambda: {"total": 0, "passed": 0, "failed": 0, "partial": 0})
    for r in results:
        b = by_po[r["pageObject"] or "（无）"]
        b["total"] += 1
        if r["verdict"] == "通过":
            b["passed"] += 1
        elif r["verdict"] == "失败":
            b["failed"] += 1
        else:
            b["partial"] += 1

    pool_info = browser_pool.status()
    browser_pool.close()

    media_bytes = sum(int((r.get("media") or {}).get("bytes") or 0) for r in results)
    summary = {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "batchId": batch_id,
        "kind": "batch",
        "target": "http://127.0.0.1:5174 (尚品汇 C 端真实前端)",
        "compiled": compiled_result["stats"],
        "executed": len(results), "passed": len(passed), "failed": len(failed),
        "partial": len(partial), "skippedCount": len(skipped),
        "passRate": round(len(passed) / len(results) * 100, 1) if results else 0,
        "totalSeconds": round(time.time() - started, 1),
        "pool": pool_info,
        "writeExecuted": sum(1 for r in results if r["writeFlow"]),
        "byPageObject": dict(sorted(by_po.items(), key=lambda kv: -kv[1]["total"])),
        "failures": [{"caseId": r["caseId"], "caseTitle": r["caseTitle"],
                      "pageObject": r["pageObject"],
                      "failedStep": next((s["raw"] for s in r["steps"] if s["status"] == "failed"), ""),
                      "detail": next((s["detail"] for s in r["steps"] if s["status"] == "failed"), ""),
                      "finalUrl": r["finalUrl"], "screenshot": r["screenshot"]} for r in failed],
        "skippedCases": skipped,
        "results": results,
        "mediaBytes": media_bytes,
    }

    # 批次记录落库：执行记录页只看到"一条批次"，点进去才是逐条明细
    store.put("uiBatches", batch_id, {
        "id": batch_id, "projectId": project_id, "kind": "batch", "status": "finished",
        "title": f"批量执行 · {len(results)} 条",
        "startedAtMs": started_ms, "finishedAtMs": int(time.time() * 1000),
        "startedAt": time.strftime("%Y/%m/%d %H:%M:%S", time.localtime(started_ms / 1000)),
        "browser": "Chromium(批量)", "total": len(pool), "executed": len(results),
        "passed": len(passed), "failed": len(failed), "partial": len(partial),
        "skippedCount": len(skipped), "passRate": summary["passRate"],
        "totalSeconds": summary["totalSeconds"], "writeExecuted": summary["writeExecuted"],
        "mediaBytes": media_bytes,
        "compiled": summary["compiled"], "byPageObject": summary["byPageObject"],
        "failures": summary["failures"], "skippedCases": skipped,
        "caseIds": [c["caseId"] for c in pool], "results": results,
    })

    # 容量守卫：媒体超过 5GiB 时删最旧的执行目录，并把记录标记为"媒体已清理"
    try:
        summary["mediaPrune"] = ui_media.prune_and_mark()
    except Exception as e:  # noqa: BLE001
        summary["mediaPrune"] = {"error": str(e)[:120]}
    summary["mediaUsage"] = ui_media.stats()
    return summary


# ---------------------------------------------------------------- 后台任务
def start_job(project_id: str, limit: int, max_write: int, delay_ms: int,
              case_ids: list[str] | None = None, only_confirmed: bool = False) -> str:
    """在后台线程启动批量执行（接口 100+ 条同步会超时）。返回 jobId。"""
    job_id = f"UIJOB-{int(time.time() * 1000)}"
    with _JOBS_LOCK:
        JOBS[job_id] = {
            "jobId": job_id, "projectId": project_id, "status": "running",
            "startedAt": time.strftime("%Y/%m/%d %H:%M:%S"),
            "index": 0, "total": limit, "current": "", "result": None, "error": "",
        }

    def worker():
        try:
            def on_progress(p):
                with _JOBS_LOCK:
                    JOBS[job_id].update({"index": p["index"], "total": p["total"],
                                         "current": f"{p['caseId']} {p['verdict']}"})

            summary = execute_batch(project_id, limit=limit, max_write=max_write,
                                    delay_ms=delay_ms, case_ids=case_ids, progress=on_progress,
                                    batch_id=job_id, only_confirmed=only_confirmed)
            with _JOBS_LOCK:
                JOBS[job_id].update({"status": "finished", "result": summary, "current": ""})
        except Exception as e:  # noqa: BLE001
            with _JOBS_LOCK:
                JOBS[job_id].update({"status": "failed", "error": str(e)[:400]})

    threading.Thread(target=worker, name=f"ui-batch-{job_id}", daemon=True).start()
    return job_id


def job_status(job_id: str) -> dict | None:
    with _JOBS_LOCK:
        job = JOBS.get(job_id)
        return dict(job) if job else None
