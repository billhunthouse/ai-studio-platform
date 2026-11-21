import { useRef, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import { requirementsApi } from "@/api";
import type { Requirement } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { confirmDelete } from "@/lib/confirm";
import { Btn, Card, Field, Icon, Input, Modal, Select, Table, Tag, Textarea, Toolbar } from "@/components/ui";
import { cx } from "@/lib/cx";

const STATUSES = ["全部状态", "待解析", "解析中", "已解析", "待评审", "已完成", "已驳回"];

export function RequirementList() {
  const { data, setData, reload, loading } = useAsync(() => requirementsApi.list(), [], [] as Requirement[]);
  const { projectId, addTask, toast } = useApp();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("全部状态");
  const [module, setModule] = useState("");
  const [expanded, setExpanded] = useState<Set<string>>(new Set());
  const [form, setForm] = useState({ title: "", priority: "P1" as Requirement["priority"], owner: "", description: "" });
  const [uploadTitle, setUploadTitle] = useState("");
  const [files, setFiles] = useState<File[]>([]);
  const [autoSplit, setAutoSplit] = useState(true);
  const [busy, setBusy] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const roots = data.filter((item) => !item.parentId);
  const childrenOf = (parentId: string) => data.filter((item) => item.parentId === parentId);
  const moduleRoots = roots.filter((root) => childrenOf(root.id).length > 0);
  const standaloneRoots = roots.filter((root) => childrenOf(root.id).length === 0);
  const matches = (item: Requirement) =>
    (status === "全部状态" || item.status === status) &&
    (!query || item.title.includes(query) || item.id.includes(query));
  const isFiltering = query.trim() !== "" || status !== "全部状态";

  const titleCounts = roots.reduce<Record<string, number>>((acc, root) => {
    acc[root.title] = (acc[root.title] ?? 0) + 1;
    return acc;
  }, {});
  const visible = roots
    .filter((root) => !module || root.id === module)
    .map((root) => {
      const all = childrenOf(root.id);
      const rootMatch = matches(root);
      const matchedChildren = all.filter(matches);
      return { root, children: rootMatch ? all : matchedChildren, show: rootMatch || matchedChildren.length > 0 };
    })
    .filter((item) => item.show);

  const toggle = (id: string) => {
    setExpanded((current) => {
      const next = new Set(current);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  };

  const expandAll = () => setExpanded(new Set(visible.filter((item) => item.children.length > 0).map((item) => item.root.id)));
  const collapseAll = () => setExpanded(new Set());

  const rows: ReactNode[][] = [];
  const targets: Requirement[] = [];
  for (const item of visible) {
    const isOpen = item.children.length > 0 && (isFiltering || expanded.has(item.root.id));
    rows.push([
      <span key="id" className="font-mono text-[11px] text-ink-500">{item.root.id}</span>,
      <div key="title" className="flex items-center gap-2">
        <button
          onClick={() => toggle(item.root.id)}
          disabled={childrenOf(item.root.id).length === 0}
          className={cx(
            "grid h-6 w-6 place-items-center rounded-md border text-[12px] transition-colors disabled:opacity-30",
            isOpen ? "border-brand-200 bg-brand-50 text-brand-600" : "border-ink-200 bg-white text-ink-500 hover:border-brand-300 hover:text-brand-600",
          )}
          aria-label={isOpen ? "收起子需求" : "展开子需求"}
        >
          {isOpen ? "−" : "+"}
        </button>
        <Tag t={childrenOf(item.root.id).length > 0 ? "模块" : "独立需求"} c={childrenOf(item.root.id).length > 0 ? "blue" : "gray"} />
        <span className="max-w-[420px] truncate font-medium text-ink-800" title={item.root.title}>{item.root.title}</span>
      </div>,
      <span key="count" className="tabular-nums text-[12px] text-ink-500">{item.children.length}</span>,
      item.root.priority,
      item.root.status,
      <span key="owner" className="text-[12px] text-ink-600">{item.root.owner || "-"}</span>,
    ]);
    targets.push(item.root);
    if (isOpen) {
      for (const child of item.children) {
        rows.push([
          <span key="id" className="pl-5 font-mono text-[11px] text-ink-400">{child.id}</span>,
          <span key="title" className="block max-w-[520px] truncate pl-8 text-[12px] text-ink-600" title={child.title}>└ {child.title}</span>,
          <span key="count" className="text-[12px] text-ink-300">—</span>,
          child.priority,
          child.status,
          <span key="owner" className="text-[12px] text-ink-600">{child.owner || "-"}</span>,
        ]);
        targets.push(child);
      }
    }
  }

  const create = async () => {
    if (!form.title.trim()) { toast("请输入需求名称"); return; }
    try {
      const requirement = await requirementsApi.create(form);
      setData([requirement, ...data]);
      setOpen(false);
      setForm({ title: "", priority: "P1", owner: form.owner, description: "" });
      toast(`需求 ${requirement.id} 已创建`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "创建失败");
    }
  };

  const upload = async () => {
    if (files.length === 0) { toast("请选择至少一个文件"); return; }
    setBusy(true);
    addTask(`需求文档解析 · ${files.length} 个文件`, "解析");
    try {
      const requirement = await requirementsApi.upload(files, uploadTitle);
      setUploadOpen(false);
      setFiles([]);
      setUploadTitle("");
      await reload();
      if (autoSplit) {
        try {
          await requirementsApi.split(requirement.id);
          toast("文档已解析，AI 已生成子需求草案");
        } catch (err) {
          toast(err instanceof Error ? err.message : "自动拆分失败，可在详情页重试");
        }
      } else {
        toast("文档已上传并解析");
      }
      navigate(`/project/${projectId}/requirements/${requirement.id}`);
    } catch (err) {
      toast(err instanceof Error ? err.message : "上传失败");
    } finally {
      setBusy(false);
    }
  };

  const remove = async (id: string) => {
    const target = data.find((item) => item.id === id);
    if (!confirmDelete(target?.title ?? id)) return;
    try {
      await requirementsApi.remove(id);
      setData(data.filter((item) => item.id !== id));
      toast("需求已删除");
    } catch (err) {
      toast(err instanceof Error ? err.message : "删除失败");
    }
  };

  const subCount = data.filter((item) => item.parentId).length;

  return (
    <>
      <Card>
        <div className="mb-5 grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
          {[
            ["业务模块", moduleRoots.length, "按主需求分组"],
            ["独立需求", standaloneRoots.length, "文档或单条需求"],
            ["子需求", subCount, "已拆分的功能点"],
            ["需求总数", data.length, "当前项目范围"],
          ].map(([label, value, hint]) => (
            <div key={String(label)} className="rounded-xl border border-line bg-ink-50/60 px-4 py-3">
              <div className="flex items-start justify-between gap-2">
                <div className="text-[11px] font-medium text-ink-500">{label}</div>
                <Icon name="folder" size={14} className="text-ink-300" />
              </div>
              <div className="mt-1 tabular-nums text-[22px] font-semibold leading-none tracking-[-0.03em] text-ink-900">{value}</div>
              <div className="mt-1.5 text-[10px] text-ink-400">{hint}</div>
            </div>
          ))}
        </div>

        <Toolbar
          placeholder="搜索需求名称/编号"
          onSearch={setQuery}
          filters={
            <div className="flex items-center gap-2">
              <select
                value={module}
                aria-label="按业务模块筛选"
                onChange={(e) => {
                  const value = e.target.value;
                  setModule(value);
                  if (value) setExpanded(new Set([value]));
                }}
                className="h-9 max-w-60 rounded-lg border border-line bg-white pl-3 pr-8 text-[13px] text-ink-700 shadow-sm outline-none focus:border-brand-400 focus:ring-4 focus:ring-brand-500/10"
              >
                <option value="">全部需求</option>
                <optgroup label="业务模块">
                  {moduleRoots.map((root) => (
                    <option key={root.id} value={root.id}>{root.title}</option>
                  ))}
                </optgroup>
                {standaloneRoots.length > 0 && (
                  <optgroup label="独立需求 / 文档">
                    {standaloneRoots.map((root) => (
                      <option key={root.id} value={root.id}>
                        {root.title}{titleCounts[root.title] > 1 ? ` (${root.id})` : ""}
                      </option>
                    ))}
                  </optgroup>
                )}
              </select>
              <Select opts={STATUSES} value={status} onChange={(e) => setStatus(e.target.value)} />
            </div>
          }
        >
          <Btn v="ghost" size="sm" onClick={expandAll}>全部展开</Btn>
          <Btn v="ghost" size="sm" onClick={collapseAll}>全部收起</Btn>
          <Btn v="secondary" size="sm" onClick={() => setUploadOpen(true)}>上传文档</Btn>
          <Btn size="sm" onClick={() => setOpen(true)}>+ 新建需求</Btn>
        </Toolbar>

        <Table
          cols={["编号", "需求名称", "子需求", "优先级", "状态", "负责人"]}
          rows={rows}
          loading={loading}
          empty="没有匹配的需求"
          emptyAction={<Btn size="sm" onClick={() => setOpen(true)}>+ 新建需求</Btn>}
          actions={(i) => (
            <>
              <Btn v="secondary" size="sm" onClick={() => navigate(`/project/${projectId}/requirements/${targets[i].id}`)}>详情</Btn>
              <Btn v="danger" size="sm" onClick={() => remove(targets[i].id)}>删除</Btn>
            </>
          )}
        />
      </Card>

      <Modal open={open} title="新建需求" onClose={() => setOpen(false)} footer={<><Btn v="ghost" onClick={() => setOpen(false)}>取消</Btn><Btn onClick={create}>创建</Btn></>}>
        <div className="space-y-3">
          <Field label="需求名称"><Input className="w-full" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} autoFocus /></Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label="优先级"><Select opts={["P0", "P1", "P2"]} className="w-full" value={form.priority} onChange={(e) => setForm({ ...form, priority: e.target.value as Requirement["priority"] })} /></Field>
            <Field label="负责人"><Input className="w-full" value={form.owner} onChange={(e) => setForm({ ...form, owner: e.target.value })} /></Field>
          </div>
          <Field label="需求描述"><Textarea className="h-24 w-full" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
        </div>
      </Modal>

      <Modal open={uploadOpen} title="上传需求文档" onClose={() => setUploadOpen(false)} footer={<><Btn v="ghost" onClick={() => setUploadOpen(false)}>取消</Btn><Btn loading={busy} onClick={upload}>{busy ? "上传解析中…" : "上传并解析"}</Btn></>}>
        <div className="space-y-3">
          <Field label="主需求名称" hint="留空则使用第一个文件名"><Input className="w-full" value={uploadTitle} onChange={(e) => setUploadTitle(e.target.value)} /></Field>
          <div className="rounded-xl border border-dashed border-ink-300 bg-ink-50/50 p-6 text-center text-[12px] text-ink-500">
            <div className="mb-3">支持 PDF / DOCX / Markdown / TXT，可一次选择多个文件</div>
            <Btn v="secondary" size="sm" onClick={() => fileRef.current?.click()}>选择文件</Btn>
            <input ref={fileRef} type="file" multiple accept=".pdf,.docx,.md,.markdown,.txt" className="hidden" onChange={(e) => setFiles(Array.from(e.target.files ?? []))} />
            {files.length > 0 && <div className="mt-3 text-ink-700">{files.map((file) => file.name).join("、")}</div>}
          </div>
          <label className="flex items-center gap-2 text-[12px] text-ink-600"><input type="checkbox" className="h-3.5 w-3.5 accent-brand-500" checked={autoSplit} onChange={(e) => setAutoSplit(e.target.checked)} />上传后自动调用 AI 拆分主/子需求</label>
          <div className="text-[11px] leading-5 text-ink-500">原文件会保存到服务器，解析后的文本用于生成子需求草案；确认后才创建子需求。</div>
        </div>
      </Modal>
    </>
  );
}
