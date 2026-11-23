import { useMemo, useState } from "react";
import { webuiApi } from "@/api";
import type { UiBindingRow, UiQualityPayload } from "@/api/webui";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Select, Table, Tag } from "@/components/ui";
import { CaseBindingModal } from "./CaseBindingModal";
import { UiDedupPanel } from "./UiDedupPanel";

/**
 * 绑定体检台：把"用例和页面是拆的"这件事显式化。
 *
 * 三件事在这页完成：
 * 1. 看得见——每条用例属于哪一类（可执行/缺 PO/接口校验/人工/待归类），为什么；
 * 2. 改得快——按建议一键确认，或批量指定到同一页面；
 * 3. 说得清——四层指标 + 闸门，回答"这个通过率能不能信"。
 */
const KIND_OPTIONS = [
  { key: "", label: "全部分类" },
  { key: "ui_po", label: "可执行" },
  { key: "ui_page_no_po", label: "缺 Page Object" },
  { key: "ui_ambiguous", label: "待选流程" },
  { key: "api", label: "接口/数据校验" },
  { key: "manual", label: "人工验证" },
  { key: "unbound", label: "待归类" },
];

const TONE: Record<string, "green" | "blue" | "amber" | "gray" | "red"> = {
  ui_po: "green", ui_page_no_po: "amber", ui_ambiguous: "amber", api: "blue", manual: "gray", unbound: "red",
};

function Metric({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "good" | "warn" | "bad" }) {
  const color = tone === "good" ? "text-emerald-600" : tone === "warn" ? "text-amber-600" : tone === "bad" ? "text-rose-600" : "text-ink-900";
  return (
    <div className="rounded-xl border border-line bg-white px-4 py-3">
      <div className="text-[11px] text-ink-500">{label}</div>
      <div className={`mt-1 text-xl font-semibold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="mt-0.5 text-[10.5px] leading-4 text-ink-400">{sub}</div>}
    </div>
  );
}

export function UiBindings() {
  const { toast } = useApp();
  const { data, loading, reload } = useAsync(async () => await webuiApi.bindings({}), [], null);
  const { data: quality, reload: refreshQuality } = useAsync<UiQualityPayload | null>(async () => await webuiApi.quality(), [], null);
  const [kind, setKind] = useState("");
  const [onlyReview, setOnlyReview] = useState(false);
  const [keyword, setKeyword] = useState("");
  const [picked, setPicked] = useState<string[]>([]);
  const [bindTarget, setBindTarget] = useState<UiBindingRow | null>(null);
  const [bulkPage, setBulkPage] = useState("");
  const [busy, setBusy] = useState(false);

  const rows = useMemo(() => {
    const all = data?.items ?? [];
    return all.filter((r) =>
      (!kind || r.kind === kind)
      && (!onlyReview || r.needsReview)
      && (!keyword || r.title.includes(keyword) || r.caseId.includes(keyword) || r.module.includes(keyword)));
  }, [data, kind, onlyReview, keyword]);

  const pages = data?.pages ?? [];
  const allPicked = rows.length > 0 && picked.length === rows.length;
  const toggleAll = () => setPicked(allPicked ? [] : rows.map((r) => r.caseId));
  const toggleOne = (id: string) => setPicked(picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]);

  const writeBulk = async (mode: "suggest" | "page") => {
    const targets = rows.filter((r) => picked.includes(r.caseId));
    const items = mode === "suggest"
      ? targets.filter((r) => r.suggestPageId).map((r) => ({ caseId: r.caseId, pageId: r.suggestPageId, poName: r.suggestPoName || undefined }))
      : targets.map((r) => ({ caseId: r.caseId, pageId: bulkPage || null }));
    if (items.length === 0) { toast(mode === "suggest" ? "选中项没有可用的绑定建议" : "请先选择目标页面"); return; }
    setBusy(true);
    try {
      const r = await webuiApi.writeBindings({ items });
      toast(`已确认 ${r.updated} 条绑定${r.errors.length ? `，${r.errors.length} 条失败` : ""}`);
      setPicked([]);
      reload();
    } catch (e) {
      toast(e instanceof Error ? e.message : "保存失败");
    } finally { setBusy(false); }
  };

  const s = data?.summary;
  const l1 = quality?.l1Effectiveness;
  const l2 = quality?.l2Outcome;
  const l4 = quality?.l4Coverage;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-5">
        <Metric label="功能用例" value={s?.total ?? "—"} sub={l1 ? `去重后仅 ${l1.uniqueTitles} 个场景` : undefined} />
        <Metric label="可执行（有页面有流程）" value={s?.runnable ?? "—"} tone="good"
          sub={l1 ? `另有 ${l1.byKind["缺 Page Object"] ?? 0} 条缺 PO` : undefined} />
        <Metric label="绑定已确认" value={`${l1?.bindingConfirmedRate ?? 0}%`}
          tone={(l1?.bindingConfirmedRate ?? 0) >= 80 ? "good" : "bad"}
          sub={s ? `${s.confirmed} / ${s.bindable} 条应绑用例已确认` : undefined} />
        <Metric label="有效通过率" value={`${l2?.effectivePassRate ?? 0}%`}
          tone={(l2?.effectivePassRate ?? 0) >= 95 ? "good" : "warn"}
          sub={l2 ? `原始 ${l2.rawPassRate}%，其中 ${l2.ineffectiveExecuted} 次执行绑定存疑` : undefined} />
        <Metric label="页面 PO 覆盖" value={`${l4?.pagePoRate ?? 0}%`}
          tone={(l4?.pagePoRate ?? 0) >= 80 ? "good" : "warn"}
          sub={l4 ? `${l4.pagesWithPo} / ${l4.pagesTotal} 个页面有自动化流程` : undefined} />
      </div>

      {quality && (
        <div className={`rounded-xl border px-4 py-3 text-[12px] leading-5 ${quality.gates.trusted
          ? "border-emerald-200 bg-emerald-50 text-emerald-800"
          : "border-amber-200 bg-amber-50 text-amber-800"}`}>
          <span className="font-medium">{quality.gates.trusted ? "结论可采信" : "结论暂不可采信"}</span>
          {quality.gates.reasons.length > 0
            ? <ul className="mt-1 list-disc pl-5">{quality.gates.reasons.map((r) => <li key={r}>{r}</li>)}</ul>
            : <span className="ml-2">绑定确认、断言密度、样本量均达阈值。</span>}
        </div>
      )}

      <UiDedupPanel onChanged={() => { reload(); refreshQuality(); }} />

      <Card title="用例-页面绑定">
        <div className="flex flex-wrap items-center gap-2 pb-3">
          <Select opts={KIND_OPTIONS.map((k) => k.label)} className="w-40"
            value={KIND_OPTIONS.find((k) => k.key === kind)?.label ?? "全部分类"}
            onChange={(e) => setKind(KIND_OPTIONS.find((k) => k.label === e.target.value)?.key ?? "")} />
          <input value={keyword} onChange={(e) => setKeyword(e.target.value)} placeholder="搜索用例 / 模块"
            className="h-9 w-52 rounded-lg border border-line bg-white px-3 text-[13px] outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10" />
          <label className="flex items-center gap-1.5 text-[12px] text-ink-600">
            <input type="checkbox" className="accent-brand-600" checked={onlyReview} onChange={(e) => setOnlyReview(e.target.checked)} />
            只看待确认
          </label>
          <span className="text-[11px] text-ink-400">{rows.length} 条</span>
          <div className="ml-auto flex items-center gap-2">
            <label className="flex items-center gap-1.5 text-[12px] text-ink-600">
              <input type="checkbox" className="accent-brand-600" checked={allPicked} onChange={toggleAll} />
              全选当前 {rows.length} 条
            </label>
            <Btn v="secondary" size="sm" disabled={busy || picked.length === 0} onClick={() => void writeBulk("suggest")}>
              按建议确认 {picked.length || ""}
            </Btn>
            <select value={bulkPage} onChange={(e) => setBulkPage(e.target.value)}
              className="h-9 rounded-lg border border-line bg-white pl-3 pr-8 text-[12px] text-ink-700 shadow-sm outline-none">
              <option value="">指定页面…</option>
              {pages.map((p) => <option key={p.pageId} value={p.pageId}>{p.name} · {p.path}</option>)}
            </select>
            <Btn size="sm" disabled={busy || picked.length === 0 || !bulkPage} onClick={() => void writeBulk("page")}>
              应用到选中
            </Btn>
          </div>
        </div>

        <Table
          cols={["", "ID", "标题", "模块", "分类", "绑定页面 / 流程", "来源", "判断依据"]}
          loading={loading}
          rows={rows.map((r) => [
            <input type="checkbox" className="accent-brand-600" checked={picked.includes(r.caseId)}
              onChange={() => toggleOne(r.caseId)} onClick={(e) => e.stopPropagation()} />,
            <span className="font-mono text-[11px] text-ink-500">{r.caseId}</span>,
            <span className="block max-w-[240px] truncate" title={r.title}>{r.title}</span>,
            <span className="block max-w-[92px] truncate text-[11px] text-ink-500" title={r.module}>{r.module}</span>,
            <span title={r.reason}><Tag t={r.kindLabel} c={TONE[r.kind] ?? "gray"} dot={false} /></span>,
            <span className="block max-w-[150px]" title={r.pagePath}>
              {r.source === "human"
                ? <span className="flex items-center gap-1.5 text-[12px] text-ink-700">
                    <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                    <span className="truncate">{r.pageName}</span>
                  </span>
                : <span className="block truncate text-[11px] text-ink-400">{r.pageName || "未绑定"}</span>}
              <span className="block truncate text-[10px] text-ink-400">{r.poName || (r.pageId ? "无流程" : "—")}</span>
            </span>,
            r.source === "human"
              ? <Tag t="人工" c="green" dot={false} />
              : r.source === "rule" ? <Tag t="规则" c="amber" dot={false} /> : <Tag t="无" c="gray" dot={false} />,
            <span className="block max-w-[300px] truncate text-[11px] text-ink-500" title={r.reason}>{r.reason}</span>,
          ])}
          empty="没有匹配的用例"
          actions={(i) => (
            <Btn v="secondary" size="sm" onClick={(e) => { e.stopPropagation(); setBindTarget(rows[i]); }}>改绑定</Btn>
          )}
        />
      </Card>

      {bindTarget && (
        <CaseBindingModal
          caseId={bindTarget.caseId}
          caseTitle={bindTarget.title}
          module={bindTarget.module}
          current={bindTarget}
          suggestion={bindTarget.source === "human" ? undefined : {
            pageId: bindTarget.suggestPageId, pageName: bindTarget.suggestPageName,
            poName: bindTarget.suggestPoName, kind: bindTarget.kind, reason: bindTarget.reason,
          }}
          onClose={() => setBindTarget(null)}
          onSaved={() => { reload(); toast("绑定已保存"); }}
        />
      )}
    </div>
  );
}
