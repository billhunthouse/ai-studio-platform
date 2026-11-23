import { useMemo } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { traceApi } from "@/api";
import type { ApiParam, TableColumn, TraceDetail, TraceLink } from "@/api/trace";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { Btn, Card, Empty, Icon, Tag, Table } from "@/components/ui";
import { traceHref } from "@/lib/traceLinks";

const TYPE_LABEL: Record<string, string> = {
  requirement: "需求", page: "功能页面", api: "接口",
  code_artifact: "实现代码", table: "数据表",
};

const TYPE_HINT: Record<string, string> = {
  requirement: "需求本身与其拆解出的功能页面",
  page: "一个功能页面会调用哪些接口、最终落到哪些表",
  api: "接口契约、实现代码与上下游实体",
  code_artifact: "一个 Controller 入口方法，以及它所属的接口",
  table: "表结构、字段定义，以及谁在读写它",
};

function authLabel(v: string) {
  if (v === "public") return "公开访问";
  if (v.startsWith("login:")) return `需登录（${v.slice(6)}）`;
  return v;
}

function Row({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div className="flex gap-4 border-b border-ink-100 py-2.5 last:border-0">
      <div className="w-24 shrink-0 text-[12px] text-ink-500">{label}</div>
      <div className="min-w-0 flex-1 text-[13px] text-ink-800">{children}</div>
    </div>
  );
}

function LinkList({ items, pid, empty }: { items: TraceLink[]; pid: string; empty: string }) {
  if (!items.length) return <div className="px-1 py-4 text-[12px] text-ink-400">{empty}</div>;
  return (
    <div className="divide-y divide-ink-100">
      {items.map((x) => (
        <Link key={`${x.type}-${x.id}`} to={traceHref(x.type, x.id, pid)}
          className="group flex items-center gap-3 py-2.5 first:pt-0 last:pb-0">
          <span className="w-16 shrink-0 text-[10px] text-ink-400">{TYPE_LABEL[x.type] ?? x.type}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-[13px] font-medium text-ink-800 group-hover:text-brand-600">
              {x.name}
            </span>
            {x.subtitle && (
              <span className="block truncate font-mono text-[10px] text-ink-400">{x.subtitle}</span>
            )}
          </span>
          {x.relLabel && <span className="shrink-0 text-[10px] text-ink-400">{x.relLabel}</span>}
          <Icon name="chevron-right" size={14} className="shrink-0 text-ink-300 group-hover:text-brand-500" />
        </Link>
      ))}
    </div>
  );
}

export function TraceEntity() {
  const [params] = useSearchParams();
  const type = params.get("type") ?? "";
  const id = params.get("id") ?? "";
  const { projectId } = useApp();
  const navigate = useNavigate();

  const { data, loading, error } = useAsync<TraceDetail | null>(
    () => (type && id ? traceApi.detail(type, id) : Promise.resolve(null)),
    [type, id, projectId], null);

  const title = useMemo(() => {
    const e = data?.entity ?? {};
    return String(e.title ?? e.name ?? e.entry_point ?? e.summary ?? e.path ?? id);
  }, [data, id]);

  if (!type || !id) {
    return <Empty text="缺少实体参数，请从追溯中心的链路节点进入。"
      action={<Btn onClick={() => navigate(`/project/${projectId}/trace`)}>返回追溯中心</Btn>} />;
  }
  if (error) {
    return <Empty text={`加载失败：${error}`}
      action={<Btn onClick={() => navigate(`/project/${projectId}/trace`)}>返回追溯中心</Btn>} />;
  }
  if (loading || !data) {
    return <div className="h-96 animate-pulse rounded-card border border-line bg-white" />;
  }

  const e = data.entity as Record<string, unknown>;
  const extra = data.extra;
  const apiPath = String(e.path ?? "");
  const apiMethod = String(e.method ?? "");
  const isApi = type === "api";
  const contract = extra.contract;
  // body 参数单独用字段表展示，这里只留 query/path/header，避免重复
  const params2 = (contract?.requestSchema?.params ?? []).filter((p) => p.in !== "body");
  const bodyFields = contract?.requestSchema?.bodyFields ?? [];
  const hasContract = params2.length > 0 || bodyFields.length > 0 || !!contract?.responseSchema?.wrapper;
  const columns = (extra.columns ?? []) as TableColumn[];

  return (
    <div className="space-y-4">
      <nav className="flex items-center gap-1.5 text-[12px] text-ink-400">
        <Link to={`/project/${projectId}/trace`} className="hover:text-brand-600">追溯中心</Link>
        <Icon name="chevron-right" size={12} />
        <span className="text-ink-600">{TYPE_LABEL[type] ?? type}详情</span>
      </nav>

      <Card>
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="rounded-md bg-brand-50 px-2 py-0.5 text-[11px] font-semibold text-brand-600">
                {TYPE_LABEL[type] ?? type}
              </span>
              {isApi && <Tag t={apiMethod} c="blue" dot={false} />}
              <h1 className="text-[18px] font-semibold tracking-[-0.01em] text-ink-900">
                {isApi ? String(e.summary || `${apiMethod} ${apiPath}`) : title}
              </h1>
              {String(e.status ?? "") === "active" && <Tag t="有效" c="green" />}
            </div>
            <p className="mt-1 font-mono text-[11px] text-ink-400">{id}</p>
            <p className="mt-2 text-[12px] text-ink-500">{TYPE_HINT[type]}</p>
          </div>
          <div className="flex shrink-0 gap-2">
            {type === "page" && extra.requirementDetail && (
              <Btn onClick={() => navigate(`/project/${projectId}/requirements/${extra.requirementDetail!.id}`)}>
                进入需求详情 <Icon name="arrow-right" size={14} />
              </Btn>
            )}
            {isApi && (
              <Btn onClick={() => navigate(`/project/${projectId}/api/debug?method=${apiMethod}&path=${encodeURIComponent(apiPath)}`)}>
                <Icon name="play" size={14} /> 发起调试
              </Btn>
            )}
            <Btn v="ghost" onClick={() => navigate(`/project/${projectId}/trace?tab=chain`)}>
              返回链路
            </Btn>
          </div>
        </div>
      </Card>

      <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
        <div className="space-y-4">
          {/* ---------- 接口 ---------- */}
          {isApi && (
            <>
              <Card title="接口契约"
                extra={hasContract
                  ? <Tag t={String(e.source ?? "") === "CODE_SCAN" ? "扫描自代码" : "人工登记"} c="gray" />
                  : <Tag t="待补充" c="amber" />}>
                <Row label="请求方法">
                  <span className="font-mono font-semibold">{apiMethod}</span>
                  <span className="ml-2 font-mono text-ink-600">{apiPath}</span>
                </Row>
                <Row label="摘要">{String(e.summary || "—")}</Row>
                <Row label="鉴权">{authLabel(String(contract?.authRequirement ?? "public"))}</Row>
                <Row label="所属服务">{String(contract?.service ?? "—")}</Row>
                <Row label="契约来源">
                  <span className="font-mono text-[11px] text-ink-500">{String(contract?.specRef ?? "—")}</span>
                </Row>
                {contract?.internalCalls && <Row label="内部说明">{contract.internalCalls}</Row>}
              </Card>

              {!hasContract && (
                <div className="rounded-card border border-amber-200 bg-amber-50/60 px-5 py-4 text-[12px] leading-6 text-amber-800">
                  该接口在代码里能定位到实现，但还没有登记请求/响应契约。
                  建议在需求的「详细设计」里补一份 OpenAPI 片段，重新扫描后会自动合并。
                </div>
              )}

              {params2.length > 0 && (
                <Card title={`请求参数 · ${params2.length}`}>
                  <Table
                    cols={["参数名", "位置", "类型", "必填", "默认值", "说明"]}
                    rows={params2.map((p: ApiParam) => [
                      <span className="font-mono text-[12px] font-semibold text-ink-800">{p.name}</span>,
                      <span className="text-[11px] text-ink-500">{p.in}</span>,
                      <span className="font-mono text-[11px] text-ink-600">{p.type}</span>,
                      p.required ? <Tag t="必填" c="amber" /> : <span className="text-[11px] text-ink-400">可选</span>,
                      <span className="font-mono text-[11px] text-ink-500">{p.default ?? "—"}</span>,
                      <span className="text-[12px] text-ink-600">
                        {p.description || "—"}
                        {p.example && <span className="ml-1 text-ink-400">例: {p.example}</span>}
                      </span>,
                    ])}
                  />
                </Card>
              )}

              {bodyFields.length > 0 && (
                <Card title={`请求体 · ${contract?.requestSchema?.bodyType ?? ""}`}>
                  <Table
                    cols={["字段", "类型", "必填", "说明"]}
                    rows={bodyFields.map((f) => [
                      <span className="font-mono text-[12px] font-semibold">{f.name}</span>,
                      <span className="font-mono text-[11px] text-ink-600">{f.type}</span>,
                      f.required ? <Tag t="必填" c="amber" /> : <span className="text-[11px] text-ink-400">可选</span>,
                      <span className="text-[12px] text-ink-600">
                        {f.description || "—"}
                        {f.example && <span className="ml-1 text-ink-400">例: {f.example}</span>}
                      </span>,
                    ])}
                  />
                </Card>
              )}

              <Card title="实现代码">
                {(extra.implementations ?? []).length === 0 ? (
                  <div className="rounded-lg border border-dashed border-ink-200 px-4 py-6 text-center text-[12px] text-ink-400">
                    未在代码仓库中找到实现，可能是规划中接口或实现类未被扫描覆盖。
                  </div>
                ) : (
                  <div className="space-y-2">
                    {(extra.implementations ?? []).map((impl) => (
                      <div key={impl.entryPoint}
                        className="rounded-lg border border-line bg-ink-50/50 px-4 py-3">
                        <div className="flex items-center justify-between gap-3">
                          <span className="font-mono text-[12px] font-semibold text-ink-800">
                            {impl.entryPoint}
                          </span>
                          {impl.commitSha && (
                            <span className="font-mono text-[10px] text-ink-400">@{impl.commitSha}</span>
                          )}
                        </div>
                        <div className="mt-1 break-all font-mono text-[11px] text-ink-500">
                          {impl.filePath}
                        </div>
                      </div>
                    ))}
                  </div>
                )}
              </Card>
            </>
          )}

          {/* ---------- 数据表 ---------- */}
          {type === "table" && (
            <>
              <Card title={`表结构 · ${columns.length} 个字段`}
                extra={<span className="font-mono text-[11px] text-ink-400">
                  {String(e.database_name)}.{String(e.schema_name)}.{String(e.name)}
                </span>}>
                <Table
                  cols={["#", "字段", "类型", "可空", "主键", "说明"]}
                  rows={columns.map((c, i) => [
                    <span className="font-mono text-[11px] text-ink-400">{i + 1}</span>,
                    <span className={`font-mono text-[12px] ${c.primaryKey ? "font-semibold text-brand-600" : "text-ink-800"}`}>
                      {c.name}
                    </span>,
                    <span className="font-mono text-[11px] text-ink-600">{c.type}</span>,
                    c.nullable === false ? "否" : <span className="text-ink-400">是</span>,
                    c.primaryKey ? <Tag t="PK" c="green" dot={false} /> : <span className="text-ink-300">—</span>,
                    <span className="text-[12px] text-ink-600">{c.comment || "—"}</span>,
                  ])}
                />
              </Card>
              {(extra.indexes ?? []).length > 0 && (
                <Card title="索引">
                  <Table cols={["索引名", "字段", "唯一"]}
                    rows={(extra.indexes ?? []).map((x) => {
                      const cols = Array.isArray(x.columns)
                        ? x.columns
                        : typeof x.columns === "string" ? x.columns.split(",").map((s) => s.trim()) : [];
                      return [
                        <span className="font-mono text-[12px]">{x.name}</span>,
                        <span className="font-mono text-[11px] text-ink-600" title={x.definition || ""}>
                          {cols.filter(Boolean).join(", ") || x.definition || "—"}
                        </span>,
                        x.unique ? "是" : "否",
                      ];
                    })} />
                </Card>
              )}
            </>
          )}

          {/* ---------- 功能页面 ---------- */}
          {type === "page" && (
            <>
              {extra.requirementDetail ? (
                <Card title="归属功能需求"
                  extra={
                    <Link to={`/project/${projectId}/requirements/${extra.requirementDetail.id}`}
                      className="inline-flex items-center gap-1 text-[12px] font-medium text-brand-600 hover:underline">
                      查看需求详情 <Icon name="arrow-right" size={13} />
                    </Link>
                  }>
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-mono text-[11px] text-brand-600">{extra.requirementDetail.id}</span>
                    <span className="text-[14px] font-semibold text-ink-900">{extra.requirementDetail.title}</span>
                    <Tag t={extra.requirementDetail.priority} c="blue" dot={false} />
                    <Tag t={extra.requirementDetail.status} c="gray" />
                  </div>
                  <p className="mt-2 text-[12px] leading-6 text-ink-600">
                    {extra.requirementDetail.description || "（暂无描述）"}
                  </p>
                  <div className="mt-2 text-[11px] text-ink-400">负责人：{extra.requirementDetail.owner || "未指派"}</div>
                </Card>
              ) : (
                <div className="rounded-card border border-amber-200 bg-amber-50/60 px-5 py-4 text-[12px] text-amber-800">
                  这个功能页面还没有挂到任何需求上，追溯链在需求侧是断的。
                </div>
              )}
              <Card title={`调用接口 · ${(extra.apis ?? []).length}`}>
                <LinkList items={extra.apis ?? []} pid={projectId} empty="该页面尚未登记接口" />
              </Card>
              <Card title={`涉及数据表 · ${(extra.tables ?? []).length}`}>
                <LinkList items={extra.tables ?? []} pid={projectId} empty="尚无接口读写数据表" />
              </Card>
            </>
          )}

          {/* ---------- 实现代码 ---------- */}
          {type === "code_artifact" && (
            <Card title="实现信息">
              <Row label="入口方法">
                <span className="font-mono text-[12px] font-semibold">{String(e.entry_point ?? id)}</span>
              </Row>
              <Row label="所属服务">{String(e.service ?? "—")}</Row>
              <Row label="仓库">{String(e.repo ?? "—")}</Row>
              <Row label="文件路径">
                <span className="break-all font-mono text-[11px] text-ink-600">{String(e.file_path ?? "—")}</span>
              </Row>
              <Row label="最近提交">
                <span className="font-mono text-[11px] text-ink-600">{String(e.commit_sha ?? "—")}</span>
              </Row>
            </Card>
          )}

          {/* ---------- 需求 ---------- */}
          {type === "requirement" && (
            <>
              <Card title="需求信息">
                <Row label="标题">{String(e.title ?? "")}</Row>
                <Row label="优先级 / 状态">
                  <Tag t={String(e.priority ?? "")} c="blue" dot={false} />
                  <span className="ml-2"><Tag t={String(e.status ?? "")} c="gray" /></span>
                </Row>
                <Row label="负责人">{String(e.owner_name ?? "未指派")}</Row>
                <Row label="描述">
                  <span className="whitespace-pre-wrap leading-6">{String(e.description ?? "—")}</span>
                </Row>
              </Card>
              <Card title={`功能页面 · ${(extra.pages ?? []).length}`}>
                <LinkList items={extra.pages ?? []} pid={projectId} empty="该需求尚未拆出功能页面" />
              </Card>
            </>
          )}
        </div>

        {/* ---------- 右侧关联 ---------- */}
        <div className="space-y-4">
          <Card title={`上游 · ${data.relations.upstream.length}`}>
            <LinkList items={data.relations.upstream} pid={projectId} empty="没有上游实体" />
          </Card>
          <Card title={`下游 · ${data.relations.downstream.length}`}>
            <LinkList items={data.relations.downstream} pid={projectId} empty="没有下游实体" />
          </Card>
          {type === "table" && (
            <Card title={`反向需求 · ${(extra.requirements ?? []).length}`}>
              <LinkList items={extra.requirements ?? []} pid={projectId} empty="还没有需求追溯到这里" />
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}
