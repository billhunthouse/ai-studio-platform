import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { webuiApi, type UiRunItem, type UiRunsPayload } from "@/api/webui";
import { useAsync } from "@/hooks/useAsync";
import { Btn, Card, Empty, Modal, Stat, Table, Tag } from "@/components/ui";
import { DetailDrawer } from "@/components/business";

const EMPTY: UiRunsPayload = {
  items: [],
  stats: { total: 0, passed: 0, failed: 0, avgSeconds: 0, batches: 0, singles: 0 },
  media: { usage: "0 MB / 5 GB", usedMB: 0, budgetGB: 5, runs: 0 },
};

const verdictTone = (v: string) => (v === "通过" || v === "成功" ? "green" : v === "失败" ? "red" : v === "执行中" ? "blue" : v === "未执行" ? "gray" : "amber");

export function UiRuns() {
  const { pid = "ecommerce" } = useParams<{ pid: string }>();
  const navigate = useNavigate();
  const { data, loading } = useAsync(() => webuiApi.runs(), [], EMPTY);
  const [detail, setDetail] = useState<UiRunItem | null>(null);
  const [lightbox, setLightbox] = useState<{ url: string; caption: string } | null>(null);

  const open = (item: UiRunItem) => {
    if (item.kind === "batch") navigate(`/project/${pid}/webui/runs/${encodeURIComponent(item.id)}`);
    else setDetail(item);
  };

  const media = detail?.media;

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-5 gap-4">
        <Stat label="执行总数" value={data.stats.total} hint={`单条 ${data.stats.singles} · 批次 ${data.stats.batches}`} />
        <Stat label="成功" value={data.stats.passed} />
        <Stat label="失败" value={data.stats.failed} />
        <Stat label="平均耗时" value={`${data.stats.avgSeconds}s`} />
        <Stat label="媒体占用" value={data.media.usage} hint="超过 5GB 自动清理最旧媒体" />
      </div>

      <Card title="执行记录" extra={<span className="text-[11px] text-ink-400">倒序 · 批量执行折叠为一条批次，点进去看逐条明细</span>}>
        <Table
          cols={["名称", "类型", "用例数", "结果", "截图/视频", "执行时间", "耗时"]}
          rows={data.items.map((r) => [
            <span className="flex flex-col">
              <span className="truncate text-ink-800">{r.title}</span>
              <span className="font-mono text-[10px] text-ink-400">{r.id}{r.caseId ? ` · ${r.caseId}` : ""}</span>
            </span>,
            <Tag t={r.kind === "batch" ? "批次" : "单条"} c={r.kind === "batch" ? "blue" : "gray"} dot={false} />,
            r.kind === "batch" ? `${r.caseCount} 条` : "1 条",
            <span className="flex items-center gap-1.5">
              <Tag t={r.verdict} c={verdictTone(r.verdict)} dot={false} />
              {r.kind === "batch" && r.failed > 0 && <span className="text-[10px] text-red-500">{r.failed} 失败</span>}
            </span>,
            <span className="text-[11px] text-ink-600">
              {r.shots > 0 ? `${r.shots} 张` : "—"} / {r.hasVideo ? "1 段" : "无"}
              {r.mediaPruned && <span className="ml-1 text-[10px] text-amber-600">（已清理）</span>}
            </span>,
            r.time,
            r.duration,
          ])}
          loading={loading}
          empty="还没有执行记录，去「用例脚本」跑一条试试"
          onRowClick={(i) => open(data.items[i])}
          actions={(i) => (
            <Btn v="ghost" size="sm" onClick={(e) => { e.stopPropagation(); open(data.items[i]); }}>
              {data.items[i].kind === "batch" ? "查看批次" : "详情"}
            </Btn>
          )}
        />
      </Card>

      <DetailDrawer
        open={!!detail}
        title={detail ? `执行详情 · ${detail.title}` : ""}
        onClose={() => setDetail(null)}
        width="max-w-2xl"
        fields={detail ? [
          { label: "用例", value: <span className="font-mono text-[11px]">{detail.caseId || "—"}</span> },
          { label: "浏览器", value: detail.browser },
          { label: "结果", value: <Tag t={detail.verdict} c={verdictTone(detail.verdict)} dot={false} /> },
          { label: "断言", value: `${detail.assertionsPassed}/${detail.assertions}` },
          { label: "执行时间", value: detail.time },
          { label: "耗时", value: detail.duration },
          { label: "最终页面", value: <span className="break-all font-mono text-[10px] text-brand-600">{detail.finalUrl || "—"}</span> },
          ...(detail.orderNo ? [{ label: "真实订单号", value: <span className="font-mono text-[11px] text-green-700">{detail.orderNo}</span> }] : []),
        ] : []}
      >
        {detail && (
          <div className="space-y-5 text-xs">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-ink-500">步骤截图（{media?.steps.length ?? 0} 张）</span>
                <span className="text-[10px] text-ink-400">点击可放大</span>
              </div>
              {media && media.steps.length > 0 ? (
                <div className="grid grid-cols-2 gap-2">
                  {media.steps.map((s) => {
                    const step = detail.steps.find((x) => x.index === s.index);
                    return (
                      <button key={s.name} onClick={() => setLightbox({ url: s.url, caption: `步骤 ${s.index} · ${step?.raw ?? ""}` })}
                        className="group overflow-hidden rounded-lg border border-line text-left">
                        <img src={s.url} alt={`步骤 ${s.index}`} className="aspect-video w-full object-cover object-top transition group-hover:opacity-90" />
                        <div className="truncate px-2 py-1 text-[10px] text-ink-500">步骤 {s.index} · {step?.raw ?? s.name}</div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <Empty text={detail.mediaPruned ? "媒体已按 5GB 容量策略清理" : "本次执行没有留存步骤截图"} />
              )}
            </div>

            <div>
              <div className="mb-2 text-ink-500">执行视频</div>
              {media?.videoUrl ? (
                <video src={media.videoUrl} controls preload="metadata" className="w-full rounded-lg border border-line bg-ink-950" />
              ) : (
                <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-ink-400">
                  {detail.mediaPruned ? "视频已按 5GB 容量策略清理" : "本次执行未录制视频"}
                </div>
              )}
            </div>

            <div>
              <div className="mb-2 text-ink-500">执行步骤</div>
              <div className="overflow-hidden rounded-lg border border-line">
                {detail.steps.length === 0 && <div className="px-3 py-2 text-[11px] text-ink-400">历史记录未留存步骤明细</div>}
                {detail.steps.map((s) => (
                  <div key={s.index} className="flex items-center gap-2 border-b border-line/60 px-2.5 py-1 text-[11px] last:border-0">
                    <span className="w-5 font-mono text-ink-400">{s.index}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-700">{s.raw}</span>
                    <span className="font-mono text-[10px] text-ink-400">{s.keyword}</span>
                    <span className={s.status === "passed" ? "text-green-600" : s.status === "failed" ? "text-red-600" : "text-amber-600"}>
                      {s.status === "passed" ? "通过" : s.status === "failed" ? "失败" : "待补全"}
                    </span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        )}
      </DetailDrawer>

      <Modal open={!!lightbox} title={lightbox?.caption ?? "步骤截图"} width="max-w-5xl" onClose={() => setLightbox(null)}
        footer={<Btn v="ghost" onClick={() => setLightbox(null)}>关闭</Btn>}>
        {lightbox && <img src={lightbox.url} alt={lightbox.caption} className="w-full rounded-lg border border-line" />}
      </Modal>
    </div>
  );
}
