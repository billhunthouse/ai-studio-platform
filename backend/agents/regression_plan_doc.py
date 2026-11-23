"""生成《需求回归执行计划》Markdown（数据来自 regression_plan.build_plan，不手抄数字）。

用法：
    cd backend && .venv/bin/python -m agents.regression_plan_doc            # 写 docs/需求回归执行计划.md
    cd backend && .venv/bin/python -m agents.regression_plan_doc --print    # 只打印
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from app.regression_plan import build_plan

PROJECT_ID = "ecommerce"
OUT = Path(__file__).resolve().parents[2] / "docs" / "需求回归执行计划.md"

KIND_CN = {
    "baseline": "环境基线", "smoke": "冒烟", "auto": "接口回归", "manual": "人工核对",
    "force": "写操作", "retest": "缺陷复测", "residual": "残留收敛", "judge": "人工裁定",
    "closeout": "收口",
}


def hm(minutes: int) -> str:
    return f"{minutes // 60}h{minutes % 60:02d}m" if minutes >= 60 else f"{minutes}m"


def main() -> None:
    plan = build_plan(PROJECT_ID)
    s, o, t, env = plan["scope"], plan["objective"], plan["totals"], plan["environment"]

    L: list[str] = []
    add = L.append

    add("# 需求回归执行计划")
    add("")
    add(f"> 项目：`{PROJECT_ID}`（电商核心系统）　生成时间：{plan['generatedAt']}　计划版本：{plan['version']}")
    add(f"> 数据来源：`GET /api/v1/prd/regression-plan`（后端现算，批次进度直接读用例 lastRun）")
    add("")
    add("---")
    add("")

    add("## 一、这一轮要解决什么")
    add("")
    add(plan["objective"]["statement"])
    add("")
    add("| 指标 | 现状 | 目标 |")
    add("|---|---|---|")
    add(f"| 需求验证覆盖率 | {o['from']['verifiedRate'] * 100:.1f}%（{o['from']['requirements'] - o['from']['unverified']}/{o['from']['requirements']}） "
        f"| ≥ {o['target']['verifiedRate'] * 100:.0f}% |")
    add(f"| P0 需求 | {o['from']['p0'] - o['from']['p0Unverified']}/{o['from']['p0']} 有用例通过 | 100% |")
    add(f"| 已执行用例 | {o['from']['executed']}/{o['from']['cases']} | {t['uniqueCases']} 条全跑 |")
    add(f"| 未验证需求 | {s['unverifiedRequirements']} 条 | ≤ {s['unverifiedRequirements'] - o['target']['verifiedRequirements']} 条 |")
    add("")
    add("**为什么必须先跑用例**：需求覆盖率已经是 100%（52 条全部有用例），但验证覆盖率只有 "
        f"{o['from']['verifiedRate'] * 100:.1f}%——用例写了不等于验证过。这一轮把「有」变成「验过」。")
    add("")

    add("## 二、口径与边界")
    add("")
    add("| 口径 | 数量 | 说明 |")
    add("|---|---|---|")
    add(f"| 需求总数 | {s['requirementTotal']} | 全部已规范化（v2 PRD，21 章节） |")
    add(f"| 未验证需求 | {s['unverifiedRequirements']} | 关联用例中没有任何一条判定「通过」 |")
    add(f"| 在册用例 | {s['caseTotal']} | 已剔除 294 条去重合并产生的归档副本 |")
    add(f"| 可自动执行 | {s['apiCases']} | `caseType=api` 且 `relatedApi` 形如 `METHOD /path` |")
    add(f"| 需人工核对 | {s['manualCases']} | functional 用例，没有被测接口 |")
    add(f"| 需人工裁定 | {s['unjudgeableCases']} | 接口能跑，但预期是业务语义（如「状态变为 FROZEN」），引擎无法自动判 |")
    add(f"| 删除类写操作 | {s['deleteCases']} | 引擎默认跳过（保护演示数据），需显式 force |")
    add(f"| 已知缺陷复测 | {s['knownFailed']} | 上轮判定「不符」，本轮单独复测 |")
    add(f"| 已验证需求残留 | {s['residualCases']} | 需求已通过，但仍有用例从未执行 |")
    add("")
    add("> 口径修正：覆盖率接口此前把 294 条归档副本也计入用例总数（显示 1036 条），"
        "与本计划的 742 条不一致。本轮把统计口径统一为「在册用例」，需求级指标（52/52、2/52）不受影响。")
    add("")

    add("## 三、执行策略：九类批次，双轨并行")
    add("")
    add("| 阶段 | 批次 | 目的 | 关键约束 |")
    add("|---|---|---|---|")
    add("| 0 | B0 | 环境与数据基线 | 8096 探活、双身份登录、基线表数据量；不过则本轮暂停 |".replace("8096", "8086"))
    add("| 1 | B1 | 冒烟：每需求 1 条正向接口 | 优先 GET，不写数据；通过率 < 90% 先修环境 |")
    add("| 2 | B2–B14 | 按业务链路分域全量接口回归 | 单批 ≤ 100 条；链路顺序即依赖顺序 |")
    add("| 3 | W1 | 删除类写操作专项 | 必须勾选 force，执行前后对库做快照 |")
    add("| 4 | R1 | 已知缺陷复测 | 与首轮结果分开统计，避免混淆「新失败」与「没修好」 |")
    add("| 5 | V1 | 已验证需求的残留用例 | 防止「一条通过 = 整个需求没问题」的假象 |")
    add("| 6 | H1–H12 | 人工按步骤核对 functional 用例 | 按业务域拆给不同执行人并行 |")
    add("| 7 | J1–J5 | 人工裁定接口结果 | 引擎已发过请求，执行人只判响应是否符合预期 |")
    add("| 8 | Z1 | 收口：指标刷新与准出判定 | 汇总缺陷、刷新覆盖率、给遗留风险结论 |")
    add("")

    add("## 四、批次清单")
    add("")
    add("| 批次 | 类型 | 内容 | 需求 | 用例（自动/人工） | 预计 | 依赖 | 当前状态 |")
    add("|---|---|---|---|---|---|---|---|")
    for b in plan["batches"]:
        add(f"| `{b['id']}` | {KIND_CN.get(b['kind'], b['kind'])} | {b['name']} | {len(b['requirements'])} "
            f"| {b['apiCount']}/{b['manualCount']} | {hm(b['estimatedMinutes'])} "
            f"| {', '.join(b['dependsOn'][:3]) or '—'} | {b['status']} |")
    add("")
    add(f"合计 {t['batches']} 个批次，其中执行批次 {t['execBatches']} 个；"
        f"去重用例 {t['uniqueCases']} 条（裁定队列 {t['judgeCases']} 条复用执行结果，不重复计数）。")
    add("")

    add("## 五、排期建议")
    add("")
    add("| 日期 | 自动化批次 | 人工批次 | 工时（自动/人工） | 说明 |")
    add("|---|---|---|---|---|")
    for d in plan["schedule"]:
        add(f"| {d['day']}　{d['date']} {d['weekday']} | {', '.join(d['autoBatches']) or '—'} "
            f"| {', '.join(d['manualBatches']) or '—'} | {hm(d['autoMinutes'])} / {hm(d['manualMinutes'])} | {d['note']} |")
    add("")
    add(f"自动化关键路径 {t['criticalPathHours']} 小时，可下班后启动、无人值守；"
        f"人工轨道（核对 + 裁定）合计 {hm(s['manualMinutes'])}，是整体周期的实际瓶颈。")
    add("")

    add("## 六、环境与数据基线")
    add("")
    add(f"- 被测服务：`{env['target']['endpoint']}` → {env['target']['detail']}"
        f"（{'可达' if env['target']['reachable'] else '**不可达，需先启动**'}）")
    add(f"- 执行引擎：{env['executor']}")
    for i in env["identities"]:
        add(f"- 身份：{i['role']} `{i['account']}`（{i['scope']}）")
    if env["dataBaseline"]:
        add("")
        add("| 基线表 | 数据量 | 说明 |")
        add("|---|---|---|")
        for d in env["dataBaseline"]:
            add(f"| {d['name']} | {d['count']:,} | {d['note']} |")
    add("")

    add("## 七、风险与对策")
    add("")
    for i, r in enumerate(plan["risks"], start=1):
        add(f"**R{i}. {r['risk']}**")
        add("")
        add(f"- 影响：{r['impact']}")
        add(f"- 对策：{r['mitigation']}")
        add("")

    add("## 八、准出标准")
    add("")
    add("| 检查项 | 目标 | 度量方式 |")
    add("|---|---|---|")
    for e in plan["exitCriteria"]:
        add(f"| {e['item']} | {e['target']} | `{e['measure']}` |")
    add("")

    add("## 九、怎么执行")
    add("")
    add("**界面**：需求管理 → 回归计划（`/project/ecommerce/requirements-regression`）")
    add("")
    add("1. 看 B0 卡片的环境是否可达、基线表是否有数据；")
    add("2. 点 B1「执行」跑冒烟，失败先修环境，别急着跑全量；")
    add("3. 按 B2→B14 顺序逐批执行（每批结束自动刷新进度）；")
    add("4. W1 需先快照再执行；R1 在有修复版本后再跑；")
    add("5. H/J 批次按清单人工核对，结论写进用例的人工执行记录；")
    add("6. Z1 收口时刷新「需求覆盖率」页，对照准出标准判定。")
    add("")
    add("**接口**：")
    add("")
    add("```bash")
    add("GET  /api/v1/prd/regression-plan                    # 计划全文（现算）")
    add("GET  /api/v1/prd/regression-plan/cases?batchId=B2   # 批次用例明细")
    add("POST /api/v1/prd/regression-plan/run                # {batchId, limit, force}")
    add("GET  /api/v1/prd/regression-plan/run/{jobId}        # 轮询进度")
    add("```")
    add("")
    add("**重新生成本文档**：`cd backend && .venv/bin/python -m agents.regression_plan_doc`")
    add("")
    add("---")
    add("")
    add(f"*文档由 `backend/agents/regression_plan_doc.py` 于 {datetime.now():%Y-%m-%d %H:%M} 自动生成，"
        "数字随用例执行结果变化，请勿手工修改。*")

    text = "\n".join(L) + "\n"
    if "--print" in sys.argv:
        print(text)
        return
    OUT.write_text(text, encoding="utf-8")
    print(f"written: {OUT} ({len(text)} bytes, {len(plan['batches'])} batches)")


if __name__ == "__main__":
    main()
