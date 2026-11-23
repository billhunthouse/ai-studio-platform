/** 产品文档视图：展示符合《需求文档规范》的 PRD（含质量门禁与追溯矩阵）。 */

import { useState } from "react";
import { useNavigate } from "react-router-dom";
import type { PrdDoc } from "@/api/prd";
import { Card, Icon, Tag, Table } from "@/components/ui";
import { cx } from "@/lib/cx";
import { traceHref } from "@/lib/traceLinks";

const LAYER_CN: Record<string, string> = {
  page: "功能页面", api: "接口", code_artifact: "实现代码", table: "数据表",
};

const SEVERITY_TONE: Record<string, "red" | "amber" | "gray"> = {
  高: "red", 中: "amber", 低: "gray",
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

function KV({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="rounded-lg border border-line bg-ink-50/40 px-3 py-2">
      <div className="text-[10px] font-medium text-ink-500">{label}</div>
      <div className="mt-0.5 text-[12px] leading-5 text-ink-700">{children}</div>
    </div>
  );
}

const TYPE_CN: Record<string, { label: string; tone: "green" | "red" | "amber" | "blue" | "gray" }> = {
  positive: { label: "正向", tone: "green" },
  negative: { label: "负向", tone: "red" },
  boundary: { label: "边界", tone: "amber" },
  checklist: { label: "清单", tone: "blue" },
};

export function PrdDocument({ doc, domain, coverage, generatedAt, projectId }: {
  doc: PrdDoc; domain: string; coverage: number; generatedAt: string; projectId?: string;
}) {
  const s = doc.sections;
  const navigate = useNavigate();
  const [expandedTable, setExpandedTable] = useState<string | null>(null);
  const [checked, setChecked] = useState<Record<string, boolean>>({});

  const goEntity = (type: string, id: string) => {
    if (!projectId) return;
    navigate(traceHref(type, id, projectId));
  };

  let seq = 0;
  const no = () => ++seq;
  const q = s.quality;
  const tb = s.traceability;

  return (
    <div className="space-y-3">
      {/* 文档头 */}
      <div className="rounded-card border border-brand-100 bg-gradient-to-r from-brand-50/70 to-white px-5 py-4">
        <div className="flex flex-wrap items-center gap-2">
          <span className="rounded-md bg-brand-500 px-2 py-0.5 text-[10px] font-bold text-white">产品需求文档 · PRD</span>
          <Tag t={domain} c="blue" />
          <Tag t={`${coverage}/4 层覆盖`} c={coverage === 4 ? "green" : "amber"} />
          {q && <Tag t={`规范符合度 ${q.score} 分 · ${q.grade} 级`} c={q.score >= 90 ? "green" : q.score >= 75 ? "amber" : "red"} />}
          {s.docInfo && <Tag t={s.docInfo.version} c="gray" dot={false} />}
          <span className="ml-auto text-[10px] text-ink-400">
            规范化 · {new Date(generatedAt).toLocaleString("zh-CN")}
          </span>
        </div>
        <p className="mt-2 text-[11px] leading-5 text-ink-500">
          按《需求文档规范》组织：范围、角色、术语、NFR、数据字典、异常七类、依赖假设与质量门禁齐备；
          验收标准为 Given-When-Then 并标注四级断言锚点；接口/字段/代码入口均来自真实扫描，不臆造。
        </p>
      </div>

      {/* 1 文档信息 */}
      {s.docInfo && (
        <Section no={no()} title="文档信息" subtitle={`${s.docInfo.docId} · ${s.docInfo.version}`}>
          <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
            <KV label="版本 / 上一版">{s.docInfo.version} ← {s.docInfo.previousVersion || "—"}</KV>
            <KV label="作者">{s.docInfo.author}</KV>
            <KV label="评审人">{s.docInfo.reviewers.join("、") || "—"}</KV>
            <KV label="状态">{s.docInfo.status}</KV>
          </div>
          <div className="mt-3">
            <div className="mb-1.5 text-[11px] font-semibold text-ink-700">变更记录</div>
            <Table
              cols={["版本", "日期", "作者", "变更摘要"]}
              rows={s.docInfo.changeLog.map((c) => [
                <span className="font-mono text-[11px] font-medium text-ink-700">{c.version}</span>,
                c.at, c.author,
                <span className="text-[11px] leading-5 text-ink-600">{c.summary}</span>,
              ])}
            />
          </div>
        </Section>
      )}

      {/* 2 概述 */}
      <Section no={no()} title="需求概述" subtitle={`${s.overview.id} · ${s.overview.priority}`}>
        <div className="space-y-3">
          <div className="flex flex-wrap items-center gap-2">
            <Tag t={s.overview.priority} c={s.overview.priority === "P0" ? "red" : "amber"} />
            <Tag t={s.overview.status} c="green" />
            <span className="text-[11px] text-ink-500">负责人 {s.overview.owner}</span>
            <span className="text-[10px] text-ink-400">来源 {s.overview.sourceDoc}</span>
          </div>
          {s.overview.problem && (
            <div>
              <div className="text-[11px] font-semibold text-ink-700">业务痛点</div>
              <p className="mt-1 text-[12px] leading-6 text-ink-600">{s.overview.problem}</p>
            </div>
          )}
          <div>
            <div className="text-[11px] font-semibold text-ink-700">背景</div>
            <p className="mt-1 text-[12px] leading-6 text-ink-600">{s.overview.background}</p>
          </div>
          <div>
            <div className="text-[11px] font-semibold text-ink-700">目标</div>
            <p className="mt-1 text-[12px] leading-6 text-ink-600">{s.overview.goal}</p>
          </div>
          {s.overview.businessValue && (
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/50 px-3 py-2.5">
              <div className="text-[11px] font-semibold text-emerald-800">业务价值（量化）</div>
              <p className="mt-1 text-[12px] leading-5 text-emerald-900">{s.overview.businessValue}</p>
            </div>
          )}
          {s.overview.consequence && (
            <div className="rounded-lg border border-amber-200 bg-amber-50/50 px-3 py-2.5">
              <div className="text-[11px] font-semibold text-amber-800">不做 / 失效的后果</div>
              <p className="mt-1 text-[12px] leading-5 text-amber-900">{s.overview.consequence}</p>
            </div>
          )}
        </div>
      </Section>

      {/* 3 范围 */}
      {s.scope && (
        <Section no={no()} title="范围" subtitle="In Scope / Out of Scope">
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 px-3 py-2.5">
              <div className="mb-1.5 text-[11px] font-semibold text-emerald-800">本次包含</div>
              <ul className="space-y-1">
                {s.scope.inScope.map((x, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] leading-5 text-emerald-900">
                    <span className="text-emerald-600">✓</span>{x}
                  </li>
                ))}
              </ul>
            </div>
            <div className="rounded-lg border border-rose-200 bg-rose-50/40 px-3 py-2.5">
              <div className="mb-1.5 text-[11px] font-semibold text-rose-800">本次不做</div>
              <ul className="space-y-1">
                {s.scope.outOfScope.map((x, i) => (
                  <li key={i} className="flex gap-1.5 text-[11px] leading-5 text-rose-900">
                    <span className="text-rose-500">✕</span>{x}
                  </li>
                ))}
              </ul>
            </div>
          </div>
          {s.scope.assumptions.length > 0 && (
            <div className="mt-3">
              <div className="mb-1.5 text-[11px] font-semibold text-ink-700">前提假设</div>
              <ul className="space-y-1">
                {s.scope.assumptions.map((x, i) => (
                  <li key={i} className="text-[11px] leading-5 text-ink-600">· {x}</li>
                ))}
              </ul>
            </div>
          )}
        </Section>
      )}

      {/* 4 角色与权限 */}
      {s.roles && s.roles.length > 0 && (
        <Section no={no()} title="角色与权限" subtitle={`${s.roles.length} 类角色`}>
          <Table
            cols={["角色", "入口", "可执行操作", "数据范围"]}
            rows={s.roles.map((r) => [
              <Tag t={r.role} c="gray" dot={false} />,
              <span className="font-mono text-[10px] text-ink-600">{r.entry}</span>,
              <span className="text-[11px] leading-5 text-ink-700">{r.operations.join("、")}</span>,
              <span className="font-mono text-[10px] text-ink-500">{r.dataScope}</span>,
            ])}
          />
        </Section>
      )}

      {/* 5 术语表 */}
      {s.glossary && s.glossary.length > 0 && (
        <Section no={no()} title="术语表" subtitle={`${s.glossary.length} 个术语`} defaultOpen={false}>
          <Table
            cols={["术语", "定义", "别名", "禁止使用"]}
            rows={s.glossary.map((g) => [
              <span className="font-mono text-[11px] font-medium text-ink-800">{g.term}</span>,
              <span className="text-[11px] leading-5 text-ink-600">{g.definition}</span>,
              <span className="text-[10px] text-ink-500">{g.aliases.join("、") || "—"}</span>,
              <span className="text-[10px] text-rose-600">{g.forbidden.join("、") || "—"}</span>,
            ])}
          />
        </Section>
      )}

      {/* 6 用户故事 */}
      <Section no={no()} title="用户故事" subtitle={`${s.userStories.length} 条`} defaultOpen={false}>
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

      {/* 7 功能规格 */}
      <Section no={no()} title="功能规格" subtitle={`${s.features.length} 条 FR`}>
        <div className="space-y-2">
          {s.features.map((f) => (
            <div key={f.id} className="rounded-lg border border-line px-4 py-3">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-[10px] font-semibold text-brand-500">{f.id}</span>
                <span className="text-[12px] font-semibold text-ink-800">{f.name}</span>
                {f.role && <Tag t={f.role} c="gray" dot={false} />}
                {f.kind === "constraint" && <Tag t="约束类" c="blue" dot={false} />}
              </div>
              <p className="mt-1 text-[11px] leading-5 text-ink-600">{f.behavior}</p>
              {f.preconditionDetail ? (
                <div className="mt-2 grid gap-1.5 sm:grid-cols-3">
                  <KV label="数据前置">{f.preconditionDetail.data}</KV>
                  <KV label="权限前置">{f.preconditionDetail.permission}</KV>
                  <KV label="环境前置">{f.preconditionDetail.env}</KV>
                </div>
              ) : (
                <div className="mt-2 text-[10px] text-ink-500">前置：{f.precondition}</div>
              )}
              {f.trigger && <div className="mt-1.5 text-[10px] text-ink-500">触发：{f.trigger}</div>}
              {f.rules && f.rules.length > 0 && (
                <ul className="mt-1.5 space-y-0.5">
                  {f.rules.map((r, i) => (
                    <li key={i} className="text-[11px] leading-5 text-ink-600">R{i + 1}. {r}</li>
                  ))}
                </ul>
              )}
              {f.postcondition && (
                <div className="mt-1.5 rounded bg-emerald-50/60 px-2 py-1 text-[10px] leading-5 text-emerald-800">
                  后置：{f.postcondition}
                </div>
              )}
              <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-[10px] text-ink-500">
                <span>入口：{Array.isArray(f.entry) ? f.entry.join(" / ") : f.entry}</span>
                {f.relatedApis && f.relatedApis.length > 0 && (
                  <span className="font-mono">接口：{f.relatedApis.join("、")}</span>
                )}
                {f.relatedData && f.relatedData.length > 0 && (
                  <span className="font-mono">数据：{f.relatedData.join("、")}</span>
                )}
              </div>
              {f.exceptions && f.exceptions.length > 0 && (
                <div className="mt-1.5 border-t border-dashed border-ink-100 pt-1.5">
                  <div className="text-[10px] font-medium text-ink-500">异常分支</div>
                  <ul className="mt-0.5 space-y-0.5">
                    {f.exceptions.map((e, i) => (
                      <li key={i} className="text-[10px] leading-5 text-amber-800">· {e}</li>
                    ))}
                  </ul>
                </div>
              )}
            </div>
          ))}
        </div>
      </Section>

      {/* 8 业务流程与状态机 */}
      {(s.stateMachine?.length || s.flows.length > 0) && (
        <Section no={no()} title="业务流程与状态机"
          subtitle={s.stateMachine?.length ? `${s.stateMachine.length} 条迁移` : `${s.flows.length} 条流程`}>
          {s.flows.length > 0 && (
            <div className="mb-3 rounded-lg border border-brand-100 bg-brand-50/40 px-4 py-3">
              <div className="mb-1.5 text-[11px] font-semibold text-brand-700">主流程</div>
              {s.flows.map((f, i) => (
                <div key={i} className="font-mono text-[11px] leading-6 text-ink-700">→ {f}</div>
              ))}
            </div>
          )}
          {s.stateMachine && s.stateMachine.length > 0 && (
            <Table
              cols={["当前状态", "事件", "目标状态", "触发者", "副作用", "非法迁移处理"]}
              rows={s.stateMachine.map((m) => [
                <span className="font-mono text-[10px] text-ink-700">{m.from}</span>,
                <span className="text-[11px] text-ink-700">{m.event}</span>,
                <span className="font-mono text-[10px] font-medium text-brand-600">{m.to}</span>,
                <span className="text-[10px] text-ink-500">{m.actor}</span>,
                <span className="text-[10px] leading-4 text-ink-600">{m.effect}</span>,
                <span className="text-[10px] leading-4 text-rose-700">{m.illegal}</span>,
              ])}
            />
          )}
        </Section>
      )}

      {/* 9 业务规则 */}
      <Section no={no()} title="业务规则" subtitle={`${s.businessRules.length} 条`} defaultOpen={false}>
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

      {/* 10 验收标准（GWT） */}
      <Section no={no()} title="验收标准" subtitle={`${s.acceptance.length} 项 · Given-When-Then`}>
        <div className="space-y-2">
          {s.acceptance.map((a) => {
            const isChecked = checked[a.id] ?? a.checked;
            const t = a.type ? TYPE_CN[a.type] : undefined;
            return (
              <div key={a.id} className={cx("rounded-lg border px-3 py-2.5",
                isChecked ? "border-emerald-200 bg-emerald-50/40" : "border-line")}>
                <div className="flex flex-wrap items-center gap-2">
                  <button onClick={() => setChecked({ ...checked, [a.id]: !isChecked })}
                    className={cx("grid h-4 w-4 shrink-0 place-items-center rounded border text-[10px]",
                      isChecked ? "border-emerald-500 bg-emerald-500 text-white" : "border-ink-300")}>
                    {isChecked ? "✓" : ""}
                  </button>
                  <span className="font-mono text-[10px] text-ink-400">{a.id}</span>
                  {a.frId && <span className="font-mono text-[9px] text-brand-500">{a.frId}</span>}
                  {t && <Tag t={t.label} c={t.tone} dot={false} />}
                  {(a.anchors ?? []).map((x) => (
                    <span key={x} className="rounded bg-ink-100 px-1 py-0.5 font-mono text-[9px] text-ink-600">{x}</span>
                  ))}
                  {(a.anchors?.length ?? 0) < 2 && (
                    <Tag t="锚点不足" c="red" dot={false} />
                  )}
                </div>
                {a.given ? (
                  <div className="mt-2 space-y-0.5 pl-6">
                    <div className="text-[11px] leading-5 text-ink-600">
                      <b className="text-ink-500">Given</b> {a.given}
                    </div>
                    <div className="text-[11px] leading-5 text-ink-600">
                      <b className="text-ink-500">When</b> {a.when}
                    </div>
                    <div className="text-[11px] leading-5 text-ink-700">
                      <b className="text-ink-500">Then</b>
                      <ul className="mt-0.5 space-y-0.5">
                        {(a.then ?? []).map((x, i) => <li key={i}>· {x}</li>)}
                      </ul>
                    </div>
                  </div>
                ) : (
                  <div className="mt-1.5 pl-6 text-[12px] leading-5 text-ink-700">{a.text}</div>
                )}
              </div>
            );
          })}
          {s.acceptance.length === 0 && <div className="text-[11px] text-ink-400">暂无明确验收标准。</div>}
        </div>
      </Section>

      {/* 11 非功能需求 */}
      {s.nfr && s.nfr.length > 0 && (
        <Section no={no()} title="非功能需求" subtitle={`${s.nfr.length} 条 · 含量化目标与测量方法`} defaultOpen={false}>
          <Table
            cols={["类别", "指标", "目标", "测量方法"]}
            rows={s.nfr.map((n) => [
              <Tag t={n.category} c="blue" dot={false} />,
              <span className="text-[11px] font-medium text-ink-800">{n.metric}</span>,
              <span className="text-[11px] leading-5 text-ink-700">{n.target}</span>,
              <span className="font-mono text-[10px] leading-4 text-ink-500">{n.measure}</span>,
            ])}
          />
        </Section>
      )}

      {/* 12 数据字典 */}
      {s.dataDictionary && s.dataDictionary.tables.length > 0 && (
        <Section no={no()} title="数据字典" subtitle={`${s.dataDictionary.tables.length} 张表 · 字段级约束`} defaultOpen={false}>
          <div className="space-y-2">
            {s.dataDictionary.tables.map((t) => (
              <div key={t.table} className="rounded-lg border border-line">
                <button onClick={() => setExpandedTable(expandedTable === t.table ? null : t.table)}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-ink-50/40">
                  <Icon name="database" size={14} className="text-ink-400" />
                  <code className="font-mono text-[11px] font-semibold text-ink-800">{t.table}</code>
                  <span className="text-[10px] text-ink-400">{t.fieldCount} 字段</span>
                  <Icon name={expandedTable === t.table ? "chevron-down" : "chevron-right"} size={12}
                    className="ml-auto text-ink-400" />
                </button>
                {expandedTable === t.table && (
                  <div className="border-t border-ink-100 px-4 py-3">
                    <Table
                      cols={["字段", "类型", "必填", "唯一", "脱敏", "说明"]}
                      rows={t.fields.map((f) => [
                        <code className="font-mono text-[11px] text-ink-700">{f.name}</code>,
                        <code className="font-mono text-[10px] text-ink-500">{f.type}</code>,
                        f.required ? "是" : "否",
                        f.unique ? "是" : "—",
                        f.masked ? "是" : "—",
                        <span className="text-[10px] text-ink-500">{f.note || (f.audit ? "审计字段" : "—")}</span>,
                      ])}
                    />
                  </div>
                )}
              </div>
            ))}
          </div>
          {s.dataDictionary.invariants.length > 0 && (
            <div className="mt-3 rounded-lg border border-brand-100 bg-brand-50/40 px-3 py-2.5">
              <div className="mb-1 text-[11px] font-semibold text-brand-700">不变式（并发场景必须成立）</div>
              {s.dataDictionary.invariants.map((x, i) => (
                <div key={i} className="font-mono text-[10px] leading-5 text-ink-700">{x}</div>
              ))}
            </div>
          )}
        </Section>
      )}

      {/* 13 异常与边界 */}
      <Section no={no()} title="异常与边界" subtitle={`${s.exceptions.filter((e) => e.covered).length} 条 / 7 类`} defaultOpen={false}>
        {s.exceptions.length ? (
          <Table
            cols={["编号", "类别", "场景", "系统反馈", "数据回滚", "可重试"]}
            rows={s.exceptions.map((e) => [
              <span className="font-mono text-[10px] text-ink-500">{e.id}</span>,
              <Tag t={e.category ?? "—"} c={e.covered === false ? "gray" : "amber"} dot={false} />,
              <span className="text-[11px] leading-5 text-ink-800">{e.scenario}</span>,
              <span className="text-[10px] leading-4 text-ink-600">{e.feedback || "—"}</span>,
              <span className="text-[10px] leading-4 text-ink-600">{e.rollback || "—"}</span>,
              <span className="text-[10px] text-ink-600">{e.retryable || "—"}</span>,
            ])}
          />
        ) : (
          <div className="text-[11px] text-ink-400">源码中未见该需求的已知负面场景。</div>
        )}
      </Section>

      {/* 14 依赖与假设 */}
      {s.dependencies && s.dependencies.length > 0 && (
        <Section no={no()} title="依赖与假设" subtitle={`${s.dependencies.length} 项`} defaultOpen={false}>
          <Table
            cols={["依赖", "类型", "假设", "失效后降级"]}
            rows={s.dependencies.map((d) => [
              <span className="text-[11px] font-medium text-ink-800">{d.name}</span>,
              <Tag t={d.type} c="gray" dot={false} />,
              <span className="text-[11px] leading-5 text-ink-600">{d.assumption}</span>,
              <span className="text-[11px] leading-5 text-amber-800">{d.fallback}</span>,
            ])}
          />
        </Section>
      )}

      {/* 15 遗留与待定 */}
      {s.openIssues && s.openIssues.length > 0 && (
        <Section no={no()} title="遗留与待定" subtitle={`${s.openIssues.length} 项`}>
          <div className="space-y-2">
            {s.openIssues.map((o, i) => (
              <div key={i} className="rounded-lg border border-amber-200 bg-amber-50/40 px-3 py-2.5">
                <div className="flex flex-wrap items-center gap-2">
                  <Tag t={o.severity} c={SEVERITY_TONE[o.severity] ?? "gray"} dot={false} />
                  <span className="text-[10px] text-ink-500">{o.owner} · {o.deadline}</span>
                </div>
                <p className="mt-1 text-[11px] leading-5 text-amber-900">{o.issue}</p>
              </div>
            ))}
          </div>
        </Section>
      )}

      {/* 16 接口清单 */}
      <Section no={no()} title="接口清单" subtitle={`${s.apis.length} 个 · 来自代码扫描`} defaultOpen={false}>
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
                {a.specRef && <div className="mt-1.5 font-mono text-[10px] text-ink-400">{a.specRef}</div>}
              </div>
            ))}
          </div>
        ) : (
          <div className="text-[11px] text-ink-400">该需求无独立接口（交互规范类）。</div>
        )}
      </Section>

      {/* 17 数据模型 */}
      <Section no={no()} title="数据模型" subtitle={`${s.dataModel.length} 张表 · ${doc.counts.columns} 个字段`} defaultOpen={false}>
        {s.dataModel.length ? (
          <div className="space-y-2">
            {s.dataModel.map((t) => (
              <div key={t.id} className="rounded-lg border border-line">
                <button onClick={() => setExpandedTable(expandedTable === t.id ? null : t.id)}
                  onDoubleClick={() => goEntity("table", t.id)}
                  title={projectId ? "展开字段 · 双击跳转表详情" : "展开字段"}
                  className="flex w-full items-center gap-2 px-4 py-2.5 text-left hover:bg-ink-50/40">
                  <Icon name="database" size={14} className="text-ink-400" />
                  <code className="font-mono text-[11px] font-semibold text-ink-800">{t.schema}.{t.name}</code>
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

      {/* 18 覆盖与缺口 */}
      <Section no={no()} title="覆盖与缺口" subtitle={`${coverage}/4 层 · 点击可跳转`} defaultOpen={false}>
        <div className="flex flex-wrap gap-2">
          {["page", "api", "code_artifact", "table"].map((layer) => {
            const hit = s.coverage.coveredLayers.includes(layer);
            const entities = (s.coverage.layerEntities?.[layer] ?? []).filter(Boolean);
            const linkable = hit && projectId && entities.length > 0;
            const body = (
              <>
                <div className="flex items-center gap-1 text-[10px] text-ink-500">
                  {LAYER_CN[layer]}
                  {hit && <span className="text-emerald-600">{entities.length || ""}</span>}
                </div>
                <div className={cx("mt-1 text-[12px] font-semibold", hit ? "text-emerald-700" : "text-amber-700")}>
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
                className="flex-1 rounded-lg border border-emerald-200 bg-emerald-50/40 px-3 py-2.5 text-left transition-colors hover:border-emerald-300 hover:bg-emerald-50">
                {body}
              </button>
            ) : (
              <div key={layer} className={cx("flex-1 rounded-lg border px-3 py-2.5",
                hit ? "border-emerald-200 bg-emerald-50/40" : "border-amber-200 bg-amber-50/40")}>
                {body}
              </div>
            );
          })}
        </div>
        <p className="mt-2 text-[11px] leading-5 text-ink-500">{s.coverage.note}</p>
      </Section>

      {/* 19 追溯矩阵 */}
      {tb && (
        <Section no={no()} title="追溯矩阵" subtitle={`链路 ${tb.layerCoverage}% · 用例 ${tb.caseVerified}/${tb.caseCount} 已验证`} defaultOpen={false}>
          <Table
            cols={["层", "数量", "实体 / 说明", "状态"]}
            rows={tb.rows.map((r) => [
              <span className="text-[11px] font-medium text-ink-800">{r.layer}</span>,
              <span className="tabular-nums text-[11px] text-ink-600">{r.count}</span>,
              <span className="block max-w-[420px] truncate font-mono text-[10px] text-ink-500"
                title={r.items.join("、")}>
                {r.items.join("、") || "—"}
              </span>,
              <Tag t={r.status} c={r.status === "缺失" ? "red" : r.status === "已验证" || r.status === "已关联" ? "green" : "amber"} dot={false} />,
            ])}
          />
        </Section>
      )}

      {/* 20 质量评分 */}
      {q && (
        <Section no={no()} title="质量门禁" subtitle={`${q.score} 分 · ${q.gatesPassed}/${q.gatesTotal} 条通过`}>
          <div className="grid gap-3 lg:grid-cols-2">
            <div>
              <div className="mb-1.5 text-[11px] font-semibold text-ink-700">12 项质量属性</div>
              <div className="space-y-1">
                {q.attributes.map((a) => (
                  <div key={a.name} className="flex items-start gap-2 text-[11px]">
                    <span className={cx("mt-0.5 grid h-3.5 w-3.5 shrink-0 place-items-center rounded text-[9px] text-white",
                      a.pass ? "bg-emerald-500" : "bg-rose-500")}>{a.pass ? "✓" : "✕"}</span>
                    <span className="w-20 shrink-0 font-medium text-ink-700">{a.name}</span>
                    <span className="text-ink-500">{a.note}</span>
                  </div>
                ))}
              </div>
            </div>
            <div>
              <div className="mb-1.5 text-[11px] font-semibold text-ink-700">{q.gates.length} 条自动门禁</div>
              <div className="space-y-1">
                {q.gates.map((g) => (
                  <div key={g.rule} className="flex items-start gap-2 text-[11px]">
                    <span className={cx("mt-0.5 grid h-3.5 w-3.5 shrink-0 place-items-center rounded text-[9px] text-white",
                      g.pass ? "bg-emerald-500" : "bg-rose-500")}>{g.pass ? "✓" : "✕"}</span>
                    <span className="w-28 shrink-0 font-medium text-ink-700">{g.rule}</span>
                    <span className="text-ink-500">{g.detail}</span>
                  </div>
                ))}
              </div>
            </div>
          </div>
        </Section>
      )}

      {/* 21 代码证据 */}
      <Section no={no()} title="代码证据" subtitle={`${s.codeEvidence.length} 处入口`} defaultOpen={false}>
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
                <div className="mt-1 break-all font-mono text-[10px] leading-4 text-ink-400">{c.filePath}</div>
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
