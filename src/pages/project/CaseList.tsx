import { useRef, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { testcasesApi } from "@/api";
import type { CaseRunReport, TestCase } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { confirmDelete } from "@/lib/confirm";
import { downloadBlob } from "@/lib/download";
import { Btn, Card, Field, Input, Modal, Select, Table, Tag, Textarea, Toolbar } from "@/components/ui";

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

export function CaseList() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { pid = "ecommerce" } = useParams<{ pid: string }>();
  const reqFilter = params.get("requirement") ?? "";
  const { data, setData, reload, loading } = useAsync(
    () => testcasesApi.list(reqFilter || undefined), [reqFilter], [] as TestCase[]);
  const { user } = useAuth();
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("全部状态");
  const [typeFilter, setTypeFilter] = useState("全部类型");
  const [open, setOpen] = useState(false);
  const [editing, setEditing] = useState<TestCase | null>(null);
  const [runTarget, setRunTarget] = useState<TestCase | null>(null);
  const [form, setForm] = useState(EMPTY);
  const fileRef = useRef<HTMLInputElement>(null);
  const { toast } = useApp();

  const list = data.filter((c) =>
    (status === "全部状态" || c.status === status)
    && (typeFilter === "全部类型" || caseTypeOf(c) === (typeFilter === "API 测试" ? "api" : "functional"))
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
          <Select opts={["全部类型", "API 测试", "功能测试"]} className="w-28" value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} />
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
        <Table
          cols={["ID", "标题", "模块", "测试类型", "类型", "优先级", "关联需求", "状态", "最近运行", "版本"]}
          rows={list.map((c) => {
            const ct = caseTypeOf(c);
            const run = c.lastRun;
            return [
              c.id, c.title, c.module,
              <span title={ct === "api" ? "API 测试用例：点击运行可真实执行" : "功能测试用例：人工按步骤执行并记录结果"}>
                <Tag t={CASE_TYPE_CN[ct]} c={ct === "api" ? "blue" : "gray"} dot={false} />
              </span>,
              c.type, c.priority,
              (c.relatedRequirementIds ?? []).length > 0
                ? <span className="font-mono text-[10px] text-brand-600" title={(c.relatedRequirementIds ?? []).join(", ")}>
                    {(c.relatedRequirementIds ?? []).join(" / ")}
                  </span>
                : <span className="text-[10px] text-ink-300">—</span>,
              c.status,
              run
                ? <span className="flex items-center gap-1.5">
                    <Tag t={run.verdict} c={run.verdict === "通过" ? "green" : run.verdict === "不符" || run.verdict === "失败" ? "red" : "amber"} dot={false} />
                    <span className="text-[10px] text-ink-400">{run.at?.slice(5, 16)}</span>
                  </span>
                : <span className="text-[10px] text-ink-300">未运行</span>,
              c.version,
            ];
          })}
          loading={loading}
          empty="当前项目还没有测试用例"
          emptyAction={<Btn size="sm" onClick={openCreate}>+ 新建用例</Btn>}
          onRowClick={(i) => navigate(`/project/${pid}/testcases/${encodeURIComponent(list[i].id)}`)}
          actions={(i) => (
            <>
              <Btn v="secondary" size="sm" onClick={(e) => { e.stopPropagation(); setRunTarget(list[i]); }}>
                运行
              </Btn>
              <Btn v="secondary" size="sm" onClick={(e) => { e.stopPropagation(); openEdit(list[i]); }}>编辑</Btn>
              <Btn v="danger" size="sm" onClick={(e) => { e.stopPropagation(); remove(list[i].id); }}>删除</Btn>
            </>
          )}
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
    </>
  );
}
