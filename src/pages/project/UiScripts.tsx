import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { webuiApi, type UiCaseIndexItem, type UiRunOneResult } from "@/api/webui";
import type { UiScript } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Empty, Input, Modal, Tag } from "@/components/ui";
import { MonacoEditor } from "@/components/business";
import { cx } from "@/lib/cx";

type CompileDetail = {
  caseId: string; title: string; total: number; executable: number; unknown: number; ready: boolean;
};
type StepResult = {
  index: number; raw: string; keyword: string; status: string; detail: string; shot?: string;
};
type RunResult = {
  caseId: string; caseTitle: string; verdict: string; durationMs: number; screenshot: string;
  steps: StepResult[];
};

type BatchResult = {
  generatedAt: string; target: string; batchId?: string;
  compiled: { total: number; ready: number; partial: number; blocked: number };
  executed: number; passed: number; failed: number; partial: number; skippedCount: number;
  passRate: number; totalSeconds: number; writeExecuted: number;
  byPageObject: Record<string, { total: number; passed: number; failed: number; partial: number }>;
  failures: Array<{ caseId: string; caseTitle: string; pageObject: string; failedStep: string; detail: string; finalUrl: string; screenshot: string }>;
  skippedCases: Array<{ caseId: string; caseTitle: string; pageObject: string; reason: string }>;
  results: Array<{
    caseId: string; caseTitle: string; module: string; pageObject: string; writeFlow: boolean;
    verdict: string; assertions: number; assertionsPassed: number;
    finalUrl: string; pageText: string; orderNos: string[]; screenshot: string; seconds: number;
    steps: StepResult[];
  }>;
};

const STATUS_CN: Record<string, string> = {
  passed: "通过", failed: "失败", blocked: "待补全", skipped: "跳过",
};

export function UiScripts() {
  const { data, setData, reload } = useAsync(() => webuiApi.scripts(), [], [] as UiScript[]);
  const [selected, setSelected] = useState<string | null>(null);
  const [draft, setDraft] = useState("");
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("");
  const [compiling, setCompiling] = useState(false);
  const [running, setRunning] = useState(false);
  const [compileInfo, setCompileInfo] = useState<{
    total: number; ready: number; partial: number; blocked: number; details: CompileDetail[];
  } | null>(null);
  const [results, setResults] = useState<RunResult[] | null>(null);
  const [pool, setPool] = useState<{ browserAlive: boolean; activeContexts: number } | null>(null);
  const [limit, setLimit] = useState(120);
  const [maxWrite, setMaxWrite] = useState(8);
  const [batch, setBatch] = useState<{ jobId: string; status: string; index: number; total: number; current: string } | null>(null);
  const [batchResult, setBatchResult] = useState<BatchResult | null>(null);
  // 单条执行
  const [index, setIndex] = useState<{ total: number; ready: number; writeFlows: number; cases: UiCaseIndexItem[] } | null>(null);
  const [q, setQ] = useState("");
  const [targetId, setTargetId] = useState("");
  const [allowWrite, setAllowWrite] = useState(false);
  const [onlyConfirmed, setOnlyConfirmed] = useState(false);
  const [one, setOne] = useState<UiRunOneResult | null>(null);
  const [oneRunning, setOneRunning] = useState(false);
  const [shotOpen, setShotOpen] = useState(false);
  const [scriptOpen, setScriptOpen] = useState(false);
  const [expandedStep, setExpandedStep] = useState<number | null>(null);
  const [picked, setPicked] = useState<string[]>([]);
  const [batchLink, setBatchLink] = useState("");
  const { addTask, toast } = useApp();
  const navigate = useNavigate();
  const script = data.find((s) => s.id === selected) ?? data[0];

  useEffect(() => {
    webuiApi.caseIndex().then(setIndex).catch(() => undefined);
  }, []);

  // 支持从其它页面深链过来：?caseId=TC-1001 自动选中该用例
  const [params] = useSearchParams();
  useEffect(() => {
    const cid = params.get("caseId");
    if (cid) { setTargetId(cid); setQ(cid); }
  }, [params]);

  const target = index?.cases.find((c) => c.caseId === targetId);
  const kw = q.trim();
  const candidates = (index?.cases ?? []).filter(
    (c) => !kw || c.caseId.toLowerCase().includes(kw.toLowerCase())
      || c.title.includes(kw) || c.module.includes(kw) || c.pageObject.includes(kw),
  );

  const togglePick = (caseId: string) =>
    setPicked((p) => (p.includes(caseId) ? p.filter((x) => x !== caseId) : [...p, caseId]));
  const pickedInView = candidates.filter((c) => picked.includes(c.caseId));
  const allPicked = candidates.length > 0 && pickedInView.length === candidates.length;
  const togglePickAll = () => {
    if (allPicked) setPicked((p) => p.filter((id) => !candidates.some((c) => c.caseId === id)));
    else setPicked((p) => Array.from(new Set([...p, ...candidates.map((c) => c.caseId)])));
  };

  /** 单条用例：真实驱动浏览器跑一遍，逐步回放每步状态与断言 */
  const runOne = async (item?: UiCaseIndexItem) => {
    const c = item ?? target;
    if (!c) { toast("请先在上方列表选择一条用例"); return; }
    if (c.writeFlow && !allowWrite) { toast("这条用例会真实下单/支付，请先勾选「允许真实写操作」"); return; }
    setTargetId(c.caseId);
    setOneRunning(true);
    setOne(null);
    setExpandedStep(null);
    addTask(`UI 单条执行 · ${c.caseId}`, "WebUI");
    try {
      const r = await webuiApi.runOne({ caseId: c.caseId, delayMs: 300, force: c.writeFlow && allowWrite });
      setOne(r);
      toast(`${r.caseId} 执行完成：${r.verdict} · 断言 ${r.assertionsPassed}/${r.assertions} · ${(r.durationMs / 1000).toFixed(1)}s`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "执行失败");
    } finally {
      setOneRunning(false);
    }
  };

  /** 勾选多条 → 作为一次批量执行（执行记录里折叠成一条批次） */
  const runSelected = async () => {
    const items = picked
      .map((id) => index?.cases.find((c) => c.caseId === id))
      .filter(Boolean) as UiCaseIndexItem[];
    if (items.length === 0) { toast("请先勾选用例"); return; }
    const writeCount = items.filter((x) => x.writeFlow).length;
    if (writeCount > 0 && !allowWrite) {
      toast(`选中的用例里有 ${writeCount} 条会真实下单/支付，请先勾选「允许真实写操作」`);
      return;
    }
    if (items.length === 1) { await runOne(items[0]); return; }

    setOneRunning(true);
    setOne(null);
    setBatchResult(null);
    setBatchLink("");
    addTask(`UI 批量执行 · ${items.length} 条`, "WebUI");
    try {
      const r = await webuiApi.runBatch({
        limit: items.length,
        maxWrite: allowWrite ? Math.max(maxWrite, writeCount) : 0,
        delayMs: 300,
        caseIds: items.map((x) => x.caseId),
        onlyConfirmed,
      });
      setBatch({ jobId: r.jobId, status: "running", index: 0, total: items.length, current: "启动中…" });
      void poll(r.jobId);
    } catch (e) {
      toast(e instanceof Error ? e.message : "批量执行失败");
      setOneRunning(false);
    }
  };


  useEffect(() => {
    if (script) { setSelected(script.id); setDraft(script.content); }
  }, [script?.id]);

  useEffect(() => {
    webuiApi.poolStatus().then((s) => setPool(s)).catch(() => undefined);
  }, [results]);

  /** 第一步：批量编译功能测试用例 → 可复用脚本（一次编译、处处复用） */
  const compile = async (overwrite = false) => {
    setCompiling(true);
    try {
      const r = await webuiApi.compile({ overwrite });
      const info = { total: r.stats.total, ready: r.stats.ready, partial: r.stats.partial, blocked: r.stats.blocked, details: r.details };
      setCompileInfo(info);
      await reload();
      addTask(`UI 自动化编译 · ${r.created} 条脚本`, "WebUI");
      toast(`编译完成：${r.stats.ready} 条可直接执行，${r.stats.partial} 条需补全定位器`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "编译失败");
    } finally {
      setCompiling(false);
    }
  };

  /** 第二步：批量真实执行（后台任务 + 轮询）——100+ 条同步会 HTTP 超时 */
  const runAll = async () => {
    setRunning(true);
    setResults(null);
    setBatchResult(null);
    addTask(`WebUI 批量真实执行 · ${limit} 条`, "WebUI");
    try {
      const r = await webuiApi.runBatch({ limit, maxWrite, delayMs: 300 });
      setBatch({ jobId: r.jobId, status: "running", index: 0, total: limit, current: "启动中…" });
      void poll(r.jobId);
    } catch (e) {
      toast(e instanceof Error ? e.message : "执行失败");
      setRunning(false);
    }
  };

  const poll = async (jobId: string) => {
    try {
      const s = await webuiApi.runBatchStatus(jobId);
      setBatch({ jobId, status: s.status, index: s.index, total: s.total, current: s.current });
      if (s.status === "running") {
        window.setTimeout(() => void poll(jobId), 2500);
        return;
      }
      setRunning(false);
      setOneRunning(false);
      if (s.status === "finished" && s.result) {
        setBatchResult(s.result);
        if (s.result.batchId) setBatchLink(`/project/ecommerce/webui/runs/${s.result.batchId}`);
        toast(`真实执行完成：通过 ${s.result.passed} / 失败 ${s.result.failed} / 共 ${s.result.executed} 条`);
      } else {
        toast(s.error || "执行任务失败");
      }
    } catch (e) {
      setRunning(false);
      setOneRunning(false);
      toast(e instanceof Error ? e.message : "轮询失败");
    }
  };

  const save = async () => {
    if (!script) return;
    const updated = await webuiApi.saveScript(script.id, draft);
    setData(data.map((s) => (s.id === updated.id ? updated : s)));
    toast("脚本已保存");
  };

  const create = async () => {
    if (!name.trim()) { toast("请输入脚本名称"); return; }
    const created = await webuiApi.createScript(name, "# 自定义 Playwright 脚本\n", "Playwright · 自定义");
    setData([created, ...data]);
    setSelected(created.id);
    setOpen(false);
    setName("");
    toast("脚本已创建");
  };

  const selectedResult = results?.find((r) => r.caseId === script?.caseId);

  return (
    <div className="space-y-4">
      {/* 单条用例执行：选一条 → 真实跑一遍 → 逐步回放 */}
      <Card title="单条用例执行" extra={
        <span className="text-[11px] text-ink-500">
          {index ? `${index.ready}/${index.total} 条可直接执行 · 写操作用例 ${index.writeFlows} 条` : "正在加载用例索引…"}
        </span>
      }>
        <div className="flex flex-wrap items-center gap-2">
          <Input className="w-72" value={q} onChange={(e) => setQ(e.target.value)}
            placeholder="搜索用例 ID / 标题 / 模块，如 TC-1001 或 登录" />
          <Btn onClick={() => void runOne()} disabled={!target || oneRunning || (target.writeFlow && !allowWrite)}>
            {oneRunning ? "真实执行中…" : "运行这条用例"}
          </Btn>
          <Btn v="secondary" onClick={() => void runSelected()} disabled={picked.length === 0 || oneRunning}>
            {oneRunning ? "执行中…" : `执行选中 ${picked.length} 条`}
          </Btn>
          <label className="flex items-center gap-1.5 text-[11px] text-ink-600">
            <input type="checkbox" className="accent-brand-600" checked={allowWrite}
              onChange={(e) => setAllowWrite(e.target.checked)} />
            允许真实写操作（下单 / 支付）
          </label>
          <label className="flex items-center gap-1.5 text-[11px] text-ink-600" title="只跑页面绑定已人工确认的用例，避免用无关流程刷通过率">
            <input type="checkbox" className="accent-brand-600" checked={onlyConfirmed}
              onChange={(e) => setOnlyConfirmed(e.target.checked)} />
            只跑已确认绑定
          </label>
          <span className="text-[11px] text-ink-400">真实浏览器逐步执行 · 步骤间 300ms · 返回断言与截图</span>
        </div>

        <div className="mt-2 overflow-hidden rounded-lg border border-line">
          <div className="flex items-center gap-2 border-b border-line bg-ink-50/60 px-2.5 py-1.5 text-[10px] text-ink-500">
            <input type="checkbox" className="accent-brand-600" checked={allPicked} onChange={togglePickAll} />
            <span>全选当前 {candidates.length} 条</span>
            <span className="ml-auto">已勾选 {picked.length} 条{pickedInView.length !== picked.length ? `（本页 ${pickedInView.length}）` : ""}</span>
          </div>
          <div className="max-h-56 overflow-auto">
            {candidates.length === 0 && (
              <div className="px-3 py-4 text-[11px] text-ink-400">
                {index ? "没有匹配的用例" : "加载中…"}
              </div>
            )}
            {candidates.map((c) => (
              <div key={c.caseId}
                className={cx("flex items-center gap-2 border-b border-line/60 px-2.5 py-1.5 text-[11px] last:border-0",
                  c.caseId === targetId ? "bg-brand-50" : "hover:bg-ink-50")}>
                <input type="checkbox" className="accent-brand-600" checked={picked.includes(c.caseId)}
                  onChange={() => togglePick(c.caseId)} title="勾选后可批量执行" />
                <button onClick={() => setTargetId(c.caseId)} className="flex min-w-0 flex-1 items-center gap-2 text-left">
                  <span className="w-20 shrink-0 font-mono text-ink-400">{c.caseId}</span>
                  <span className={cx("min-w-0 flex-1 truncate", c.caseId === targetId ? "text-brand-700" : "text-ink-800")}>{c.title}</span>
                  <span className="w-28 shrink-0 truncate text-ink-400">{c.pageObject || "无 UI 流程"}</span>
                  <span className="w-16 shrink-0 text-right text-ink-400">{c.executable}/{c.totalSteps} 步</span>
                  {c.assertions > 0 && <span className="w-12 shrink-0 text-right text-ink-400">{c.assertions} 断言</span>}
                  {c.writeFlow && <Tag t="写操作" c="amber" dot={false} />}
                  {!c.ready && <Tag t="需补全" c="gray" dot={false} />}
                </button>
              </div>
            ))}
          </div>
        </div>

        <div className="mt-2 text-[11px] text-ink-500">
          {target ? (
            <>
              已选 <span className="font-mono text-ink-700">{target.caseId}</span>
              {" · "}{target.module}{" · "}{target.pageObject || "无对应 Page Object"}
              {" · "}断言 {target.assertions} 个
              {target.writeFlow && <span className="text-amber-600"> · 该用例会真实创建订单，需勾选写操作确认</span>}
            </>
          ) : "从列表里选一条用例：直接点「运行这条用例」即由平台驱动浏览器按步骤执行"}
        </div>
      </Card>

      {/* 单条执行回放 */}
      {one && (
        <Card title="单条执行回放" extra={
          <span className="flex items-center gap-2 text-[11px] text-ink-500">
            <span className="font-mono">{one.runId}</span>
            <span>{(one.durationMs / 1000).toFixed(1)}s</span>
            <Tag t={one.verdict} c={one.verdict === "通过" ? "green" : one.verdict === "失败" ? "red" : "amber"} dot={false} />
          </span>
        }>
          <div className="grid grid-cols-4 gap-2">
            {[
              { label: "结论", value: one.verdict, c: one.verdict === "通过" ? "text-green-600" : one.verdict === "失败" ? "text-red-600" : "text-amber-600" },
              { label: "步骤", value: `${one.steps.filter((s) => s.status === "passed").length}/${one.steps.length} 通过`, c: "text-ink-800" },
              { label: "业务断言", value: `${one.assertionsPassed}/${one.assertions}`, c: "text-ink-800" },
              { label: "Page Object", value: one.pageObject || "—", c: "text-brand-600" },
            ].map((x) => (
              <div key={x.label} className="rounded-lg border border-line px-3 py-2">
                <div className="text-[10px] text-ink-500">{x.label}</div>
                <div className={cx("mt-0.5 truncate text-sm font-semibold", x.c)}>{x.value}</div>
              </div>
            ))}
          </div>

          <div className="mt-1 text-[10px] text-ink-400">点击任意步骤，查看它实际执行的关键字、定位器与输入值</div>
          <div className="mt-1 overflow-hidden rounded-lg border border-line">
            <div className="grid grid-cols-[18px_32px_1.4fr_70px_58px_1.5fr] gap-2 border-b border-line bg-ink-50/60 px-2.5 py-1.5 text-[10px] font-medium text-ink-500">
              <span /><span>#</span><span>步骤（用例原文 / PO 展开）</span><span>关键字</span><span>耗时</span><span>详情</span>
            </div>
            {one.steps.map((s) => {
              const ir = one.irSteps.find((x) => x.index === s.index);
              const opened = expandedStep === s.index;
              const args = ir ? Object.entries(ir.args)
                .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`).join("  ·  ") : "";
              return (
                <div key={s.index} className="border-b border-line/60 last:border-0">
                  <button onClick={() => setExpandedStep(opened ? null : s.index)}
                    className="grid w-full grid-cols-[18px_32px_1.4fr_70px_58px_1.5fr] items-center gap-2 px-2.5 py-1.5 text-left text-[11px] hover:bg-ink-50/60">
                    <span className={cx("text-[9px] text-ink-400 transition-transform", opened && "rotate-90")}>▶</span>
                    <span className="font-mono text-ink-400">{s.index}</span>
                    <span className={cx("truncate", s.status === "failed" ? "text-red-700" : "text-ink-800")} title={s.raw}>{s.raw}</span>
                    <span className="font-mono text-[10px] text-ink-500">{s.keyword}</span>
                    <span className="text-[10px] text-ink-400">{s.durationMs != null ? `${s.durationMs}ms` : "—"}</span>
                    <span className={cx("truncate text-[10px]",
                      s.status === "failed" ? "text-red-600" : s.status === "blocked" ? "text-amber-600" : "text-ink-400")}
                      title={s.detail}>
                      {s.status === "passed" ? "通过" : s.detail || STATUS_CN[s.status] || s.status}
                    </span>
                  </button>
                  {opened && (
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 border-t border-line/60 bg-ink-50/40 px-3 py-2 text-[10px]">
                      <div><span className="text-ink-400">用例原文：</span><span className="text-ink-700">{s.raw}</span></div>
                      <div><span className="text-ink-400">执行关键字：</span><span className="font-mono text-ink-700">{s.keyword}</span></div>
                      <div className="col-span-2 break-all">
                        <span className="text-ink-400">执行参数：</span>
                        <span className="font-mono text-ink-700">{args || "—（此步无需参数）"}</span>
                      </div>
                      {ir?.note && (
                        <div className="col-span-2"><span className="text-ink-400">PO 展开说明：</span><span className="text-ink-600">{ir.note}</span></div>
                      )}
                      <div className="col-span-2">
                        <span className="text-ink-400">执行详情：</span>
                        <span className={s.status === "failed" ? "text-red-600" : "text-ink-600"}>
                          {s.detail || (s.status === "passed" ? "成功" : STATUS_CN[s.status] || "—")}
                        </span>
                      </div>
                    </div>
                  )}
                </div>
              );
            })}
          </div>

          <div className="mt-3 grid grid-cols-3 gap-3">
            <div className="col-span-2 space-y-2">
              <div className="rounded-lg border border-line px-2.5 py-2 text-[11px]">
                <div className="text-[10px] text-ink-500">最终页面</div>
                <div className="mt-0.5 break-all font-mono text-[10px] text-brand-600">{one.finalUrl || "—"}</div>
              </div>
              <div className="rounded-lg border border-line px-2.5 py-2 text-[11px]">
                <div className="text-[10px] text-ink-500">页面文本（前 300 字，证明真的渲染到了这一步）</div>
                <div className="mt-0.5 line-clamp-3 text-[10px] text-ink-600">{one.pageText || "—"}</div>
              </div>
              {one.orderNo && (
                <div className="rounded-lg border border-green-200 bg-green-50/60 px-2.5 py-2 text-[11px] text-green-800">
                  <span className="font-medium">真实落库订单：</span>
                  <span className="font-mono">{one.orderNo}</span>
                </div>
              )}
              <div className="flex gap-2">
                <Btn v="secondary" size="sm" onClick={() => setScriptOpen(true)}>查看本次执行脚本</Btn>
                {one.stepShots.length > 0 && <Btn v="ghost" size="sm" onClick={() => setShotOpen(true)}>放大截图</Btn>}
                {one.videoUrl && <a className="text-[11px] text-brand-600 underline" href={one.videoUrl} target="_blank" rel="noreferrer">下载/播放视频</a>}
              </div>
            </div>
            <div>
              <div className="mb-1 text-[10px] text-ink-500">执行截图</div>
              {one.stepShots.length > 0 ? (
                <button onClick={() => setShotOpen(true)} className="block w-full overflow-hidden rounded-lg border border-line">
                  <img src={one.stepShots[one.stepShots.length - 1].url} alt="执行截图" className="h-32 w-full object-cover object-top" />
                </button>
              ) : (
                <div className="grid h-32 place-items-center rounded-lg border border-dashed border-line text-[10px] text-ink-400">无截图</div>
              )}
              <div className="mt-1 text-[10px] text-ink-400">{one.stepShots.length} 张截图 · {one.videoUrl ? "已录屏" : "无视频"}</div>
            </div>
          </div>
        </Card>
      )}

      {/* 编译 + 执行控制台 */}
      <Card title="UI 自动化执行台" extra={
        <span className="flex items-center gap-2 text-[11px] text-ink-500">
          <span className={cx("h-2 w-2 rounded-full", pool?.browserAlive ? "bg-green-500" : "bg-ink-300")} />
          共享浏览器池：{pool?.browserAlive ? `运行中${pool.activeContexts ? ` · ${pool.activeContexts} 个 context` : " · 空闲"}` : "未启动（首次执行自动拉起）"}
        </span>
      }>
        <div className="flex flex-wrap items-center gap-2">
          <Btn onClick={() => void compile(false)} disabled={compiling}>
            {compiling ? "编译中…" : "编译功能测试用例"}
          </Btn>
          <Btn v="secondary" size="sm" onClick={() => void compile(true)} disabled={compiling}>重新编译全部</Btn>
          <span className="mx-1 h-4 w-px bg-line" />
          <span className="text-[11px] text-ink-500">条数</span>
          <Input className="w-16" value={String(limit)} onChange={(e) => setLimit(Number(e.target.value) || 1)} />
          <span className="text-[11px] text-ink-500">写操作配额</span>
          <Input className="w-14" value={String(maxWrite)} onChange={(e) => setMaxWrite(Number(e.target.value) || 0)} />
          <Btn onClick={() => void runAll()} disabled={running}>
            {running ? "真实执行中…" : "批量真实执行"}
          </Btn>
          <span className="text-[11px] text-ink-400">步骤间 300ms · 单浏览器池复用 · 真实断言 · 失败自动截图</span>
        </div>

        {batch && (
          <div className="mt-3 rounded-lg border border-line px-3 py-2">
            <div className="flex items-center gap-2 text-[11px]">
              <span className={cx("h-2 w-2 rounded-full", batch.status === "running" ? "bg-amber-500 animate-pulse" : batch.status === "finished" ? "bg-green-500" : "bg-red-500")} />
              <span className="font-mono text-ink-500">{batch.jobId}</span>
              <span className="text-ink-700">{batch.status === "running" ? "执行中" : batch.status === "finished" ? "已完成" : "失败"}</span>
              <span className="ml-auto text-ink-500">{batch.index} / {batch.total}</span>
            </div>
            <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-100">
              <div className="h-full rounded-full bg-brand-500 transition-all"
                style={{ width: `${Math.min(100, Math.round((batch.index / Math.max(1, batch.total)) * 100))}%` }} />
            </div>
            {batch.current && <div className="mt-1 truncate text-[10px] text-ink-400">{batch.current}</div>}
          </div>
        )}

        {compileInfo && (
          <div className="mt-3 grid grid-cols-4 gap-2">
            {[
              { label: "用例总数", value: compileInfo.total, c: "text-ink-800" },
              { label: "可直接执行", value: compileInfo.ready, c: "text-green-600" },
              { label: "需补全定位器", value: compileInfo.partial, c: "text-amber-600" },
              { label: "不可执行", value: compileInfo.blocked, c: "text-red-600" },
            ].map((x) => (
              <div key={x.label} className="rounded-lg border border-line px-3 py-2">
                <div className="text-[10px] text-ink-500">{x.label}</div>
                <div className={cx("mt-0.5 text-lg font-semibold", x.c)}>{x.value}</div>
              </div>
            ))}
          </div>
        )}
        {compileInfo && (
          <div className="mt-3 max-h-32 overflow-auto rounded-lg border border-line">
            {compileInfo.details.map((d) => (
              <div key={d.caseId} className="flex items-center gap-2 border-b border-line/60 px-3 py-1.5 text-[11px] last:border-0">
                <span className="font-mono text-ink-400">{d.caseId}</span>
                <span className="min-w-0 flex-1 truncate text-ink-700">{d.title}</span>
                <Tag t={d.ready ? "可执行" : `${d.executable}/${d.total} 步`} c={d.ready ? "green" : "amber"} dot={false} />
              </div>
            ))}
          </div>
        )}
      </Card>

      {/* 批量真实执行结果 */}
      {batchResult && (
        <>
          <Card title="真实执行结果" extra={<span className="text-[11px] text-ink-500">{batchResult.generatedAt} · 目标 {batchResult.target}</span>}>
            <div className="grid grid-cols-6 gap-2">
              {[
                { label: "真实执行", value: batchResult.executed, c: "text-ink-800" },
                { label: "通过", value: batchResult.passed, c: "text-green-600" },
                { label: "失败", value: batchResult.failed, c: "text-red-600" },
                { label: "通过率", value: `${batchResult.passRate}%`, c: "text-brand-600" },
                { label: "写操作真实落库", value: batchResult.writeExecuted, c: "text-amber-600" },
                { label: "总耗时", value: `${batchResult.totalSeconds}s`, c: "text-ink-600" },
              ].map((x) => (
                <div key={x.label} className="rounded-lg border border-line px-3 py-2">
                  <div className="text-[10px] text-ink-500">{x.label}</div>
                  <div className={cx("mt-0.5 text-lg font-semibold", x.c)}>{x.value}</div>
                </div>
              ))}
            </div>
            {batchLink && (
              <div className="mt-2 flex items-center gap-2">
                <Btn v="secondary" size="sm" onClick={() => navigate(batchLink)}>查看批次详情（逐条截图 / 视频）</Btn>
                <span className="text-[10px] text-ink-400">本次批量已折叠为执行记录里的一条批次</span>
              </div>
            )}
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <div className="mb-1 text-[11px] font-medium text-ink-600">按 Page Object 汇总</div>
                <div className="overflow-hidden rounded-lg border border-line">
                  {Object.entries(batchResult.byPageObject).map(([name, s]) => (
                    <div key={name} className="flex items-center gap-2 border-b border-line/60 px-2 py-1 text-[11px] last:border-0">
                      <span className="min-w-0 flex-1 truncate text-ink-700">{name}</span>
                      <span className="text-ink-500">{s.passed}/{s.total}</span>
                      {s.failed > 0 && <Tag t={`失败 ${s.failed}`} c="red" dot={false} />}
                    </div>
                  ))}
                </div>
              </div>
              <div>
                <div className="mb-1 text-[11px] font-medium text-ink-600">失败明细（真实错误）</div>
                <div className="max-h-40 overflow-auto rounded-lg border border-line">
                  {batchResult.failures.length === 0 && <div className="px-2 py-3 text-[11px] text-ink-400">无失败</div>}
                  {batchResult.failures.map((f) => (
                    <div key={f.caseId} className="border-b border-line/60 px-2 py-1.5 text-[11px] last:border-0">
                      <div className="flex items-center gap-1.5">
                        <span className="font-mono text-ink-400">{f.caseId}</span>
                        <span className="min-w-0 flex-1 truncate">{f.caseTitle}</span>
                      </div>
                      <div className="mt-0.5 text-red-600">{f.failedStep} · {f.detail}</div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
            {batchResult.results.some((r) => r.orderNos.length > 0) && (
              <div className="mt-3 rounded-lg border border-green-200 bg-green-50/50 px-3 py-2 text-[11px] text-green-800">
                <span className="font-medium">真实落库订单：</span>
                {batchResult.results.flatMap((r) => r.orderNos.map((n) => `${r.caseId} → ${n}`)).join("；")}
              </div>
            )}
          </Card>

          <Card title="逐条执行证据" extra={<span className="text-[11px] text-ink-500">断言 {batchResult.results.reduce((a, r) => a + r.assertionsPassed, 0)}/{batchResult.results.reduce((a, r) => a + r.assertions, 0)} 通过</span>}>
            <div className="max-h-96 space-y-1.5 overflow-auto">
              {batchResult.results.map((r) => (
                <div key={r.caseId} className="rounded-lg border border-line px-2.5 py-1.5">
                  <div className="flex items-center gap-2 text-[11px]">
                    <span className="font-mono text-ink-400">{r.caseId}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-700">{r.caseTitle}</span>
                    <Tag t={r.pageObject} c="blue" dot={false} />
                    {r.writeFlow && <Tag t="写操作" c="amber" dot={false} />}
                    <span className="text-ink-400">{r.seconds}s</span>
                    <Tag t={r.verdict} c={r.verdict === "通过" ? "green" : "red"} dot={false} />
                  </div>
                  <div className="mt-1 flex flex-wrap gap-1">
                    {r.steps.map((s) => (
                      <span key={s.index} title={`${s.raw}${s.detail ? ` · ${s.detail}` : ""}`}
                        className={cx("rounded px-1.5 py-0.5 font-mono text-[10px]",
                          s.status === "passed" ? "bg-green-50 text-green-700"
                            : s.status === "failed" ? "bg-red-50 text-red-700"
                              : "bg-amber-50 text-amber-700")}>
                        {s.index}.{s.keyword}
                      </span>
                    ))}
                  </div>
                  <div className="mt-1 truncate text-[10px] text-ink-400">
                    最终页面：{r.finalUrl || "—"}{r.orderNos.length > 0 ? ` · 订单号 ${r.orderNos.join(",")}` : ""}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </>
      )}

      {/* 执行结果 */}
      {results && (
        <Card title="执行结果" extra={<span className="text-[11px] text-ink-500">
          通过 {results.filter((r) => r.verdict === "通过").length} / 共 {results.length}
        </span>}>
          <div className="space-y-2">
            {results.map((r) => (
              <div key={r.caseId} className="rounded-lg border border-line px-3 py-2">
                <div className="flex items-center gap-2 text-[11px]">
                  <span className="font-mono text-ink-400">{r.caseId}</span>
                  <span className="min-w-0 flex-1 truncate">{r.caseTitle}</span>
                  <Tag t={r.verdict} c={r.verdict === "通过" ? "green" : r.verdict === "失败" ? "red" : "amber"} dot={false} />
                  <span className="text-ink-400">{r.durationMs}ms</span>
                </div>
                <div className="mt-1.5 flex flex-wrap gap-1">
                  {r.steps.map((s) => (
                    <span key={s.index} title={`${s.raw}${s.detail ? ` · ${s.detail}` : ""}`}
                      className={cx("rounded px-1.5 py-0.5 font-mono text-[10px]",
                        s.status === "passed" ? "bg-green-50 text-green-700"
                        : s.status === "failed" ? "bg-red-50 text-red-700"
                        : "bg-amber-50 text-amber-700")}>
                      {s.index}.{s.keyword} {STATUS_CN[s.status] ?? s.status}
                    </span>
                  ))}
                </div>
                {r.screenshot && <div className="mt-1 text-[10px] text-brand-600">失败截图：{r.screenshot}</div>}
              </div>
            ))}
          </div>
        </Card>
      )}

      {/* 脚本编辑与复用 */}
      <div className="grid grid-cols-4 gap-4">
        <Card title="可复用脚本" extra={<Btn v="ghost" onClick={() => setOpen(true)}>+ 新建</Btn>}>
          {data.length === 0 && <Empty text="暂无脚本，请先编译功能测试用例" />}
          {data.map((s) => (
            <button key={s.id} onClick={() => setSelected(s.id)}
              className={cx("w-full rounded px-2 py-2 text-left text-xs", script?.id === s.id ? "bg-brand-50 text-brand-700" : "hover:bg-ink-50")}>
              <div className="flex justify-between gap-2">
                <span className="truncate">{s.name}</span>
                <Tag t={s.status ?? "启用"} c={s.status === "待补全" ? "amber" : "green"} dot={false} />
              </div>
              <div className="mt-0.5 text-[11px] text-ink-500">{s.framework} · {s.updatedAt}</div>
            </button>
          ))}
        </Card>

        <Card className="col-span-3" title={script ? `脚本编辑 · ${script.name}` : "脚本编辑"} extra={
          <div className="flex items-center gap-2">
            <Btn v="ghost" onClick={save}>保存修改</Btn>
          </div>
        }>
          {script ? (
            <>
              <MonacoEditor value={draft} onChange={setDraft} language="python" height={460} path={`${script.id}.py`} />
              {selectedResult && (
                <div className="mt-2 rounded-lg border border-line bg-ink-50/40 p-2 text-[11px]">
                  <div className="mb-1 font-medium">当前脚本最近执行：{selectedResult.verdict}</div>
                  {selectedResult.steps.map((s) => (
                    <div key={s.index} className="flex gap-2 py-0.5">
                      <span className="font-mono text-ink-400">{s.index}.</span>
                      <span>{s.raw}</span>
                      <span className="ml-auto text-ink-500">{STATUS_CN[s.status] ?? s.status}{s.detail ? ` · ${s.detail}` : ""}</span>
                    </div>
                  ))}
                </div>
              )}
            </>
          ) : <Empty text="请选择或编译脚本" />}
        </Card>
      </div>

      <Modal open={shotOpen} title={`执行截图 · ${one?.caseId ?? ""}`} width="max-w-5xl"
        onClose={() => setShotOpen(false)} footer={<Btn v="ghost" onClick={() => setShotOpen(false)}>关闭</Btn>}>
        {one && one.stepShots.length > 0
          ? <img src={one.stepShots[one.stepShots.length - 1].url} alt="执行截图" className="w-full rounded-lg border border-line" />
          : <Empty text="本次执行没有截图" />}
        {one?.screenshot && <div className="mt-2 break-all font-mono text-[10px] text-ink-400">{one.screenshot}</div>}
      </Modal>

      <Modal open={scriptOpen} title={`本次执行脚本 · ${one?.caseId ?? ""}`} width="max-w-4xl"
        onClose={() => setScriptOpen(false)} footer={<Btn v="ghost" onClick={() => setScriptOpen(false)}>关闭</Btn>}>
        <div className="mb-2 text-[11px] text-ink-500">
          由「用例原文 → Page Object 展开 → 关键字」生成的 Playwright 脚本，断言语义与平台执行内核一致，可导出后独立复跑。
        </div>
        <MonacoEditor value={one?.script ?? ""} onChange={() => undefined} language="python" height={420} path={`${one?.caseId ?? "case"}.py`} />
      </Modal>

      <Modal open={open} title="新建用例脚本" onClose={() => setOpen(false)}
        footer={<><Btn v="ghost" onClick={() => setOpen(false)}>取消</Btn><Btn onClick={create}>创建</Btn></>}>
        <div className="space-y-3 text-xs">
          <div>脚本名称</div>
          <Input className="w-full" value={name} onChange={(e) => setName(e.target.value)} placeholder="例如：支付流程回归" autoFocus />
          <div className="text-[11px] text-ink-500">自定义脚本可自由编辑；编译生成的脚本遵循关键字驱动规范，可保存后复用。</div>
        </div>
      </Modal>
    </div>
  );
}
