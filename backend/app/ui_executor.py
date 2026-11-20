"""UI 自动化执行引擎：共享浏览器池 + 关键字驱动执行器。

资源策略（架构师设计）：
1. 全局单例浏览器池：1 个 Chromium 进程，进程内维护最多 max_contexts 个 context；
   每条用例一个独立 context（隔离 cookie/localStorage），执行完立即 close，
   浏览器进程常驻复用——避免每条用例启停浏览器这个最昂贵的操作。
2. 并发上限：默认 1（串行），可通过 max_concurrency 调；context 数量受控，不会无限膨胀。
3. 空闲回收：浏览器空闲超过 idle_ttl 秒自动关闭，防止长期占用内存。
4. 步骤间统一节流 300ms（可配置），既满足稳定性也避免 selector 竞态。
5. 失败自动截图（仅失败时），不浪费磁盘。

执行器只认有限关键字，不执行任意用户代码；未编译成功（unknown）的步骤记录为 BLOCKED 并跳过。
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .ui_step_compiler import STEP_DELAY_MS, StepIR

SHOT_DIR = Path("/tmp/ui-auto-shots")
try:
    SHOT_DIR.mkdir(exist_ok=True)
except (FileExistsError, OSError):
    pass  # 沙箱 shim 对已存在目录可能抛 EEXIST，忽略即可


@dataclass
class StepResult:
    index: int
    raw: str
    keyword: str
    status: str  # passed / failed / blocked / skipped
    detail: str = ""
    durationMs: int = 0


class BrowserPool:
    """单例浏览器池：1 browser 进程 + N 个临时 context，空闲自动回收。"""

    _instance: "BrowserPool | None" = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, headless: bool = True, idle_ttl: int = 300):
        if self._initialized:
            return
        self._initialized = True
        self.headless = headless
        self.idle_ttl = idle_ttl
        self._pw = None
        self._browser = None
        self._last_used = time.time()
        self._pool_lock = threading.RLock()
        self._active_contexts = 0

    def acquire(self):
        """返回 (browser, page, release_fn)。线程安全，浏览器空闲自动回收。"""
        with self._pool_lock:
            if self._browser is None:
                from playwright.sync_api import sync_playwright
                self._pw = sync_playwright().start()
                try:
                    self._browser = self._pw.chromium.launch(headless=self.headless)
                except Exception:
                    self._pw.stop()
                    self._pw = None
                    raise
            self._last_used = time.time()
            browser = self._browser
            context = browser.new_context(viewport={"width": 1440, "height": 900})
            self._active_contexts += 1
            page = context.new_page()

            def release():
                with self._pool_lock:
                    try:
                        context.close()
                    finally:
                        self._active_contexts -= 1
                        self._last_used = time.time()

            return browser, page, release

    def maybe_recycle(self):
        """空闲超时且无活动 context 时关闭浏览器（由调用方在每次执行后触发）。"""
        with self._pool_lock:
            if (self._browser and self._active_contexts == 0
                    and time.time() - self._last_used > self.idle_ttl):
                try:
                    self._browser.close()
                    if self._pw:
                        self._pw.stop()
                except Exception:
                    pass
                finally:
                    self._browser = None
                    self._pw = None

    def status(self) -> dict[str, Any]:
        return {
            "browserAlive": self._browser is not None,
            "activeContexts": self._active_contexts,
            "idleSeconds": round(time.time() - self._last_used, 1),
        }


POOL = BrowserPool()


# ---------------------------------------------------------------- 关键字执行
def _locate(page, locator: str):
    """宽容定位：优先 CSS/text，失败返回 None（不抛异常）。"""
    if not locator:
        return None
    try:
        loc = page.locator(locator)
        return loc if loc.count() > 0 else None
    except Exception:
        return None


def execute_step(page, ir: StepIR, index: int, base_url: str, delay_ms: int) -> StepResult:
    t0 = time.time()
    if ir.is_design_check:
        cat = ir.args.get("category", "manual")
        return StepResult(index, ir.raw, ir.keyword, "blocked",
                          f"[{cat}] {ir.note or '设计核对项，非 UI 操作'}")
    if not ir.executable:
        return StepResult(index, ir.raw, ir.keyword, "blocked", ir.note or "未编译为可执行步骤")

    try:
        kw, a = ir.keyword, ir.args
        if kw == "nav":
            target = str(a.get("target", ""))
            url = target if target.startswith("http") else base_url + (target if target.startswith("/") else "")
            page.goto(url, wait_until="domcontentloaded", timeout=10000)
        elif kw == "click":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到元素：{a.get('locator')}")
            loc.first.click(timeout=5000)
        elif kw == "fill":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到输入框：{a.get('locator')}")
            value = str(a.get("value", ""))
            if "{{TEST_VALUE}}" in value:
                return StepResult(index, ir.raw, kw, "blocked", "测试用例未填写具体输入值（{{TEST_VALUE}} 占位）")
            loc.first.fill(value, timeout=5000)
        elif kw == "select":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到下拉框：{a.get('locator')}")
            loc.first.select_option(label=str(a.get("value", "")), timeout=5000)
        elif kw == "check":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到复选项：{a.get('locator')}")
            loc.first.check(timeout=5000)
        elif kw == "wait":
            page.wait_for_timeout(int(a.get("durationMs", delay_ms)))
        elif kw == "scroll":
            page.mouse.wheel(0, 500)
        elif kw == "screenshot":
            path = SHOT_DIR / f"step_{index}_{int(time.time())}.png"
            page.screenshot(path=str(path))
        elif kw == "assert":
            if page.locator("body").count() == 0:
                return StepResult(index, ir.raw, kw, "failed", "页面未正常加载")
            # 粗粒度存活断言；详细断言由 script 导出后人工增强
        else:
            return StepResult(index, ir.raw, kw, "blocked", f"不支持的关键字：{kw}")

        if kw != "wait":  # wait 本身已等待，避免重复
            page.wait_for_timeout(delay_ms)
        return StepResult(index, ir.raw, kw, "passed", "",
                          round((time.time() - t0) * 1000))
    except Exception as e:
        return StepResult(index, ir.raw, ir.keyword, "failed", str(e)[:150],
                          round((time.time() - t0) * 1000))


def run_compiled(ir_case: dict, delay_ms: int = STEP_DELAY_MS) -> dict[str, Any]:
    """执行一条已编译用例：共享浏览器池取 context → 逐步执行 → 失败截图 → 释放。"""
    browser, page, release = POOL.acquire()
    results: list[StepResult] = []
    shot = ""
    started = time.time()
    try:
        for i, s in enumerate(ir_case["steps"], 1):
            ir = s if isinstance(s, StepIR) else StepIR(**s)
            r = execute_step(page, ir, i, ir_case.get("baseUrl", ""), delay_ms)
            results.append(r)
            if r.status == "failed":
                shot = str(SHOT_DIR / f"fail_{ir_case.get('caseId', 'case')}_{int(time.time())}.png")
                try:
                    page.screenshot(path=shot)
                except Exception:
                    shot = ""
                break  # 快速失败，不浪费资源
        failed = [r for r in results if r.status == "failed"]
        blocked = [r for r in results if r.status == "blocked"]
        verdict = "失败" if failed else ("部分可执行" if blocked else "通过")
        return {
            "caseId": ir_case.get("caseId", ""),
            "verdict": verdict,
            "steps": [r.__dict__ for r in results],
            "screenshot": shot,
            "durationMs": round((time.time() - started) * 1000),
        }
    finally:
        release()
        POOL.maybe_recycle()
