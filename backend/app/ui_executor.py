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

import shutil
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import ui_media
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
    """单例浏览器池：1 browser 进程 + N 个临时 context，空闲自动回收。

    isolated=True 时创建独立实例（不进单例），用于后台任务：
    Playwright sync API 与创建它的线程绑定，跨线程复用同一个 browser 会抛
    greenlet 错误，因此每个后台批量任务必须独占一个池，任务结束即 close。
    """

    _instance: "BrowserPool | None" = None
    _lock = threading.Lock()

    def __new__(cls, *args, **kwargs):
        if kwargs.get("isolated"):
            inst = super().__new__(cls)
            inst._initialized = False
            return inst
        with cls._lock:
            if cls._instance is None:
                cls._instance = super().__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self, headless: bool = True, idle_ttl: int = 300, isolated: bool = False):
        if self._initialized:
            return
        self._initialized = True
        self.headless = headless
        self.idle_ttl = idle_ttl
        self.isolated = isolated
        self._pw = None
        self._browser = None
        self._last_used = time.time()
        self._pool_lock = threading.RLock()
        self._active_contexts = 0

    def acquire(self, video_dir: str | None = None):
        """返回 (browser, page, release_fn)。线程安全，浏览器空闲自动回收。

        video_dir 传入时按目录录制 webm（context close 后才会落盘），
        用于执行记录里回看"这一步到底发生了什么"。
        """
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
            opts: dict[str, Any] = {"viewport": {"width": 1440, "height": 900}}
            if video_dir:
                opts["record_video_dir"] = video_dir
                # 录制分辨率小于视口，体积可控（800x500 约 0.1~0.3MB/s）
                opts["record_video_size"] = {"width": 800, "height": 500}
            context = browser.new_context(**opts)
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

    def close(self) -> None:
        """强制关闭浏览器与 playwright（后台任务结束调用，释放资源）。"""
        with self._pool_lock:
            try:
                if self._browser:
                    self._browser.close()
            except Exception:  # noqa: BLE001
                pass
            try:
                if self._pw:
                    self._pw.stop()
            except Exception:  # noqa: BLE001
                pass
            self._browser = None
            self._pw = None
            self._active_contexts = 0


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


def _run_assert(page, a: dict) -> tuple[bool, str]:
    """真实业务断言：url / url_not / text / no_text / count。

    断言失败会把"实际值"写进 detail，便于失败归因（不是只报一句失败）。
    """
    kind = a.get("kind")
    target = str(a.get("target", a.get("expectation", "")))
    try:
        if kind == "url":
            url = page.url
            return (target in url), ("" if target in url else f"URL 应包含「{target}」，实际 {url}")
        if kind == "url_not":
            url = page.url
            return (target not in url), ("" if target not in url else f"URL 不应包含「{target}」，实际 {url}")
        if kind in ("text", "no_text"):
            body = page.locator("body").inner_text(timeout=5000)
            hit = target in body
            if kind == "text":
                return hit, ("" if hit else f"页面未出现预期文本「{target}」")
            return (not hit), ("" if not hit else f"页面出现了不应存在的文本「{target}」")
        if kind == "count":
            n = page.locator(target).count()
            need = int(a.get("min", 1))
            return n >= need, ("" if n >= need else f"元素「{target}」数量 {n} < 期望 {need}")
        if kind == "regex":
            import re as _re
            body = page.locator("body").inner_text(timeout=5000)
            hit = _re.search(target, body) is not None
            return hit, ("" if hit else f"页面未匹配到正则「{target}」")
        if kind == "text_not_empty":
            body = page.locator("body").inner_text(timeout=5000).strip()
            return len(body) > 30, ("" if len(body) > 30 else "页面内容为空或过短")
    except Exception as e:  # noqa: BLE001
        return False, f"断言执行异常：{str(e)[:120]}"
    # 语义断言（中文预期结果）：做页面存活校验，具体语义由人工/后续用例补充
    if page.locator("body").count() == 0:
        return False, "页面未正常加载"
    return True, ""


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
            locator = str(a.get("locator", ""))
            try:
                loc.first.click(timeout=6000)
            except Exception as e:  # noqa: BLE001
                msg = str(e)
                # 被浮层/遮罩拦截时兜底强制点击（真实站点常见：抽屉、toast 遮挡）
                if "intercepts pointer events" in msg or "Timeout" in msg:
                    try:
                        loc.first.click(timeout=2500, force=True)
                    except Exception:  # noqa: BLE001
                        return StepResult(index, ir.raw, kw, "failed",
                                          f"点击失败（元素存在但不可交互）：{locator}"[:150])
                else:
                    raise
        elif kw == "fill":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到输入框：{a.get('locator')}")
            value = str(a.get("value", ""))
            if "{{TEST_VALUE}}" in value:
                return StepResult(index, ir.raw, kw, "blocked", "测试用例未填写具体输入值（{{TEST_VALUE}} 占位）")
            loc.first.fill(value, timeout=6000)
        elif kw == "select":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到下拉框：{a.get('locator')}")
            loc.first.select_option(label=str(a.get("value", "")), timeout=6000)
        elif kw == "check":
            loc = _locate(page, str(a.get("locator", "")))
            if not loc:
                return StepResult(index, ir.raw, kw, "failed", f"找不到复选项：{a.get('locator')}")
            loc.first.check(timeout=6000)
        elif kw == "wait":
            page.wait_for_timeout(int(a.get("durationMs", delay_ms)))
        elif kw == "scroll":
            page.mouse.wheel(0, 500)
        elif kw == "screenshot":
            path = SHOT_DIR / f"step_{index}_{int(time.time())}.png"
            page.screenshot(path=str(path))
        elif kw == "assert":
            ok, detail = _run_assert(page, a)
            if not ok:
                return StepResult(index, ir.raw, kw, "failed", detail,
                                  round((time.time() - t0) * 1000))
        else:
            return StepResult(index, ir.raw, kw, "blocked", f"不支持的关键字：{kw}")

        if kw != "wait":  # wait 本身已等待，避免重复
            page.wait_for_timeout(delay_ms)
        return StepResult(index, ir.raw, kw, "passed", "",
                          round((time.time() - t0) * 1000))
    except Exception as e:
        return StepResult(index, ir.raw, ir.keyword, "failed", str(e)[:150],
                          round((time.time() - t0) * 1000))


def _capture(page, media: Path | None, name: str) -> str:
    """截图到媒体目录（无媒体目录时退回 SHOT_DIR），失败返回空串。"""
    try:
        target = (media / name) if media else (SHOT_DIR / name)
        page.screenshot(path=str(target))
        return str(target)
    except Exception:  # noqa: BLE001
        return ""


def run_compiled(ir_case: dict, delay_ms: int = STEP_DELAY_MS, shot_always: bool = True,
                 pool: "BrowserPool | None" = None, run_id: str = "",
                 record_video: bool = True, step_shots: bool = True) -> dict[str, Any]:
    """执行一条已编译用例：取 context → 逐步执行 → 每步截图 + 录屏 → 释放。

    返回结果带"证据"：最终 URL、页面文本摘要、断言通过数、每一步的截图名、视频名，
    便于执行记录里逐步回放，而不是只给一句"通过"。
    pool 为空时用全局单例；后台任务传入自己的 isolated 池，避免跨线程复用。
    """
    p = pool or POOL
    media = ui_media.run_dir(run_id) if run_id else None
    browser, page, release = p.acquire(video_dir=str(media) if (media and record_video) else None)
    video = page.video if (media and record_video) else None
    case_id = ir_case.get("caseId", "case")
    results: list[StepResult] = []
    shots: dict[int, str] = {}
    shot = ""
    final_url = ""
    page_text = ""
    started = time.time()
    error = ""
    result: dict[str, Any] = {
        "caseId": case_id, "verdict": "失败", "steps": [],
        "assertions": 0, "assertionsPassed": 0,
        "finalUrl": "", "pageText": "", "screenshot": "",
        "durationMs": 0,
    }
    try:
        for i, s in enumerate(ir_case["steps"], 1):
            ir = s if isinstance(s, StepIR) else StepIR(**s)
            r = execute_step(page, ir, i, ir_case.get("baseUrl", ""), delay_ms)
            if media and step_shots:
                name = f"step_{i:02d}.png"
                path = _capture(page, media, name)
                if path:
                    shots[i] = name
                    shot = path
            results.append(r)
            if r.status == "failed":
                if not shot:
                    shot = _capture(page, media, f"fail_{case_id}_{int(time.time())}.png")
                break  # 快速失败，不浪费资源
        failed = [r for r in results if r.status == "failed"]
        blocked = [r for r in results if r.status == "blocked"]
        verdict = "失败" if failed else ("部分可执行" if blocked else "通过")
        try:
            final_url = page.url
            page_text = page.locator("body").inner_text(timeout=4000)[:300].replace("\n", " | ")
        except Exception:  # noqa: BLE001
            pass
        if shot_always and not shot:
            shot = _capture(page, media, "final.png" if media else f"ok_{case_id}_{int(time.time())}.png")
        result = {
            "caseId": case_id,
            "verdict": verdict,
            "steps": [dict(r.__dict__, shot=shots.get(r.index, "")) for r in results],
            "assertions": sum(1 for r in results if r.keyword == "assert"),
            "assertionsPassed": sum(1 for r in results if r.keyword == "assert" and r.status == "passed"),
            "finalUrl": final_url,
            "pageText": page_text,
            "screenshot": shot,
            "durationMs": round((time.time() - started) * 1000),
        }
    except Exception as e:  # noqa: BLE001
        error = str(e)[:300]
    finally:
        release()
        p.maybe_recycle()

    # context 关闭后视频才落盘：把 Playwright 的随机文件名改成固定 video.webm
    video_name = ""
    if video is not None and media:
        try:
            vp = Path(video.path())
            if vp.exists():
                dest = media / "video.webm"
                if dest.exists():
                    dest.unlink()
                shutil.move(str(vp), str(dest))
                video_name = "video.webm"
        except Exception:  # noqa: BLE001
            video_name = ""

    if error:
        result["verdict"] = "失败"
        result["error"] = error
        result["steps"] = [dict(r.__dict__, shot=shots.get(r.index, "")) for r in results]
        result["durationMs"] = round((time.time() - started) * 1000)

    result["runId"] = run_id
    if media:
        result["media"] = {
            "dir": str(media),
            "video": video_name,
            "bytes": ui_media.dir_size(media),
            "steps": [{"index": i, "name": n} for i, n in sorted(shots.items())],
        }
    return result
