/** 产品文档 AGENT 还原出的 PRD 展示组件。 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { PrdDoc } from "@/api/prd";
import { Btn, Card, Icon, Tag, Table } from "@/components/ui";
import { cx } from "@/lib/cx";
import { traceHref } from "@/lib/traceLinks";

const LAYER_CN: Record<string, string> = {
  page: "功能页面", api: "接口", code_artifact: "实现代码", table: "数据表",
};

function Section({ no, title, subtitle, children, defaultOpen = true }: {
  no: number; title: string; subtitle?: string; children: React.ReactNode; defaultOpen?: boolean;
}) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <Card className="overflow-hidden">
      <button onClick={() => setOpen(!open)}
        className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-ink-50/50">
        <span className="grid h-6 w-6 shrink-0 place-items-center rounded-md bg-brand-50 text-[11px] font-bold text-brand-600">
          {no}
        </span>
        <span className="text-[13px] font-semibold text-ink-900">{title}</span>
        {subtitle && <span className="text-[11px] text-ink-400">{subtitle}</span>}
        <Icon name={open ? "chevron-down" : "chevron-right"} size={14}
          className="ml-auto shrink-0 text-ink-400" />
      </button>
      {open && <div className="border-t border-ink-100 px-5 py-4">{children}</div>}
    </Card>
  );
}

function Evidence({ text }: { text: string }) {
  if (!text) return null;
  return <span className="ml-2 text-[10px] text-ink-400" title={text}>〔{text}〕</span>;
}

export function PrdDocument({ doc, domain, coverage, generatedAt, projectId }: {
  doc: PrdDoc; domain: string; coverage: number; generatedAt: string; projectId?: string;
}) {
  const s = doc.sections;
  const navigate = useNavigate();
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  /** 跳转到追溯实体详情页（type/id 走查询参数）。 */
  const goEntity = (type: string, id: string) => {
    if (!projectId) return;
    navigate(traceHref(type, id, projectId));
  };

  return (
    <div className="space-y-3">
      {/* 文档头 */}
      <div className="rounded-card border border-brand-100 bg-gradient-to-r from-brand-50/70 to-white px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-brand-500 px-2 py-0.5 text-[10px] font-bold text-white">产品需求文档 · PRD</span>
          <Tag t={domain} c="blue" />
          <Tag t={`${coverage}/4 层覆盖`} c={coverage === 4 ? "green" : "amber"} />
          <span className="ml-auto text-[10px] text-ink-400">
            产品文档 AGENT 还原 · {new Date(generatedAt).toLocaleString("zh-CN")}
          </span>
        </div>
        <p className="mt-2 text-[11px] leading-5 text-ink-500">
          本文档由 AGENT 从真实代码、追溯链与业务规则逆向还原，每条规则与接口都附代码证据，
          不是人工编撰的占位说明。
        </p>
      </div>

      {/* 1 概述 */}
      <Section no={1} title="需求概述" subtitle={`${s.overview.id} · ${s.overview.version}`}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Tag t={s.overview.priority} c={s.overview.priority === "P0" ? "red" : "amber"} />
            <Tag t={s.overview.status} c="green" />
            <span className="text-[11px] text-ink-500">负责人 {s.overview.owner}</span>
            <span className="text-[10px] text-ink-400">来源 {s.overview.sourceDoc}</span>
          </div>
          <div>
            <div className="text-[11px] font-semibold text-ink-700">背景</div>
            <p className="mt-1 text-[12px] leading-6 text-ink-600">{s.overview.background}</p>
          </div>
          <div>
            <div className="text-[11px] font-semibold text-ink-700">目标</div>
            <p className="mt-1 text-[12px] leading-6 text-ink-600">{s.overview.goal}</p>
          </div>
        </div>
      </Section>

      {/* 2 用户故事 */}
      <Section no={2} title="用户故事" subtitle={`${s.userStories.length} 条`}>
        <div className="space-y-2">
          {s.userStories.map((us, i) => (
            <div key={i} className="rounded-lg border border-line bg-ink-50/40 px-4 py-3">
              <div className="flex items-center gap-2">
                <Tag t={us.role} c="gray" dot={false} />
                <span className="text-[12px] font-medium text-ink-800">{us.want}</span>
              </div>
              <p className="mt-1.5 text-[11px] leading-5 text-ink-500">{us.as_json}</p>
            </div>
          ))}
        </div>
      </Section>

      {/* 3 功能规格 */}
      <Section no={3} title="功能规格" subtitle={`${s.features.length} 个功能点`}>
        <div className="space-y-2">
          {s.features.map((f) => (
            <div key={f.id} className="rounded-lg border border-line px-4 py-3">
              <div className="flex items-center gap-2">
                <span className="font-mono text-[10px] font-semibold text-brand-500">{f.id}</span>
                <span className="text-[12px] font-semibold text-ink-800">{f.name}</span>
              </div>
              <p className="mt-1 text-[11px] leading-5 text-ink-600">{f.behavior}</p>
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-500">
                <span>前置：{f.precondition}</span>
                <span>入口：{Array.isArray(f.entry) ? f.entry.join(" / ") : f.entry}</span>
              </div>
            </div>
          ))}
        </div>
      </Section>

      {/* 4 业务规则 */}
      <Section no={4} title="业务规则" subtitle={`${s.businessRules.length} 条 · 含状态机与校验`}>
        {s.flows.length > 0 && (
          <div className="mb-3 rounded-lg border border-brand-100 bg-brand-50/40 px-4 py-3">
            <div className="mb-1.5 text-[11px] font-semibold text-brand-700">状态流转 / 主流程</div>
            {s.flows.map((f, i) => (
              <div key={i} className="font-mono text-[11px] leading-6 text-ink-700">→ {f}</div>
            ))}
          </div>
        )}
        <div className="space-y-2">
          {s.businessRules.map((r, i) => (
            <div key={i} className="flex gap-2 rounded-lg border border-line px-4 py-2.5">
              <span className="mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded bg-ink-100 text-[9px] font-bold text-ink-600">
                {i + 1}
              </span>
              <div className="min-w-0">
                <span className="text-[12px] leading-5 text-ink-700">{r.text}</span>
                <Evidence text={r.evidence} />
              </div>
            </div>
          ))}
          {s.businessRules.length === 0 && (
            <div className="text-[11px] text-ink-400">源码中未见该需求的明确业务规则。</div>
          )}
        </div>
      </Section>

      {/* 5 接口清单 */}
      <Section no={5} title="接口清单" subtitle={`${s.apis.length} 个 · 来自代码扫描`}>
        {s.apis.length ? (
          <div className="space-y-2">
            {s.apis.map((a) => (
              <div key={a.id} className="rounded-lg border border-line px-4 py-3">
                <div className="flex flex-wrap items-center gap-2">
                  <Tag t={a.method || "—"} c={a.method === "GET" ? "blue" : a.method === "DELETE" ? "red" : "green"} dot={false} />
                  {projectId ? (
                    <button onClick={() => goEntity("api", a.id)}
                      title="跳转到接口详情（含调试入口）"
                      className="font-mono text-[11px] font-semibold text-ink-800 underline decoration-brand-300 decoration-dotted underline-offset-2 hover:text-brand-600">
                      {a.path || a.id}
                    </button>
                  ) : (
                    <code className="font-mono text-[11px] font-semibold text-ink-800">{a.path || a.id}</code>
                  )}
                  <span className="text-[11px] text-ink-500">{a.summary}</span>
                  <span className="ml-auto text-[10px] text-ink-400">{a.auth}</span>
                </div>
                {(a.params.length > 0 || a.bodyFields.length > 0) && (
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {a.params.map((p, i) => (
                      <span key={i} className="rounded bg-ink-50 px-1.5 py-0.5 font-mono text-[10px] text-ink-600">
                        {String(p.name ?? "")}:{String(p.type ?? "")}
                      </span>
                    ))}
                    {a.bodyFields.slice(0, 6).map((f, i) => (
                      <span key={`b${i}`} className="rounded bg-blue-50 px-1.5 py-0.5 font-mono text-[10px] text-blue-700">
                        {String(f.name ?? "")}
                      </span>
                    ))}
                  </div>
                )}
                {a.specRef && (
                  <div className="mt-1.5 font-mono text-[10px] text-ink-400">{a.specRef}</div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-ink-400">该需求无独立接口（交互规范类）。</div>
        )}
      </Section>

      {/* 6 数据模型 */}
      <Section no={6} title="数据模型" subtitle={`${s.dataModel.length} 张表 · ${doc.counts.columns} 个字段`} defaultOpen={false}>
        {s.dataModel.length ? (
          <div className="space-y-2">
            {s.dataModel.map((t) => (
              <div key={t.id} className="rounded-lg border border-line">
                <button onClick={() => setExpandedTable(expandedTable === t.id ? null : t.id)}
                  onDoubleClick={() => goEntity("table", t.id)}
                  title={projectId ? "展开字段 · 双击跳转表详情" : "展开字段"}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-ink-50/40">
                  <Icon name="database" size={14} className="text-ink-400" />
                  {projectId ? (
                    <code onClick={(e) => { e.stopPropagation(); goEntity("table", t.id); }}
                      className="font-mono text-[11px] font-semibold text-ink-800 underline decoration-brand-300 decoration-dotted underline-offset-2 hover:text-brand-600">
                      {t.schema}.{t.name}
                    </code>
                  ) : (
                    <code className="font-mono text-[11px] font-semibold text-ink-800">
                      {t.schema}.{t.name}
                    </code>
                  )}
                  <span className="text-[10px] text-ink-400">{t.columnCount} 字段</span>
                  {!!t.primaryKey && <Tag t="有主键" c="green" dot={false} />}
                  <Icon name={expandedTable === t.id ? "chevron-down" : "chevron-right"} size={12}
                    className="ml-auto text-ink-400" />
                </button>
                {expandedTable === t.id && (
                  <div className="border-t border-ink-100 px-4 py-3">
                    <Table
                      cols={["字段", "类型", "可空", "说明"]}
                      rows={t.columns.map((c) => [
                        <code className="font-mono text-[11px] text-ink-700">{c.name}</code>,
                        <code className="font-mono text-[10px] text-ink-500">{c.type}</code>,
                        c.nullable ? "是" : "否",
                        c.comment || "—",
                      ])}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-ink-400">该需求不落地数据表。</div>
        )}
      </Section>

      {/* 7 异常与边界 */}
      <Section no={7} title="异常与边界" subtitle={`${s.exceptions.length} 条负面场景`}
        defaultOpen={s.exceptions.length > 0}>
        {s.exceptions.length ? (
          <div className="space-y-2">
            {s.exceptions.map((e) => (
              <div key={e.id} className="rounded-lg border border-amber-200 bg-amber-50/50 px-4 py-2.5">
                <div className="flex items-center gap-2">
                  <span className="font-mono text-[10px] font-bold text-amber-700">{e.id}</span>
                  <Evidence text={e.evidence} />
                </div>
                <p className="mt-1 text-[12px] leading-5 text-amber-900">{e.scenario}</p>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-ink-400">源码中未见该需求的已知负面场景。</div>
        )}
      </Section>

      {/* 8 验收标准 */}
      <Section no={8} title="验收标准" subtitle={`${s.acceptance.length} 项 · 可勾选`}>
        <div className="space-y-1.5">
          {s.acceptance.map((a) => {
            const isChecked = checked[a.id] ?? a.checked;
            return (
              <button key={a.id} onClick={() => setChecked({ ...checked, [a.id]: !isChecked })}
                className={cx("flex w-full items-start gap-2.5 rounded-lg border px-3 py-2.5 text-left text-[12px] leading-5",
                  isChecked ? "border-green-200 bg-green-50/40 text-ink-500 line-through" : "border-line text-ink-700 hover:bg-ink-50/40")}>
                <span className={cx("mt-0.5 grid h-4 w-4 shrink-0 place-items-center rounded border text-[10px]",
                  isChecked ? "border-green-500 bg-green-500 text-white" : "border-ink-300")}>
                  {isChecked ? "✓" : ""}
                </span>
                <span className="font-mono text-[10px] text-ink-400">{a.id}</span>
                <span className="flex-1">{a.text}</span>
              </button>
            );
          })}
          {s.acceptance.length === 0 && <div className="text-[11px] text-ink-400">暂无明确验收标准。</div>}
        </div>
      </Section>

      {/* 9 覆盖与缺口：已覆盖层可点击跳转到对应追溯实体详情 */}
      <Section no={9} title="覆盖与缺口" subtitle={`${coverage}/4 层 · 点击可跳转`}>
        <div className="flex flex-wrap gap-2">
          {["page", "api", "code_artifact", "table"].map((layer) => {
            const hit = s.coverage.coveredLayers.includes(layer);
            const entities = (s.coverage.layerEntities?.[layer] ?? []).filter(Boolean);
            const linkable = hit && projectId && entities.length > 0;
            const body = (
              <>
                <div className="flex items-center gap-1 text-[10px] text-ink-500">
                  {LAYER_CN[layer]}
                  {hit && <span className="text-green-600">{entities.length || ""}</span>}
                </div>
                <div className={cx("mt-1 text-[12px] font-semibold", hit ? "text-green-700" : "text-amber-700")}>
                  {hit ? "已覆盖" : "缺失"}
                </div>
                {hit && entities.length > 1 && (
                  <div className="mt-0.5 truncate text-[10px] text-ink-400" title={entities.map((e) => e.name).join("、")}>
                    {entities.slice(0, 2).map((e) => e.name).join("、")} 等
                  </div>
                )}
              </>
            );
            return linkable ? (
              <button key={layer} onClick={() => goEntity(layer, entities[0].id)}
                title={`跳转：${entities[0].name}`}
                className={cx("flex-1 rounded-lg border px-3 py-2.5 text-left transition-colors",
                  "border-green-200 bg-green-50/40 hover:border-green-300 hover:bg-green-50")}>
                {body}
              </button>
            ) : (
              <div key={layer} className={cx("flex-1 rounded-lg border px-3 py-2.5",
                hit ? "border-green-200 bg-green-50/40" : "border-amber-200 bg-amber-50/40")}>
                {body}
              </div>
            );
          })}
        </div>
        {s.coverage.coveredLayers.includes("page") && !!projectId && (s.coverage.layerEntities?.page ?? []).length > 0 && (
          <div className="mt-2 flex flex-wrap gap-1.5">
            {s.coverage.layerEntities!.page.map((e) => (
              <button key={e.id} onClick={() => goEntity("page", e.id)}
                className="rounded-md bg-brand-50 px-2 py-0.5 text-[10px] font-medium text-brand-700 hover:bg-brand-100">
                {e.name}
              </button>
            ))}
          </div>
        )}
        <p className="mt-2 text-[11px] leading-5 text-ink-500">{s.coverage.note}</p>
      </Section>

      {/* 10 代码证据 */}
      <Section no={10} title="代码证据" subtitle={`${s.codeEvidence.length} 处入口`} defaultOpen={false}>
        {s.codeEvidence.length ? (
          <div className="space-y-1.5">
            {s.codeEvidence.map((c, i) => (
              <div key={i} className="rounded-lg border border-line px-3 py-2">
                <div className="flex flex-wrap items-center gap-2">
                  {projectId && c.id ? (
                    <button onClick={() => goEntity("code_artifact", String(c.id))}
                      title="跳转到代码实体详情"
                      className="font-mono text-[11px] font-semibold text-brand-600 underline decoration-brand-300 decoration-dotted underline-offset-2 hover:text-brand-700">
                      {c.entryPoint}
                    </button>
                  ) : (
                    <code className="font-mono text-[11px] font-semibold text-brand-600">{c.entryPoint}</code>
                  )}
                  {c.commit && <span className="font-mono text-[10px] text-ink-400">@{c.commit}</span>}
                  <span className="ml-auto text-[10px] text-ink-400">{c.service}</span>
                </div>
                <div className="mt-1 font-mono text-[10px] leading-4 text-ink-400 break-all">{c.filePath}</div>
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-ink-400">该需求无独立代码实现。</div>
        )}
      </Section>
    </div>
  );
}
