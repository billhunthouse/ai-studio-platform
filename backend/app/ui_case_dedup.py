"""用例去重合并：把"同一件事被登记 N 次"收敛成一条可执行用例。

问题
----
363 条功能用例只有 69 个唯一标题，343 条（94.5%）是副本。副本来源不是人工重复录入，
而是**用例生成器按需求逐条套模板**：一条"库存不变式校验"被挂到 V1-FR-008 ~ V1-FR-013
六个需求下，再跨"商品与类目 / 库存 / 订单交易"三个模块各存一份。

后果不是"数据冗余"这么轻：
1. UI 自动化的分母被放大 5 倍——同一条用例跑 23 次，通过率看起来很高，实际只验证了 1 件事；
2. 覆盖统计虚高——某个需求"有用例"，点开发现是别的需求的副本；
3. 人一看列表 363 条就放弃评审，绑定确认率永远上不去。

做法
----
按**归一化标题**分组（标题即测试意图，steps/expected 是同一意图的不同模板措辞），
每组选一条**主用例**保留在册，其余标记 `archived=True, duplicateOf=<主用例>`，
并把副本携带的模块、需求关联**聚合到主用例**上——这样"一条用例覆盖 6 个需求"
这个事实被保留了，而不是随副本一起丢弃。

三条安全约束
------------
- **不删除。** 只写标记字段，`restore()` 可完整回滚。
- **不改内容。** 主用例的 title/steps/expected 一字不动，只追加元数据。
- **可解释。** 每条合并都带 `mergeReason` 与主用例选择依据，能向人交代为什么选它。

主用例怎么选（分数高者胜）
--------------------------
人工绑定 > 已执行过 > 已通过 > 需求关联多 > 优先级高 > ID 小（先登记的通常是原始用例）
"""
from __future__ import annotations

import hashlib
import re
import time
from collections import defaultdict
from typing import Any

ARCHIVE_REASON = "duplicate_title"

# 优先级权重：P0 最高。生成器常把同一条用例同时标成 P0/P1/P2，取最严的那条当主。
PRIORITY_SCORE = {"P0": 40, "P1": 24, "P2": 10, "P3": 4}


def normalize(text: str) -> str:
    """标题归一化：去空白 + 全角括号转半角。不做同义词归并（那会引入不可控的错并）。"""
    s = re.sub(r"\s+", "", text or "")
    return s.replace("（", "(").replace("）", ")").replace("，", ",").replace("：", ":")


def fingerprint(case: dict[str, Any]) -> str:
    """内容指纹：标题 + 步骤 + 预期。用于区分"真副本"与"同标题不同内容"。"""
    steps = case.get("steps") or []
    if not isinstance(steps, list):
        steps = [steps]
    raw = "|".join([normalize(case.get("title") or ""),
                    ">".join(normalize(str(s)) for s in steps),
                    normalize(case.get("expected") or "")])
    return hashlib.md5(raw.encode("utf-8")).hexdigest()[:12]


def is_active(case: dict[str, Any]) -> bool:
    """在册用例：未被合并归档。所有统计/编译/执行都应先过这道筛。"""
    return not case.get("archived")


def active_cases(cases: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [c for c in cases if is_active(c)]


def _req_ids(case: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for rid in (case.get("relatedRequirementIds") or []):
        if rid and rid not in out:
            out.append(rid)
    own = case.get("requirementId")
    if own and own not in out:
        out.insert(0, own)
    return out


def _req_titles(case: dict[str, Any]) -> list[str]:
    return [t for t in (case.get("relatedRequirementTitles") or []) if t]


def _score(case: dict[str, Any]) -> tuple[int, list[str]]:
    """主用例打分，同时返回"为什么选它"，让报告能自证。"""
    s = 0
    why: list[str] = []
    if case.get("bindingSource") == "human":
        s += 200
        why.append("已人工确认绑定")
    last = case.get("lastRun") or {}
    if last:
        s += 50
        why.append("已有执行记录")
        if last.get("verdict") == "通过":
            s += 20
            why.append("最近一次通过")
    if case.get("status") == "通过":
        s += 12
        why.append("状态为通过")
    n_req = len(_req_ids(case))
    if n_req > 1:
        s += min(n_req * 3, 30)
        why.append(f"关联 {n_req} 个需求")
    p = str(case.get("priority") or "")
    if p in PRIORITY_SCORE:
        s += PRIORITY_SCORE[p]
        why.append(f"优先级 {p}")
    if len(case.get("steps") or []) > 0:
        s += 2
    # ID 越小越可能是最早登记的原始用例
    m = re.search(r"(\d+)", str(case.get("id") or ""))
    s -= int(m.group(1)) / 100000 if m else 0
    return s, why


def plan(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """生成合并计划（只读，不落库）。

    返回 groups 明细 + 汇总，供前端预览与人工抽查。
    """
    live = active_cases(cases)
    archived_already = len(cases) - len(live)
    buckets: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in live:
        buckets[normalize(c.get("title") or "")].append(c)

    groups: list[dict[str, Any]] = []
    for _key, members in buckets.items():
        if len(members) < 2:
            continue
        ranked = sorted(members, key=lambda c: (-_score(c)[0], str(c.get("id"))))
        primary = ranked[0]
        p_score, p_why = _score(primary)
        dups = ranked[1:]
        modules = []
        req_ids: list[str] = []
        req_titles: list[str] = []
        for c in members:
            for m in [c.get("module")] + list(c.get("relatedModules") or []):
                if m and m not in modules:
                    modules.append(m)
            for rid in _req_ids(c):
                if rid not in req_ids:
                    req_ids.append(rid)
            for t in _req_titles(c):
                if t not in req_titles:
                    req_titles.append(t)
        fps = {fingerprint(c) for c in members}
        groups.append({
            "title": primary.get("title"),
            "primary": primary.get("id"),
            "primaryModule": primary.get("module"),
            "primaryReason": "；".join(p_why) or "按 ID 取最早登记",
            "primaryScore": round(p_score, 2),
            "duplicates": [c.get("id") for c in dups],
            "duplicateCount": len(dups),
            "modules": modules,
            "crossModule": len(modules) > 1,
            "requirementIds": req_ids,
            "requirementTitles": req_titles,
            "fingerprints": len(fps),
            # 同标题但内容不同 → 合并仍成立（同一意图），但值得人工抽查
            "contentVaries": len(fps) > 1,
            "priority": primary.get("priority"),
        })

    groups.sort(key=lambda g: (-g["duplicateCount"], str(g["primary"])))
    dup_total = sum(g["duplicateCount"] for g in groups)
    for g in groups:
        g["status"] = "pending"

    # 已合并的历史组：从 archived + duplicateOf 反推。
    # 合并完成后再点"查看明细"必须还能看到"谁并了谁"，否则人无法复核已经发生的事，
    # 只能盲信——这比没有明细更糟。
    history: dict[str, dict[str, Any]] = {}
    by_id = {c.get("id"): c for c in cases}
    for c in cases:
        if not c.get("archived") or not c.get("duplicateOf"):
            continue
        pid = str(c["duplicateOf"])
        g = history.setdefault(pid, {
            "title": (by_id.get(pid) or {}).get("title") or c.get("title"),
            "primary": pid,
            "primaryModule": (by_id.get(pid) or {}).get("module") or "",
            "primaryReason": (by_id.get(pid) or {}).get("dedupPrimaryReason") or "去重时已选定并归档",
            "primaryScore": 0,
            "duplicates": [], "duplicateCount": 0,
            "modules": [], "crossModule": False,
            "requirementIds": [], "requirementTitles": [],
            "fingerprints": 1, "contentVaries": False,
            "priority": (by_id.get(pid) or {}).get("priority") or "",
            "status": "merged",
            "archivedAt": c.get("archivedAt") or "",
        })
        g["duplicates"].append(c.get("id"))
        g["duplicateCount"] = len(g["duplicates"])
        for m in [c.get("module")] + list(c.get("relatedModules") or []):
            if m and m not in g["modules"]:
                g["modules"].append(m)
        for rid in _req_ids(c):
            if rid not in g["requirementIds"]:
                g["requirementIds"].append(rid)
    for g in history.values():
        g["crossModule"] = len(g["modules"]) > 1
    hist_rows = sorted(history.values(), key=lambda g: (-g["duplicateCount"], str(g["primary"])))

    return {
        "total": len(cases),
        "active": len(live),
        "alreadyArchived": archived_already,
        "uniqueTitles": len(buckets),
        "groups": len(groups),
        "duplicates": dup_total,
        "duplicateRate": round(dup_total / len(live) * 100, 1) if live else 0.0,
        "afterMerge": len(buckets),
        "crossModuleGroups": sum(1 for g in groups if g["crossModule"]),
        "contentVariesGroups": sum(1 for g in groups if g["contentVaries"]),
        # 已合并的历史组统计（合并完成后用这组数讲历史，而不是显示 0）
        "mergedGroups": len(hist_rows),
        "mergedDuplicates": sum(g["duplicateCount"] for g in hist_rows),
        "mergedCrossModuleGroups": sum(1 for g in hist_rows if g["crossModule"]),
        "items": groups + hist_rows,
    }


def apply(
    cases: list[dict[str, Any]],
    project_id: str,
    ids: list[str] | None = None,
    now: str | None = None,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """执行合并。返回 (报告, 需要写回的用例列表)。

    只处理 `ids` 指定的主用例（None = 全部），便于分批合并与人工只并部分组。
    """
    stamp = now or time.strftime("%Y/%m/%d %H:%M:%S")
    p = plan(cases)
    by_id = {c.get("id"): c for c in cases}
    wanted = set(ids) if ids else None
    touched: dict[str, dict[str, Any]] = {}
    applied: list[dict[str, Any]] = []

    for g in p["items"]:
        # 只处理待合并组；history 组是已合并的历史回放，重跑不应重复累加
        if g.get("status") != "pending":
            continue
        if wanted is not None and g["primary"] not in wanted:
            continue
        primary = dict(by_id[g["primary"]])
        merged_from = list(primary.get("mergedFrom") or [])
        req_ids = list(primary.get("relatedRequirementIds") or [])
        req_titles = list(primary.get("relatedRequirementTitles") or [])
        modules = list(primary.get("relatedModules") or [])
        if primary.get("module") and primary["module"] not in modules:
            modules.insert(0, primary["module"])
        for rid in _req_ids(primary):
            if rid not in req_ids:
                req_ids.append(rid)
        for t in _req_titles(primary):
            if t not in req_titles:
                req_titles.append(t)

        for did in g["duplicates"]:
            dup = by_id.get(did)
            if not dup:
                continue
            for rid in _req_ids(dup):
                if rid not in req_ids:
                    req_ids.append(rid)
            for t in _req_titles(dup):
                if t not in req_titles:
                    req_titles.append(t)
            for m in [dup.get("module")] + list(dup.get("relatedModules") or []):
                if m and m not in modules:
                    modules.append(m)
            if did not in merged_from:
                merged_from.append(did)

            d = dict(dup)
            d.update({
                "archived": True,
                "duplicateOf": g["primary"],
                "archiveReason": ARCHIVE_REASON,
                "archivedAt": stamp,
                "archivedBy": "dedup",
            })
            touched[did] = d

        primary.update({
            "mergedFrom": merged_from,
            "mergedCount": len(merged_from),
            "relatedRequirementIds": req_ids,
            "relatedRequirementTitles": req_titles,
            "relatedModules": modules,
            "dedupAt": stamp,
            "dedupVersion": 1,
            # 把"当初为什么选它当主用例"一起落库：合并完成后明细表还能自证，不用回头查日志
            "dedupPrimaryReason": g.get("primaryReason") or "",
        })
        # 合并会改写主用例的需求/模块聚合字段，回滚必须能精确还原。
        # 只记第一次的原值——重复执行 apply 不能把"合并后的值"当成原值记下来。
        if "dedupPrev" not in primary:
            primary["dedupPrev"] = {
                "requirementIds": list(by_id[g["primary"]].get("relatedRequirementIds") or []),
                "requirementTitles": list(by_id[g["primary"]].get("relatedRequirementTitles") or []),
                "modules": list(by_id[g["primary"]].get("relatedModules") or []),
            }
        touched[g["primary"]] = primary
        applied.append({
            "primary": g["primary"], "title": g["title"],
            "merged": g["duplicates"], "mergedCount": g["duplicateCount"],
            "requirementIds": req_ids, "modules": modules,
        })

    report = {
        "projectId": project_id,
        "appliedAt": stamp,
        "groupsMerged": len(applied),
        "casesArchived": sum(a["mergedCount"] for a in applied),
        "before": p["active"],
        "after": p["active"] - sum(a["mergedCount"] for a in applied),
        "items": applied,
    }
    return report, list(touched.values())


def restore(cases: list[dict[str, Any]]) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    """回滚：清掉 archived/mergedFrom 标记，并把聚合字段还原成合并前的值。

    重点在"还原"而不是"清空"：有些用例（如 TC-1027）在去重之前就人为聚过需求，
    直接 pop 会把原本合法的关联一起删掉，回滚反而造成新损坏。
    """
    touched: dict[str, dict[str, Any]] = {}
    restored = 0
    cleared = 0
    for c in cases:
        d = dict(c)
        dirty = False
        if d.get("archived") and d.get("archiveReason") == ARCHIVE_REASON:
            for k in ("archived", "duplicateOf", "archiveReason", "archivedAt", "archivedBy"):
                d.pop(k, None)
            restored += 1
            dirty = True
        if d.get("mergedFrom") or d.get("dedupPrev"):
            prev = d.pop("dedupPrev", None) or {}
            if prev:
                if prev.get("requirementIds"):
                    d["relatedRequirementIds"] = prev["requirementIds"]
                else:
                    d.pop("relatedRequirementIds", None)
                if prev.get("requirementTitles"):
                    d["relatedRequirementTitles"] = prev["requirementTitles"]
                else:
                    d.pop("relatedRequirementTitles", None)
                if prev.get("modules"):
                    d["relatedModules"] = prev["modules"]
                else:
                    d.pop("relatedModules", None)
            for k in ("mergedFrom", "mergedCount", "dedupAt", "dedupVersion", "dedupPrimaryReason"):
                d.pop(k, None)
            cleared += 1
            dirty = True
        if dirty:
            touched[d["id"]] = d
    return {"restored": restored, "primariesCleared": cleared}, list(touched.values())


def summary(cases: list[dict[str, Any]]) -> dict[str, Any]:
    """给前端用的轻量摘要（不返回 69 条明细）。"""
    p = plan(cases)
    return {k: p[k] for k in
            ("total", "active", "alreadyArchived", "uniqueTitles", "groups",
             "duplicates", "duplicateRate", "afterMerge", "crossModuleGroups",
             "contentVariesGroups")}
