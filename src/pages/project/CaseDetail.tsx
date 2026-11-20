import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { testcasesApi } from "@/api";
import type { CaseRunReport, TestCase } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Field, Icon, Input, Select, Tag, Textarea } from "@/components/ui";

const CASE_TYPE_CN = { api: "API 测试", functional: "功能测试" } as const;
const caseTypeOf = (c: TestCase): "api" | "functional" => c.caseType ?? (c.relatedApi ? "api" : "functional");
const verdictTone = (v?: string) =>
  v === "通过" ? "green" : v === "不符" || v === "失败" ? "red" : v === "跳过" || v === "阻塞" ? "amber" : "blue";

type FormState = {
  title: string; module: string; type: string; priority: string; status: string; version: string;
  precondition: string; steps: string; expected: string;
  caseType: "api" | "functional"; relatedApi: string; testData: string; dbCheck: string; designMethod: string;
};

const toForm = (c: TestCase): FormState => ({
  title: c.title, module: c.module, type: c.type, priority: c.priority, status: c.status, version: c.version,
  precondition: c.precondition, steps: c.steps.join("\n"), expected: c.expected,
  caseType: caseTypeOf(c), relatedApi: c.relatedApi ?? "", testData: c.testData ?? "",
  dbCheck: c.dbCheck ?? "", designMethod: c.designMethod ?? "",
});

export function CaseDetail() {
  const { pid = "ecommerce", caseId = "" } = useParams<{ pid: string; caseId: string }>();
  const navigate = useNavigate();
  const { toast } = useApp();
  const { data: case_, setData } = useAsync<TestCase | null>(
    async () => (await testcasesApi.list()).find((c) => c.id === caseId) ?? null,
    [caseId], null);
  const [editing, setEditing] = useState(false);
  const [form, setForm] = useState<FormState | null>(null);

  // 运行状态（API / 人工）
  const [report, setReport] = useState<CaseRunReport | null>(null);
  const [running, setRunning] = useState(false);
  const [force, setForce] = useState(false);
  const [manualVerdict, setManualVerdict] = useState<"通过" | "失败" | "阻塞" | null>(null);
  const [manualNote, setManualNote] = useState("");
  const [checkedSteps, setCheckedSteps] = useState<Record<number, boolean>>({});

  if (!case_) return <Card><div className="py-16 text-center text-xs text-ink-400">用例不存在或已删除</div></Card>;
  const c = case_;
  const isApi = caseTypeOf(c) === "api";
  const isDelete = !!report?.request?.method?.startsWith("DELETE");

  const startEdit = () => { setForm(toForm(c)); setEditing(true); };

  const save = async () => {
    if (!form) return;
    try {
      const updated = await testcasesApi.update(c.id, {
        title: form.title, module: form.module, type: form.type,
        priority: form.priority as TestCase["priority"], status: form.status, version: form.version,
        precondition: form.precondition,
        steps: form.steps.split("\n").map((s) => s.trim()).filter(Boolean),
        expected: form.expected,
        caseType: form.caseType,
        relatedApi: form.relatedApi, testData: form.testData,
        dbCheck: form.dbCheck, designMethod: form.designMethod,
      });
      setData(updated);
      setEditing(false);
      toast("用例已保存");
    } catch (e) {
      toast(e instanceof Error ? e.message : "保存失败");
    }
  };

  const run = async () => {
    setRunning(true);
    try {
      const r = await testcasesApi.run(c.id, {
        force: isApi ? force : undefined,
        manualVerdict: !isApi ? (manualVerdict ?? undefined) : undefined,
        manualNote: !isApi ? manualNote : undefined,
      });
      setReport(r);
      if (r.lastRun) setData({ ...c, lastRun: r.lastRun });
      if (isApi) toast(`运行完成：${r.verdict}`);
      else if (manualVerdict) toast("执行结果已记录");
    } catch (e) {
      toast(e instanceof Error ? e.message : "运行失败");
    } finally {
      setRunning(false);
    }
  };

  const info = (label: string, node: React.ReactNode) => (
    <div>
      <dt className="text-[11px] text-ink-500">{label}</dt>
      <dd className="mt-1 text-[12px] font-medium text-ink-800">{node}</dd>
    </div>
  );

  return (
    <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
      {/* 左：用例信息 */}
      <Card className="h-fit" title="用例信息" extra={
        editing
          ? <Btn size="sm" onClick={save}>保存</Btn>
          : <Btn v="secondary" size="sm" onClick={startEdit}>编辑</Btn>
      }>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] text-ink-400">{c.id}</span>
          <Tag t={CASE_TYPE_CN[isApi ? "api" : "functional"]} c={isApi ? "blue" : "gray"} dot={false} />
          {c.lastRun && <Tag t={c.lastRun.verdict} c={verdictTone(c.lastRun.verdict)} dot={false} />}
        </div>
        {editing && form ? (
          <Field label="标题" className="mt-2"><Input className="w-full" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} /></Field>
        ) : (
          <h2 className="mt-2 text-[16px] font-semibold leading-7 tracking-[-0.02em] text-ink-900">{c.title}</h2>
        )}

        {editing && form ? (
          <div className="mt-3 space-y-3">
            <div className="grid grid-cols-2 gap-3">
              <Field label="模块"><Input className="w-full" value={form.module} onChange={(e) => setForm({ ...form, module: e.target.value })} /></Field>
              <Field label="用例类型"><Select opts={["正向", "边界", "异常", "安全"]} className="w-full" value={form.type} onChange={(e) => setForm({ ...form, type: e.target.value })} /></Field>
              <Field label="优先级"><Select opts={["P0", "P1", "P2"]} className="w-full" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value })} /></Field>
              <Field label="状态"><Select opts={["草稿", "待评审", "通过", "失败"]} className="w-full" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })} /></Field>
              <Field label="测试类型" hint="决定能否自动运行">
                <Select opts={["API 测试", "功能测试"]} className="w-full"
                  value={CASE_TYPE_CN[form.caseType]}
                  onChange={(e) => setForm({ ...form, caseType: e.target.value === "API 测试" ? "api" : "functional" })} />
              </Field>
              <Field label="版本"><Input className="w-full" value={form.version} onChange={(e) => setForm({ ...form, version: e.target.value })} /></Field>
            </div>
            <Field label="被测接口" hint="格式：METHOD /path，如 POST /admin/permissions">
              <Input className="w-full font-mono text-[11px]" value={form.relatedApi} onChange={(e) => setForm({ ...form, relatedApi: e.target.value })} />
            </Field>
            <Field label="设计方法"><Input className="w-full" value={form.designMethod} onChange={(e) => setForm({ ...form, designMethod: e.target.value })} /></Field>
            <Field label="测试数据"><Textarea className="h-16 w-full" value={form.testData} onChange={(e) => setForm({ ...form, testData: e.target.value })} /></Field>
            <Field label="数据库校验点"><Textarea className="h-16 w-full" value={form.dbCheck} onChange={(e) => setForm({ ...form, dbCheck: e.target.value })} /></Field>
          </div>
        ) : (
          <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-ink-100 pt-4">
            {info("优先级", <Tag t={c.priority} c={c.priority === "P0" ? "red" : "amber"} />)}
            {info("状态", <Tag t={c.status} c={c.status === "通过" ? "green" : c.status === "失败" ? "red" : "amber"} />)}
            {info("用例类型", c.type)}
            {info("版本", <span className="font-mono">{c.version}</span>)}
            {info("来源", c.source)}
            {info("负责人", c.owner)}
            {info("更新时间", <span className="font-mono text-[11px]">{c.updatedAt}</span>)}
            {c.designMethod && info("设计方法", c.designMethod)}
          </dl>
        )}

        {!editing && (
          <div className="mt-4 space-y-2 border-t border-ink-100 pt-4">
            <div className="text-[11px] font-medium text-ink-500">被测接口</div>
            {c.relatedApi
              ? <code className="block rounded-md bg-ink-50 px-2.5 py-1.5 font-mono text-[11px] text-brand-700">{c.relatedApi}</code>
              : <div className="text-[11px] text-ink-400">功能测试用例，无被测接口</div>}
            {c.requirementId && (
              <button onClick={() => navigate(`/project/${pid}/requirements/${c.requirementId}`)}
                className="inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700">
                归属需求 {c.requirementId} <Icon name="arrow-right" size={12} />
              </button>
            )}
            {(c.relatedRequirementIds ?? []).length > 0 && (
              <div className="text-[11px] text-ink-500">
                关联需求：
                {(c.relatedRequirementIds ?? []).map((rid, i) => (
                  <span key={rid}>
                    {i > 0 && "、"}
                    <button onClick={() => navigate(`/project/${pid}/requirements/${rid}`)} className="text-brand-600 hover:text-brand-700">{rid}</button>
                  </span>
                ))}
              </div>
            )}
          </div>
        )}

        {editing && <Btn v="ghost" size="sm" className="mt-3 w-full" onClick={() => setEditing(false)}>取消编辑</Btn>}
      </Card>

      {/* 右：执行与内容 */}
      <div className="space-y-4">
        {/* 运行面板 */}
        <Card title="执行" extra={
          isApi && c.lastRun
            ? <span className="text-[10px] text-ink-400">最近：{c.lastRun.verdict} · {c.lastRun.at}</span>
            : !isApi && c.lastRun
              ? <span className="text-[10px] text-ink-400">最近人工：{c.lastRun.verdict} · {c.lastRun.at}{c.lastRun.executor ? ` · ${c.lastRun.executor}` : ""}</span>
              : undefined
        }>
          {isApi ? (
            <div className="space-y-3 text-xs">
              <p className="text-[11px] leading-5 text-ink-500">
                点击运行将按被测接口契约自动构造请求与测试数据，打到真实后端执行，并按预期（HTTP 状态 / 业务码）自动判定。
                管理端与 C 端身份自动切换；删除类接口需勾选强制执行。
              </p>
              <div className="flex flex-wrap items-center gap-3">
                <Btn size="sm" onClick={run} disabled={running}>{running ? "运行中…" : isDelete && report ? "强制执行" : "运行"}</Btn>
                {isDelete && (
                  <label className="flex items-center gap-1.5 text-[11px] text-ink-600">
                    <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
                    强制执行删除（会真实删除演示库数据，不可恢复）
                  </label>
                )}
              </div>
              {report && (
                <div className="space-y-2">
                  <div className="flex items-center gap-2">
                    <span className="text-ink-500">判定</span>
                    <Tag t={report.verdict ?? "—"} c={verdictTone(report.verdict)} dot={false} />
                    <span className="text-[11px] text-ink-500">{report.detail}</span>
                  </div>
                  <div className="grid gap-2 md:grid-cols-2">
                    <div className="rounded-lg border border-line px-3 py-2">
                      <div className="mb-1 text-[10px] font-semibold text-ink-500">请求</div>
                      <code className="font-mono text-[11px] break-all">{report.request?.method} {report.request?.path}</code>
                      {report.request?.body != null && (
                        <pre className="mt-1 max-h-24 overflow-auto rounded bg-ink-50 p-2 font-mono text-[10px]">{JSON.stringify(report.request.body)}</pre>
                      )}
                    </div>
                    <div className="rounded-lg border border-line px-3 py-2">
                      <div className="mb-1 text-[10px] font-semibold text-ink-500">实际响应</div>
                      <div className="flex gap-3 font-mono text-[11px]">
                        <span>HTTP {report.actual?.http}</span>
                        <span>code={report.actual?.code ?? "—"}</span>
                      </div>
                      <div className="text-[11px] text-ink-500">{report.actual?.msg}</div>
                      {report.actual?.dataPreview && (
                        <pre className="mt-1 max-h-28 overflow-auto rounded bg-ink-50 p-2 font-mono text-[10px] whitespace-pre-wrap">{report.actual.dataPreview}</pre>
                      )}
                    </div>
                  </div>
                </div>
              )}
            </div>
          ) : (
            <div className="space-y-3 text-xs">
              <p className="text-[11px] leading-5 text-ink-500">功能测试用例：请按步骤在系统页面上人工操作，逐项确认后记录执行结论。</p>
              <ol className="space-y-1.5">
                {c.steps.map((s, i) => (
                  <li key={i} className="flex items-center gap-2 rounded border border-line px-3 py-1.5">
                    <label className="flex flex-1 items-center gap-2">
                      <input type="checkbox" checked={!!checkedSteps[i]} onChange={(e) => setCheckedSteps({ ...checkedSteps, [i]: e.target.checked })} />
                      <span className="min-w-0 flex-1">{s}</span>
                    </label>
                    <span className="font-mono text-[10px] text-ink-400">步骤 {i + 1}</span>
                  </li>
                ))}
              </ol>
              <div className="flex flex-wrap items-center gap-2">
                <span className="text-[11px] text-ink-500">执行结论</span>
                {(["通过", "失败", "阻塞"] as const).map((v) => (
                  <button key={v} type="button" onClick={() => setManualVerdict(v)}
                    className={`rounded-md border px-3 py-1.5 text-[11px] ${manualVerdict === v ? "border-brand-500 bg-brand-50 text-brand-700" : "border-line text-ink-600 hover:bg-ink-50"}`}>
                    {v}
                  </button>
                ))}
                <Input className="h-8 w-56 text-[11px]" placeholder="备注（失败/阻塞原因）" value={manualNote} onChange={(e) => setManualNote(e.target.value)} />
                <Btn size="sm" onClick={run} disabled={running || !manualVerdict}>{running ? "保存中…" : "记录结果"}</Btn>
              </div>
              {report?.lastRun && (
                <div className="text-[11px] text-ink-500">
                  已记录：{report.lastRun.verdict} · {report.lastRun.at}{report.lastRun.executor ? ` · ${report.lastRun.executor}` : ""}
                  {report.lastRun.note ? ` · ${report.lastRun.note}` : ""}
                </div>
              )}
            </div>
          )}
        </Card>

        {/* 测试内容 */}
        <Card title="测试内容">
          <div className="space-y-3 text-xs">
            <div><div className="mb-1 text-[11px] text-ink-500">前置条件</div><div>{c.precondition || "无"}</div></div>
            {c.testData && <div><div className="mb-1 text-[11px] text-ink-500">测试数据</div><div className="whitespace-pre-wrap">{c.testData}</div></div>}
            <div>
              <div className="mb-1 text-[11px] text-ink-500">测试步骤</div>
              <ol className="list-decimal space-y-1 pl-4">{c.steps.map((s, i) => <li key={i}>{s}</li>)}</ol>
            </div>
            <div><div className="mb-1 text-[11px] text-ink-500">预期结果</div><div>{c.expected}</div></div>
            {c.dbCheck && (
              <div className="rounded-lg border border-brand-100 bg-brand-50/50 px-3 py-2">
                <div className="mb-1 text-[11px] font-semibold text-brand-700">数据库校验点</div>
                <div className="font-mono text-[11px] text-brand-800">{c.dbCheck}</div>
              </div>
            )}
          </div>
        </Card>

        <div>
          <Btn v="ghost" size="sm" onClick={() => navigate(`/project/${pid}/testcases`)}>
            ← 返回用例列表
          </Btn>
        </div>
      </div>
    </div>
  );
}
