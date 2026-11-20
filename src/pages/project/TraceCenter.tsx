import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { requirementsApi, traceApi } from "@/api";
import type { Requirement } from "@/api/types";
import type { RelationMeta } from "@/api/trace";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Card, Stat, Table, Tag, Btn, Icon } from "@/components/ui";
import { traceHref } from "@/lib/traceLinks";

type Tab = "overview" | "chain" | "pending" | "matrix" | "semantics";

const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "总览" },
  { key: "chain", label: "关联链路" },
  { key: "pending", label: "待确认" },
  { key: "matrix", label: "追踪矩阵" },
  { key: "semantics", label: "关系语义" },
];

function initialTab(): Tab {
  const t = new URLSearchParams(window.location.search).get("tab");
  return TABS.some((x) => x.key === t) ? (t as Tab) : "overview";
}

const TYPE_LABEL: Record<string, string> = {
  requirement: "需求", page: "功能页面", api: "接口",
  code_artifact: "实现代码", table: "数据表",
};

const CATEGORY_TONE: Record<string, "green" | "red" | "amber" | "blue" | "gray"> = {
  structure: "blue", call: "gray", implement: "amber", data: "green", derive: "gray",
};

export function TraceCenter() {
  const { projectId } = useApp();
  const navigate = useNavigate();
  const [tab, setTab] = useState<Tab>(initialTab);
  const [selectedReq, setSelectedReq] = useState("");
  const [hop, setHop] = useState(0); // 0 = 全部层级
  const [toast, setToast] = useState("");

  const { data: reqList } = useAsync(() => requirementsApi.list(), [projectId], [] as Requirement[]);
  const { data: overview } = useAsync(() => traceApi.overview(), [projectId], null);
  const { data: matrix } = useAsync(() => traceApi.matrix(), [projectId], { columns: [], rows: [] });
  const { data: pending, reload: reloadPending } = useAsync(
    () => traceApi.pending("proposed"), [projectId], { total: 0, staleCount: 0, items: [] });
  const { data: meta } = useAsync(() => traceApi.relationsMeta(), [projectId],
    { items: [] as RelationMeta[], categories: {} as Record<string, string> });
  const { data: impact } = useAsync(
    () => (selectedReq ? traceApi.impactForward("requirement", selectedReq, 5) : Promise.resolve(null)),
    [projectId, selectedReq], null);

  const relLabel = useMemo(() => {
    const m: Record<string, string> = {};
    meta.items.forEach((x) => { m[x.type] = x.label; });
    return m;
  }, [meta.items]);

  // 需求字段列表：按需求编号索引各层关联情况
  const matrixMap = useMemo(() => {
    const m: Record<string, typeof matrix.rows[number]> = {};
    (matrix?.rows ?? []).forEach((r) => { m[r.id] = r; });
    return m;
  }, [matrix]);

  useEffect(() => {
    if (!selectedReq && reqList?.length) setSelectedReq(reqList[0].id);
  }, [reqList, selectedReq]);

  // 链路真实深度由后端给出：只有 3 层就不该出现"4 跳"这种空选项
  const maxDepth = impact?.maxDepth ?? 0;
  const shown = useMemo(() => {
    const items = impact?.items ?? [];
    return hop === 0 ? items : items.filter((x) => x.hop === hop);
  }, [impact, hop]);

  const grouped = useMemo(() => {
    const map = new Map<number, typeof shown>();
    shown.forEach((it) => {
      const arr = map.get(it.hop) ?? [];
      arr.push(it);
      map.set(it.hop, arr);
    });
    return [...map.entries()].sort((a, b) => a[0] - b[0]);
  }, [shown]);

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
    try { const r = await traceApi.batchConfirm(pending.items.map((x) => x.relationId)); flash(`已批量确认 ${r.confirmed} 条`); reloadPending(); }
    catch (e) { flash(`批量确认失败：${(e as Error).message}`); }
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-1 overflow-x-auto border-b border-line">
        {TABS.map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`whitespace-nowrap px-4 py-2 text-xs font-semibold border-b-2 -mb-px ${
              tab === t.key ? "border-brand-500 text-brand-500" : "border-transparent text-ink-500"}`}>
            {t.label}
          </button>
        ))}
      </div>

      {tab === "overview" && (
        <>
          <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
            <Stat label="需求总数" value={overview?.requirementTotal ?? "--"} />
            <Stat label="至少一层关联" value={overview ? `${Math.round(overview.linkedRate * 100)}%` : "--"} />
            <Stat label="待确认" value={overview?.pendingRelationCount ?? "--"} />
            <Stat label="待复核 stale" value={overview?.staleRelationCount ?? "--"} />
          </div>
          <Card title="需求字段列表"
            extra={<span className="text-[11px] text-ink-400">点击任意行进入需求详情</span>}>
            <Table
              cols={["编号", "标题", "优先级", "状态", "负责人", "版本", "页面", "接口", "代码", "表"]}
              rows={(reqList ?? []).map((r) => {
                const m = matrixMap[r.id];
                return [
                  <span className="font-mono text-brand-500 text-[11px]">{r.id}</span>,
                  r.title,
                  <Tag t={r.priority} c={r.priority === "P0" ? "red" : r.priority === "P1" ? "amber" : "blue"} />,
                  r.status,
                  r.owner || "—",
                  r.version || "—",
                  m ? m.page : "—", m ? m.api : "—", m ? m.code_artifact : "—", m ? m.table : "—",
                ];
              })}
              onRowClick={(i) => {
                const r = reqList?.[i];
                if (r) navigate(`/project/${projectId}/requirements/${r.id}`);
              }}
            />
          </Card>
        </>
      )}

      {tab === "chain" && (
        <>
          <Card title="选择需求">
            <div className="flex flex-wrap items-center gap-3">
              <select value={selectedReq} onChange={(e) => { setSelectedReq(e.target.value); setHop(0); }}
                className="h-9 w-80 rounded-lg border border-line px-3 text-xs">
                {!reqList?.length && <option value="">暂无需求</option>}
                {reqList?.map((r) => (
                  <option key={r.id} value={r.id}>{r.id} · {r.title}</option>
                ))}
              </select>
              <select value={hop} onChange={(e) => setHop(Number(e.target.value))}
                className="h-9 rounded-lg border border-line px-3 text-xs">
                <option value={0}>全部层级</option>
                {Array.from({ length: maxDepth }, (_, i) => i + 1).map((n) => (
                  <option key={n} value={n}>只看第 {n} 层</option>
                ))}
              </select>
              <span className="text-xs text-ink-500">影响实体：{impact?.affectedCount ?? "--"}</span>
              {maxDepth > 0 && (
                <span className="text-[11px] text-ink-400">链路共 {maxDepth} 层</span>
              )}
              {impact?.crossDatabaseWarning && <Tag t="涉及跨库" c="amber" />}
            </div>
            {maxDepth > 0 && (
              <div className="mt-3 flex flex-wrap items-center gap-1.5 text-[11px] text-ink-500">
                <span className="rounded bg-ink-100 px-1.5 py-0.5 font-medium text-ink-700">需求</span>
                <span className="text-ink-300">拆分为 →</span>
                <span className="rounded bg-blue-50 px-1.5 py-0.5 text-blue-700">功能页面</span>
                <span className="text-ink-300">调用接口 →</span>
                <span className="rounded bg-gray-100 px-1.5 py-0.5 text-gray-700">接口</span>
                <span className="text-ink-300">由代码实现 / 读写数据表 →</span>
                <span className="rounded bg-amber-50 px-1.5 py-0.5 text-amber-700">实现代码</span>
                <span className="text-ink-300">·</span>
                <span className="rounded bg-emerald-50 px-1.5 py-0.5 text-emerald-700">数据表</span>
              </div>
            )}
          </Card>

          <Card title={`影响链路 · ${selectedReq}`}
            extra={<span className="text-[11px] text-ink-400">点击任一节点进入实体详情</span>}>
            {!impact || !shown.length ? (
              <div className="py-8 text-center text-xs text-ink-400">
                {impact ? "没有可展示的实体，试试切换层级" : "请选择需求"}
              </div>
            ) : (
              <div className="space-y-5">
                {grouped.map(([hopNo, items]) => (
                  <div key={hopNo}>
                    <div className="mb-2 flex items-center gap-2">
                      <span className="rounded bg-brand-500 px-2 py-0.5 text-[10px] font-bold text-white">
                        第 {hopNo} 层
                      </span>
                      <span className="text-[11px] text-ink-500">
                        {[...new Set(items.map((x) => TYPE_LABEL[x.type] ?? x.type))].join(" / ")}
                        {" · "}{items.length} 个
                      </span>
                      <span className="h-px flex-1 bg-ink-100" />
                    </div>
                    <div className="space-y-2">
                      {items.map((it, i) => (
                        <button key={`${it.id}-${i}`}
                          onClick={() => navigate(traceHref(it.type, it.id, projectId))}
                          className="group flex w-full items-center gap-3 rounded-lg border border-line px-4 py-2.5 text-left hover:border-brand-300 hover:bg-brand-50/40">
                          <span className="w-16 shrink-0 text-[10px] text-ink-400">
                            {TYPE_LABEL[it.type] ?? it.type}
                          </span>
                          <span className="min-w-0 flex-1">
                            <span className="block truncate text-xs font-semibold text-ink-800 group-hover:text-brand-600">
                              {it.name}
                            </span>
                            <span className="block truncate font-mono text-[10px] text-ink-400">{it.id}</span>
                          </span>
                          {relLabel[it.relType] && (
                            <span className="shrink-0 text-[10px] text-ink-400">{relLabel[it.relType]}</span>
                          )}
                          <Icon name="chevron-right" size={14}
                            className="shrink-0 text-ink-300 group-hover:text-brand-500" />
                        </button>
                      ))}
                    </div>
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
                <span>
                  <span className="text-ink-800">{relLabel[r.relType] ?? r.relType}</span>
                  <span className="ml-1 font-mono text-[10px] text-ink-400">{r.relType}</span>
                </span>,
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
        <Card title="追踪矩阵 · 需求 × 各层关联">
          <Table
            cols={["需求", "标题", "页面", "接口", "代码", "表", "覆盖率", "缺口"]}
            rows={(matrix?.rows ?? []).map((r) => [
              <span className="font-mono text-brand-500 text-[11px]">{r.id}</span>,
              r.title,
              r.page || "—", r.api || "—", r.code_artifact || "—", r.table || "—",
              `${r.coverage}%`,
              r.missing.length ? r.missing.join("/") : "无",
            ])}
            onRowClick={(i) => {
              const row = matrix?.rows[i];
              if (row) navigate(`/project/${projectId}/trace/entity?type=requirement&id=${row.id}`);
            }}
          />
        </Card>
      )}

      {tab === "semantics" && (
        <Card title="关系语义 · 6 种关联到底在说什么">
          <p className="mb-4 text-xs leading-6 text-ink-600">
            关系表的 <span className="font-mono text-[11px]">rel_type</span> 是英文枚举，
            每个枚举回答一个具体问题。下面这张表就是它的字典，界面上的中文标签都来自这里。
          </p>
          <div className="space-y-2">
            {meta.items.map((m) => (
              <div key={m.type} className="rounded-lg border border-line px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-mono text-[11px] font-semibold text-ink-800">{m.type}</span>
                  <Icon name="arrow-right" size={12} className="text-ink-300" />
                  <span className="text-[12px] font-semibold text-brand-600">{m.label}</span>
                  <Tag t={meta.categories[m.category] ?? m.category} c={CATEGORY_TONE[m.category] ?? "gray"} dot={false} />
                  <span className="ml-auto text-[10px] text-ink-400">
                    {TYPE_LABEL[m.from.split("|")[0]] ?? m.from} → {TYPE_LABEL[m.to] ?? m.to}
                  </span>
                </div>
                <div className="mt-1.5 text-[12px] text-ink-700">问：{m.question}</div>
                <div className="mt-0.5 font-mono text-[11px] text-ink-400">例：{m.example}</div>
                {m.note && <div className="mt-1 text-[11px] text-ink-500">注：{m.note}</div>}
              </div>
            ))}
          </div>
          <div className="mt-4 rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3 text-[11px] leading-6 text-amber-800">
            <b>可精简的地方：</b>CROSS_DB_READ 本质是「读写数据表 + 跨库标记」，
            独立成一个枚举会让每个跨库关系都要建两条边；建议后续收敛为 READS_WRITES 加一个
            cross_db 布尔标记。<b>EXPOSED_BY 的方向也是反的</b>（代码暴露接口），语义上等于 IMPLEMENTS。
          </div>
        </Card>
      )}

      {toast && <div className="fixed bottom-6 left-1/2 -translate-x-1/2 bg-ink-900 text-white text-xs rounded-lg px-4 py-2 shadow-lg">{toast}</div>}
    </div>
  );
}
