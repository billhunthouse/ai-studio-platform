import { useEffect, useState } from "react";
import { requirementsApi, traceApi } from "@/api";
import type { Requirement } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Card, Stat, Table, Tag } from "@/components/ui";

type Tab = "overview" | "chain" | "pending" | "matrix";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "总览" },
  { key: "chain", label: "关联链路" },
  { key: "pending", label: "待确认" },
  { key: "matrix", label: "追踪矩阵" },
];

function initialTab(): Tab {
  const t = new URLSearchParams(window.location.search).get("tab");
  return TABS.some((x) => x.key === t) ? (t as Tab) : "overview";
}

const TYPE_LABEL: Record<string, string> = {
  requirement: "需求", page: "功能页面", api: "接口",
  code_artifact: "代码", table: "数据表",
};

export function TraceCenter() {
  const { projectId } = useApp();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [selectedReq, setSelectedReq] = useState("");
  const [cohort, setCohort] = useState(3);
  const [toast, setToast] = useState("");

  const { data: reqList } = useAsync(() => requirementsApi.list(), [projectId], [] as Requirement[]);
  const { data: overview } = useAsync(() => traceApi.overview(), [projectId], null);
  const { data: matrix, reload: reloadMatrix } = useAsync(() => traceApi.matrix(), [projectId], { columns: [], rows: [] });
  const { data: pending, reload: reloadPending } = useAsync(
    () => traceApi.pending("proposed"), [projectId], { total: 0, staleCount: 0, items: [] });
  const { data: impact } = useAsync(
    () => (selectedReq ? traceApi.impactForward("requirement", selectedReq, cohort) : Promise.resolve(null)),
    [projectId, selectedReq, cohort], null);

  // 需求列表就绪后默认选中第一条，避免手填 unknow ID
  useEffect(() => {
    if (!selectedReq && reqList?.length) setSelectedReq(reqList[0].id);
  }, [reqList, selectedReq]);

  const flash = (msg: string) => { setToast(msg); setTimeout(() => setToast(""), 2200); };
  const confirm = async (rid: string) => {
    try { await traceApi.confirmRelation(rid); flash("已确认关联"); reloadPending(); }
    catch (e) { flash(`确认失败：${(e as Error).message}`); }
  };
  const reject = async (rid: string) => {
    try { await traceApi.rejectRelation(rid, "页面驳回"); flash("已驳回关联"); reloadPending(); }
    catch (e) { flash(`驳回失败：${(e as Error).message}`); }
  };
  const batch = async () => {
    if (!pending?.items.length) return;
    try { const r = await traceApi.batchConfirm(pending.items.map((x) => x.relationId)); flash(`已批量确认 ${r.confirmed} 条`); reloadPending(); reloadMatrix(); }
    catch (e) { flash(`批量确认失败：${(e as Error).message}`); }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-1 border-b border-line">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-4 py-2 text-xs font-semibold border-b-2 -mb-px ${
              tab === t.key ? "border-brand-500 text-brand-500" : "border-transparent text-ink-500"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="grid grid-cols-4 gap-4">
            <Stat label="需求总数" value={overview?.requirementTotal ?? "--"} />
            <Stat label="关联覆盖率" value={overview ? `${Math.round(overview.coverageRate * 100)}%` : "--"} />
            <Stat label="待确认关联" value={overview?.pendingRelationCount ?? "--"} />
            <Stat label="待复核 stale" value={overview?.staleRelationCount ?? "--"} />
          </div>
          <Card title="使用说明">
            <div className="text-xs text-ink-600 leading-6 space-y-1">
              <p>1. 「关联链路」选择需求后，查看它经功能页面、接口、代码到数据表的完整影响路径。</p>
              <p>2. 扫描发现的候选关联进入「待确认」，确认后才进入正式图谱。</p>
              <p>3. 「追踪矩阵」按需求列出五层关联数量，快速发现覆盖缺口。</p>
              <p className="text-ink-400">当前为 v0.5 能力：实体登记与人工关联可用；自动扫描器在待办清单中。</p>
            </div>
          </Card>
        </>
      )}

      {tab === "chain" && (
        <>
          <Card title="选择需求">
            <div className="flex items-center gap-3">
              <select value={selectedReq} onChange={(e) => setSelectedReq(e.target.value)}
                className="border border-line rounded-md px-3 py-2 text-xs w-80">
                {!reqList?.length && <option value="">暂无需求</option>}
                {reqList?.map((r) => (
                  <option key={r.id} value={r.id}>{r.id} · {r.title}</option>
                ))}
              </select>
              <select value={cohort} onChange={(e) => setCohort(Number(e.target.value))}
                className="border border-line rounded-md px-3 py-2 text-xs">
                <option value={1}>1 跳</option><option value={2}>2 跳</option>
                <option value={3}>3 跳</option><option value={4}>4 跳</option>
              </select>
              <span className="text-xs text-ink-500">影响实体：{impact?.affectedCount ?? "--"}</span>
              {impact?.crossDatabaseWarning && <Tag t="涉及跨库" c="amber" />}
            </div>
          </Card>
          <Card title={`影响链路 · ${selectedReq}`}>
            {!impact || !impact.items.length ? (
              <div className="text-xs text-ink-400 py-6 text-center">未发现关联，请确认需求 ID 或先在待确认中建立关联</div>
            ) : (
              <div className="space-y-2">
                {impact.items.map((it, i) => (
                  <div key={`${it.id}-${i}`} className="flex items-center gap-3 border border-line rounded-lg px-4 py-3">
                    <span className="text-[10px] font-bold text-brand-500 bg-brand-50 rounded px-2 py-0.5">HOP {it.hop}</span>
                    <span className="text-[10px] text-ink-500 w-20">{TYPE_LABEL[it.type] ?? it.type}</span>
                    <span className="text-xs font-semibold flex-1">{it.name}</span>
                    <span className="text-[10px] text-ink-400 font-mono">{it.id}</span>
                    <Tag t={it.relType} c="blue" />
                  </div>
                ))}
              </div>
            )}
          </Card>
        </>
      )}

      {tab === "pending" && (
        <Card title={`待确认关联 · proposed ${pending?.total ?? 0} / stale ${pending?.staleCount ?? 0}`}
          extra={<button onClick={batch} className="text-xs px-3 py-1.5 rounded-md bg-brand-500 text-white">批量确认</button>}>
          {!pending?.items.length ? (
            <div className="text-xs text-ink-400 py-6 text-center">暂无待确认关联</div>
          ) : (
            <Table cols={["关系", "源 → 目标", "来源", "置信度", "操作"]}
              rows={pending.items.map((r) => [
                r.relType,
                `${r.src.id} → ${r.dst.id}`,
                r.source,
                `${r.confidence}%`,
                r.status === "stale" ? "需复核" : "确认 / 驳回",
              ])}
            />
          )}
          <div className="mt-3 flex gap-2 flex-wrap">
            {pending?.items.slice(0, 8).map((r) => (
              <div key={r.relationId} className="border border-line rounded px-2 py-1 text-[10px] flex items-center gap-2">
                <span className="font-mono text-ink-500">{r.src.id.slice(0, 28)}</span>
                <button onClick={() => confirm(r.relationId)} className="text-brand-500 font-semibold">确认</button>
                <button onClick={() => reject(r.relationId)} className="text-rose-600 font-semibold">驳回</button>
              </div>
            ))}
          </div>
        </Card>
      )}

      {tab === "matrix" && (
        <Card title="追踪矩阵 · 需求 × 五层关联">
          <Table
            cols={["需求", "标题", "页面", "接口", "代码", "表", "覆盖率", "缺口"]}
            rows={(matrix?.rows ?? []).map((r) => [
              <span className="font-mono text-brand-500 text-[11px]">{r.id}</span>,
              r.title,
              r.page || "—", r.api || "—", r.code_artifact || "—", r.table || "—",
              `${r.coverage}%`,
              r.missing.length ? r.missing.join("/") : "无",
            ])}
          />
        </Card>
      )}

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink-900 text-white text-xs rounded-lg px-4 py-2 shadow-lg">{toast}</div>}
    </div>
  );
}
