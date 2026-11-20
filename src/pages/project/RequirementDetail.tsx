import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { prdApi, requirementsApi, testcasesApi } from "@/api";
import type { PrdResponse } from "@/api/prd";
import type { Requirement, TestCase } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { downloadBlob } from "@/lib/download";
import { Btn, Card, Empty, Field, Icon, Input, Modal, Select, Tag, Textarea } from "@/components/ui";
import { PrdDocument } from "@/components/business";

/** 需求详情：主体是产品文档 AGENT 从真实代码还原出的 PRD。 */
export function RequirementDetail() {
  const { rid = "" } = useParams<{ rid: string }>();
  const { data: req, setData: setReq } = useAsync<Requirement | null>(
    () => requirementsApi.get(rid).then((r) => r ?? null), [rid], null);
  const { data: children } = useAsync(
    () => req ? requirementsApi.children(req.id) : Promise.resolve([]), [req?.id], [] as Requirement[]);
  const { data: prd, reload: reloadPrd } = useAsync<PrdResponse | null>(
    () => prdApi.get(rid).then((r) => r ?? null).catch(() => null), [rid], null);
  const { data: relatedCases, reload: reloadCases } = useAsync<TestCase[]>(
    () => testcasesApi.list(rid).catch(() => []), [rid], []);
  const { projectId, toast } = useApp();
  const navigate = useNavigate();

  const [reqOpen, setReqOpen] = useState(false);
  const [preview, setPreview] = useState<{ filename: string; text: string } | null>(null);
  const [regenerating, setRegenerating] = useState(false);
  const [agentRunning, setAgentRunning] = useState(false);
  const [reqForm, setReqForm] = useState({
    title: "", priority: "P1" as Requirement["priority"], owner: "", status: "", description: "",
  });

  if (!req) {
    return (
      <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
        <div className="h-96 animate-pulse rounded-card border border-line bg-white" />
        <div className="h-96 animate-pulse rounded-card border border-line bg-white" />
      </div>
    );
  }

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

  const previewFile = async (fileId: string) => {
    try {
      setPreview(await requirementsApi.fileText(req.id, fileId));
    } catch (e) {
      toast(e instanceof Error ? e.message : "预览失败");
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

  const regenerate = async () => {
    setRegenerating(true);
    try {
      await prdApi.regenerate();
      await reloadPrd();
      toast("PRD 已由产品文档 AGENT 重新还原");
    } catch (e) {
      toast(e instanceof Error ? e.message : "重新生成失败");
    } finally {
      setRegenerating(false);
    }
  };

  /** 资深测试工程师 AGENT：需求无用例时一键生成专业用例 */
  const runCaseAgent = async () => {
    setAgentRunning(true);
    try {
      const r = await testcasesApi.agentGenerate({ requirementId: req.id });
      await reloadCases();
      toast(r.message || "测试工程师 AGENT 已完成生成");
    } catch (e) {
      toast(e instanceof Error ? e.message : "AGENT 生成失败");
    } finally {
      setAgentRunning(false);
    }
  };

  return (
    <div className="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)]">
      {/* 左：需求信息 */}
      <Card className="h-fit" title="需求信息" extra={<Btn v="secondary" size="sm" onClick={openReqEdit}>编辑</Btn>}>
        <div className="flex flex-wrap items-center gap-2">
          <span className="font-mono text-[11px] text-ink-400">{req.id}</span>
          <Tag t={req.status} />
        </div>
        <h2 className="mt-2 text-[16px] font-semibold leading-7 tracking-[-0.02em] text-ink-900">{req.title}</h2>

        <dl className="mt-4 grid grid-cols-2 gap-x-4 gap-y-3 border-t border-ink-100 pt-4">
          <div>
            <dt className="text-[11px] text-ink-500">优先级</dt>
            <dd className="mt-1"><Tag t={req.priority} c={req.priority === "P0" ? "red" : "amber"} /></dd>
          </div>
          <div>
            <dt className="text-[11px] text-ink-500">状态</dt>
            <dd className="mt-1"><Tag t={req.status} c="green" /></dd>
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
          <button onClick={() => navigate(`/project/${projectId}/requirements/${req.parentId}`)}
            className="mt-3 inline-flex items-center gap-1 text-[11px] font-medium text-brand-600 hover:text-brand-700">
            ← 返回主需求
          </button>
        )}

        {req.files && req.files.length > 0 && (
          <div className="mt-4 border-t border-ink-100 pt-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-medium text-ink-500">原始需求文档</div>
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

        {children.length > 0 && (
          <div className="mt-4 border-t border-ink-100 pt-4">
            <div className="mb-2 flex items-center justify-between">
              <div className="text-[11px] font-medium text-ink-500">子需求</div>
              <span className="text-[10px] text-ink-400">{children.length} 项</span>
            </div>
            <div className="space-y-0.5">
              {children.map((child) => (
                <button key={child.id} onClick={() => navigate(`/project/${projectId}/requirements/${child.id}`)}
                  className="flex w-full items-center justify-between gap-2 rounded-lg px-2 py-2 text-left text-[11px] text-ink-600 hover:bg-ink-50 hover:text-brand-600">
                  <span className="min-w-0 flex-1 truncate">{child.title}</span>
                  <Tag t={child.priority} />
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-4 border-t border-ink-100 pt-4">
          <div className="mb-2 flex items-center justify-between">
            <div className="text-[11px] font-medium text-ink-500">关联测试用例</div>
            <span className="text-[10px] text-ink-400">{relatedCases.length} 条</span>
          </div>
          {relatedCases.length > 0 ? (
            <div className="max-h-32 space-y-0.5 overflow-auto">
              {relatedCases.map((c) => (
                <button key={c.id} onClick={() => navigate(`/project/${projectId}/testcases?case=${encodeURIComponent(c.id)}`)}
                  className="flex w-full items-center gap-2 rounded px-2 py-1.5 text-left text-[11px] hover:bg-ink-50">
                  <span className="font-mono text-[10px] text-ink-400">{c.id}</span>
                  <span className="min-w-0 flex-1 truncate text-ink-600">{c.title}</span>
                  <Tag t={c.type} c={c.type === "异常" ? "red" : "blue"} dot={false} />
                </button>
              ))}
            </div>
          ) : (
            <div className="rounded-lg border border-amber-200 bg-amber-50/40 px-2.5 py-2 text-[10px] leading-4 text-amber-700">
              暂无用例。可由资深测试工程师 AGENT 按 PRD、接口契约与状态机，
              用等价类 / 边界值 / 状态迁移等七类方法生成专业用例。
            </div>
          )}
          {relatedCases.length === 0 && (
            <Btn size="sm" className="mt-2 w-full" loading={agentRunning} onClick={runCaseAgent}>
              <Icon name="sparkles" size={13} className={agentRunning ? "animate-pulse" : ""} />
              资深测试工程师 AGENT 生成用例
            </Btn>
          )}
          <Btn v="secondary" size="sm" className="mt-2 w-full"
            onClick={() => navigate(`/project/${projectId}/testcases/generate?requirement=${encodeURIComponent(req.id)}&source=${encodeURIComponent("需求文档")}`)}>
            基于需求生成测试用例 <Icon name="arrow-right" size={13} />
          </Btn>
        </div>
      </Card>

      {/* 右：产品文档 AGENT 还原的 PRD */}
      <div className="space-y-3">
        <div className="flex items-center justify-between gap-3 rounded-card border border-line bg-white px-5 py-3">
          <div>
            <div className="text-[13px] font-semibold text-ink-900">需求文档（代码还原）</div>
            <div className="mt-0.5 text-[11px] text-ink-500">
              由产品文档 AGENT 从追溯链、接口契约、表结构与业务规则逆向还原
            </div>
          </div>
          <Btn v="secondary" size="sm" loading={regenerating} onClick={regenerate}>
            <Icon name="spinner" size={13} className={regenerating ? "animate-spin" : "hidden"} />
            重新还原
          </Btn>
        </div>

        {prd ? (
          <PrdDocument
            doc={prd.doc}
            domain={prd.domain}
            coverage={prd.coverage}
            generatedAt={prd.generatedAt || prd.doc.generatedAt}
            projectId={projectId}
          />
        ) : (
          <Card>
            <Empty text="该需求尚未被产品文档 AGENT 还原，点击「重新还原」生成。" />
          </Card>
        )}
      </div>

      <Modal open={reqOpen} title="编辑需求信息" onClose={() => setReqOpen(false)}
        footer={<><Btn v="ghost" onClick={() => setReqOpen(false)}>取消</Btn><Btn onClick={saveReq}>保存</Btn></>}>
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

      {preview && (
        <Modal open title={`文档预览 · ${preview.filename}`} onClose={() => setPreview(null)} width="max-w-3xl">
          <pre className="max-h-[60vh] overflow-auto whitespace-pre-wrap text-[11px] leading-relaxed text-ink-700">{preview.text}</pre>
        </Modal>
      )}
    </div>
  );
}
