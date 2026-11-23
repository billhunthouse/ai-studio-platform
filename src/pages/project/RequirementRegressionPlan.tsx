/** 需求回归执行计划：把「已覆盖但未验证」的需求编排成可执行批次，并支持按批发起真实接口执行。 */

import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { prdApi } from "@/api";
import type { PlanBatch, PlanCase, PlanJob, PrdRegressionPlan } from "@/api/prd";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Icon, Progress, Stat, Table, Tag } from "@/components/ui";
import type { Tone } from "@/components/ui";
import { cx } from "@/lib/cx";

const KIND_CN: Record<string, string> = {
  baseline: "环境基线", smoke: "冒烟", auto: "接口回归", manual: "人工核对",
  force: "写操作", retest: "缺陷复测", residual: "残留收敛", judge: "人工裁定", closeout: "收口",
};

const KIND_TONE: Record<string, Tone> = {
  baseline: "gray", smoke: "blue", auto: "blue", manual: "amber",
  force: "red", retest: "red", residual: "gray", judge: "amber", closeout: "green",
};

const STATUS_TONE: Record<string, Tone> = {
  已完成: "green", 有失败: "red", 进行中: "blue", 未开始: "gray",
  待人工: "amber", 待裁定: "amber", 环境不可达: "red",
};

const toneOf = (s: string): Tone => STATUS_TONE[s] ?? (s.startsWith("已裁定") ? "green" : "gray");

const FILTERS = ["全部", "自动化", "人工", "未开始", "有失败", "已完成"] as const;

function hours(minutes: number) {
  if (minutes < 60) return `${minutes}m`;
  const h = Math.floor(minutes / 60);
  const m = minutes % 60;
  return m ? `${h}h${m}m` : `${h}h`;
}

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

export function RequirementRegressionPlan() {
  const { projectId, toast } = useApp();
  const navigate = useNavigate();
  const { data: plan, loading, reload } = useAsync<PrdRegressionPlan | null>(
    () => prdApi.regressionPlan().then((r) => r ?? null).catch(() => null), [projectId], null);

  const [filter, setFilter] = useState<string>("全部");
  const [selected, setSelected] = useState<string | null>(null);
  const [cases, setCases] = useState<{ total: number; items: PlanCase[]; truncated: boolean } | null>(null);
  const [casesLoading, setCasesLoading] = useState(false);
  const [job, setJob] = useState<PlanJob | null>(null);
  const [starting, setStarting] = useState<string | null>(null);
  const [tick, setTick] = useState(0);

  // 默认选中第一个「未开始」的自动化批次，省一次点击
  useEffect(() => {
    if (!plan || selected) return;
    const first = plan.batches.find((b) => b.kind === "auto");
    setSelected(first?.id ?? plan.batches[0]?.id ?? null);
  }, [plan, selected]);

  // 批次明细按需拉取（计划接口不带用例明细，避免首屏过大）
  useEffect(() => {
    if (!selected) { setCases(null); return; }
    let alive = true;
    setCasesLoading(true);
    prdApi.planCases(selected, 60)
      .then((r) => { if (alive) setCases(r); })
      .catch(() => { if (alive) setCases(null); })
      .finally(() => { if (alive) setCasesLoading(false); });
    return () => { alive = false; };
  }, [selected, tick]);

  // 执行中轮询；结束后刷新计划与明细，让进度回到真实状态
  useEffect(() => {
    if (!job || job.status !== "running") return;
    const timer = window.setInterval(() => {
      prdApi.planJob(job.jobId)
        .then((next) => {
          setJob(next);
          if (next.status !== "running") {
            setTick((v) => v + 1);
            reload();
            toast(`批次 ${next.batchId} 执行完成：通过 ${next.passed} / ${next.total}`);
          }
        })
        .catch(() => undefined);
    }, 1500);
    return () => window.clearInterval(timer);
  }, [job?.jobId, job?.status, reload, toast]);

  const visible = useMemo(() => {
    if (!plan) return [];
    return plan.batches.filter((b) => {
      if (filter === "全部") return true;
      if (filter === "自动化") return b.track === "自动化";
      if (filter === "人工") return b.track === "人工";
      if (filter === "未开始") return b.status === "未开始";
      if (filter === "有失败") return b.status === "有失败";
      if (filter === "已完成") return b.status === "已完成";
      return true;
    });
  }, [plan, filter]);

  const selectedBatch = plan?.batches.find((b) => b.id === selected) ?? null;
  const running = job?.status === "running";

  async function runBatch(batch: PlanBatch) {
    setStarting(batch.id);
    try {
      const r = await prdApi.runPlanBatch(batch.id, 0, Boolean(batch.needsForce));
      toast(`已启动 ${batch.id}：${r.total} 条接口用例`);
      setJob({
        jobId: r.jobId, batchId: batch.id, status: "running", total: r.total, done: 0,
        passed: 0, failed: 0, skipped: 0, current: null, startedAt: "", finishedAt: "", rate: 0, results: [],
      });
    } catch (e) {
      toast(e instanceof Error ? e.message : "启动失败");
    } finally {
      setStarting(null);
    }
  }

  if (loading && !plan) {
    return <div className="grid h-40 place-items-center text-xs text-ink-500">正在编排回归计划…</div>;
  }
  if (!plan) {
    return (
      <Card>
        <div className="py-10 text-center text-[12px] text-ink-500">
          计划生成失败。请确认需求已规范化（有 PRD 业务域）且用例已关联需求编号。
        </div>
      </Card>
    );
  }

  const s = plan.scope;
  const t = plan.totals;
  const env = plan.environment;

  return (
    <div className="space-y-4">
      {/* 目标 & 关键数字 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="待回归需求"
          value={`${s.unverifiedRequirements}`}
          hint={`共 ${s.requirementTotal} 条，其中 ${s.unverifiedRequirements} 条没有一条用例通过`}
          icon={<Icon name="clipboard" size={16} />}
        />
        <Stat
          label="待执行用例"
          value={`${t.uniqueCases}`}
          hint={`接口 ${s.apiCases} 条可自动跑，${s.manualCases} 条只能人工核对`}
          icon={<Icon name="play" size={16} />}
        />
        <Stat
          label="预计工时"
          value={hours(t.estimatedMinutes)}
          hint={`自动化关键路径 ${t.criticalPathHours}h，可无人值守`}
          icon={<Icon name="activity" size={16} />}
        />
        <Stat
          label="执行批次"
          value={`${t.execBatches}`}
          hint={`自动化 ${t.autoBatches} 批 / 人工 ${t.manualBatches} 批，单批 ≤ 100 条`}
          icon={<Icon name="filter" size={16} />}
        />
      </div>

      <Card title="本轮目标" extra={<span className="text-[10px] text-ink-400">生成于 {plan.generatedAt}</span>}>
        <p className="text-[13px] leading-6 text-ink-800">{plan.objective.statement}</p>
        <div className="mt-3 grid gap-2 sm:grid-cols-3">
          {[
            { k: "验证覆盖率", from: pct(plan.objective.from.verifiedRate), to: `≥ ${pct(plan.objective.target.verifiedRate)}` },
            { k: "P0 需求", from: `${plan.objective.from.p0 - plan.objective.from.p0Unverified} / ${plan.objective.from.p0}`, to: "100% 有用例通过" },
            { k: "已执行用例", from: `${plan.objective.from.executed} / ${plan.objective.from.cases}`, to: `${t.uniqueCases} 条全跑` },
          ].map((x) => (
            <div key={x.k} className="rounded-lg border border-line bg-ink-50/40 px-3 py-2">
              <div className="text-[10px] text-ink-500">{x.k}</div>
              <div className="mt-1 flex items-center gap-1.5 text-[12px]">
                <span className="tabular-nums text-ink-500 line-through decoration-ink-300">{x.from}</span>
                <Icon name="activity" size={11} className="text-brand-500" />
                <span className="font-semibold text-ink-900">{x.to}</span>
              </div>
            </div>
          ))}
        </div>
        <div className="mt-3 flex flex-wrap gap-2 text-[11px]">
          <Tag t={`人工裁定 ${s.unjudgeableCases} 条`} c="amber" dot={false} />
          <Tag t={`删除类写操作 ${s.deleteCases} 条需 force`} c="red" dot={false} />
          <Tag t={`已知缺陷复测 ${s.knownFailed} 条`} c="red" dot={false} />
          <Tag t={`已验证需求残留 ${s.residualCases} 条`} c="gray" dot={false} />
          <Tag t={`并发幂等 ${s.concurrencyCases} 条（建议压测环境）`} c="gray" dot={false} />
        </div>
      </Card>

      {/* 环境 & 链路 */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
        <Card title="执行前置（B0 检查项）" extra={
          <Tag t={env.target.reachable ? "被测服务可达" : "服务不可达"}
               c={env.target.reachable ? "green" : "red"} />
        }>
          <div className="space-y-3">
            <div className="rounded-lg border border-line px-3 py-2.5">
              <div className="flex items-center justify-between text-[11px]">
                <span className="font-mono text-ink-600">{env.target.endpoint}</span>
                <span className="text-ink-500">{env.target.detail}</span>
              </div>
              <div className="mt-1 text-[11px] text-ink-400">{env.executor}</div>
            </div>
            <div className="grid gap-2 sm:grid-cols-2">
              {env.identities.map((i) => (
                <div key={i.role} className="rounded-lg border border-line px-3 py-2">
                  <div className="text-[11px] text-ink-500">{i.role} · {i.scope}</div>
                  <div className="mt-0.5 font-mono text-[12px] text-ink-800">{i.account}</div>
                </div>
              ))}
            </div>
            <div>
              <div className="mb-1.5 text-[11px] text-ink-500">数据基线（被测库实时读取）</div>
              <div className="flex flex-wrap gap-1.5">
                {env.dataBaseline.length === 0 && <span className="text-[11px] text-ink-400">未连上被测库，执行前请人工核对</span>}
                {env.dataBaseline.map((d) => (
                  <span key={d.name} title={d.note}
                    className={cx("rounded-md px-2 py-1 text-[11px] ring-1 ring-inset",
                      d.count === 0 ? "bg-rose-50 text-rose-700 ring-rose-200" : "bg-ink-50 text-ink-700 ring-ink-200")}>
                    {d.name} <b className="tabular-nums">{d.count.toLocaleString()}</b>
                  </span>
                ))}
              </div>
            </div>
          </div>
        </Card>

        <Card title="执行链路（顺序即依赖）" extra={<span className="text-[10px] text-ink-400">后一环依赖前一环的数据</span>}>
          <div className="space-y-1.5">
            {plan.chains.map((c, i) => (
              <div key={c.code} className="flex items-start gap-2.5 rounded-lg px-2 py-1.5 hover:bg-ink-50">
                <span className="mt-0.5 grid h-5 w-5 shrink-0 place-items-center rounded-md bg-brand-50 text-[10px] font-semibold text-brand-700">
                  {c.code}
                </span>
                <div className="min-w-0 flex-1">
                  <div className="flex items-baseline justify-between gap-2">
                    <span className="text-[12px] font-medium text-ink-800">{c.name}</span>
                    <span className="shrink-0 tabular-nums text-[11px] text-ink-500">
                      {c.requirements} 需求 / {c.cases} 用例
                    </span>
                  </div>
                  <div className="truncate text-[10px] text-ink-400" title={c.why}>{i + 1}. {c.why}</div>
                </div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* 执行进度 */}
      {job && (
        <Card
          title={`批次 ${job.batchId} 执行进度`}
          extra={
            <div className="flex items-center gap-2">
              <Tag t={job.status === "running" ? "执行中" : job.status === "done" ? "已完成" : "失败"}
                   c={job.status === "running" ? "blue" : job.status === "done" ? "green" : "red"} />
              <span className="tabular-nums text-[11px] text-ink-500">
                {job.done} / {job.total}（通过 {job.passed}，失败 {job.failed}
                {job.skipped > 0 ? `，待裁定 ${job.skipped}` : ""}）
              </span>
            </div>
          }
        >
          <Progress value={Math.round(job.rate * 100)} />
          <div className="mt-2 flex items-center justify-between text-[11px] text-ink-500">
            <span className="truncate">
              {job.current ? `正在执行：${job.current.caseId} ${job.current.title}` : job.error ?? "已结束"}
            </span>
            <span className="tabular-nums">{job.startedAt}{job.finishedAt ? ` → ${job.finishedAt}` : ""}</span>
          </div>
          {job.results.length > 0 && (
            <div className="mt-3 max-h-52 overflow-y-auto rounded-lg border border-line">
              <table className="w-full text-[11px]">
                <tbody>
                  {[...job.results].reverse().map((r) => (
                    <tr key={r.caseId} className="border-b border-ink-100 last:border-0">
                      <td className="px-2 py-1.5 font-mono text-ink-500">{r.caseId}</td>
                      <td className="px-2 py-1.5 text-ink-700"><span className="line-clamp-1">{r.title}</span></td>
                      <td className="whitespace-nowrap px-2 py-1.5">
                        <Tag t={r.verdict} c={r.verdict === "通过" ? "green" : ["已执行", "跳过"].includes(r.verdict) ? "amber" : "red"} dot={false} />
                      </td>
                      <td className="max-w-[280px] px-2 py-1.5 text-ink-500"><span className="line-clamp-1">{r.detail}</span></td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      )}

      {/* 批次表 */}
      <Card
        title="执行批次"
        extra={
          <div className="flex flex-wrap items-center gap-1">
            {FILTERS.map((f) => (
              <button key={f} onClick={() => setFilter(f)}
                className={cx("rounded-md px-2 py-1 text-[11px] transition-colors",
                  filter === f ? "bg-brand-50 font-medium text-brand-700" : "text-ink-500 hover:bg-ink-100")}>
                {f}
                {f === "全部" ? ` ${plan.batches.length}` : ""}
              </button>
            ))}
            <Btn v="ghost" size="sm" onClick={reload}><Icon name="activity" size={12} />刷新</Btn>
          </div>
        }
      >
        <Table
          cols={["批次", "内容", "类型", "需求", "用例（自动/人工）", "预计", "状态", "进度", "操作"]}
          onRowClick={(i) => setSelected(visible[i].id)}
          rows={visible.map((b) => [
            <span className="font-mono text-[11px] font-semibold text-ink-700">{b.id}</span>,
            <div className="min-w-0">
              <div className="max-w-[240px] truncate font-medium text-ink-800" title={b.name}>{b.name}</div>
              <div className="text-[10px] text-ink-400">{b.domain}{b.reuse ? " · 复用已执行结果" : ""}</div>
            </div>,
            <Tag t={KIND_CN[b.kind] ?? b.kind} c={KIND_TONE[b.kind] ?? "gray"} dot={false} />,
            <span className="tabular-nums text-[11px] text-ink-600">{b.requirements.length}</span>,
            <span className="tabular-nums text-[11px] text-ink-600">
              {b.apiCount}<span className="text-ink-400"> / {b.manualCount}</span>
            </span>,
            <span className="tabular-nums text-[11px] text-ink-600">{hours(b.estimatedMinutes)}</span>,
            <Tag t={b.status} c={toneOf(b.status)} dot={false} />,
            <div className="w-24">
              <Progress value={Math.round(b.progress.rate * 100)} />
              <div className="mt-1 text-[10px] text-ink-400">
                {b.progress.executed}/{b.caseCount}
                {b.progress.failed > 0 && <span className="ml-1 text-rose-600">失败 {b.progress.failed}</span>}
              </div>
            </div>,
            b.apiCount > 0 ? (
              <Btn v="secondary" size="sm" loading={starting === b.id || (running && job?.batchId === b.id)}
                disabled={running || starting !== null}
                onClick={(e) => { e.stopPropagation(); void runBatch(b); }}>
                {running && job?.batchId === b.id ? "执行中" : "执行"}
              </Btn>
            ) : (
              <span className="text-[10px] text-ink-400">人工</span>
            ),
          ])}
          empty="没有符合筛选条件的批次"
        />
        <div className="mt-2 text-[10px] text-ink-400">
          点击任意行查看该批次的准入条件、准出标准与用例明细；「执行」只跑接口用例，写操作按批次的 force 设置。
        </div>
      </Card>

      {/* 选中批次明细 */}
      {selectedBatch && (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.15fr)]">
          <Card
            title={`${selectedBatch.id} · ${selectedBatch.name}`}
            extra={<Tag t={selectedBatch.status} c={toneOf(selectedBatch.status)} />}
          >
            <div className="space-y-3 text-[12px] leading-6">
              <div>
                <div className="text-[11px] font-medium text-ink-500">准入条件</div>
                <div className="text-ink-700">{selectedBatch.entry}</div>
              </div>
              <div>
                <div className="text-[11px] font-medium text-ink-500">准出标准</div>
                <div className="text-ink-700">{selectedBatch.exit}</div>
              </div>
              {selectedBatch.checklist.length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] font-medium text-ink-500">检查清单</div>
                  <ul className="space-y-1">
                    {selectedBatch.checklist.map((c) => (
                      <li key={c} className="flex gap-1.5 text-[11px] text-ink-600">
                        <Icon name="check" size={12} className="mt-1 shrink-0 text-emerald-500" />
                        <span>{c}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}
              <div className="grid grid-cols-4 gap-2 border-t border-ink-100 pt-2 text-center">
                {[
                  { k: "自动", v: selectedBatch.apiCount },
                  { k: "人工", v: selectedBatch.manualCount },
                  { k: "已执行", v: selectedBatch.progress.executed },
                  { k: "通过", v: selectedBatch.progress.passed },
                ].map((x) => (
                  <div key={x.k}>
                    <div className="tabular-nums text-[16px] font-semibold text-ink-800">{x.v}</div>
                    <div className="text-[10px] text-ink-500">{x.k}</div>
                  </div>
                ))}
              </div>
              {selectedBatch.requirements.length > 0 && (
                <div>
                  <div className="mb-1 text-[11px] font-medium text-ink-500">覆盖需求（{selectedBatch.requirements.length}）</div>
                  <div className="flex flex-wrap gap-1">
                    {selectedBatch.requirements.map((r) => (
                      <button key={r.id} onClick={() => navigate(`/project/${projectId}/requirements/${r.id}`)}
                        title={`${r.title}（用例 ${r.caseCount}）`}
                        className="rounded-md bg-ink-50 px-1.5 py-0.5 text-[10px] text-ink-600 ring-1 ring-inset ring-ink-200 hover:text-brand-700">
                        {r.id}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </Card>

          <Card
            title="用例明细"
            extra={
              <span className="text-[10px] text-ink-400">
                {casesLoading ? "加载中…" : `显示 ${cases?.items.length ?? 0} / ${cases?.total ?? 0} 条`}
              </span>
            }
          >
            <div className="max-h-[430px] overflow-y-auto">
              <Table
                cols={["编号", "用例", "接口", "结果"]}
                rows={(cases?.items ?? []).map((c) => [
                <span className="font-mono text-[10px] text-ink-500">{c.id}</span>,
                <div className="max-w-[230px]">
                  <div className="truncate text-[12px] text-ink-800" title={c.title}>{c.title}</div>
                  <div className="flex items-center gap-1 text-[10px] text-ink-400">
                    <span className={cx("rounded px-1", c.priority === "P0" ? "bg-rose-50 text-rose-600" : "bg-amber-50 text-amber-600")}>
                      {c.priority}
                    </span>
                    <span>{c.requirementId}</span>
                    <span>·</span>
                    <span>{c.type}</span>
                  </div>
                </div>,
                <span className="block max-w-[150px] truncate font-mono text-[10px] text-ink-500" title={c.relatedApi}>
                  {c.relatedApi || "—"}
                </span>,
                <Tag t={c.verdict} c={c.verdict === "通过" ? "green" : c.verdict === "未执行" ? "gray" : c.verdict === "已执行" ? "amber" : "red"} dot={false} />,
              ])}
                empty={casesLoading ? "加载中…" : "该批次没有用例明细"}
              />
            </div>
            {cases?.truncated && (
              <div className="mt-2 text-[10px] text-ink-400">
                仅展示前 60 条，完整清单可在「用例管理」按需求编号筛选。
              </div>
            )}
          </Card>
        </div>
      )}

      {/* 排期 */}
      <Card title="排期建议" extra={<span className="text-[10px] text-ink-400">自动化与人工双轨并行，收口压最后一天</span>}>
        <Table
          cols={["日期", "自动化批次", "人工批次", "工时（自动 / 人工）", "说明"]}
          rows={plan.schedule.map((d) => [
            <div>
              <div className="text-[12px] font-medium text-ink-800">{d.day}</div>
              <div className="text-[10px] text-ink-500">{d.date} {d.weekday}</div>
            </div>,
            <div className="flex max-w-[280px] flex-wrap gap-1">
              {d.autoBatches.length ? d.autoBatches.map((id) => (
                <span key={id} className="rounded bg-brand-50 px-1 py-0.5 font-mono text-[10px] text-brand-700">{id}</span>
              )) : <span className="text-[10px] text-ink-400">—</span>}
            </div>,
            <div className="flex max-w-[280px] flex-wrap gap-1">
              {d.manualBatches.length ? d.manualBatches.map((id) => (
                <span key={id} className="rounded bg-amber-50 px-1 py-0.5 font-mono text-[10px] text-amber-700">{id}</span>
              )) : <span className="text-[10px] text-ink-400">—</span>}
            </div>,
            <span className="tabular-nums text-[11px] text-ink-600">{hours(d.autoMinutes)} / {hours(d.manualMinutes)}</span>,
            <span className="text-[11px] text-ink-500">{d.note}</span>,
          ])}
        />
      </Card>

      {/* 风险与准出 */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
        <Card title="风险与对策" extra={<span className="text-[10px] text-ink-400">{plan.risks.length} 项</span>}>
          <div className="space-y-2.5">
            {plan.risks.map((r) => (
              <div key={r.risk} className="rounded-lg border border-amber-200 bg-amber-50/40 px-3 py-2">
                <div className="text-[12px] font-medium text-ink-800">{r.risk}</div>
                <div className="mt-0.5 text-[11px] text-ink-600">影响：{r.impact}</div>
                <div className="text-[11px] text-emerald-700">对策：{r.mitigation}</div>
              </div>
            ))}
          </div>
        </Card>

        <Card title="准出标准" extra={<span className="text-[10px] text-ink-400">Z1 收口批次据此判定</span>}>
          <Table
            cols={["检查项", "目标", "度量方式"]}
            rows={plan.exitCriteria.map((e) => [
              <span className="text-[12px] font-medium text-ink-800">{e.item}</span>,
              <span className="text-[11px] text-ink-700">{e.target}</span>,
              <span className="block max-w-[220px] font-mono text-[10px] text-ink-500">{e.measure}</span>,
            ])}
          />
        </Card>
      </div>
    </div>
  );
}
