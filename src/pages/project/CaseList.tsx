import { useRef, useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { testcasesApi, webuiApi } from "@/api";
import type { UiCaseIndexItem, UiRunOneResult } from "@/api/webui";
import type { CaseRunReport, TestCase } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { confirmDelete } from "@/lib/confirm";
import { downloadBlob } from "@/lib/download";
import { Btn, Card, Field, Input, Modal, Select, Table, Tag, Textarea, Toolbar } from "@/components/ui";
import { CaseBindingModal } from "./CaseBindingModal";

const EMPTY = { title: "", module: "会员", type: "正向", priority: "P1" as TestCase["priority"], precondition: "", steps: "", expected: "" };

const CASE_TYPE_CN = { api: "API 测试", functional: "功能测试" } as const;

function caseTypeOf(c: TestCase): "api" | "functional" {
  return c.caseType ?? (c.relatedApi ? "api" : "functional");
}

/** 运行结果弹窗：API 用例展示请求/实际/判定；功能用例走人工执行面板。 */
function RunModal({ target, onClose, onDone }: {
  target: TestCase | null;
  onClose: () => void;
  onDone: (updated: TestCase) => void;
}) {
  const { toast } = useApp();
  const [report, setReport] = useState<CaseRunReport | null>(null);
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);
  const [manualVerdict, setManualVerdict] = useState<"通过" | "失败" | "阻塞" | null>(null);
  const [manualNote, setManualNote] = useState("");
  const [checkedSteps, setCheckedSteps] = useState<Record<number, boolean>>({});

  const isApi = target ? caseTypeOf(target) === "api" : false;
  const isDelete = !!report?.request?.method?.startsWith("DELETE");

  const run = async () => {
    if (!target) return;
    setBusy(true);
    try {
      const r = await testcasesApi.run(target.id, {
        force: isApi ? force : undefined,
        manualVerdict: !isApi ? (manualVerdict ?? undefined) : undefined,
        manualNote: !isApi ? manualNote : undefined,
      });
      if (!isApi && !manualVerdict) { setReport(r); return; }
      setReport(r);
      onDone({ ...target, lastRun: r.lastRun ?? target.lastRun });
      toast(r.verdict ? `运行完成：${r.verdict}` : "执行结果已记录");
    } catch (e) {
      toast(e instanceof Error ? e.message : "运行失败");
    } finally {
      setBusy(false);
    }
  };

  const verdictTone = (v?: string) =>
    v === "通过" ? "green" : v === "不符" || v === "失败" ? "red" : v === "跳过" || v === "阻塞" ? "amber" : "blue";

  return (
    <Modal
      open={!!target}
      title={target ? `运行用例 · ${target.id}` : ""}
      onClose={onClose}
      width="max-w-2xl"
      footer={
        <>
          <Btn v="ghost" onClick={onClose}>关闭</Btn>
          {!isApi && manualVerdict && report && <Btn onClick={run} disabled={busy}>保存执行结果</Btn>}
          {!isApi && !report && <span className="text-[11px] text-ink-500">请按步骤勾选执行后记录结论</span>}
          {isApi && <Btn onClick={run} disabled={busy}>{busy ? "运行中…" : isDelete ? "强制执行" : "运行"}</Btn>}
        </>
      }
    >
      {target && (
        <div className="space-y-3 text-xs">
          <div className="rounded-lg bg-ink-50/60 px-3 py-2">
            <div className="font-medium text-ink-800">{target.title}</div>
            <div className="mt-1 flex items-center gap-2">
              <Tag t={CASE_TYPE_CN[caseTypeOf(target)]} c={isApi ? "blue" : "gray"} dot={false} />
              {target.relatedApi && <code className="font-mono text-[10px] text-ink-500">{target.relatedApi}</code>}
            </div>
          </div>

          {isApi && !report && (
            <p className="text-[11px] leading-5 text-ink-500">
              将把用例打到真实后端（127.0.0.1:8086）执行：按被测接口契约自动构造请求与测试数据，
              并按预期（HTTP 状态 / 业务码）自动判定。管理端与 C 端身份自动切换。
            </p>
          )}

          {isApi && report && (
            <>
              <div className="flex items-center gap-2">
                <span className="text-ink-500">判定</span>
                <Tag t={report.verdict ?? "—"} c={verdictTone(report.verdict)} dot={false} />
                <span className="text-[11px] text-ink-500">{report.detail}</span>
              </div>
              <div className="rounded-lg border border-line px-3 py-2">
                <div className="mb-1 text-[10px] font-semibold text-ink-500">请求</div>
                <code className="font-mono text-[11px]">
                  {report.request?.method} {report.request?.path}
                </code>
                {report.request?.body != null && (
                  <pre className="mt-1 max-h-24 overflow-auto rounded bg-ink-50 p-2 font-mono text-[10px]">
                    {JSON.stringify(report.request.body)}
                  </pre>
                )}
              </div>
              <div className="rounded-lg border border-line px-3 py-2">
                <div className="mb-1 text-[10px] font-semibold text-ink-500">实际响应</div>
                <div className="flex gap-3 font-mono text-[11px]">
                  <span>HTTP {report.actual?.http}</span>
                  <span>code={report.actual?.code ?? "—"}</span>
                  <span className="text-ink-500">{report.actual?.msg}</span>
                </div>
                {report.actual?.dataPreview && (
                  <pre className="mt-1 max-h-28 overflow-auto rounded bg-ink-50 p-2 font-mono text-[10px] whitespace-pre-wrap">
                    {report.actual.dataPreview}
                  </pre>
                )}
              </div>
              {isDelete && (
                <label className="flex items-center gap-1.5 text-[11px] text-ink-600">
                  <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
                  强制执行删除（会真实删除演示库数据，不可恢复）
                </label>
              )}
            </>
          )}

          {!isApi && (
            <div className="space-y-2">
              <div className="text-[11px] text-ink-500">
                功能测试用例需人工在页面上按步骤操作，逐项确认后记录结论。
              </div>
              {target.precondition && <div className="rounded bg-ink-50/60 px-3 py-1.5 text-[11px]">前置：{target.precondition}</div>}
              <ol className="space-y-1.5">
                {target.steps.map((s, i) => (
                  <li key={i} className="flex items-center gap-2 rounded border border-line px-3 py-1.5">
                    <label className="flex items-center gap-2">
                      <input type="checkbox" checked={!!checkedSteps[i]}
                        onChange={(e) => setCheckedSteps({ ...checkedSteps, [i]: e.target.checked })} />
                      <span className="min-w-0 flex-1">{s}</span>
                    </label>
                    <span className="ml-auto font-mono text-[10px] text-ink-400">步骤 {i + 1}</span>
                  </li>
                ))}
              </ol>
              <div className="rounded bg-ink-50/60 px-3 py-1.5 text-[11px]">预期：{target.expected}</div>
              <Field label="执行结论" as="div">
                <div className="mt-1 flex gap-2">
                  {(["通过", "失败", "阻塞"] as const).map((v) => (
                    <button key={v} type="button"
                      onClick={() => setManualVerdict(v)}
                      className={`rounded-md border px-3 py-1.5 text-[11px] ${
                        manualVerdict === v ? "border-brand-500 bg-brand-50 text-brand-700" : "border-line text-ink-600 hover:bg-ink-50"
                      }`}>
                      {v}
                    </button>
                  ))}
                </div>
              </Field>
              <Field label="备注（可选）">
                <Textarea className="h-16 w-full" value={manualNote} onChange={(e) => setManualNote(e.target.value)}
                  placeholder="失败/阻塞原因、现场描述…" />
              </Field>
              {report?.lastRun && (
                <div className="text-[11px] text-ink-500">
                  已记录：{report.lastRun.verdict} · {report.lastRun.at}
                  {report.lastRun.executor ? ` · ${report.lastRun.executor}` : ""}
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

/** 已自动化的功能用例：直接驱动真实浏览器跑一遍，逐步回显 */
function UiRunModal({ target, writeFlow, onClose, onDone }: {
  target: TestCase | null;
  writeFlow: boolean;
  onClose: () => void;
  onDone: (id: string, verdict: string) => void;
}) {
  const { toast } = useApp();
  const navigate = useNavigate();
  const { pid = "ecommerce" } = useParams<{ pid: string }>();
  const [report, setReport] = useState<UiRunOneResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [force, setForce] = useState(false);

  const run = async () => {
    if (!target) return;
    setBusy(true);
    setReport(null);
    try {
      const r = await webuiApi.runOne({ caseId: target.id, delayMs: 300, force: force || !writeFlow });
      setReport(r);
      onDone(target.id, r.verdict);
      toast(`UI 自动化执行完成：${r.verdict} · 断言 ${r.assertionsPassed}/${r.assertions}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "UI 自动化执行失败");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal open={!!target} title={target ? `UI 自动化执行 · ${target.id}` : ""} width="max-w-2xl"
      onClose={onClose}
      footer={
        <>
          <Btn v="ghost" onClick={onClose}>关闭</Btn>
          <Btn v="secondary" onClick={() => navigate(`/project/${pid}/webui/runs`)}>打开执行记录</Btn>
          <Btn onClick={run} disabled={busy || (writeFlow && !force)}>{busy ? "执行中…" : report ? "重新执行" : "开始执行"}</Btn>
        </>
      }>
      {target && (
        <div className="space-y-3 text-xs">
          <div className="rounded-lg bg-ink-50/60 px-3 py-2">
            <div className="font-medium text-ink-800">{target.title}</div>
            <div className="mt-1 flex items-center gap-2">
              <Tag t="已转为自动化脚本" c="green" dot={false} />
              <span className="text-[10px] text-ink-500">真实浏览器逐步执行 · 每步截图 + 录屏</span>
            </div>
          </div>
          {writeFlow && (
            <label className="flex items-center gap-1.5 text-[11px] text-amber-700">
              <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
              该用例会真实下单/支付，勾选确认后再执行
            </label>
          )}
          {!report && <p className="text-[11px] leading-5 text-ink-500">点击「开始执行」，平台会把用例步骤展开成关键字脚本并在尚品汇真实前端跑一遍，失败会停在出错那一步并留证。</p>}
          {report && (
            <div className="space-y-2">
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-ink-500">判定</span>
                <Tag t={report.verdict} c={report.verdict === "通过" ? "green" : report.verdict === "失败" ? "red" : "amber"} dot={false} />
                <span className="text-ink-500">步骤 {report.steps.filter((s) => s.status === "passed").length}/{report.steps.length}</span>
                <span className="text-ink-500">断言 {report.assertionsPassed}/{report.assertions}</span>
                <span className="text-ink-500">{(report.durationMs / 1000).toFixed(1)}s</span>
              </div>
              <div className="overflow-hidden rounded-lg border border-line">
                {report.steps.map((s) => (
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
              <div className="flex flex-wrap items-center gap-3 text-[10px] text-ink-500">
                <span>最终页面：<span className="break-all font-mono text-brand-600">{report.finalUrl || "—"}</span></span>
                <span>{report.stepShots.length} 张截图{report.videoUrl ? " · 已录屏" : ""}</span>
                {report.orderNo && <span className="text-green-700">订单号 {report.orderNo}</span>}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

export function CaseList() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { pid = "ecommerce" } = useParams<{ pid: string }>();
  const reqFilter = params.get("requirement") ?? "";
  const { data, setData, reload, loading } = useAsync(
    () => testcasesApi.list(reqFilter || undefined), [reqFilter], [] as TestCase[]);
  const { user } = useAuth();
  // 自动化索引：判断每条用例是否已转成可执行脚本（有 PO 映射、步骤可展开）
  const { data: autoIndex, reload: reloadAuto } = useAsync<{ cases: UiCaseIndexItem[] } | null>(
    async () => await webuiApi.caseIndex(), [], null);
  const autoMap = new Map((autoIndex?.cases ?? []).map((c) => [c.caseId, c]));
  // 列表默认只给在册用例，被去重归档的副本不显示——但必须让人知道"少了多少、去哪还原"，
  // 否则第一反应是"数据丢了"。
  const { data: dedupInfo } = useAsync<{ alreadyArchived: number } | null>(
    async () => await webuiApi.dedup(), [], null);
  const archivedCount = dedupInfo?.alreadyArchived ?? 0;
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("全部状态");
  const [typeFilter, setTypeFilter] = useState("全部测试类型");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TestCase | null>(null);
  const [runTarget, setRunTarget] = useState<TestCase | null>(null);
  const [uiTarget, setUiTarget] = useState<TestCase | null>(null);
  const [bindTarget, setBindTarget] = useState<TestCase | null>(null);
  const [form, setForm] = useState(EMPTY);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useApp();

  const list = data.filter((c) =>
    (status === "全部状态" || c.status === status)
    && (typeFilter === "全部测试类型" || caseTypeOf(c) === (typeFilter === "API 测试" ? "api" : "functional"))
    && (!query || c.title.includes(query) || c.id.includes(query)));

  const openCreate = () => { setEditing(null); setForm(EMPTY); setOpen(true); };
  const openEdit = (c: TestCase) => {
    setEditing(c);
    setForm({ title: c.title, module: c.module, type: c.type, priority: c.priority, precondition: c.precondition, steps: c.steps.join("\n"), expected: c.expected });
    setOpen(true);
  };

  const save = async () => {
    if (!form.title.trim()) { toast("请填写用例标题"); return; }
    const payload = { ...form, steps: form.steps.split("\n").map((s) => s.trim()).filter(Boolean) };
    if (editing) {
      const updated = await testcasesApi.update(editing.id, payload);
      setData(data.map((c) => (c.id === updated.id ? updated : c)));
      toast("用例已更新");
    } else {
      const created = await testcasesApi.create({ ...payload, source: "手工", owner: user?.name ?? "" });
      setData([created, ...data]);
      toast("用例已创建");
    }
    setOpen(false);
  };

  const remove = async (id: string) => {
    const target = data.find((x) => x.id === id);
    if (!confirmDelete(target?.title ?? id)) return;
    await testcasesApi.remove(id);
    setData(data.filter((c) => c.id !== id));
    toast("用例已删除");
  };

  const exportExcel = async () => {
    try {
      downloadBlob("testcases.xlsx", await testcasesApi.exportXlsx());
      toast("已导出 Excel");
    } catch (err) {
      toast(err instanceof Error ? err.message : "导出失败");
    }
  };

  const importExcel = async (file: File) => {
    try {
      const result = await testcasesApi.importXlsx(file);
      await reload();
      toast(`导入完成：新增 ${result.created}，更新 ${result.updated}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "导入失败");
    }
  };

  return (
    <>
      <Card>
        <Toolbar placeholder="搜索用例标题/编号" onSearch={setQuery} onStatusChange={setStatus} statusOptions={["全部状态", "通过", "待评审", "草稿"]}>
          <Select opts={["全部测试类型", "API 测试", "功能测试"]} className="w-36" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} />
          {reqFilter && (
            <span className="mr-1 rounded-md bg-brand-50 px-2 py-1 font-mono text-[10px] text-brand-700 ring-1 ring-brand-100"
              title="按需求过滤中">
              需求 {reqFilter}
            </span>
          )}
          <Btn v="secondary" size="sm" onClick={exportExcel}>导出 Excel</Btn>
          <Btn v="secondary" size="sm" onClick={() => fileRef.current?.click()}>导入 Excel</Btn>
          <input ref={fileRef} type="file" accept=".xlsx" className="hidden" onChange={(e) => { const file = e.target.files?.[0]; if (file) void importExcel(file); e.target.value = ""; }} />
          <Btn size="sm" onClick={openCreate}>+ 新建用例</Btn>
        </Toolbar>
        {archivedCount > 0 && (
          <div className="mb-2 flex items-center gap-2 rounded-lg border border-line bg-ink-50 px-3 py-1.5 text-[11.5px] text-ink-500">
            <span className="h-1.5 w-1.5 rounded-full bg-ink-300" />
            已隐藏 <b className="mx-0.5 tabular-nums text-ink-700">{archivedCount}</b> 条重复副本（同一场景被登记多次）。
            它们保留在库中可回滚，去重与还原入口见
            <Link className="text-brand-600 underline decoration-dotted" to={`/project/${pid}/webui/bindings`}>绑定体检</Link>。
          </div>
        )}
        <Table
          cols={["ID", "标题", "模块", "测试类型", "自动化", "绑定页面", "类型", "优先级", "关联需求", "状态", "最近运行"]}
          rows={list.map((c) => {
            const ct = caseTypeOf(c);
            const run = c.lastRun;
            const b = autoMap.get(c.id)?.binding;
            const riskDot: Record<string, string> = {
              confirmed: "bg-emerald-500", guess: "bg-amber-400", mismatch: "bg-rose-500",
              blocked_no_po: "bg-ink-300", stale_po: "bg-rose-400", none: "bg-ink-200",
            };
            const riskLabel: Record<string, string> = {
              confirmed: "已人工确认绑定", guess: "规则推断，待确认", mismatch: "规则认为该用例更适合接口/数据校验，UI 跑通不代表验证了它",
              blocked_no_po: "绑定的页面暂无 Page Object", stale_po: "绑定的流程已不存在，需重新绑定", none: "未绑定页面",
            };
            const bindText = ct === "api" ? "接口" : (b?.pageName || (b?.kind === "api" ? "非 UI" : "未绑定"));
            return [
              c.id,
              <span className="block max-w-[180px] truncate" title={c.title}>{c.title}</span>,
              <span className="block max-w-[72px] truncate text-[12px]" title={c.module}>{c.module}</span>,
              <span title={ct === "api" ? "API 测试用例：点击运行可真实执行" : "功能测试用例：已转为自动化脚本的可直接驱动浏览器执行"}>
                <Tag t={CASE_TYPE_CN[ct]} c={ct === "api" ? "blue" : "gray"} dot={false} />
              </span>,
              ct === "api"
                ? <span title="API 用例天然可自动化执行"><Tag t="是" c="blue" dot={false} /></span>
                : autoMap.get(c.id)?.ready
                  ? <span title={`已转化为自动化脚本（Page Object：${autoMap.get(c.id)?.pageObject || "—"}）`}><Tag t="是" c="green" dot={false} /></span>
                  : <span title="尚未转化为自动化脚本：用例步骤无法映射到可执行 UI 操作"><Tag t="否" c="gray" dot={false} /></span>,
              ct === "api"
                ? <span className="text-[10px] text-ink-300">—</span>
                : <span className="inline-flex max-w-[86px] items-center gap-1" onClick={(e) => e.stopPropagation()}>
                    <span className={`h-1.5 w-1.5 shrink-0 rounded-full ${riskDot[b?.risk ?? "none"] ?? "bg-ink-200"}`} />
                    <button type="button" onClick={() => setBindTarget(c)}
                      className="truncate text-left text-[11px] text-ink-600 underline-offset-2 hover:text-brand-600 hover:underline"
                      title={`${riskLabel[b?.risk ?? "none"] ?? ""}${b?.reason ? `：${b.reason}` : ""}`}>
                      {bindText}
                    </button>
                  </span>,
              c.type, c.priority,
              (c.relatedRequirementIds ?? []).length > 0
                ? <span className="block max-w-[76px] truncate font-mono text-[10px] text-brand-600" title={(c.relatedRequirementIds ?? []).join(", ")}>
                    {(c.relatedRequirementIds ?? [])[0]}
                    {(c.relatedRequirementIds ?? []).length > 1 ? ` +${(c.relatedRequirementIds ?? []).length - 1}` : ""}
                  </span>
                : <span className="text-[10px] text-ink-300">—</span>,
              c.status,
              run
                ? <span className="flex items-center gap-1.5">
                    <Tag t={run.verdict} c={run.verdict === "通过" ? "green" : run.verdict === "不符" || run.verdict === "失败" ? "red" : "amber"} dot={false} />
                    <span className="text-[10px] text-ink-400">{run.at?.slice(5, 16)}</span>
                  </span>
                : <span className="text-[10px] text-ink-300">未运行</span>,
            ];
          })}
          loading={loading}
          empty="当前项目还没有测试用例"
          emptyAction={<Btn size="sm" onClick={openCreate}>+ 新建用例</Btn>}
          onRowClick={(i) => navigate(`/project/${pid}/testcases/${encodeURIComponent(list[i].id)}`)}
          actions={(i) => {
            const ct = caseTypeOf(list[i]);
            const auto = autoMap.get(list[i].id);
            const uiRunnable = ct === "api" || !!auto?.ready;
            return (
              <>
                <span title={!uiRunnable ? "尚未转化为自动化脚本，运行按钮不可用" : ct === "api" ? "真实调用后端接口执行" : "驱动真实浏览器执行 UI 步骤"}>
                  <Btn v="secondary" size="sm" disabled={!uiRunnable}
                    onClick={(e) => {
                      e.stopPropagation();
                      if (ct === "api") setRunTarget(list[i]);
                      else setUiTarget(list[i]);
                    }}>
                    运行
                  </Btn>
                </span>
                <Btn v="secondary" size="sm" onClick={(e) => { e.stopPropagation(); openEdit(list[i]); }}>编辑</Btn>
                <Btn v="danger" size="sm" onClick={(e) => { e.stopPropagation(); remove(list[i].id); }}>删除</Btn>
              </>
            );
          }}
        />
      </Card>

      <Modal open={open} title={editing ? `编辑用例 · ${editing.id}` : "新建用例"} onClose={() => setOpen(false)} width="max-w-2xl" footer={<><Btn v="ghost" onClick={() => setOpen(false)}>取消</Btn><Btn onClick={save}>保存</Btn></>}>
        <div className="space-y-3">
          <Field label="标题"><Input className="w-full" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} autoFocus /></Field>
          <div className="grid grid-cols-3 gap-3">
            <Field label="模块"><Input className="w-full" value={form.module} onChange={(e) => setForm({ ...form, module: e.target.value })} /></Field>
            <Field label="类型"><Select opts={["正向", "边界", "异常", "安全"]} className="w-full" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} /></Field>
            <Field label="优先级"><Select opts={["P0", "P1", "P2"]} className="w-full" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value as TestCase["priority"] })} /></Field>
          </div>
          <Field label="前置条件"><Input className="w-full" value={form.precondition} onChange={(e) => setForm({ ...form, precondition: e.target.value })} /></Field>
          <Field label="测试步骤" hint="每行一个步骤"><Textarea className="w-full h-28" value={form.steps} onChange={(e) => setForm({ ...form, steps: e.target.value })} /></Field>
          <Field label="预期结果"><Textarea className="w-full h-20" value={form.expected} onChange={(e) => setForm({ ...form, expected: e.target.value })} /></Field>
        </div>
      </Modal>

      <RunModal target={runTarget} onClose={() => setRunTarget(null)}
        onDone={(updated) => setData(data.map((c) => (c.id === updated.id ? { ...c, lastRun: updated.lastRun } : c)))} />

      <UiRunModal target={uiTarget} writeFlow={!!(uiTarget && autoMap.get(uiTarget.id)?.writeFlow)}
        onClose={() => setUiTarget(null)}
        onDone={(id, verdict) => setData(data.map((c) => (c.id === id
          ? { ...c, lastRun: { at: new Date().toLocaleString("zh-CN", { hour12: false }).slice(0, 16), mode: "ui", verdict } }
          : c)))} />

      {bindTarget && (() => {
        const b = autoMap.get(bindTarget.id)?.binding;
        const isHuman = b?.source === "human";
        return (
          <CaseBindingModal
            caseId={bindTarget.id}
            caseTitle={bindTarget.title}
            module={bindTarget.module}
            current={b}
            suggestion={!isHuman && b ? { pageId: b.pageId, pageName: b.pageName, poName: b.poName, kind: b.kind, reason: b.reason } : undefined}
            onClose={() => setBindTarget(null)}
            onSaved={() => { void reloadAuto(); toast("绑定已保存，下次执行按新页面走"); }}
          />
        );
      })()}
    </>
  );
}
