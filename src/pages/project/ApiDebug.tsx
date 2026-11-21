import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { apiTestApi, testcasesApi, traceApi } from "@/api";
import type { ApiResponse, Assertion } from "@/api/types";
import { useAsync } from "@/hooks/useAsync";
import { useApp } from "@/store/app";
import { useAuth } from "@/store/auth";
import { Btn, Card, Input, Select, Table, Tag, Textarea } from "@/components/ui";
import { cx } from "@/lib/cx";

const BASE = "http://127.0.0.1:8086";
const TABS = ["Params", "Body", "Headers", "断言"] as const;
type Tab = (typeof TABS)[number];
type AuthChoice = "auto" | "admin" | "customer" | "none";

const AUTH_LABELS: Record<AuthChoice, string> = {
  auto: "身份: 自动", admin: "身份: 管理端", customer: "身份: C 端会员", none: "身份: 不注入",
};
const AUTH_FROM_LABEL: Record<string, AuthChoice> = Object.fromEntries(
  Object.entries(AUTH_LABELS).map(([k, v]) => [v, k as AuthChoice]),
);

interface ApiRow { id: string; method: string; path: string; summary: string; service: string }

interface Contract {
  method: string; path: string; summary: string; service: string; authRequirement: string;
  requestSchema: {
    params?: Array<{ in: string; name: string; type?: string; required?: boolean; description?: string; example?: string }>;
    bodyFields?: Array<{ name: string; type?: string; required?: boolean; description?: string; example?: string }>;
    bodyType?: string;
  };
}

/** 从契约描述里解析枚举取值，如 "售后类型：REFUND仅退款 / REFUND_RETURN退货退款"。 */
function parseEnums(desc: string | undefined): string[] {
  if (!desc) return [];
  const m = desc.match(/[:：]\s*(.+)$/);
  if (!m) return [];
  return m[1].split(/[;；/、]/).map((s) => s.trim()).filter((s) => /^[A-Z][A-Z_0-9]*$/.test(s));
}

function ParamCell({ desc, value, onChange }: {
  desc: string; value: string; onChange: (v: string) => void;
}) {
  const enums = parseEnums(desc);
  if (enums.length > 0) {
    return (
      <Select opts={["", ...enums]} className="w-full min-w-32" value={value} onChange={(e) => onChange(e.target.value)} />
    );
  }
  return <Input className="w-full min-w-32 font-mono text-[11px]" value={value} onChange={(e) => onChange(e.target.value)} />;
}

export function ApiDebug() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const { toast } = useApp();
  const { user } = useAuth();

  // 接口选择（真实追溯清单）
  const { data: apis } = useAsync<ApiRow[]>(() => traceApi.apis() as unknown as Promise<ApiRow[]>, [], []);
  const [keyword, setKeyword] = useState("");
  const [picking, setPicking] = useState(false);
  const [contract, setContract] = useState<Contract | null>(null);
  const [loadingContract, setLoadingContract] = useState(false);

  // 请求状态
  const initialPath = params.get("path") ?? "";
  const [method, setMethod] = useState(params.get("method") ?? "GET");
  const [url, setUrl] = useState(initialPath ? `${BASE}${initialPath}` : "");
  const [auth, setAuth] = useState<"auto" | "admin" | "customer" | "none">("auto");
  const [paramValues, setParamValues] = useState<Record<string, string>>({});
  const [bodyValues, setBodyValues] = useState<Record<string, string>>({});
  const [bodyMode, setBodyMode] = useState<"表格" | "JSON">("表格");
  const [bodyJson, setBodyJson] = useState("");
  const [extraHeaders, setExtraHeaders] = useState<Array<{ key: string; value: string }>>([]);
  const [assertions, setAssertions] = useState<Assertion[]>([
    { type: "状态码", expression: "-", expected: "200" },
    { type: "JSONPath", expression: "$.code", expected: "0" },
  ]);
  const [tab, setTab] = useState<Tab>("Params");
  const [res, setRes] = useState<ApiResponse | null>(null);
  const [sending, setSending] = useState(false);

  const filteredApis = useMemo(() => {
    const kw = keyword.trim().toLowerCase();
    if (!kw) return (apis ?? []).slice(0, 12);
    return (apis ?? [])
      .filter((a) => a.path.toLowerCase().includes(kw) || a.summary.toLowerCase().includes(kw) || a.method.toLowerCase().includes(kw))
      .slice(0, 30);
  }, [apis, keyword]);

  /** 选中真实接口：拉契约 → 探测真实样本 → 填充 URL/参数/Body */
  const pickApi = async (a: ApiRow) => {
    setPicking(false);
    setKeyword("");
    setLoadingContract(true);
    try {
      let c: Contract | null = null;
      try {
        c = await traceApi.apiContract(a.method, a.path) as unknown as Contract;
        setContract(c);
        setMethod(c.method);
      } catch {
        // 接口不在追溯清单（如手输路径），降级为仅样本探测
        setContract(null);
        setMethod(a.method);
      }
      const s = await apiTestApi.sample(a.method, a.path) as unknown as {
        filledPath: string; query: string; body: Record<string, unknown> | null; auth: string; notes: string[];
      };
      setUrl(`${BASE}${s.filledPath}${s.query}`);
      // 填充路径/查询参数默认值
      const pv: Record<string, string> = {};
      if (c) {
        for (const p of c.requestSchema.params ?? []) {
          if (p.in === "path") pv[p.name] = (s.filledPath.match(new RegExp(`${c.path.split("{")[0]}(.+?)(/|$)`)) ?? [])[1] ?? p.example ?? "";
        }
      }
      setParamValues(pv);
      // 填充请求体
      const bv: Record<string, string> = {};
      if (c) for (const f of c.requestSchema.bodyFields ?? []) bv[f.name] = "";
      if (s.body) for (const [k, v] of Object.entries(s.body)) bv[k] = String(v);
      setBodyValues(bv);
      setBodyJson(s.body ? JSON.stringify(s.body) : "");
      // 身份自动判定
      setAuth(s.auth === "customer" ? "customer" : "admin");
      toast(`已加载真实样本：${(c?.summary || a.path)}${s.notes.length ? `（${s.notes[0]}）` : ""}`);
    } catch (e) {
      toast(e instanceof Error ? e.message : "样本探测失败");
    } finally {
      setLoadingContract(false);
    }
  };

  // 从追溯实体页等入口带 path/method 跳转进来时，自动探测真实样本
  useEffect(() => {
    const p = params.get("path");
    const m = params.get("method");
    if (p && m && !url) void pickApi({ id: "", method: m, path: p, summary: "", service: "" });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const effectiveAuth = useMemo<"admin" | "customer" | "none">(() => {
    if (auth !== "auto") return auth;
    return url.replace(BASE, "").startsWith("/api/") ? "customer" : "admin";
  }, [auth, url]);

  const buildRequestBody = (): string => {
    if (bodyMode === "JSON") return bodyJson;
    if (!contract) return "";
    const obj: Record<string, unknown> = {};
    for (const f of contract.requestSchema.bodyFields ?? []) {
      const v = bodyValues[f.name];
      if (v === undefined || v === "") continue;
      const t = (f.type ?? "").toLowerCase();
      if (t.includes("long") || t.includes("int")) obj[f.name] = Number(v) || v;
      else if (t.includes("bool")) obj[f.name] = v === "true";
      else obj[f.name] = v;
    }
    return Object.keys(obj).length ? JSON.stringify(obj) : "";
  };

  const send = async () => {
    if (!url.trim()) { toast("请先选择接口或填写 URL"); return; }
    setSending(true);
    setRes(null);
    try {
      const response = await apiTestApi.send({
        method: method as "GET" | "POST" | "PUT" | "DELETE" | "PATCH",
        url,
        body: method === "GET" ? "" : buildRequestBody(),
        auth: effectiveAuth,
        headers: Object.fromEntries(extraHeaders.filter((h) => h.key).map((h) => [h.key, h.value])),
        assertions,
      });
      setRes(response);
    } catch (e) {
      toast(e instanceof Error ? e.message : "发送失败");
    } finally {
      setSending(false);
    }
  };

  /** 保存为测试用例（关联真实被测接口，可在用例页直接运行） */
  const saveCase = async () => {
    const templatePath = contract?.path ?? url.replace(BASE, "");
    await testcasesApi.create({
      title: contract?.summary || `${method} ${templatePath}`,
      module: contract?.service || "调试",
      type: "正向",
      priority: "P1",
      precondition: `可访问 ${method} ${templatePath}${effectiveAuth === "admin" ? "（管理端身份）" : effectiveAuth === "customer" ? "（C 端会员身份）" : ""}`,
      steps: [`发送 ${method} ${templatePath}`, method === "GET" ? "核对返回数据" : "核对业务码与数据写入"],
      expected: "HTTP 200 且业务码为 0；返回数据与操作一致",
      source: "API 调试",
      owner: user?.name ?? "",
      caseType: "api",
      relatedApi: `${method} ${templatePath}`,
    });
    toast("已保存为 API 测试用例，可在用例页直接运行");
    navigate(`/project/ecommerce/testcases`);
  };

  const pathParams = (contract?.requestSchema.params ?? []).filter((p) => p.in === "path" || p.in === "query");
  const bodyFields = contract?.requestSchema.bodyFields ?? [];

  return (
    <div className="space-y-4">
      <Card>
        {/* 接口选择：来自真实追溯清单 */}
        <div className="relative flex gap-2">
          <Input
            className="w-80 font-mono text-[12px]"
            placeholder="搜索真实接口（路径 / 名称），如 orders、发货、/api/cart"
            value={keyword}
            onChange={(e) => { setKeyword(e.target.value); setPicking(true); }}
            onFocus={() => setPicking(true)}
          />
          {contract && (
            <span className="flex items-center gap-1.5 text-[11px] text-ink-500">
              <Tag t={contract.method} c={contract.method === "GET" ? "blue" : "green"} dot={false} />
              <code className="font-mono text-[11px]">{contract.path}</code>
              {contract.summary && <span>{contract.summary}</span>}
            </span>
          )}
          {loadingContract && <span className="self-center text-[11px] text-ink-400">契约加载中…</span>}
          {picking && (
            <div className="absolute top-9 z-20 max-h-72 w-[520px] overflow-auto rounded-lg border border-line bg-white shadow-lg">
              {filteredApis.length === 0 && <div className="px-3 py-4 text-xs text-ink-400">无匹配接口</div>}
              {filteredApis.map((a) => (
                <button key={a.id} onClick={() => void pickApi(a)}
                  className="flex w-full items-center gap-2 px-3 py-2 text-left text-[11px] hover:bg-ink-50">
                  <Tag t={a.method} c={a.method === "GET" ? "blue" : a.method === "DELETE" ? "red" : "green"} dot={false} />
                  <code className="min-w-0 flex-1 truncate font-mono text-ink-800">{a.path}</code>
                  <span className="max-w-40 truncate text-ink-500">{a.summary}</span>
                </button>
              ))}
            </div>
          )}
        </div>

        {/* 请求行 */}
        <div className="mt-3 flex gap-2">
          <Select opts={["GET", "POST", "PUT", "DELETE", "PATCH"]} className="w-24" value={method} onChange={(e) => setMethod(e.target.value)} />
          <Input className="flex-1 font-mono text-[12px]" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="选择上方真实接口，或输入完整 URL" />
          <Select
            className="w-36"
            opts={["身份: 自动", "身份: 管理端", "身份: C 端会员", "身份: 不注入"]}
            value={AUTH_LABELS[auth]}
            onChange={(e) => setAuth(AUTH_FROM_LABEL[e.target.value])}
          />
          <Btn onClick={send} disabled={sending}>{sending ? "发送中…" : "发送"}</Btn>
          <Btn v="ghost" onClick={saveCase}>保存为用例</Btn>
        </div>
        <p className="mt-1.5 text-[11px] text-ink-400">
          请求经平台后端代理发送至真实业务后端（127.0.0.1:8086）；
          身份「自动」按路径前缀选择：/api/** 使用 C 端会员（张三 13800000001），其余使用管理端 admin，鉴权自动注入，无需手填 token。
        </p>

        {/* Tabs */}
        <div className="mt-3 flex gap-4 border-b">
          {TABS.map((t) => (
            <button key={t} onClick={() => setTab(t)}
              className={cx("pb-2 text-xs border-b-2", tab === t ? "border-brand-500 text-brand-600" : "border-transparent text-ink-500")}>{t}</button>
          ))}
          {!contract && <span className="ml-auto self-center pb-1 text-[10px] text-ink-400">选择真实接口后，参数与请求体将按追溯契约自动生成</span>}
        </div>

        {tab === "Params" && (
          pathParams.length === 0 ? (
            <div className="mt-3 text-xs text-ink-400">{contract ? "该接口无路径/查询参数" : "尚未选择接口"}</div>
          ) : (
            <div className="mt-3">
              <Table
                cols={["参数", "位置", "必填", "值", "说明"]}
                rows={pathParams.map((p) => [
                  <code className="font-mono text-[11px] font-semibold text-ink-800">{p.name}</code>,
                  <Tag t={p.in} c={p.in === "path" ? "amber" : "gray"} dot={false} />,
                  p.required ? <Tag t="必填" c="red" dot={false} /> : <span className="text-[11px] text-ink-400">可选</span>,
                  <ParamCell desc={p.description ?? ""} value={paramValues[p.name] ?? ""} onChange={(v) => setParamValues({ ...paramValues, [p.name]: v })} />,
                  <span className="text-[11px] text-ink-500">{p.description || p.type || "—"}</span>,
                ])}
              />
            </div>
          )
        )}

        {tab === "Body" && (
          method === "GET" ? (
            <div className="mt-3 text-xs text-ink-400">GET 请求无请求体</div>
          ) : bodyFields.length === 0 && bodyMode === "表格" ? (
            <div className="mt-3 space-y-2">
              <div className="text-xs text-ink-400">{contract ? "契约中未解析出请求体字段，请切换 JSON 模式手动填写" : "尚未选择接口"}</div>
              <Btn v="secondary" size="sm" onClick={() => setBodyMode("JSON")}>切换 JSON 模式</Btn>
            </div>
          ) : (
            <div className="mt-3 space-y-2">
              <div className="flex items-center gap-2">
                <span className="text-[11px] text-ink-500">编辑模式</span>
                <Select opts={["表格", "JSON"]} className="w-24" value={bodyMode} onChange={(e) => {
                  const m = e.target.value as "表格" | "JSON";
                  if (m === "JSON" && !bodyJson) {
                    const obj: Record<string, unknown> = {};
                    for (const f of bodyFields) if (bodyValues[f.name]) obj[f.name] = bodyValues[f.name];
                    setBodyJson(JSON.stringify(obj, null, 2));
                  }
                  setBodyMode(m);
                }} />
                {contract?.requestSchema.bodyType && <span className="text-[10px] text-ink-400">DTO：{contract.requestSchema.bodyType}</span>}
              </div>
              {bodyMode === "表格" ? (
                <Table
                  cols={["字段", "类型", "必填", "值", "说明"]}
                  rows={bodyFields.map((f) => [
                    <code className="font-mono text-[11px] font-semibold text-ink-800">{f.name}</code>,
                    <span className="font-mono text-[11px] text-ink-500">{f.type}</span>,
                    f.required ? <Tag t="必填" c="red" dot={false} /> : <span className="text-[11px] text-ink-400">可选</span>,
                    <ParamCell desc={f.description ?? ""} value={bodyValues[f.name] ?? ""} onChange={(v) => setBodyValues({ ...bodyValues, [f.name]: v })} />,
                    <span className="text-[11px] text-ink-500">{f.description || "—"}</span>,
                  ])}
                />
              ) : (
                <Textarea className="h-40 w-full font-mono text-xs" spellCheck={false} value={bodyJson} onChange={(e) => setBodyJson(e.target.value)} />
              )}
            </div>
          )
        )}

        {tab === "Headers" && (
          <div className="mt-3 space-y-2">
            <div className="rounded-lg bg-ink-50/60 px-3 py-2 text-[11px] leading-5 text-ink-600">
              Authorization 请求头由平台按所选身份自动注入（当前：<b>{effectiveAuth === "admin" ? "管理端 admin" : effectiveAuth === "customer" ? "C 端会员 张三" : "不注入"}</b>），无需手动填写 token。
            </div>
            <Table
              cols={["Header", "Value", ""]}
              rows={[
                ...extraHeaders.map((h, i) => [
                  <Input className="w-full font-mono text-[11px]" value={h.key} onChange={(e) => setExtraHeaders(extraHeaders.map((x, j) => (j === i ? { ...x, key: e.target.value } : x)))} />,
                  <Input className="w-full font-mono text-[11px]" value={h.value} onChange={(e) => setExtraHeaders(extraHeaders.map((x, j) => (j === i ? { ...x, value: e.target.value } : x)))} />,
                  <Btn v="ghost" size="sm" onClick={() => setExtraHeaders(extraHeaders.filter((_, j) => j !== i))}>删除</Btn>,
                ]),
                [<Btn v="secondary" size="sm" onClick={() => setExtraHeaders([...extraHeaders, { key: "", value: "" }])}>+ 添加 Header</Btn>, "", ""],
              ]}
            />
          </div>
        )}

        {tab === "断言" && (
          <div className="mt-3 space-y-2">
            <Table
              cols={["类型", "表达式", "期望值"]}
              rows={assertions.map((a, i) => [
                <Select opts={["状态码", "JSONPath", "响应时间"]} className="w-full" value={a.type}
                  onChange={(e) => setAssertions(assertions.map((x, j) => (j === i ? { ...x, type: e.target.value } : x)))} />,
                <Input className="w-full font-mono text-[11px]" value={a.expression}
                  onChange={(e) => setAssertions(assertions.map((x, j) => (j === i ? { ...x, expression: e.target.value } : x)))} />,
                <Input className="w-full font-mono text-[11px]" value={a.expected}
                  onChange={(e) => setAssertions(assertions.map((x, j) => (j === i ? { ...x, expected: e.target.value } : x)))} />,
              ])}
            />
            <div className="flex gap-2">
              <Btn v="secondary" size="sm" onClick={() => setAssertions([...assertions, { type: "JSONPath", expression: "$.data", expected: "" }])}>+ 添加断言</Btn>
            </div>
          </div>
        )}
      </Card>

      {res && (
        <Card title="响应" extra={
          <div className="flex gap-3 items-center text-xs">
            <Tag t={`${res.status} ${res.statusText}`} c={res.status === 200 ? "green" : "red"} />
            <span>{res.timeMs}ms</span>
            <span>{res.sizeKb}KB</span>
            <span className={res.assertionsPassed === res.assertionsTotal ? "text-emerald-600" : "text-red-500"}>
              断言 {res.assertionsPassed}/{res.assertionsTotal} 通过
            </span>
          </div>
        }>
          <pre className="max-h-96 overflow-auto rounded-md bg-slate-900 p-3 text-xs text-emerald-300">{res.body}</pre>
        </Card>
      )}
    </div>
  );
}
