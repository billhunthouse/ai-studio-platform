import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { knowledgeApi } from "@/api";
import type { KnowledgeBase } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { confirmDelete } from "@/lib/confirm";
import { Btn, Card, Field, Input, Modal, Select, Stat, Tag, Textarea } from "@/components/ui";

export function KnowledgeList() {
  const { data, setData } = useAsync(() => knowledgeApi.list(), [], [] as KnowledgeBase[]);
  const { projectId, toast } = useApp();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ name: "", description: "", embedding: "bge-m3" });

  const create = async () => {
    if (!form.name.trim()) { toast("请输入知识库名称"); return; }
    const kb = await knowledgeApi.create(form);
    setData([kb, ...data]);
    setOpen(false);
    setForm({ name: "", description: "", embedding: "bge-m3" });
    toast("知识库已创建");
  };

  const remove = async (id: string) => {
    const target = data.find((x) => x.id === id);
    if (!confirmDelete(target?.name ?? id)) return;
    await knowledgeApi.remove(id);
    setData(data.filter((k) => k.id !== id));
    toast("知识库已删除");
  };

  return (
    <div className="space-y-4">
      <div className="grid grid-cols-4 gap-4">
        <Stat label="知识库" value={data.length} />
        <Stat label="文档总数" value={data.reduce((n, k) => n + k.docs, 0)} />
        <Stat label="切片总数" value={data.reduce((n, k) => n + k.chunks, 0)} />
        <Stat label="平均召回耗时" value="86ms" />
      </div>

      <div className="flex justify-end"><Btn onClick={() => setOpen(true)}>+ 新建知识库</Btn></div>

      <div className="rounded-lg border border-brand-200 bg-gradient-to-r from-blue-50 to-indigo-50 px-5 py-4 flex items-center gap-4">
        <div className="w-10 h-10 rounded-lg bg-brand-500 text-white grid place-items-center text-xs font-semibold shrink-0">Wiki</div>
        <div className="min-w-0">
          <div className="text-sm font-semibold text-ink-900">LLM-wiki 学习中心</div>
          <div className="text-xs text-ink-600 mt-0.5">13 节课程 + 6 篇笔记，从需求、页面、接口、代码到数据表建立系统地图。</div>
        </div>
        <div className="flex-1" />
        <Btn onClick={() => navigate(`/project/${projectId}/knowledge/learning`)}>进入学习中心</Btn>
      </div>

      <div className="grid grid-cols-2 gap-4">
        {data.map((k) => (
          <Card key={k.id} title={k.name} extra={<Tag t={k.status} />}>
            <div className="text-xs text-ink-500 h-8">{k.description}</div>
            <div className="grid grid-cols-3 gap-2 mt-2 text-xs">
              <div className="bg-ink-50 rounded p-2"><div className="text-[11px] text-ink-500">文档</div>{k.docs}</div>
              <div className="bg-ink-50 rounded p-2"><div className="text-[11px] text-ink-500">切片</div>{k.chunks.toLocaleString()}</div>
              <div className="bg-ink-50 rounded p-2"><div className="text-[11px] text-ink-500">嵌入模型</div><div className="truncate">{k.embedding}</div></div>
            </div>
            <div className="flex justify-between items-center mt-3 pt-3 border-t border-ink-100">
              <span className="text-[11px] text-ink-500">更新于 {k.updatedAt}</span>
              <div className="flex gap-1">
                <Btn v="ghost" onClick={() => navigate(`/project/${projectId}/knowledge/documents?kb=${k.id}`)}>文档管理</Btn>
                <Btn v="ghost" onClick={() => navigate(`/project/${projectId}/knowledge/recall?kb=${k.id}`)}>召回测试</Btn>
                <Btn v="danger" onClick={() => remove(k.id)}>删除</Btn>
              </div>
            </div>
          </Card>
        ))}
      </div>

      <Modal open={open} title="新建知识库" onClose={() => setOpen(false)} footer={<><Btn v="ghost" onClick={() => setOpen(false)}>取消</Btn><Btn onClick={create}>创建</Btn></>}>
        <div className="space-y-3">
          <Field label="名称"><Input className="w-full" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} autoFocus /></Field>
          <Field label="描述"><Textarea className="w-full h-20" value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} /></Field>
          <Field label="嵌入模型"><Select opts={["bge-m3", "text-embedding-3", "bge-large-zh"]} className="w-full" value={form.embedding} onChange={(e) => setForm({ ...form, embedding: e.target.value })} /></Field>
        </div>
      </Modal>
    </div>
  );
}
