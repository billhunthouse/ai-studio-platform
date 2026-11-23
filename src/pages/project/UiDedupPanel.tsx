import { useState } from "react";
import { webuiApi } from "@/api";
import type { UiDedupPayload } from "@/api/webui";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Table, Tag } from "@/components/ui";

/**
 * 用例去重合并面板。
 *
 * 为什么放在绑定体检页：363 条用例里 294 条是同一件事被登记多次，
 * 人一看到这个量就放弃评审——绑定确认率永远上不去。先去重，再谈绑定，
 * 顺序反过来做不动。
 *
 * 合并是三段式、可回滚的：
 *   预览（只读看明细）→ 执行（副本归档 + 需求/模块聚合）→ 回滚（清标记还原）
 * 副本不删除，只打 archived 标记，所以任何一步都能退回去。
 */
export function UiDedupPanel({ onChanged }: { onChanged: () => void }) {
  const { toast } = useApp();
  const { data, loading, reload } = useAsync<UiDedupPayload | null>(async () => await webuiApi.dedup(), [], null);
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);

  const run = async (kind: "apply" | "restore") => {
    setBusy(true);
    try {
      if (kind === "apply") {
        const r = await webuiApi.dedupApply();
        toast(`已合并 ${r.groupsMerged} 组，归档 ${r.casesArchived} 条副本：${r.before} → ${r.after} 条`);
      } else {
        const r = await webuiApi.dedupRestore();
        toast(`已回滚：恢复 ${r.restored} 条副本，清理 ${r.primariesCleared} 条主用例的合并标记`);
      }
      reload();
      onChanged();
    } catch (e) {
      toast(e instanceof Error ? e.message : "操作失败");
    } finally { setBusy(false); }
  };

  const d = data;
  const merged = (d?.alreadyArchived ?? 0) > 0;
  const pending = (d?.duplicates ?? 0) > 0;

  return (
    <Card
      title="用例去重合并"
      extra={d ? (
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-ink-400">
            {merged
              ? `已归档 ${d.alreadyArchived} 条副本 · 在册 ${d.active} 条`
              : `${d.active} 条 · ${d.uniqueTitles} 个唯一场景`}
          </span>
          <Btn v="secondary" size="sm" onClick={() => setOpen(!open)} disabled={!pending && !merged}>
            {open ? "收起明细" : "查看明细"}
          </Btn>
          {pending && (
            <Btn size="sm" disabled={busy} onClick={() => void run("apply")}>
              执行合并
            </Btn>
          )}
          {merged && (
            <Btn v="secondary" size="sm" disabled={busy} onClick={() => void run("restore")}>
              回滚去重
            </Btn>
          )}
        </div>
      ) : undefined}
    >
      <div className="grid grid-cols-2 gap-3 pb-1 lg:grid-cols-4">
        <Cell label="在册用例" value={d?.active ?? "—"} sub={merged ? "副本已归档，统计口径已收敛" : "含重复副本"} />
        <Cell label="唯一场景" value={d?.uniqueTitles ?? "—"} tone="good"
          sub={merged ? "每条场景只剩一条用例" : `${d?.groups ?? 0} 组存在重复`} />
        <Cell label="可归档副本" value={d?.duplicates ?? "—"} tone={pending ? "warn" : undefined}
          sub={merged
            ? `已归档 ${d?.mergedDuplicates ?? 0} 条（${d?.mergedGroups ?? 0} 组）`
            : `占比 ${d?.duplicateRate ?? 0}%`} />
        <Cell label="合并后" value={d?.afterMerge ?? "—"} tone="good"
          sub={`跨模块重复 ${(merged ? d?.mergedCrossModuleGroups : d?.crossModuleGroups) ?? 0} 组`
            + ` · 内容有差异 ${d?.contentVariesGroups ?? 0} 组`} />
      </div>

      <p className="pt-2 text-[11.5px] leading-5 text-ink-500">
        同一件事被生成器按需求逐条套模板，挂到多个需求和模块下。合并保留一条主用例，
        副本标记归档，<span className="text-ink-700">需求与模块关联聚合到主用例</span>——
        “一条用例覆盖 6 个需求”这个事实保留下来，重复执行被去掉。
        副本不删除，随时可回滚。
      </p>

      {open && (
        <div className="pt-3">
          <Table
            cols={["状态", "主用例", "场景", "副本", "涉及模块", "覆盖需求", "选它的原因"]}
            loading={loading}
            rows={(d?.items ?? []).map((g) => [
              g.status === "merged"
                ? <Tag t="已归档" c="gray" dot={false} />
                : <Tag t="待合并" c="amber" dot={false} />,
              <span className="font-mono text-[11px] text-ink-600">{g.primary}</span>,
              <span className="block max-w-[240px] truncate text-[12px] text-ink-800" title={g.title}>
                {g.title}
                {g.contentVaries && <Tag t="含变体" c="amber" dot={false} />}
              </span>,
              <span className="tabular-nums text-[12px] text-ink-700">
                {g.duplicateCount > 0 ? `+${g.duplicateCount}` : "—"}
              </span>,
              <span className="block max-w-[160px] truncate text-[11px] text-ink-500" title={g.modules.join(" / ")}>
                {g.crossModule && <Tag t="跨模块" c="amber" dot={false} />}
                {g.modules.join(" / ") || "—"}
              </span>,
              <span className="tabular-nums text-[11px] text-ink-600">{g.requirementIds.length}</span>,
              <span className="block max-w-[200px] truncate text-[11px] text-ink-500" title={g.primaryReason}>
                {g.primaryReason}
              </span>,
            ])}
            empty="没有重复用例"
          />
        </div>
      )}
    </Card>
  );
}

function Cell({ label, value, sub, tone }: { label: string; value: string | number; sub?: string; tone?: "good" | "warn" }) {
  const color = tone === "good" ? "text-emerald-600" : tone === "warn" ? "text-amber-600" : "text-ink-900";
  return (
    <div className="rounded-lg border border-line bg-ink-50 px-3 py-2">
      <div className="text-[11px] text-ink-500">{label}</div>
      <div className={`mt-0.5 text-lg font-semibold tabular-nums ${color}`}>{value}</div>
      {sub && <div className="text-[10.5px] leading-4 text-ink-400">{sub}</div>}
    </div>
  );
}
