import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { webuiApi, type UiBatchDetail } from "@/api/webui";
import { useAsync } from "@/hooks/useAsync";
import { Btn, Card, Empty, Modal, Stat, Table, Tag } from "@/components/ui";
import { DetailDrawer } from "@/components/business";

const tone = (v: string) => (v === "通过" ? "green" : v === "失败" ? "red" : "amber");

export function UiRunBatch() {
  const { pid = "ecommerce", runId = "" } = useParams<{ pid: string; runId: string }>();
  const navigate = useNavigate();
  const { data, loading } = useAsync<UiBatchDetail | null>(
    async () => (runId ? await webuiApi.batchDetail(runId) : null), [runId], null);
  const [caseDetail, setCaseDetail] = useState<UiBatchDetail["cases"][number] | null>(null);
  const [lightbox, setLightbox] = useState<{ url: string; caption: string } | null>(null);

  if (!data) {
    return (
      <Card title="批次详情">
        <Empty text={loading ? "加载中…" : "批次不存在或已被清理"} />
        <div className="mt-3">
          <Btn v="ghost" size="sm" onClick={() => navigate(`/project/${pid}/webui/runs`)}>← 返回执行记录</Btn>
        </div>
      </Card>
    );
  }

  const media = caseDetail?.media;

  return (
    <div className="space-y-4">
      <Card title={`批次详情 · ${data.title}`} extra={
        <div className="flex items-center gap-2">
          <span className="font-mono text-[11px] text-ink-400">{data.id}</span>
          <Btn v="ghost" size="sm" onClick={() => navigate(`/project/${pid}/webui/runs`)}>← 返回执行记录</Btn>
        </div>
      }>
        <div className="grid grid-cols-5 gap-3">
          <Stat label="用例数" value={data.executed} hint={`计划 ${data.total} 条`} />
          <Stat label="通过" value={data.passed} />
          <Stat label="失败" value={data.failed} />
          <Stat label="通过率" value={`${data.passRate ?? 0}%`} />
          <Stat label="总耗时" value={`${data.totalSeconds ?? 0}s`} hint={`写操作 ${data.writeExecuted} 条`} />
        </div>
        <div className="mt-3 flex flex-wrap items-center gap-x-6 gap-y-1 text-[11px] text-ink-500">
          <span>开始时间：{data.startedAt || "—"}</span>
          <span>媒体：{((data.mediaBytes || 0) / 1024 / 1024).toFixed(1)} MB</span>
          {data.skippedCount > 0 && <span className="text-amber-600">跳过 {data.skippedCount} 条（写操作配额）</span>}
          {data.mediaPruned && <span className="text-amber-600">媒体已按 5GB 容量策略清理</span>}
        </div>
      </Card>

      <Card title="批次内用例" extra={<span className="text-[11px] text-ink-400">点击任意一条查看每步截图与视频</span>}>
        <Table
          cols={["用例", "模块", "Page Object", "结果", "断言", "耗时", "证据"]}
          rows={data.cases.map((c) => [
            <span className="flex flex-col">
              <span className="truncate text-ink-800">{c.caseTitle}</span>
              <span className="font-mono text-[10px] text-ink-400">{c.caseId}</span>
            </span>,
            c.module,
            c.pageObject || "—",
            <span className="flex items-center gap-1.5">
              <Tag t={c.verdict} c={tone(c.verdict)} dot={false} />
              {c.writeFlow && <Tag t="写操作" c="amber" dot={false} />}
            </span>,
            `${c.assertionsPassed}/${c.assertions}`,
            `${c.seconds}s`,
            <span className="text-[11px] text-ink-600">{c.media.steps.length} 张 / {c.media.video ? "1 段" : "无"}</span>,
          ])}
          loading={loading}
          empty="该批次没有用例记录"
          onRowClick={(i) => setCaseDetail(data.cases[i])}
          actions={(i) => (
            <Btn v="ghost" size="sm" onClick={(e) => { e.stopPropagation(); setCaseDetail(data.cases[i]); }}>详情</Btn>
          )}
        />
      </Card>

      {data.skippedCases.length > 0 && (
        <Card title={`未执行（${data.skippedCases.length} 条）`}>
          <div className="space-y-1.5">
            {data.skippedCases.map((s) => (
              <div key={s.caseId} className="rounded-lg border border-amber-100 bg-amber-50/40 px-3 py-1.5 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-ink-400">{s.caseId}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-800">{s.caseTitle}</span>
                </div>
                <div className="mt-0.5 text-amber-700">{s.reason}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      {data.failures.length > 0 && (
        <Card title="失败明细">
          <div className="space-y-1.5">
            {data.failures.map((f) => (
              <div key={f.caseId} className="rounded-lg border border-red-100 bg-red-50/40 px-3 py-1.5 text-[11px]">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-ink-400">{f.caseId}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-800">{f.caseTitle}</span>
                </div>
                <div className="mt-0.5 text-red-600">{f.failedStep} · {f.detail}</div>
              </div>
            ))}
          </div>
        </Card>
      )}

      <DetailDrawer
        open={!!caseDetail}
        title={caseDetail ? `执行详情 · ${caseDetail.caseTitle}` : ""}
        onClose={() => setCaseDetail(null)}
        width="max-w-2xl"
        fields={caseDetail ? [
          { label: "用例", value: <span className="font-mono text-[11px]">{caseDetail.caseId}</span> },
          { label: "结果", value: <Tag t={caseDetail.verdict} c={tone(caseDetail.verdict)} dot={false} /> },
          { label: "断言", value: `${caseDetail.assertionsPassed}/${caseDetail.assertions}` },
          { label: "耗时", value: `${caseDetail.seconds}s` },
          { label: "最终页面", value: <span className="break-all font-mono text-[10px] text-brand-600">{caseDetail.finalUrl || "—"}</span> },
          ...(caseDetail.orderNos.length ? [{ label: "真实订单号", value: <span className="font-mono text-[11px] text-green-700">{caseDetail.orderNos.join(", ")}</span> }] : []),
        ] : []}
      >
        {caseDetail && (
          <div className="space-y-5 text-xs">
            <div>
              <div className="mb-2 flex items-center justify-between">
                <span className="text-ink-500">步骤截图（{media?.steps.length ?? 0} 张）</span>
                <span className="text-[10px] text-ink-400">点击可放大</span>
              </div>
              {media && media.steps.length > 0 ? (
                <div className="grid grid-cols-2 gap-2">
                  {media.steps.map((s) => {
                    const step = caseDetail.steps.find((x) => x.index === s.index);
                    return (
                      <button key={s.name} onClick={() => setLightbox({ url: s.url, caption: `步骤 ${s.index} · ${step?.raw ?? ""}` })}
                        className="overflow-hidden rounded-lg border border-line text-left">
                        <img src={s.url} alt={`步骤 ${s.index}`} className="aspect-video w-full object-cover object-top" />
                        <div className="truncate px-2 py-1 text-[10px] text-ink-500">步骤 {s.index} · {step?.raw ?? s.name}</div>
                      </button>
                    );
                  })}
                </div>
              ) : (
                <Empty text={data.mediaPruned ? "媒体已按 5GB 容量策略清理" : "本次执行没有留存步骤截图"} />
              )}
            </div>

            <div>
              <div className="mb-2 text-ink-500">执行视频</div>
              {media?.videoUrl ? (
                <video src={media.videoUrl} controls preload="metadata" className="w-full rounded-lg border border-line bg-ink-950" />
              ) : (
                <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-ink-400">
                  {data.mediaPruned ? "视频已按 5GB 容量策略清理" : "本次执行未录制视频"}
                </div>
              )}
            </div>

            <div>
              <div className="mb-2 text-ink-500">执行步骤</div>
              <div className="overflow-hidden rounded-lg border border-line">
                {caseDetail.steps.map((s) => (
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
