import { useEffect, useState } from "react";
import { webuiApi } from "@/api";
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
  index: number; raw: string; keyword: string; status: string; detail: string;
};
type RunResult = {
  caseId: string; caseTitle: string; verdict: string; durationMs: number; screenshot: string;
  steps: StepResult[];
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
  const { addTask, toast } = useApp();
  const script = data.find((s) => s.id === selected) ?? data[0];

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

  /** 第二步：共享浏览器池真实执行（步骤间 300ms 节流） */
  const runAll = async () => {
    setRunning(true);
    setResults(null);
    addTask("WebUI 自动化执行 · 共享浏览器池", "WebUI");
    try {
      const r = await webuiApi.runCases({ delayMs: 300 });
      setResults(r.results);
      toast(`执行完成：通过 ${r.passed} / 失败 ${r.failed} / 待补全 ${r.partial}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "执行失败");
    } finally {
      setRunning(false);
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
          <Btn onClick={() => void runAll()} disabled={running || data.length === 0}>
            {running ? "执行中…" : "执行全部自动化用例"}
          </Btn>
          <span className="text-[11px] text-ink-400">步骤间自动延时 300ms · 单浏览器池复用 · 失败自动截图</span>
        </div>
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
