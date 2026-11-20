import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { requirementsApi, testcasesApi } from "@/api";
import type { Requirement, TestCase } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { MODELS } from "@/config/constants";
import { Btn, Card, Field, Input, Modal, Select, Table, Textarea, Tag } from "@/components/ui";
import { cx } from "@/lib/cx";

const STRATEGIES = ["正向流程", "边界值", "异常场景", "安全"];

type Engine = "internal" | "external";

export function CaseGenerate() {
  const [params] = useSearchParams();
  const { projectId, addTask, toast } = useApp();
  const navigate = useNavigate();
  const { data: reqs } = useAsync(() => requirementsApi.list(), [], [] as Requirement[]);
  const { data: engines } = useAsync(() => testcasesApi.engines(), [], null);

  const requirementId = params.get("requirement") ?? undefined;
  const [src, setSrc] = useState(params.get("source") ?? "需求文档");
  const [engine, setEngine] = useState<Engine>("internal");
  const [relatedIds, setRelatedIds] = useState<string[]>(
    requirementId ? [requirementId] : []);
  const [relatedSearch, setRelatedSearch] = useState("");
  const [strategies, setStrategies] = useState<string[]>(["正向流程", "边界值", "异常场景"]);
  const [model, setModel] = useState("GPT-4o");
  const [rag, setRag] = useState(true);
  const [out, setOut] = useState<TestCase[]>([]);
  const [busy, setBusy] = useState(false);
  const [editing, setEditing] = useState<TestCase | null>(null);
  const [editForm, setEditForm] = useState({ title: "", steps: "", expected: "" });

  // URL 带 requirement 时默认选中它作为主需求
  useEffect(() => {
    if (requirementId) setRelatedIds((ids) => ids.includes(requirementId) ? ids : [requirementId, ...ids]);
  }, [requirementId]);

  // 外部 AI 不可用时强制切到内部引擎
  useEffect(() => {
    if (engines && !engines.externalReady && engine === "external") setEngine("internal");
  }, [engines, engine]);

  const reqById = useMemo(() => {
    const m: Record<string, Requirement> = {};
    reqs.forEach((r) => { m[r.id] = r; });
    return m;
  }, [reqs]);

  const filteredReqs = useMemo(() => {
    const q = relatedSearch.trim().toLowerCase();
    if (!q) return reqs.slice(0, 8);
    return reqs.filter((r) => r.id.toLowerCase().includes(q) || r.title.toLowerCase().includes(q)).slice(0, 8);
  }, [reqs, relatedSearch]);

  const gen = async () => {
    setBusy(true);
    setOut([]);
    addTask(`AI 生成用例 · ${engine === "internal" ? "内部逻辑" : "外部AI"}`);
    try {
      const items = await testcasesApi.generate({
        source: src,
        requirementId: relatedIds[0],
        engine,
        strategies,
        rag,
        model: engine === "external" ? model : undefined,
        relatedRequirementIds: relatedIds,
      });
      if (!items.length) {
        setBusy(false);
        toast("未生成用例，请检查配置");
        return;
      }
      items.forEach((c, i) => {
        window.setTimeout(() => {
          setOut((prev) => [...prev, c]);
          if (i === items.length - 1) {
            setBusy(false);
            toast(`生成 ${items.length} 条用例草稿`);
          }
        }, 220 * (i + 1));
      });
    } catch (e) {
      setBusy(false);
      toast(e instanceof Error ? e.message : "生成失败");
    }
  };

  const submit = async () => {
    const count = await testcasesApi.submitReview(out);
    toast(`已提交 ${count} 条用例评审`);
    navigate(`/project/${projectId}/testcases/review`);
  };

  const openEdit = (c: TestCase) => {
    setEditing(c);
    setEditForm({ title: c.title, steps: c.steps.join("\n"), expected: c.expected });
  };

  const saveEdit = () => {
    if (!editing) return;
    setOut(out.map((c) => c.id === editing.id ? {
      ...c, title: editForm.title,
      steps: editForm.steps.split("\n").filter(Boolean),
      expected: editForm.expected,
    } : c));
    setEditing(null);
    toast("草稿已更新");
  };

  const toggleStrategy = (s: string) => setStrategies((list) => list.includes(s) ? list.filter((x) => x !== s) : [...list, s]);
  const toggleRelated = (id: string) => setRelatedIds((ids) => ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]);

  const externalEngine = engines?.engines.find((e) => e.value === "external");

  return (
    <div className="grid grid-cols-5 gap-4">
      <Card title="生成配置" className="col-span-2">
        <div className="space-y-4 text-xs">
          {/* 引擎选择 */}
          <Field label="生成引擎" as="div">
            <div className="grid grid-cols-2 gap-2 mt-1">
              {(engines?.engines ?? [
                { value: "internal" as Engine, label: "系统内部逻辑", available: true, desc: "本地生成" },
                { value: "external" as Engine, label: "外部 AI API", available: false, desc: "未配置" },
              ]).map((e) => (
                <button key={e.value} disabled={!e.available}
                  onClick={() => setEngine(e.value as Engine)}
                  className={cx(
                    "rounded-lg border px-3 py-2.5 text-left transition-colors",
                    !e.available && "opacity-50 cursor-not-allowed",
                    engine === e.value && e.available
                      ? "border-brand-500 bg-brand-50/60 ring-1 ring-brand-200"
                      : "border-line hover:border-brand-300",
                  )}>
                  <div className="flex items-center gap-1.5">
                    <span className={cx("h-1.5 w-1.5 rounded-full",
                      e.available ? "bg-green-500" : "bg-ink-300")} />
                    <span className="text-[12px] font-semibold text-ink-800">{e.label}</span>
                  </div>
                  <div className="mt-1 text-[10px] leading-4 text-ink-500">{e.desc}</div>
                </button>
              ))}
            </div>
          </Field>

          <Field label="输入来源">
            <Select value={src} onChange={(e) => setSrc(e.target.value)} opts={["需求文档", "PRD 文档（代码还原）", "原型：会员中心", "接口设计：会员中心 API"]} className="w-full" />
          </Field>

          {/* 关联需求：多选 + 搜索 */}
          <Field label="关联需求（可多选）" as="div">
            <div className="mt-1 rounded-lg border border-line p-2">
              {relatedIds.length > 0 && (
                <div className="mb-2 flex flex-wrap gap-1">
                  {relatedIds.map((id) => (
                    <span key={id} className="inline-flex items-center gap-1 rounded bg-brand-50 px-2 py-1 text-[10px] text-brand-700 ring-1 ring-brand-100">
                      <span className="font-mono">{id}</span>
                      <button onClick={() => toggleRelated(id)} className="text-brand-400 hover:text-brand-700">×</button>
                    </span>
                  ))}
                </div>
              )}
              <Input className="w-full text-[11px]" placeholder="搜索需求编号或标题…"
                value={relatedSearch} onChange={(e) => setRelatedSearch(e.target.value)} />
              <div className="mt-1.5 max-h-32 overflow-auto space-y-0.5">
                {filteredReqs.map((r) => (
                  <button key={r.id} onClick={() => toggleRelated(r.id)}
                    className={cx("flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11px] hover:bg-ink-50",
                      relatedIds.includes(r.id) ? "bg-brand-50/60 text-brand-700" : "text-ink-600")}>
                    <span className={cx("grid h-3.5 w-3.5 place-items-center rounded border text-[9px]",
                      relatedIds.includes(r.id) ? "border-brand-500 bg-brand-500 text-white" : "border-ink-300")}>
                      {relatedIds.includes(r.id) ? "✓" : ""}
                    </span>
                    <span className="font-mono text-[10px]">{r.id}</span>
                    <span className="min-w-0 flex-1 truncate">{r.title}</span>
                  </button>
                ))}
              </div>
            </div>
            <div className="mt-1 text-[10px] text-ink-400">第一条作为主需求，其余作为关联上下文，生成的用例会记录全部关联。</div>
          </Field>

          <Field label="生成策略" as="div">
            <div className="flex flex-wrap gap-3 mt-1">
              {STRATEGIES.map((s) => (
                <label key={s} className="flex gap-1 items-center">
                  <input type="checkbox" checked={strategies.includes(s)} onChange={() => toggleStrategy(s)} />{s}
                </label>
              ))}
            </div>
          </Field>

          {engine === "external" && (
            <>
              <Field label="模型"><Select opts={MODELS} className="w-full" value={model} onChange={(e) => setModel(e.target.value)} /></Field>
              <label className="flex gap-2 items-center"><input type="checkbox" checked={rag} onChange={(e) => setRag(e.target.checked)} />启用知识库增强（RAG）</label>
            </>
          )}

          {engine === "internal" && (
            <div className="rounded-lg border border-green-200 bg-green-50/50 px-3 py-2 text-[10px] leading-5 text-green-800">
              内部引擎基于 PRD 的业务规则、负面清单（NEG）、接口契约与验收标准生成用例，
              无外部 API 依赖，结果稳定可复现。
            </div>
          )}

          <Btn onClick={gen} disabled={busy || strategies.length === 0 || relatedIds.length === 0} className="w-full">
            {busy ? "生成中…" : "开始生成"}
          </Btn>
          <div className="text-[11px] text-ink-500 leading-relaxed">
            生成结果会推送到右下角任务悬浮窗，可在「任务与报告」查看历史。提交评审后用例入库并保留需求关联。
          </div>
        </div>
      </Card>

      <Card title={`用例草稿（${out.length}）`} className="col-span-3"
        extra={out.length > 0 && !busy && <Btn onClick={submit}>提交评审</Btn>}>
        {out.length > 0 ? (
          <Table
            cols={["#", "标题", "类型", "优先级", "关联需求", "来源"]}
            rows={out.map((c) => [
              <span className="font-mono text-[10px] text-ink-400">{c.id}</span>,
              <span className="max-w-[260px] truncate" title={c.title}>{c.title}</span>,
              <Tag t={c.type} c={c.type === "异常" ? "red" : c.type === "边界" ? "amber" : c.type === "安全" ? "gray" : "blue"} dot={false} />,
              c.priority,
              <span className="font-mono text-[10px] text-brand-600" title={(c.relatedRequirementIds ?? []).join(", ")}>
                {(c.relatedRequirementIds ?? []).join(" / ") || "—"}
              </span>,
              <span className="text-[10px] text-ink-500">{c.source}</span>,
            ])}
            actions={(i) => (
              <>
                <Btn v="ghost" onClick={() => openEdit(out[i])}>编辑</Btn>
                <Btn v="danger" onClick={() => setOut(out.filter((_, idx) => idx !== i))}>移除</Btn>
              </>
            )}
          />
        ) : (
          <div className="h-60 grid place-items-center text-xs text-ink-500">
            {busy ? "正在生成…" : "选择引擎与需求后点击「开始生成」"}
          </div>
        )}
      </Card>

      <Modal open={!!editing} title={editing ? `编辑草稿 · ${editing.id}` : ""} onClose={() => setEditing(null)}
        width="max-w-2xl" footer={<><Btn v="ghost" onClick={() => setEditing(null)}>取消</Btn><Btn onClick={saveEdit}>保存</Btn></>}>
        <div className="space-y-3">
          <Field label="标题"><Input className="w-full" value={editForm.title} onChange={(e) => setEditForm({ ...editForm, title: e.target.value })} /></Field>
          <Field label="测试步骤" hint="每行一个步骤"><Textarea className="w-full h-28" value={editForm.steps} onChange={(e) => setEditForm({ ...editForm, steps: e.target.value })} /></Field>
          <Field label="预期结果"><Textarea className="w-full h-20" value={editForm.expected} onChange={(e) => setEditForm({ ...editForm, expected: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}
