import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiTestApi, requirementsApi, tasksApi } from "@/api";
import type { GenerationResult, Prototype, Requirement, VersionSnapshot } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { downloadBlob, downloadText } from "@/lib/download";
import { prototypeToSvg } from "@/lib/prototypeSvg";
import { MODELS } from "@/config/constants";
import { cx } from "@/lib/cx";
import { Btn, Card, Drawer, Field, Icon, Input, Modal, Progress, Select, Tag, Textarea } from "@/components/ui";
import { MonacoEditor, PrototypeEditor, PrototypeRenderer, RequirementSplit, VersionDiff } from "@/components/business";

const STAGES = ["检索知识库", "需求拆解", "结构生成", "校验", "完成"];

export function RequirementDetail() {
  const { rid = "" } = useParams<{ rid: string }>();
  const { data: req, setData: setReq } = useAsync<Requirement | null>(() => requirementsApi.get(rid).then((r) => r ?? null), [rid], null);
  const { data: versions } = useAsync(() => tasksApi.versions(), [], [] as VersionSnapshot[]);
  const { data: children } = useAsync(() => req ? requirementsApi.children(req.id) : Promise.resolve([]), [req?.id, req?.splitStatus], [] as Requirement[]);
  const { projectId, addTask, toast } = useApp();
  const navigate = useNavigate();
  const [sub, setSub] = useState<"原型图" | "接口设计">("原型图");
  const [progress, setProgress] = useState<Record<string, number>>({});
  const [editorOpen, setEditorOpen] = useState(false);
  const [diffOpen, setDiffOpen] = useState(false);
  const [yamlDraft, setYamlDraft] = useState<string | null>(null);
  const [preview, setPreview] = useState<{ filename: string; text: string } | null>(null);
  const [reqOpen, setReqOpen] = useState(false);
  const [reqForm, setReqForm] = useState({
    title: "",
    priority: "P1" as Requirement["priority"],
    owner: "",
    status: "",
    description: "",
  });

  if (!req) {
    return (
      <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
        <div className="h-96 animate-pulse rounded-card border border-line bg-white" />
        <div className="h-96 animate-pulse rounded-card border border-line bg-white" />
      </div>
    );
  }

  const p = progress[sub] ?? -1;
  const latest = (kind: GenerationResult["kind"]) => req.generations.find((g) => g.kind === kind);
  const proto = req.prototype;
  const yaml = yamlDraft ?? req.apiYaml ?? "";
  const endpoints = latest("api")?.endpoints ?? [];
  const checks = latest(sub === "原型图" ? "prototype" : "api")?.checks ?? [];
  const hasContent = sub === "原型图" ? !!proto : !!req.apiYaml;
  const showContent = p === 100 || (p < 0 && hasContent);

  const run = async () => {
    if (p >= 0 && p < 100) return;
    setProgress((m) => ({ ...m, [sub]: 0 }));
    addTask(`${sub}生成 · ${req.title}`);
    const timer = window.setInterval(() => {
      setProgress((m) => ({ ...m, [sub]: Math.min(90, (m[sub] ?? 0) + 8) }));
    }, 160);
    try {
      await requirementsApi.generate(req.id, sub === "原型图" ? "prototype" : "api");
      const fresh = await requirementsApi.get(req.id);
      if (fresh) setReq(fresh);
      setProgress((m) => ({ ...m, [sub]: 100 }));
      setYamlDraft(null);
      toast(`${sub}生成完成`);
    } catch (e) {
      setProgress((m) => ({ ...m, [sub]: -1 }));
      toast(e instanceof Error ? e.message : "生成失败");
    } finally {
      window.clearInterval(timer);
    }
  };

  const savePrototype = async (prototype: Prototype) => {
    try {
      setReq(await requirementsApi.savePrototype(req.id, prototype));
      setEditorOpen(false);
      toast("原型结构已保存");
    } catch (e) {
      toast(e instanceof Error ? e.message : "保存失败");
    }
  };

  const saveYaml = async () => {
    setReq(await requirementsApi.saveYaml(req.id, yaml));
    toast("OpenAPI 文档已保存");
  };

  const exportPng = async () => {
    if (!proto) return;
    const { svg, width, height } = prototypeToSvg(proto);
    const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
    try {
      const img = new Image();
      await new Promise<void>((resolve, reject) => {
        img.onload = () => resolve();
        img.onerror = () => reject(new Error("render failed"));
        img.src = url;
      });
      const scale = 2;
      const canvas = document.createElement("canvas");
      canvas.width = width * scale;
      canvas.height = height * scale;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("canvas unavailable");
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      await new Promise<void>((resolve) => {
        canvas.toBlob((blob) => {
          if (blob) downloadBlob(`${req.id}-prototype.png`, blob);
          resolve();
        }, "image/png");
      });
      toast("已导出原型图（PNG）");
    } catch {
      toast("导出 PNG 失败");
    } finally {
      URL.revokeObjectURL(url);
    }
  };

  const importApi = async () => {
    if (!yaml.trim()) { toast("请先生成接口设计"); return; }
    try {
      const added = await apiTestApi.importYaml(yaml, "会员");
      toast(added.length ? `已导入 ${added.length} 个接口` : "接口已存在，未新增");
      navigate(`/project/${projectId}/api?imported=1`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "导入失败");
    }
  };

  const previewFile = async (fileId: string) => {
    try {
      const result = await requirementsApi.fileText(req.id, fileId);
      setPreview(result);
    } catch (e) {
      toast(e instanceof Error ? e.message : "预览失败");
    }
  };

  const openReqEdit = () => {
    setReqForm({ title: req.title, priority: req.priority, owner: req.owner, status: req.status, description: req.description });
    setReqOpen(true);
  };

  const saveReq = async () => {
    if (!reqForm.title.trim()) { toast("请输入需求名称"); return; }
    try {
      setReq(await requirementsApi.update(req.id, reqForm));
      setReqOpen(false);
      toast("需求信息已保存");
    } catch (e) {
      toast(e instanceof Error ? e.message : "保存失败");
    }
  };

  const downloadFile = async (fileId: string, filename: string) => {
    try {
      const blob = await requirementsApi.downloadFile(req.id, fileId);
      downloadBlob(filename, blob);
    } catch (e) {
      toast(e instanceof Error ? e.message : "下载失败");
    }
  };

  const diffKind = sub === "原型图" ? "原型结构" : "接口设计";
  const diffPair = versions.filter((v) => v.kind === diffKind).slice(-2);

  return (
    <div className="grid gap-4 xl:grid-cols-[320px_minmax(0,1fr)]">
      <Card className="h-fit" title="需求信息" extra={<Btn v="secondary" size="sm" onClick={openReqEdit}>编辑</Btn>}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] text-ink-400">{req.id}</span>
          <Tag t={req.status} />
        </div>
        <h2 className="mt-2 text-[18px] font-semibold leading-7 tracking-[-0.02em] text-ink-900">{req.title}</h2>
        <p className="mt-2 line-clamp-4 text-[12px] leading-5 text-ink-500">{req.description || "暂无描述"}</p>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-ink-100 pt-4">
          <div>
            <dt className="text-[11px] text-ink-500">优先级</dt>
            <dd className="mt-1"><Tag t={req.priority} /></dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-500">状态</dt>
            <dd className="mt-1"><Tag t={req.status} /></dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-500">负责人</dt>
            <dd className="mt-1 text-[12px] font-medium text-ink-800">{req.owner || "-"}</dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-500">版本</dt>
            <dd className="mt-1 font-mono text-[12px] text-ink-800">{req.version}</dd>
          </div>
        </dl>

        {req.parentId && (
          <button onClick={() => navigate(`/project/${projectId}/requirements/${req.parentId}`)} className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700">
            ← 返回主需求
          </button>
        )}

        {req.files && req.files.length > 0 && (
          <div className="mt-4 border-t border-ink-100 pt-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-medium text-ink-500">需求文档</div>
              <span className="text-[10px] text-ink-400">{req.files.length} 个文件</span>
            </div>
            <div className="space-y-1">
              {req.files.map((file) => (
                <div key={file.id} className="group flex items-center gap-2 rounded-lg px-2 py-2 text-[11px] hover:bg-ink-50">
                  <Icon name="folder" size={14} className="shrink-0 text-ink-400" />
                  <span className="min-w-0 flex-1 truncate text-ink-600" title={file.filename}>{file.filename}</span>
                  <button onClick={() => previewFile(file.id)} className="shrink-0 text-brand-600 hover:text-brand-700">预览</button>
                  <button onClick={() => downloadFile(file.id, file.filename)} className="shrink-0 text-ink-500 hover:text-ink-800">下载</button>
                </div>
              ))}
            </div>
          </div>
        )}

        {req.points.length > 0 && (
          <div className="mt-4 border-t border-ink-100 pt-4">
            <div className="mb-2 text-[11px] font-medium text-ink-500">AI 需求拆解</div>
            <div className="space-y-1.5">
              {req.points.map((point) => (
                <div key={point} className="flex gap-2 text-[11px] leading-5 text-ink-600">
                  <span className="mt-2 h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                  <span>{point}</span>
                </div>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 border-t border-ink-100 pt-4"><RequirementSplit requirement={req} onUpdated={setReq} /></div>

        {children.length > 0 && (
          <div className="mt-4 border-t border-ink-100 pt-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-medium text-ink-500">子需求</div>
              <span className="text-[10px] text-ink-400">{children.length} 项</span>
            </div>
            <div className="space-y-0.5">
              {children.map((child) => (
                <button key={child.id} onClick={() => navigate(`/project/${projectId}/requirements/${child.id}`)} className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left text-[11px] text-ink-600 hover:bg-ink-50 hover:text-brand-600">
                  <span className="min-w-0 flex-1 truncate">{child.title}</span>
                  <Tag t={child.priority} />
                </button>
              ))}
            </div>
          </div>
        )}
      </Card>

      <Card
        title="AI 设计生成"
        extra={<span className="hidden text-[11px] text-ink-500 lg:inline">工作流模板：需求 → {sub === "原型图" ? "原型" : "接口"}</span>}
      >
        <div className="mb-5 flex flex-wrap items-center gap-3">
          <div className="inline-flex rounded-lg border border-line bg-ink-50 p-1">
            {(["原型图", "接口设计"] as const).map((s) => (
              <button
                key={s}
                onClick={() => setSub(s)}
                className={cx(
                  "rounded-md px-3.5 py-1.5 text-[12px] transition-colors",
                  sub === s ? "bg-white font-medium text-ink-900 shadow-sm" : "text-ink-500 hover:text-ink-800",
                )}
              >
                {s}
              </button>
            ))}
          </div>
          <div className="flex-1" />
          <Btn v="secondary" size="sm" onClick={() => navigate(`/project/${projectId}/testcases/generate?requirement=${encodeURIComponent(req.id)}&source=${encodeURIComponent("需求文档")}`)}>生成测试用例</Btn>
          <Select opts={MODELS} className="h-8 text-xs" />
          <Btn size="sm" onClick={run} loading={p >= 0 && p < 100} disabled={p >= 0 && p < 100}>
            {p >= 0 && p < 100 ? "生成中…" : p === 100 ? "重新生成" : `生成${sub}`}
          </Btn>
        </div>

        {p >= 0 && p < 100 && (
          <div className="mb-5 rounded-xl border border-brand-100 bg-brand-50/70 p-4">
            <div className="mb-2 flex items-center justify-between text-[11px] text-brand-700">
              <span>任务进度 · {STAGES[Math.min(4, Math.floor(p / 25))]}</span>
              <span className="tabular-nums font-medium">{p}%</span>
            </div>
            <Progress value={p} />
          </div>
        )}

        {!showContent ? (
          <div className="flex min-h-80 flex-col items-center justify-center rounded-xl border border-dashed border-ink-200 bg-ink-50/50 p-8 text-center">
            <div className="grid h-12 w-12 place-items-center rounded-xl bg-white text-brand-500 shadow-card"><Icon name={sub === "原型图" ? "monitor" : "api"} size={22} /></div>
            <div className="mt-4 text-[14px] font-medium text-ink-800">还没有生成{sub}</div>
            <div className="mt-1.5 max-w-md text-[12px] leading-6 text-ink-500">
              选择模型后点击“生成{sub}”，AI 会基于需求文档、拆分结果和知识库生成初稿，产物会在这里预览。
            </div>
            <Btn className="mt-4" size="sm" onClick={run}>生成{sub}</Btn>
          </div>
        ) : sub === "原型图" ? (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
            <div>{proto && <PrototypeRenderer prototype={proto} />}</div>
            <div className="h-fit rounded-xl border border-line bg-ink-50/50 p-4">
              <div className="mb-3 text-[12px] font-medium text-ink-700">校验结果</div>
              <div className="space-y-2">
                {checks.map((check) => <div key={check.label} className="flex items-center gap-2 text-[11px] text-ink-600"><Tag t={check.status} />{check.label}</div>)}
              </div>
              <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-200 pt-4">
                <Btn v="secondary" size="sm" onClick={() => setEditorOpen(true)}>编辑结构</Btn>
                <Btn v="secondary" size="sm" onClick={() => setDiffOpen(true)}>版本对比</Btn>
                <Btn v="secondary" size="sm" onClick={exportPng}>导出 PNG</Btn>
                <Btn size="sm" onClick={() => navigate(`/project/${projectId}/testcases/generate?requirement=${encodeURIComponent(req.id)}&source=${encodeURIComponent("原型图")}`)}>作为用例输入</Btn>
              </div>
            </div>
          </div>
        ) : (
          <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_280px]">
            <div className="overflow-hidden rounded-xl border border-line"><MonacoEditor value={yaml} onChange={setYamlDraft} language="yaml" height={420} path={`${req.id}.yaml`} /></div>
            <div className="h-fit rounded-xl border border-line bg-ink-50/50 p-4">
              <div className="mb-3 text-[12px] font-medium text-ink-700">接口清单（{endpoints.length}）</div>
              <div className="space-y-2">
                {endpoints.map((endpoint) => (
                  <div key={endpoint.id} className="flex items-center gap-2 text-[11px]"><Tag t={endpoint.method} c={endpoint.method === "GET" ? "blue" : "green"} /><code className="truncate font-mono text-ink-600">{endpoint.path}</code></div>
                ))}
                {endpoints.length === 0 && <div className="text-[11px] text-ink-500">暂无接口，生成后会显示在这里。</div>}
              </div>
              {checks.length > 0 && <div className="mt-4 space-y-2 border-t border-ink-200 pt-4">{checks.map((check) => <div key={check.label} className="flex items-center gap-2 text-[11px] text-ink-600"><Tag t={check.status} />{check.label}</div>)}</div>}
              <div className="mt-4 flex flex-wrap gap-2 border-t border-ink-200 pt-4">
                <Btn v="secondary" size="sm" onClick={() => setDiffOpen(true)}>版本对比</Btn>
                <Btn v="secondary" size="sm" onClick={saveYaml}>保存修改</Btn>
                <Btn v="secondary" size="sm" onClick={() => { downloadText(`${req.id}.yaml`, yaml, "text/yaml;charset=utf-8"); toast("已导出 YAML"); }}>导出 YAML</Btn>
                <Btn size="sm" onClick={importApi}>导入到 API 测试</Btn>
              </div>
            </div>
          </div>
        )}
      </Card>

      {editorOpen && proto && <PrototypeEditor prototype={proto} onClose={() => setEditorOpen(false)} onSave={savePrototype} />}

      <Modal open={reqOpen} title="编辑需求信息" onClose={() => setReqOpen(false)} footer={<><Btn v="ghost" onClick={() => setReqOpen(false)}>取消</Btn><Btn onClick={saveReq}>保存</Btn></>}>
        <div className="space-y-3">
          <Field label="需求名称"><Input className="w-full" value={reqForm.title} onChange={(e) => setReqForm({ ...reqForm, title: e.target.value })} /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="优先级"><Select opts={["P0", "P1", "P2"]} className="w-full" value={reqForm.priority} onChange={(e) => setReqForm({ ...reqForm, priority: e.target.value as Requirement["priority"] })} /></Field>
            <Field label="负责人"><Input className="w-full" value={reqForm.owner} onChange={(e) => setReqForm({ ...reqForm, owner: e.target.value })} /></Field>
            <Field label="状态"><Select opts={["待解析", "解析中", "已解析", "待评审", "已完成", "已驳回"]} className="w-full" value={reqForm.status} onChange={(e) => setReqForm({ ...reqForm, status: e.target.value })} /></Field>
          </div>
          <Field label="需求描述"><Textarea className="w-full h-32" value={reqForm.description} onChange={(e) => setReqForm({ ...reqForm, description: e.target.value })} /></Field>
        </div>
      </Modal>

      <Drawer open={!!preview} title={preview ? `文档预览 · ${preview.filename}` : ""} onClose={() => setPreview(null)} width="w-[720px]">
        <pre className="whitespace-pre-wrap text-[11px] leading-relaxed text-ink-700">{preview?.text}</pre>
      </Drawer>

      <Modal open={diffOpen} title={`版本对比 · ${diffKind}`} onClose={() => setDiffOpen(false)} width="max-w-3xl">
        {diffPair.length >= 2 ? (
          <VersionDiff left={diffPair[0].content} right={diffPair[1].content} leftLabel={diffPair[0].version} rightLabel={diffPair[1].version} />
        ) : (
          <div className="h-32 grid place-items-center text-xs text-ink-500">暂无足够版本可对比，请先生成两次产物</div>
        )}
      </Modal>
    </div>
  );
}
