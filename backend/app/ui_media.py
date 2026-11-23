"""UI 执行媒体库：每步截图 + 执行视频的落盘、签名访问与容量淘汰。

设计要点（对应"默认保存数据，超过 5G 删最旧"的需求）：
1. 目录结构：`/tmp/ui-auto-media/{runId}/step_01.png … video.webm`
   —— 一次执行一个目录，目录名即 runId，天然可按时间淘汰。
2. 访问控制：截图/视频要能被 <img>/<video> 直接加载，而这两个标签无法带
   Authorization 头。因此发"带过期时间的 HMAC 签名 URL"，不把 access token 暴露在 URL 里，
   也不放开成匿名接口。
3. 容量预算：总大小超过 5GiB 时，按目录 mtime 从旧到新删除，直到回到预算内；
   被删的 runId 返回给调用方，用于把执行记录标记为「媒体已清理」（记录本身保留，便于追溯）。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import shutil
import time
from pathlib import Path
from urllib.parse import quote

from .config import settings

MEDIA_ROOT = Path("/tmp/ui-auto-media")
BUDGET_BYTES = 5 * 1024**3          # 5 GiB
SIGN_TTL_SECONDS = 12 * 3600        # 签名有效期：12 小时，够看回放


def ensure_root() -> Path:
    try:
        MEDIA_ROOT.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, OSError):
        pass  # 沙箱 shim 对已存在目录可能抛 EEXIST
    return MEDIA_ROOT


def safe_id(run_id: str) -> str:
    keep = "".join(ch for ch in str(run_id) if ch.isalnum() or ch in "-_.")
    return keep[:96] or "run"


def run_dir(run_id: str) -> Path:
    p = ensure_root() / safe_id(run_id)
    try:
        p.mkdir(parents=True, exist_ok=True)
    except (FileExistsError, OSError):
        pass
    return p


def _sig(run_id: str, name: str, exp: int) -> str:
    msg = f"{safe_id(run_id)}/{name}:{exp}".encode()
    return hmac.new(settings.app_secret.encode("utf-8"), msg, hashlib.sha256).hexdigest()[:24]


def sign(run_id: str, name: str) -> str:
    exp = int(time.time()) + SIGN_TTL_SECONDS
    return f"{exp}.{_sig(run_id, name, exp)}"


def verify(run_id: str, name: str, key: str) -> bool:
    try:
        exp_s, sig = key.split(".", 1)
        exp = int(exp_s)
    except (ValueError, AttributeError):
        return False
    if exp < int(time.time()):
        return False
    return hmac.compare_digest(sig, _sig(run_id, name, exp))


def media_url(run_id: str, name: str) -> str:
    """返回前端可直接放进 <img src> / <video src> 的相对地址。"""
    return f"/api/v1/ui/media/{safe_id(run_id)}/{quote(name)}?k={sign(run_id, name)}"


def file_path(run_id: str, name: str) -> Path | None:
    """只允许取自己目录下的文件，阻断 ../ 穿越。"""
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    p = (ensure_root() / safe_id(run_id) / name).resolve()
    root = ensure_root().resolve()
    if root not in p.parents:
        return None
    return p if p.is_file() else None


def dir_size(path: Path) -> int:
    total = 0
    try:
        for f in path.rglob("*"):
            if f.is_file():
                total += f.stat().st_size
    except OSError:
        pass
    return total


def total_size() -> int:
    root = ensure_root()
    return sum(dir_size(p) for p in root.iterdir() if p.is_dir())


def enforce_budget(extra_bytes: int = 0) -> list[str]:
    """超出 5GiB 预算时删除最旧的执行目录，返回被删的 runId 列表。"""
    root = ensure_root()
    dirs = []
    for p in root.iterdir():
        if p.is_dir():
            try:
                dirs.append((p.stat().st_mtime, p))
            except OSError:
                continue
    dirs.sort(key=lambda x: x[0])
    total = sum(dir_size(p) for _, p in dirs) + extra_bytes
    removed: list[str] = []
    for _, p in dirs:
        if total <= BUDGET_BYTES:
            break
        size = dir_size(p)
        shutil.rmtree(p, ignore_errors=True)
        total -= size
        removed.append(p.name)
    return removed


def stats() -> dict:
    root = ensure_root()
    dirs = [p for p in root.iterdir() if p.is_dir()]
    used = total_size()
    return {
        "root": str(root),
        "runs": len(dirs),
        "usedBytes": used,
        "usedMB": round(used / 1024 / 1024, 1),
        "budgetBytes": BUDGET_BYTES,
        "budgetGB": round(BUDGET_BYTES / 1024**3, 2),
        "usage": f"{round(used / 1024 / 1024, 1)} MB / {round(BUDGET_BYTES / 1024**3, 2)} GB",
    }


def mark_pruned(removed: list[str], project_id: str | None = None) -> dict:
    """把被淘汰的 runId 在库里标记 mediaPruned，避免前端以为"截图丢了是 bug"。"""
    if not removed:
        return {"marked": 0}
    from .store import store  # 延迟导入，避免 store→db 初始化顺序问题

    marked = 0
    for rid in removed:
        doc = store.get("uiRuns", rid, None)
        if doc:
            doc["mediaPruned"] = True
            doc["mediaPrunedAt"] = time.strftime("%Y/%m/%d %H:%M:%S")
            store.put("uiRuns", rid, doc)
            marked += 1
            continue
        batch = store.get("uiBatches", rid, None)
        if batch:
            batch["mediaPruned"] = True
            batch["mediaPrunedAt"] = time.strftime("%Y/%m/%d %H:%M:%S")
            store.put("uiBatches", rid, batch)
            marked += 1
        # 批次的子目录名形如 {batchId}__{caseId}
        if "__" in rid:
            parent = rid.split("__", 1)[0]
            batch = store.get("uiBatches", parent, None)
            if batch and not batch.get("mediaPruned"):
                batch["mediaPruned"] = True
                batch["mediaPrunedAt"] = time.strftime("%Y/%m/%d %H:%M:%S")
                store.put("uiBatches", parent, batch)
                marked += 1
    return {"marked": marked, "removed": removed}


def prune_and_mark() -> dict:
    removed = enforce_budget()
    return {"removed": removed, **mark_pruned(removed)}


if __name__ == "__main__":  # 手工排查用：python -m app.ui_media
    print(json.dumps(stats(), ensure_ascii=False, indent=2))
