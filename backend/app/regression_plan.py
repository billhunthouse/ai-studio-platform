"""需求回归执行计划（Regression Execution Plan）。

把「已覆盖但未验证」的需求，编排成可执行、可度量、可复盘的回归批次。

口径（与 docs/需求文档规范.md §9-10 一致）：
  在册用例   testCases 中未打 archived 标记的用例（去重合并后 748 条）
  可自动执行 caseType = api 且 relatedApi 形如 "METHOD /path"
  需人工执行 functional 用例：没有被测接口，只能按步骤人工核对
  未验证需求 关联用例中没有任何一条 lastRun.verdict ∈ {通过, 符合}

批次编排原则：
  1. 依赖优先：身份 → 权限 → 主数据 → 库存 → C 端 → 交易 → 支付 → 售后 → 评价
  2. 先冒烟后全量：B1 每个需求抽 1 条正向接口用例，先判断环境与种子数据是否可用
  3. 自动/人工双轨：机器跑的与人工核对的分开排期，互不阻塞
  4. 已知缺陷单独复测：上轮判定「不符」的用例进 R1，与首轮结果分开统计
  5. 单批不超过 MAX_AUTO 条：失败可定位、可回滚、可重跑

为什么计划要动态算而不是写死：用例的 lastRun 会被执行不断改写，写死的清单
第二天就失真。本模块每次调用都从库里现算，因此「批次进度」永远等于真实执行情况。
"""
from __future__ import annotations

import threading
import time
import urllib.error
import urllib.request
from collections import defaultdict
from datetime import date, datetime, timedelta
from typing import Any

from sqlalchemy import text

from .db import SessionLocal
from .logic import now_label
from .store import store

# ---------------------------------------------------------------- 常量口径
PASS_VERDICTS = {"通过", "符合"}
FAIL_VERDICTS = {"不符", "失败", "无法执行", "不支持"}
# 跳过（DELETE 保护）/ 已执行（人工确认过）都算「跑过了」，但不能算通过
SKIP_VERDICTS = {"跳过", "已执行", "部分可执行"}

MAX_AUTO = 100      # 单个自动化批次最多用例数
MAX_MANUAL = 40     # 单个人工批次最多用例数

# 单条耗时估算（分钟）：含请求往返、身份复用、结果落库；失败排查按经验值均摊
MIN_PER_API = 0.5
MIN_PER_SMOKE = 0.4
MIN_PER_MANUAL = 3.0
MIN_PER_RETEST = 0.6
MIN_PER_JUDGE = 1.0   # 已拿到响应，只需对照预期文本裁定
MIN_BASELINE = 20
MIN_CLOSEOUT = 45

DAY_AUTO_CAP = 300   # 自动化轨道每日可用分钟
DAY_MANUAL_CAP = 300  # 人工轨道每日可用分钟

# 业务链路：code 决定批次顺序，domain 对应 PRD 的 docInfo.domain
CHAINS: list[dict[str, Any]] = [
    {"code": "A", "domain": "认证登录", "name": "身份基座", "why": "登录/登出是所有链路的入口，先过这一关再谈其他"},
    {"code": "B", "domain": "RBAC 权限", "name": "管理端基座", "why": "账号/角色/菜单/字典/日志是后台其余模块的权限前置"},
    {"code": "C", "domain": "商品与类目", "name": "商品主数据", "why": "类目、品牌、属性、SPU-SKU 是库存与交易的前置数据"},
    {"code": "D", "domain": "库存", "name": "库存与履约", "why": "扣减与回写依赖 SKU 存在，必须在交易前验证"},
    {"code": "E", "domain": "首页与运营", "name": "站点与运营位", "why": "依赖商品与类目数据，可与 C 并行"},
    {"code": "F", "domain": "购物车与个人中心", "name": "C 端账户", "why": "依赖商品详情，是下单的直接前置"},
    {"code": "G", "domain": "订单交易", "name": "交易主链路", "why": "依赖购物车与库存，回归不可跳步"},
    {"code": "H", "domain": "支付", "name": "支付", "why": "依赖订单主键与待付款状态"},
    {"code": "I", "domain": "售后", "name": "售后", "why": "依赖已发货/已完成订单，排在订单之后"},
    {"code": "J", "domain": "评价", "name": "评价", "why": "依赖已完成订单，链路独立"},
    {"code": "K", "domain": "AI 助手", "name": "AI 助手", "why": "依赖商品与知识库数据，无交易依赖，可并行"},
    {"code": "L", "domain": "全站规范", "name": "全站规范", "why": "弹窗/提示类横切用例，无数据依赖"},
]

_DOMAIN_TO_CHAIN = {c["domain"]: c for c in CHAINS}
_CHAIN_ORDER = {c["code"]: i for i, c in enumerate(CHAINS)}

_TITLE_HINTS: list[tuple[str, str]] = [
    ("登录", "A"), ("账号", "A"), ("个人资料", "F"),
    ("用户", "B"), ("角色", "B"), ("菜单", "B"), ("部门", "B"), ("字典", "B"), ("日志", "B"), ("会员", "B"),
    ("类目", "C"), ("品牌", "C"), ("属性", "C"), ("商品", "C"), ("上下架", "C"), ("文件", "C"), ("工作台", "C"),
    ("库存", "D"), ("仓库", "D"), ("出入库", "D"), ("定时上架", "C"),
    ("首页", "E"), ("站点", "E"), ("系统设置", "E"), ("交易配置", "E"), ("运营", "E"),
    ("购物车", "F"), ("地址", "F"), ("收藏", "F"), ("足迹", "F"),
    ("订单", "G"), ("交易", "G"), ("超时关单", "G"), ("发货", "G"),
    ("支付", "H"),
    ("售后", "I"),
    ("评价", "J"),
    ("AI", "K"),
    ("弹窗", "L"), ("提示", "L"), ("多端", "L"),
]


# ---------------------------------------------------------------- 数据装载
def _is_api(case: dict[str, Any]) -> bool:
    """能否交给接口引擎自动执行。relatedApi 必须形如 "METHOD /path"。"""
    kind = case.get("caseType") or ("api" if case.get("relatedApi") else "functional")
    related = (case.get("relatedApi") or "").strip()
    return kind == "api" and " " in related and related.split(" ", 1)[1].startswith("/")


def _verdict(case: dict[str, Any]) -> str:
    return ((case.get("lastRun") or {}).get("verdict") or "").strip()


def _is_delete(case: dict[str, Any]) -> bool:
    """删除类写操作：引擎默认跳过（保护演示数据），不能当普通接口用例排。"""
    return (case.get("relatedApi") or "").upper().startswith("DELETE ")


def _load(pid: str) -> tuple[list[dict[str, Any]], dict[str, dict[str, Any]]]:
    """返回（在册且关联需求的用例、需求元信息）。"""
    with SessionLocal() as db:
        rows = db.execute(
            text(
                """SELECT r.id, r.title, r.priority, r.status,
                          p.doc->'sections'->'docInfo'->>'domain' AS domain,
                          (p.doc->'sections'->'quality'->>'score')::int AS score
                   FROM requirements r
                   LEFT JOIN requirement_prd p
                          ON p.requirement_id = r.id AND p.project_id = r.project_id
                   WHERE r.project_id = :pid AND r.parent_id IS NULL"""
            ),
            {"pid": pid},
        ).all()

    reqs = {
        row[0]: {
            "id": row[0], "title": row[1], "priority": row[2] or "P1",
            "status": row[3] or "", "domain": row[4] or "", "score": row[5] or 0,
        }
        for row in rows
    }

    cases = [
        c for c in store.all("testCases", pid)
        if not c.get("archived") and c.get("requirementId") in reqs
    ]
    return cases, reqs


def _chain_of(req: dict[str, Any]) -> dict[str, Any]:
    """需求 → 业务链路。优先用 PRD 的 domain，缺失时按标题关键词兜底。"""
    chain = _DOMAIN_TO_CHAIN.get(req["domain"])
    if chain:
        return chain
    title = req["title"]
    for hint, code in _TITLE_HINTS:
        if hint in title:
            return next(c for c in CHAINS if c["code"] == code)
    return {"code": "Z", "domain": req["domain"] or "未分类", "name": "未分类", "why": "缺业务域标注，需产品补充"}


def _pick_smoke(cases: list[dict[str, Any]]) -> dict[str, Any] | None:
    """每个需求抽一条最「安全且能说明问题」的用例做冒烟。

    优先级：GET 正向 > 正向接口 > 任意接口用例。
    优先 GET 是为了让冒烟不写数据——冒烟失败时要能干净地停下来排查。
    DELETE 与上轮已失败的用例不进冒烟：前者必被跳过，后者一开跑就带红。
    """
    api = [
        c for c in cases
        if _is_api(c) and not _is_delete(c) and _verdict(c) not in FAIL_VERDICTS
    ]
    if not api:
        api = [c for c in cases if _is_api(c) and not _is_delete(c)]
    if not api:
        return None

    def rank(c: dict[str, Any]) -> tuple:
        related = (c.get("relatedApi") or "").upper()
        return (
            0 if c.get("type") == "正向" and related.startswith("GET ") else
            1 if c.get("type") == "正向" else 2,
            c.get("priority") != "P0",
            c.get("id", ""),
        )

    return sorted(api, key=rank)[0]


def _chunks(items: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [items[i:i + size] for i in range(0, len(items), size)] or []


# ---------------------------------------------------------------- 环境前置
def _probe_target() -> dict[str, Any]:
    """探活被测后端（shang-pivot 8086）。返回 401/405 也算可达——能应答就说明服务在。"""
    url = "http://127.0.0.1:8086/admin/login"
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            code = resp.status
    except urllib.error.HTTPError as exc:
        code = exc.code
    except Exception as exc:  # noqa: BLE001 连接拒绝/超时都走这里
        return {"reachable": False, "endpoint": url, "detail": str(exc)[:120]}
    return {
        "reachable": True, "endpoint": url, "detail": f"HTTP {code}（服务应答正常）",
        "expect": "管理端未带 token 返回 401，属预期",
    }


_BASELINE_TABLES = [
    ("SPU", "commerce.spu", "商品主数据，商品/交易用例的前置"),
    ("SKU", "commerce.sku", "库存与下单的最小单位"),
    ("库存", "commerce.stock", "库存扣减/回写用例的前置"),
    ("订单", 'commerce."order"', "存量偏大时列表用例需按时间窗过滤"),
    ("售后单", "commerce.after_sale", "售后用例需要至少一条可流转单据"),
    ("评价", "commerce.review", "评价展示/回复用例的前置"),
]


def _data_baseline() -> list[dict[str, Any]]:
    """被测库数据基线。连不上就返回空列表，不阻断计划编排。"""
    try:
        import psycopg  # 已有依赖（ui_batch_runner 在用）
    except Exception:  # noqa: BLE001
        return []
    import os

    dsn = os.getenv("REAL_DB_DSN", "postgresql://shang:shang@127.0.0.1:55434/shang")
    out: list[dict[str, Any]] = []
    try:
        with psycopg.connect(dsn, connect_timeout=3) as conn, conn.cursor() as cur:
            for name, table, note in _BASELINE_TABLES:
                try:
                    cur.execute(f"SELECT count(*) FROM {table}")
                    out.append({"name": name, "table": table, "count": int(cur.fetchone()[0]), "note": note})
                except Exception:  # noqa: BLE001 单表失败不影响其他表
                    conn.rollback()
    except Exception:  # noqa: BLE001
        return []
    return out


# ---------------------------------------------------------------- 计划编排
def _compose(pid: str) -> dict[str, Any]:
    """现算计划：返回 plan（对外）与 batch_cases（批次 → 用例对象，执行时复用）。"""
    cases, reqs = _load(pid)

    by_req: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for c in cases:
        by_req[c["requirementId"]].append(c)

    unverified: list[dict[str, Any]] = []
    for rid, req in reqs.items():
        own = by_req.get(rid, [])
        if any(_verdict(c) in PASS_VERDICTS for c in own):
            continue  # 已有用例执行通过，本轮不重复回归
        unverified.append({
            **req,
            "chain": _chain_of(req),
            "caseCount": len(own),
            "apiCount": sum(1 for c in own if _is_api(c)),
            "manualCount": sum(1 for c in own if not _is_api(c)),
            "knownFailed": sum(1 for c in own if _verdict(c) in FAIL_VERDICTS),
        })

    unverified.sort(key=lambda r: (
        r["priority"] != "P0",
        _CHAIN_ORDER.get(r["chain"]["code"], 99),
        -r["caseCount"],
        r["id"],
    ))

    # ---- B0 基线（无用例，人工 20 分钟）
    env_probe = _probe_target()
    baseline_rows = _data_baseline()
    batches: list[dict[str, Any]] = []
    cases_by_batch: dict[str, list[dict[str, Any]]] = {}

    batches.append({
        "id": "B0", "kind": "baseline", "track": "人工", "name": "环境与数据基线",
        "chain": "-", "domain": "全域", "requirements": [], "caseCount": 0,
        "apiCount": 0, "manualCount": 0, "estimatedMinutes": MIN_BASELINE,
        "dependsOn": [], "status": "待启动",
        "entry": "被测后端 8086 可达；管理端 admin/Admin@123 与 C 端 13800000001+123456 均能登录；种子数据满足基线表下限",
        "exit": "两项身份登录成功、基线表数据量记入执行记录；任一失败则暂停本轮回归",
        "checklist": [
            "探活 GET /admin/login 返回 401（服务在，只是没带 token）",
            "管理端登录换取 token，校验 /admin/me 返回角色",
            "C 端短信登录（演示验证码 123456），校验 /api/user/profile",
            "基线表数据量写入执行记录，订单表偏大时标记分页用例需时间窗过滤",
        ],
    })

    # ---- B1 冒烟：每个未验证需求抽 1 条接口用例
    smoke_pairs = [(r, _pick_smoke(by_req.get(r["id"], []))) for r in unverified]
    smoke_cases = [c for _, c in smoke_pairs if c]
    smoke_ids = {c["id"] for c in smoke_cases}
    smoke_reqs = [r for r, c in smoke_pairs if c]
    if smoke_cases:
        batches.append({
            "id": "B1", "kind": "smoke", "track": "自动化", "name": "冒烟基线（每需求 1 条正向接口）",
            "chain": "-", "domain": "全域",
            "requirements": [_req_brief(r) for r in smoke_reqs],
            "caseCount": len(smoke_cases), "apiCount": len(smoke_cases), "manualCount": 0,
            "estimatedMinutes": round(len(smoke_cases) * MIN_PER_SMOKE),
            "dependsOn": ["B0"], "status": "未开始",
            "entry": "B0 通过；每个需求至少抽出 1 条带 relatedApi 的用例",
            "exit": "冒烟通过率 ≥ 90%；出现整域失败先修环境再继续，不要把环境问题记成用例缺陷",
            "checklist": [],
        })
        cases_by_batch["B1"] = smoke_cases

    # ---- 自动化批次：按链路分组，剔除冒烟、已知失败与删除类写操作
    failed_cases = [c for r in unverified for c in by_req.get(r["id"], []) if _verdict(c) in FAIL_VERDICTS]
    failed_ids = {c["id"] for c in failed_cases}

    auto_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    delete_cases: list[dict[str, Any]] = []
    for r in unverified:
        for c in by_req.get(r["id"], []):
            if not _is_api(c) or c["id"] in smoke_ids or c["id"] in failed_ids:
                continue
            if _is_delete(c):
                delete_cases.append(c)   # 默认必被跳过，单独成批，执行时显式给 force
            else:
                auto_pool[r["chain"]["code"]].append(c)

    seq = 2
    prev_bid = ""
    for chain in sorted(CHAINS, key=lambda c: _CHAIN_ORDER[c["code"]]):
        pool = auto_pool.get(chain["code"]) or []
        if not pool:
            continue
        # P0 优先，同类内按用例编号稳定排序，保证每次生成的批次内容一致
        pool.sort(key=lambda c: (c.get("priority") != "P0", c.get("id", "")))
        for idx, chunk in enumerate(_chunks(pool, MAX_AUTO), start=1):
            bid = f"B{seq}"
            seq += 1
            req_ids = sorted({c["requirementId"] for c in chunk})
            batches.append({
                "id": bid, "kind": "auto", "track": "自动化",
                "name": f"{chain['name']}回归（{'第 %d 段' % idx if idx > 1 else '全量'}）",
                "chain": chain["code"], "domain": chain["domain"],
                "requirements": [_req_brief(r) for r in unverified if r["id"] in req_ids],
                "caseCount": len(chunk), "apiCount": len(chunk), "manualCount": 0,
                "estimatedMinutes": round(len(chunk) * MIN_PER_API),
                "dependsOn": ["B1"] + ([prev_bid] if prev_bid else []),
                "status": "未开始",
                "entry": f"{chain['name']}前置：{chain['why']}",
                "exit": "本批接口用例执行完成，失败用例已建缺陷单并标注可复现步骤",
                "checklist": [],
            })
            cases_by_batch[bid] = chunk
            prev_bid = bid

    # ---- 人工批次：functional 用例没有接口，只能按步骤核对
    manual_pool: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for r in unverified:
        for c in by_req.get(r["id"], []):
            if _is_api(c):
                continue
            manual_pool[r["chain"]["code"]].append(c)

    mseq = 1
    for chain in sorted(CHAINS, key=lambda c: _CHAIN_ORDER[c["code"]]):
        pool = manual_pool.get(chain["code"]) or []
        if not pool:
            continue
        pool.sort(key=lambda c: (c.get("priority") != "P0", c.get("id", "")))
        for chunk in _chunks(pool, MAX_MANUAL):
            bid = f"H{mseq}"
            mseq += 1
            req_ids = sorted({c["requirementId"] for c in chunk})
            batches.append({
                "id": bid, "kind": "manual", "track": "人工",
                "name": f"{chain['name']}人工核对",
                "chain": chain["code"], "domain": chain["domain"],
                "requirements": [_req_brief(r) for r in unverified if r["id"] in req_ids],
                "caseCount": len(chunk), "apiCount": 0, "manualCount": len(chunk),
                "estimatedMinutes": round(len(chunk) * MIN_PER_MANUAL),
                "dependsOn": ["B0"],
                "status": "未开始",
                "entry": "执行人持有对应角色账号；被测环境已由 B0 确认可用",
                "exit": "每条用例记录实际结果与截图证据；不符项进缺陷单",
                "checklist": [],
            })
            cases_by_batch[bid] = chunk

    # ---- R1 已知缺陷复测
    if failed_cases:
        batches.append({
            "id": "R1", "kind": "retest", "track": "自动化", "name": "已知缺陷复测",
            "chain": "-", "domain": "跨域",
            "requirements": [_req_brief(r) for r in unverified if r["knownFailed"]],
            "caseCount": len(failed_cases), "apiCount": sum(1 for c in failed_cases if _is_api(c)),
            "manualCount": sum(1 for c in failed_cases if not _is_api(c)),
            "estimatedMinutes": round(len(failed_cases) * MIN_PER_RETEST),
            "dependsOn": ["B1"], "status": "未开始",
            "entry": "对应缺陷单已标注修复版本；回归环境已部署该版本",
            "exit": "原判定「不符」的用例转「通过」；仍不符则升级缺陷等级",
            "checklist": [],
        })
        cases_by_batch["R1"] = failed_cases

    # ---- W1 删除类写操作（引擎默认跳过，必须显式 force）
    for n, chunk in enumerate(_chunks(sorted(delete_cases, key=lambda c: c.get("id", "")), MAX_AUTO), start=1):
        bid = f"W{n}"
        req_ids = sorted({c["requirementId"] for c in chunk})
        batches.append({
            "id": bid, "kind": "force", "track": "自动化",
            "name": "删除类写操作专项（需 force）",
            "chain": "-", "domain": "跨域",
            "requirements": [_req_brief(r) for r in unverified if r["id"] in req_ids],
            "caseCount": len(chunk), "apiCount": len(chunk), "manualCount": 0,
            "estimatedMinutes": round(len(chunk) * MIN_PER_API),
            "dependsOn": ["B1"], "status": "未开始",
            "needsForce": True,
            "entry": "演示库已快照（pg_dump commerce schema），或确认允许删除演示数据",
            "exit": "删除后校验：目标记录不存在、关联数据按规则级联或拒绝、日志留痕",
            "checklist": [
                "先跑非删除批次，避免删除数据导致后续用例前置失效",
                "执行时勾选「强制执行写操作」",
                "执行后核对数据量变化，异常则用快照恢复",
            ],
        })
        cases_by_batch[bid] = chunk

    # ---- V1 残留用例：需求已通过，但仍有用例从未执行（质量收敛，不影响覆盖率口径）
    verified_ids = set(reqs) - {r["id"] for r in unverified}
    residual = [c for c in cases if c["requirementId"] in verified_ids and not _verdict(c)]
    if residual:
        residual.sort(key=lambda c: (c.get("priority") != "P0", c.get("id", "")))
        batches.append({
            "id": "V1", "kind": "residual", "track": "自动化", "name": "已验证需求的残留用例",
            "chain": "-", "domain": "跨域",
            "requirements": [_req_brief({**reqs[i], "chain": _chain_of(reqs[i]),
                                         "caseCount": len(by_req.get(i, [])),
                                         "apiCount": sum(1 for c in by_req.get(i, []) if _is_api(c)),
                                         "manualCount": sum(1 for c in by_req.get(i, []) if not _is_api(c)),
                                         "knownFailed": 0}) for i in sorted(verified_ids)],
            "caseCount": len(residual),
            "apiCount": sum(1 for c in residual if _is_api(c)),
            "manualCount": sum(1 for c in residual if not _is_api(c)),
            "estimatedMinutes": round(
                sum(MIN_PER_API if _is_api(c) else MIN_PER_MANUAL for c in residual)),
            "dependsOn": ["B1"], "status": "未开始",
            "entry": "这些需求已有一条用例通过，需求级指标已达标；本批只做质量收敛",
            "exit": "残留用例执行完毕，避免「一条通过就代表整个需求没问题」的假象",
            "checklist": [],
        })
        cases_by_batch["V1"] = residual

    # ---- J1 人工裁定队列：引擎能发请求、但预期文本没有机器可判定条件
    # 这类用例跑完只会得到「已执行」，需求仍然不算验证通过，必须人看响应给结论。
    from .case_runner import parse_expectation

    def _judgeable(c: dict[str, Any]) -> bool:
        exp = parse_expectation(c.get("expected") or "")
        return exp["http"] is not None or exp["code"] is not None

    judge_cases = [
        c for r in unverified for c in by_req.get(r["id"], [])
        if _is_api(c) and not _is_delete(c) and c["id"] not in failed_ids and not _judgeable(c)
    ]
    for n, chunk in enumerate(_chunks(sorted(judge_cases, key=lambda c: c.get("id", "")), 60), start=1):
        bid = f"J{n}"
        req_ids = sorted({c["requirementId"] for c in chunk})
        batches.append({
            "id": bid, "kind": "judge", "track": "人工",
            "name": "判定条件补强：人工裁定接口结果",
            "chain": "-", "domain": "跨域",
            "requirements": [_req_brief(r) for r in unverified if r["id"] in req_ids],
            "caseCount": len(chunk), "apiCount": 0, "manualCount": len(chunk),
            "estimatedMinutes": round(len(chunk) * MIN_PER_JUDGE),
            "dependsOn": [b["id"] for b in batches if b["kind"] == "auto"][-1:] or ["B1"],
            "status": "未开始", "reuse": True,
            "entry": "对应用例已由接口引擎执行过（lastRun 有响应），执行人只需核对响应与预期文本",
            "exit": "每条用例记录「通过/不符」；仍无法判定的，把预期改写成可机读条件（HTTP 码或业务码）",
            "checklist": [
                "先看 lastRun.detail 与 http，再对照 expected 的业务语义",
                "结论写进该用例的人工执行记录，便于溯源",
                "高频模式（如「返回 401」）批量改写成可机读预期，下轮就能自动判",
            ],
        })
        cases_by_batch[bid] = chunk

    # ---- Z1 收口
    batches.append({
        "id": "Z1", "kind": "closeout", "track": "人工", "name": "收口：指标刷新与准出判定",
        "chain": "-", "domain": "全域", "requirements": [], "caseCount": 0,
        "apiCount": 0, "manualCount": 0, "estimatedMinutes": MIN_CLOSEOUT,
        "dependsOn": [b["id"] for b in batches if b["kind"] in {"auto", "manual", "retest"}],
        "status": "未开始",
        "entry": "全部自动化与人工批次执行完毕",
        "exit": "P0 需求 100% 有用例通过；整体验证覆盖率 ≥ 90%；S1/S2 缺陷清零或已挂起评审",
        "checklist": [
            "刷新「需求覆盖率」页，确认 verifiedCoverage 提升",
            "输出缺陷清单（按严重级/业务域）与遗留风险",
            "未通过用例逐条给出结论：缺陷 / 用例错 / 环境限制",
        ],
    })

    # ---- 进度回填（以用例 lastRun 为准，而非人工勾选）
    for b in batches:
        own = cases_by_batch.get(b["id"], [])
        executed = sum(1 for c in own if _verdict(c))
        passed = sum(1 for c in own if _verdict(c) in PASS_VERDICTS)
        skipped = sum(1 for c in own if _verdict(c) in SKIP_VERDICTS)
        failed = sum(1 for c in own if _verdict(c) in FAIL_VERDICTS)
        b["progress"] = {
            "executed": executed, "passed": passed, "failed": failed, "skipped": skipped,
            "remaining": len(own) - executed,
            "rate": round(executed / len(own), 3) if own else (1.0 if b["kind"] in {"baseline", "closeout"} else 0),
        }
        if b["kind"] == "baseline" and not env_probe["reachable"]:
            b["status"] = "环境不可达"
        elif b["kind"] in {"baseline", "closeout"}:
            b["status"] = "待人工"
        elif b["kind"] == "judge":
            b["status"] = "待裁定" if passed + failed == 0 else f"已裁定 {passed + failed}/{len(own)}"
        elif executed == 0:
            b["status"] = "未开始"
        elif failed:
            b["status"] = "有失败"
        elif executed < len(own):
            b["status"] = "进行中"
        else:
            b["status"] = "已完成"

    # ---- 汇总（judge 批次复用已执行结果，不与执行批次重复计数）
    api_total = sum(b["apiCount"] for b in batches)
    manual_total = sum(b["manualCount"] for b in batches)
    auto_minutes = sum(b["estimatedMinutes"] for b in batches if b["track"] == "自动化")
    manual_minutes = sum(b["estimatedMinutes"] for b in batches if b["track"] == "人工")
    unique_case_ids = {
        c["id"] for b in batches if b["kind"] != "judge" for c in cases_by_batch.get(b["id"], [])
    }
    judge_total = sum(b["caseCount"] for b in batches if b["kind"] == "judge")

    plan = {
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "projectId": pid,
        "version": "v1",
        "objective": {
            "from": {
                "requirements": len(reqs),
                "unverified": len(unverified),
                "verifiedRate": round((len(reqs) - len(unverified)) / len(reqs), 3) if reqs else 0,
                "cases": len(cases),
                "executed": sum(1 for c in cases if _verdict(c)),
                "p0": sum(1 for r in reqs.values() if r["priority"] == "P0"),
                "p0Unverified": sum(1 for r in unverified if r["priority"] == "P0"),
            },
            "target": {
                "verifiedRequirements": max(1, round(len(unverified) * 0.9)),
                "verifiedRate": 0.9,
                "p0Rate": 1.0,
                "s1Open": 0,
            },
            "statement": (
                f"用 {len([b for b in batches if b['kind'] not in {'baseline', 'closeout'}])} 个执行批次，"
                f"跑完 {len(cases)} 条在册用例（其中 {len(unverified)} 条需求尚无一条用例通过），"
                f"使需求验证覆盖率从 {round((len(reqs) - len(unverified)) / max(len(reqs), 1) * 100, 1)}% "
                f"提升到 ≥ 90%，P0 需求全部有用例通过。"
            ),
        },
        "environment": {
            "target": env_probe,
            "dataBaseline": baseline_rows,
            "identities": [
                {"role": "管理端", "account": "admin / Admin@123", "scope": "/admin/**"},
                {"role": "C 端", "account": "13800000001 + 验证码 123456", "scope": "/api/**"},
            ],
            "executor": "HTTP 用例引擎（backend/app/case_runner.py，单实例串行）",
        },
        "scope": {
            "requirementTotal": len(reqs),
            "unverifiedRequirements": len(unverified),
            "caseTotal": len(cases),
            "apiCases": sum(1 for c in cases if _is_api(c)),
            "manualCases": sum(1 for c in cases if not _is_api(c)),
            "smokeCases": len(smoke_cases),
            "knownFailed": len(failed_cases),
            "deleteCases": len(delete_cases),
            "residualCases": len(residual),
            "unjudgeableCases": len(judge_cases),
            "concurrencyCases": sum(1 for c in cases if c.get("type") == "并发幂等"),
            "autoMinutes": auto_minutes,
            "manualMinutes": manual_minutes,
        },
        "chains": [
            {
                "code": c["code"], "domain": c["domain"], "name": c["name"], "why": c["why"],
                "requirements": sum(1 for r in unverified if r["chain"]["code"] == c["code"]),
                "cases": sum(1 for r in unverified if r["chain"]["code"] == c["code"] for _ in by_req.get(r["id"], [])),
            }
            for c in CHAINS
        ],
        "batches": batches,
        "totals": {
            "batches": len(batches),
            "execBatches": sum(1 for b in batches if b["kind"] not in {"baseline", "closeout"}),
            "autoBatches": sum(1 for b in batches if b["track"] == "自动化"),
            "manualBatches": sum(1 for b in batches if b["track"] == "人工"),
            "uniqueCases": len(unique_case_ids),
            "judgeCases": judge_total,
            "estimatedMinutes": auto_minutes + manual_minutes,
            "estimatedHours": round((auto_minutes + manual_minutes) / 60, 1),
            "criticalPathHours": round(auto_minutes / 60, 1),
        },
        "schedule": _schedule(batches),
        "exitCriteria": [
            {"item": "P0 需求验证", "target": "100% 有用例执行通过", "measure": "需求覆盖率页 byPriority.P0.verified == total"},
            {"item": "整体验证覆盖率", "target": "≥ 90%", "measure": "GET /api/v1/prd/coverage → verifiedCoverage"},
            {"item": "AC 断言命中", "target": "保持 ≥ 95%", "measure": "coverage.acAnchorRate"},
            {"item": "缺陷", "target": "S1/S2 为 0，S3 有明确排期", "measure": "缺陷清单评审"},
            {"item": "结果可追溯", "target": "每条未通过用例有结论文本", "measure": "用例 lastRun.detail 非空"},
        ],
        "risks": [
            {
                "risk": f"{len(judge_cases)} 条接口用例的预期是业务语义描述（如「状态变为 FROZEN」「仅返回必要字段」），"
                        f"引擎只能发请求、无法自动判定",
                "impact": "跑完只会记「已执行」，需求仍不算验证通过；不处理则验证覆盖率卡在 40% 上下",
                "mitigation": "单列 J 批次人工裁定；把「返回 401」「状态变为 X」这类高频模式改写成可机读预期，下轮自动判",
            },
            {
                "risk": f"被测后端单实例（8086），{sum(1 for c in cases if _is_api(c))} 条接口用例只能串行跑",
                "impact": "全量接口回归约需 %.1f 小时机器时间" % (sum(1 for c in cases if _is_api(c)) * MIN_PER_API / 60),
                "mitigation": "批次间不并行；单批 ≤ 100 条，失败即停可定位；并发/幂等类用例移到压测环境",
            },
            {
                "risk": f"{sum(1 for c in cases if (c.get('relatedApi') or '').upper().startswith('DELETE '))} 条 DELETE 写操作用例默认跳过（保护演示数据）",
                "impact": "删除类功能本轮无自动化结论，只能人工核对",
                "mitigation": "执行时按需勾选 force，或先对 commerce 库做快照再放开",
            },
            {
                "risk": f"{sum(1 for c in cases if not _is_api(c))} 条 functional 用例没有被测接口",
                "impact": "人工工时占总量 %.0f%%，是回归周期的主要瓶颈" % (
                    manual_minutes / max(auto_minutes + manual_minutes, 1) * 100),
                "mitigation": "按业务域拆给不同执行人并行；优先只跑 P0/P1 正向步骤",
            },
            {
                "risk": "交易/支付用例会真实下单，污染演示数据",
                "impact": "订单表继续膨胀，列表用例变慢甚至超时",
                "mitigation": "执行前记录订单表水位；执行后按 id 区间清理测试单；列表用例带时间窗参数",
            },
            {
                "risk": "固定验证码 123456 无环境开关（见需求整改报告漏洞 #1）",
                "impact": "安全类用例会稳定判定「不符」，拉低通过率但不代表环境坏了",
                "mitigation": "本轮记为已知缺陷，不重复提单；修复后进 R1 复测",
            },
        ],
    }
    return {"plan": plan, "batch_cases": cases_by_batch, "requirements": unverified}


def _req_brief(r: dict[str, Any]) -> dict[str, Any]:
    return {
        "id": r["id"], "title": r["title"], "priority": r["priority"],
        "domain": r["chain"]["domain"], "chain": r["chain"]["code"],
        "caseCount": r["caseCount"], "apiCount": r["apiCount"],
        "manualCount": r["manualCount"], "knownFailed": r["knownFailed"],
    }


def _next_workday(start: date) -> date:
    cur = start
    while cur.weekday() >= 5:
        cur += timedelta(days=1)
    return cur


def _schedule(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """双轨排期：自动化与人工各按每日容量顺排，同一天并行推进。

    约束：J（人工裁定）必须等接口用例跑过才有响应可看，因此不早于自动化的最后一天开始；
    其余人工批次（基线/核对）从第一天起就能并行。
    """
    weekdays = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
    auto = [b for b in batches if b["track"] == "自动化"]
    manual = [b for b in batches if b["track"] == "人工" and b["kind"] not in {"judge", "closeout"}]
    judge = [b for b in batches if b["kind"] == "judge"]

    days: list[dict[str, Any]] = []
    closeout = [b for b in batches if b["kind"] == "closeout"]

    def ensure(idx: int) -> dict[str, Any]:
        while len(days) <= idx:
            cursor = _next_workday(date.today() + timedelta(days=1 + len(days)))
            days.append({
                "day": f"D{len(days) + 1}", "date": cursor.isoformat(),
                "weekday": weekdays[cursor.weekday()],
                "autoBatches": [], "manualBatches": [], "autoMinutes": 0, "manualMinutes": 0,
            })
        return days[idx]

    # 自动化轨道
    di = ai = 0
    while ai < len(auto):
        day = ensure(di)
        while ai < len(auto) and (day["autoMinutes"] + auto[ai]["estimatedMinutes"] <= DAY_AUTO_CAP
                                  or not day["autoBatches"]):
            day["autoBatches"].append(auto[ai]["id"])
            day["autoMinutes"] += auto[ai]["estimatedMinutes"]
            ai += 1
        di += 1
    auto_days = len(days)
    judge_start = max(0, auto_days - 1)

    # 人工轨道（H 从 D1 起，J 等接口跑过）
    di = mi = ji = 0
    while mi < len(manual) or ji < len(judge):
        day = ensure(di)
        while mi < len(manual) and (day["manualMinutes"] + manual[mi]["estimatedMinutes"] <= DAY_MANUAL_CAP
                                    or not day["manualBatches"]):
            day["manualBatches"].append(manual[mi]["id"])
            day["manualMinutes"] += manual[mi]["estimatedMinutes"]
            mi += 1
        if di >= judge_start:
            while ji < len(judge) and (day["manualMinutes"] + judge[ji]["estimatedMinutes"] <= DAY_MANUAL_CAP
                                       or not day["manualBatches"]):
                day["manualBatches"].append(judge[ji]["id"])
                day["manualMinutes"] += judge[ji]["estimatedMinutes"]
                ji += 1
        di += 1
        if di > 20:  # 防御：容量为 0 时不至于死循环
            break

    for d in days:
        d["note"] = (
            "自动化轨道可无人值守（建议下班后启动），人工轨道同时推进"
            if d["autoBatches"] and d["manualBatches"] else
            "仅自动化" if d["autoBatches"] else "仅人工"
        )

    # 收口永远压在最后一天：它要读全量结果才能判定准出
    if closeout:
        last = ensure(len(days) - 1 if days else 0)
        last["manualBatches"].extend(b["id"] for b in closeout)
        last["manualMinutes"] += sum(b["estimatedMinutes"] for b in closeout)
        last["note"] = (last["note"] + "；含收口评审") if last["note"] else "收口评审"
    return days


def build_plan(pid: str) -> dict[str, Any]:
    return _compose(pid)["plan"]


def batch_case_preview(pid: str, batch_id: str, limit: int = 60) -> dict[str, Any]:
    """批次内用例明细（给前端展开用）。"""
    composed = _compose(pid)
    plan = composed["plan"]
    batch = next((b for b in plan["batches"] if b["id"] == batch_id), None)
    if not batch:
        raise KeyError(batch_id)
    own = composed["batch_cases"].get(batch_id, [])
    items = [{
        "id": c.get("id"), "title": c.get("title"), "priority": c.get("priority"),
        "type": c.get("type"), "caseType": "api" if _is_api(c) else "functional",
        "relatedApi": c.get("relatedApi") or "", "requirementId": c.get("requirementId"),
        "verdict": _verdict(c) or "未执行",
        "at": (c.get("lastRun") or {}).get("at") or "",
    } for c in own[:limit]]
    return {"batch": {k: v for k, v in batch.items() if k != "requirements"}, "items": items,
            "total": len(own), "truncated": len(own) > limit}


# ---------------------------------------------------------------- 批次执行
JOBS: dict[str, dict[str, Any]] = {}
_LOCK = threading.Lock()
_RUNNING: dict[str, str] = {}  # project_id → job_id（同项目同时只允许一个批次在跑）


def _schema_lookup(pid: str):
    """给用例引擎补请求体 schema（等价于单条执行接口的行为）。"""
    from sqlalchemy import select

    from .trace_models import TraceApi

    def lookup(path: str, method: str) -> dict[str, Any] | None:
        with SessionLocal() as db:
            row = db.scalar(
                select(TraceApi).where(
                    TraceApi.project_id == pid, TraceApi.path == path, TraceApi.method == method)
            )
            return (row.request_schema or None) if row else None

    return lookup


def _run_job(job_id: str, pid: str, batch_id: str, cases: list[dict[str, Any]],
             force: bool, delay_ms: int) -> None:
    from .case_runner import run_case

    lookup = _schema_lookup(pid)
    job = JOBS[job_id]
    try:
        for case in cases:
            case_id = case.get("id")
            job["current"] = {"caseId": case_id, "title": case.get("title")}
            try:
                report = run_case(case, schema_lookup=lookup, force=force)
                verdict = report.get("verdict") or "无法执行"
                detail = report.get("detail") or ""
                http = (report.get("actual") or {}).get("http")
            except Exception as exc:  # noqa: BLE001 单条异常不终止整批
                verdict, detail, http = "无法执行", f"执行异常：{exc}"[:300], None

            fresh = store.get("testCases", case_id, pid) or case
            fresh["lastRun"] = {
                "at": now_label(), "mode": "api", "verdict": verdict,
                "detail": detail, "http": http, "batch": batch_id,
            }
            store.put("testCases", case_id, fresh)

            with _LOCK:
                job["done"] += 1
                if verdict in PASS_VERDICTS:
                    job["passed"] += 1
                elif verdict in SKIP_VERDICTS:
                    job["skipped"] += 1   # 跑过但无判定条件/被跳过，不算失败
                else:
                    job["failed"] += 1
                job["results"].append({
                    "caseId": case_id, "title": case.get("title") or "",
                    "verdict": verdict, "detail": detail[:200], "http": http,
                })
            if delay_ms:
                time.sleep(delay_ms / 1000)
        job["status"] = "done"
    except Exception as exc:  # noqa: BLE001
        job["status"] = "failed"
        job["error"] = str(exc)[:300]
    finally:
        job["finishedAt"] = now_label()
        job["current"] = None
        with _LOCK:
            if _RUNNING.get(pid) == job_id:
                _RUNNING.pop(pid, None)


def start_batch(pid: str, batch_id: str, limit: int = 0, force: bool = False,
                delay_ms: int = 50) -> dict[str, Any]:
    """启动一个批次的接口用例执行（后台线程，前端轮询进度）。"""
    composed = _compose(pid)
    batch = next((b for b in composed["plan"]["batches"] if b["id"] == batch_id), None)
    if not batch:
        raise KeyError(batch_id)
    if batch["kind"] == "judge":
        raise ValueError("该批次是人工裁定队列：用例已由引擎执行过，请在用例详情里记录结论")
    own = [c for c in composed["batch_cases"].get(batch_id, []) if _is_api(c)]
    if limit > 0:
        own = own[:limit]
    if not own:
        raise ValueError("该批次没有可自动执行的接口用例，请按「人工执行」清单核对步骤")

    with _LOCK:
        running = _RUNNING.get(pid)
        if running and JOBS.get(running, {}).get("status") == "running":
            raise RuntimeError(f"已有批次在执行（{running}），单实例环境请等它跑完")
        job_id = f"RG-{int(time.time() * 1000) % 10 ** 9}"
        JOBS[job_id] = {
            "jobId": job_id, "projectId": pid, "batchId": batch_id,
            "status": "running", "total": len(own), "done": 0, "passed": 0, "failed": 0, "skipped": 0,
            "results": [], "current": None, "startedAt": now_label(), "finishedAt": "",
            "force": force,
        }
        _RUNNING[pid] = job_id

    threading.Thread(
        target=_run_job, args=(job_id, pid, batch_id, own, force, delay_ms), daemon=True
    ).start()
    return {"jobId": job_id, "batchId": batch_id, "total": len(own), "status": "running"}


def job_status(job_id: str) -> dict[str, Any] | None:
    job = JOBS.get(job_id)
    if not job:
        return None
    out = {k: v for k, v in job.items() if k != "results"}
    out["results"] = job["results"][-60:]
    out["rate"] = round(job["done"] / job["total"], 3) if job["total"] else 0
    return out
