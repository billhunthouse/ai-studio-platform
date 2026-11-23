/** 需求覆盖率：四个口径（文档 / 追溯 / 用例 / 验收）与缺口清单。 */

import { useNavigate } from "react-router-dom";
import { prdApi } from "@/api";
import type { CoverGroupRow, PrdCoverage } from "@/api/prd";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Icon, Progress, Stat, Table, Tag } from "@/components/ui";
import { cx } from "@/lib/cx";

const LAYER_CN: Record<string, string> = {
  page: "功能页面", api: "接口", code_artifact: "实现代码", table: "数据表",
};

const MISSING_CN: Record<string, string> = {
  doc: "无 PRD", trace: "链路断", case: "无用例", verify: "未验证",
};

function pct(v: number) {
  return `${(v * 100).toFixed(1)}%`;
}

function RateCell({ value }: { value: number }) {
  const p = Math.round(value * 100);
  return (
    <div className="flex items-center gap-2">
      <Progress value={p} className="w-20" />
      <span className={cx("tabular-nums text-[12px]", p >= 80 ? "text-emerald-600" : p >= 50 ? "text-amber-600" : "text-rose-600")}>
        {p}%
      </span>
    </div>
  );
}

function GroupTable({ rows, keyName, label }: { rows: CoverGroupRow[]; keyName: "priority" | "domain"; label: string }) {
  return (
    <Table
      cols={[label, "需求数", "有用例", "已验证", "四层全通", "需求覆盖率", "验证通过率"]}
      rows={rows.map((r) => [
        <span className="font-medium text-ink-800">{r[keyName] ?? "-"}</span>,
        <span className="tabular-nums">{r.total}</span>,
        <span className="tabular-nums text-ink-600">{r.withCase}</span>,
        <span className="tabular-nums text-ink-600">{r.verified}</span>,
        <span className="tabular-nums text-ink-600">{r.traceFull}</span>,
        <RateCell value={r.caseRate} />,
        <RateCell value={r.verifyRate} />,
      ])}
    />
  );
}

export function RequirementCoverage() {
  const { projectId } = useApp();
  const navigate = useNavigate();
  const { data, loading } = useAsync<PrdCoverage | null>(
    () => prdApi.coverage().then((r) => r ?? null).catch(() => null), [projectId], null);

  if (loading && !data) {
    return <div className="grid h-40 place-items-center text-xs text-ink-500">加载覆盖率…</div>;
  }
  if (!data) {
    return (
      <Card>
        <div className="py-10 text-center text-[12px] text-ink-500">
          暂无覆盖率数据。请先在需求列表运行「需求规范化」。
        </div>
      </Card>
    );
  }

  const d = data.detail;
  const primary = Math.round(data.requirementCoverage * 100);
  const verified = Math.round(data.verifiedCoverage * 100);

  return (
    <div className="space-y-4">
      {/* 主指标 */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="需求覆盖率"
          value={pct(data.requirementCoverage)}
          hint={`${d.withCase} / ${data.requirementTotal} 条需求已关联用例`}
          icon={<Icon name="check" size={16} />}
        />
        <Stat
          label="已验证覆盖率"
          value={pct(data.verifiedCoverage)}
          hint={`${d.verified} / ${data.requirementTotal} 条的需求有用例执行通过`}
          icon={<Icon name="shield" size={16} />}
        />
        <Stat
          label="追溯覆盖率"
          value={pct(data.traceCoverage)}
          hint={`${d.traceFull} 条四层链路全通（页面/接口/代码/表）`}
          icon={<Icon name="activity" size={16} />}
        />
        <Stat
          label="AC 断言锚点率"
          value={pct(data.acAnchorRate)}
          hint={`${d.acStrong} / ${d.acTotal} 条验收标准命中 ≥2 级锚点`}
          icon={<Icon name="clipboard" size={16} />}
        />
      </div>

      {/* 漏斗 + 质量 */}
      <div className="grid gap-4 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="覆盖漏斗" extra={<span className="text-[10px] text-ink-400">需求 → 用例 → 执行 → 通过</span>}>
          <div className="space-y-3">
            {[
              { label: "需求总数", value: data.requirementTotal, total: data.requirementTotal, tone: "bg-ink-400" },
              { label: "有规范化 PRD", value: d.docRestored, total: data.requirementTotal, tone: "bg-brand-500" },
              { label: "有用例覆盖", value: d.withCase, total: data.requirementTotal, tone: "bg-indigo-500" },
              { label: "有用例执行过", value: d.caseExecutedReqs, total: data.requirementTotal, tone: "bg-amber-500" },
              { label: "有用例通过", value: d.verified, total: data.requirementTotal, tone: "bg-emerald-500" },
            ].map((s) => (
              <div key={s.label}>
                <div className="mb-1 flex items-baseline justify-between">
                  <span className="text-[12px] text-ink-600">{s.label}</span>
                  <span className="tabular-nums text-[12px] font-semibold text-ink-800">
                    {s.value}
                    <span className="ml-1 text-[10px] font-normal text-ink-400">
                      / {s.total}（{Math.round((s.value / Math.max(s.total, 1)) * 100)}%）
                    </span>
                  </span>
                </div>
                <div className="h-2.5 rounded-full bg-ink-100">
                  <div className={cx("h-2.5 rounded-full transition-all", s.tone)}
                    style={{ width: `${Math.max(1, (s.value / Math.max(s.total, 1)) * 100)}%` }} />
                </div>
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2.5 text-[11px] leading-5 text-amber-800">
            <b>用例执行是当前的主要缺口：</b>
            共 {d.caseTotal} 条用例，仅 {d.caseExecuted} 条执行过（通过 {d.casePassed} 条），
            其余 {d.caseNotRun} 条从未运行。这解释了为什么「有用例」是 {primary}%，而「已验证」只有 {verified}%。
          </div>
        </Card>

        <Card title="文档质量分" extra={<span className="text-[10px] text-ink-400">{data.quality.gatesPassed}/{data.quality.gatesTotal} 条门禁通过</span>}>
          <div className="flex items-end gap-3">
            <span className="tabular-nums text-[36px] font-semibold leading-none tracking-[-0.04em] text-ink-900">
              {data.quality.average}
            </span>
            <span className="pb-1 text-[11px] text-ink-500">平均分（区间 {data.quality.min}–{data.quality.max}）</span>
          </div>
          <div className="mt-4 space-y-2">
            {Object.entries(data.quality.distribution).map(([band, n]) => (
              <div key={band} className="flex items-center gap-2 text-[11px]">
                <span className="w-14 text-ink-500">{band} 分</span>
                <div className="h-2 flex-1 rounded-full bg-ink-100">
                  <div className={cx("h-2 rounded-full",
                    band === "90-100" ? "bg-emerald-500" : band === "75-89" ? "bg-brand-500" : band === "60-74" ? "bg-amber-500" : "bg-rose-500")}
                    style={{ width: `${(n / Math.max(data.requirementTotal, 1)) * 100}%` }} />
                </div>
                <span className="w-8 text-right tabular-nums text-ink-600">{n}</span>
              </div>
            ))}
          </div>
          <div className="mt-4 grid grid-cols-4 gap-2 border-t border-ink-100 pt-3">
            {Object.entries(data.layerCoverage).map(([k, v]) => (
              <div key={k} className="text-center">
                <div className="tabular-nums text-[16px] font-semibold text-ink-800">{v}</div>
                <div className="text-[10px] text-ink-500">{LAYER_CN[k] ?? k}</div>
              </div>
            ))}
          </div>
        </Card>
      </div>

      {/* 分组覆盖 */}
      <div className="grid gap-4 xl:grid-cols-2">
        <Card title="按优先级" extra={<span className="text-[10px] text-ink-400">P0 缺口优先处理</span>}>
          <GroupTable rows={data.byPriority} keyName="priority" label="优先级" />
        </Card>
        <Card title="按业务域" extra={<span className="text-[10px] text-ink-400">定位覆盖洼地</span>}>
          <GroupTable rows={data.byDomain} keyName="domain" label="业务域" />
        </Card>
      </div>

      {/* 缺口清单 */}
      <Card
        title="未完全覆盖的需求"
        extra={
          <div className="flex items-center gap-2">
            <span className="text-[10px] text-ink-400">共 {data.gaps.length} 条</span>
            <Btn v="secondary" size="sm" onClick={() => navigate(`/project/${projectId}/requirements-regression`)}>
              <Icon name="play" size={12} />排回归计划
            </Btn>
          </div>
        }
      >
        <Table
          cols={["编号", "需求名称", "优先级", "业务域", "缺口", "用例", "质量分", ""]}
          rows={data.gaps.map((g) => [
            <span className="font-mono text-[11px] text-ink-500">{g.id}</span>,
            <span className="block max-w-[280px] truncate font-medium text-ink-800" title={g.title}>{g.title}</span>,
            <Tag t={g.priority} c={g.priority === "P0" ? "red" : "amber"} />,
            <span className="text-[11px] text-ink-600">{g.domain}</span>,
            <div className="flex flex-wrap gap-1">
              {g.missing.map((m) => (
                <Tag key={m} t={MISSING_CN[m] ?? m} c={m === "case" ? "red" : m === "verify" ? "amber" : "gray"} dot={false} />
              ))}
            </div>,
            <span className="tabular-nums text-[11px] text-ink-500">{g.passed}/{g.caseCount}</span>,
            <span className={cx("tabular-nums text-[11px] font-medium",
              g.score >= 90 ? "text-emerald-600" : g.score >= 75 ? "text-ink-700" : "text-amber-600")}>{g.score}</span>,
            <Btn v="ghost" size="sm" onClick={() => navigate(`/project/${projectId}/requirements/${g.id}`)}>
              查看
            </Btn>,
          ])}
          empty="全部需求均已覆盖并验证"
        />
      </Card>
    </div>
  );
}
