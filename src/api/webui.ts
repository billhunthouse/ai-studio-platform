import { del, get, post, put } from "./http";
import type { RecorderStep, UiElement, UiPage, UiRun, UiScript } from "./types";

/** 单条执行可选的用例（编译摘要，不含脚本全文） */
export type UiCaseIndexItem = {
  caseId: string; title: string; module: string; pageObject: string;
  ready: boolean; uiRunnable: boolean; writeFlow: boolean;
  totalSteps: number; executable: number; assertions: number;
  binding?: UiBindingInfo;
};

/** 用例-页面绑定信息（编译结果里带的"这条用例到底测哪个页面"） */
export type UiBindingInfo = {
  kind: string; kindLabel?: string;
  pageId: string; pageName: string; pagePath: string;
  poName: string; source: string; confidence: number; needsReview: boolean;
  reason: string;
  /** 规则推断 / 人工确认 / 因该页无 PO 而阻塞 / 绑定指向的 PO 已不存在 */
  risk?: "confirmed" | "guess" | "mismatch" | "none" | "blocked_no_po" | "blocked_ambiguous" | "stale_po" | "unknown";
  poSource?: string;
};

/** 绑定体检行：含建议与缺口原因 */
export type UiBindingRow = UiBindingInfo & {
  caseId: string; title: string; module: string; priority: string; status: string;
  kindLabel: string; suggestPageId: string; suggestPageName: string; suggestPoName: string;
  runnable: boolean;
};

export type UiBindingsPayload = {
  summary: { total: number; byKind: Record<string, number>; confirmed: number; bindable: number; needsReview: number; runnable: number };
  total: number; items: UiBindingRow[];
  pages: Array<{ pageId: string; name: string; path: string; domain: string; pos: string[] }>;
};

/** 页面覆盖反查 */
export type UiPageCoverageRow = {
  pageId: string; pageName: string; pagePath: string; domain: string;
  poNames: string[]; total: number; confirmed: number; runnable: number; caseIds: string[];
};

/** 用例去重体检：重复组 + 合并后收益 */
export type UiDedupGroup = {
  title: string; primary: string; primaryModule: string; primaryReason: string; primaryScore: number;
  duplicates: string[]; duplicateCount: number;
  modules: string[]; crossModule: boolean;
  requirementIds: string[]; requirementTitles: string[];
  fingerprints: number; contentVaries: boolean; priority: string;
  /** pending = 待合并；merged = 已归档的历史分组 */
  status: "pending" | "merged"; archivedAt?: string;
};

export type UiDedupPayload = {
  total: number; active: number; alreadyArchived: number;
  uniqueTitles: number; groups: number; duplicates: number; duplicateRate: number;
  afterMerge: number; crossModuleGroups: number; contentVariesGroups: number;
  mergedGroups: number; mergedDuplicates: number; mergedCrossModuleGroups: number;
  items: UiDedupGroup[];
};

/** 四层质量指标 */
export type UiQualityPayload = {
  generatedAt: string;
  gates: { trusted: boolean; reasons: string[] };
  l1Effectiveness: {
    totalCases: number; uniqueTitles: number; duplicateCases: number; duplicateRate: number;
    byKind: Record<string, number>; bindable: number; confirmed: number; bindingConfirmedRate: number;
    readyCases: number; assertionDensity: number; riskDistribution: Record<string, number>;
  };
  l2Outcome: {
    executed: number; rawPassRate: number; effectiveExecuted: number; effectivePassRate: number;
    ineffectiveExecuted: number; byVerdict: Record<string, number>;
    failureAttribution: Record<string, number>; durationP50: number; durationP95: number;
  };
  l3Stability: {
    casesExecuted: number; casesMultiRun: number; flakyCases: number; flakeRate: number;
    flakyDetail: Array<{ caseId: string; verdicts: Record<string, number> }>;
  };
  l4Coverage: {
    pagesTotal: number; pagesWithPo: number; pagesCoveredByCases: number;
    pagePoRate: number; pageCoveredRate: number;
  };
};

/** 一步执行的证据：状态 + 该步截图名 */
export type UiStepResult = {
  index: number; raw: string; keyword: string; status: string; detail: string;
  durationMs?: number; shot?: string;
};

/** 媒体：每步截图与执行视频（带签名的直链，可直接喂给 img/video） */
export type UiMediaShot = { index: number; name: string; url: string };
export type UiMediaInfo = { steps: UiMediaShot[]; video: string; videoUrl: string; bytes: number };

export type UiMediaUsage = { usage: string; usedMB: number; budgetGB: number; runs: number; root?: string };

/** 单条用例真实执行结果（逐步回放 + 证据） */
export type UiRunOneResult = {
  runId: string; caseId: string; caseTitle: string; module: string; pageObject: string;
  writeFlow: boolean; verdict: string;
  steps: UiStepResult[];
  assertions: number; assertionsPassed: number;
  finalUrl: string; pageText: string; orderNo: string;
  screenshot: string; durationMs: number;
  stepShots: UiMediaShot[]; video: string; videoUrl: string; mediaBytes: number;
  mediaUsage: UiMediaUsage; mediaPrune?: { removed?: string[] };
  script: string;
  irSteps: Array<{ index: number; raw: string; keyword: string; args: Record<string, unknown>; note: string }>;
};

/** 执行记录列表项：单条（single）或批次（batch） */
export type UiRunItem = {
  id: string; kind: "single" | "batch"; title: string; caseId: string; browser: string;
  result: string; verdict: string; caseCount: number; passed: number; failed: number;
  shots: number; hasVideo: boolean; media: UiMediaInfo; mediaPruned: boolean;
  time: string; duration: string; startedAtMs: number; status?: string;
  steps: UiStepResult[]; finalUrl: string; pageText: string; orderNo: string;
  assertions: number; assertionsPassed: number;
};

export type UiRunsPayload = {
  items: UiRunItem[];
  stats: { total: number; passed: number; failed: number; avgSeconds: number; batches: number; singles: number };
  media: UiMediaUsage;
};

/** 批次详情（点进批次子页面） */
export type UiBatchDetail = {
  id: string; title: string; status: string; startedAt: string; totalSeconds: number;
  total: number; executed: number; passed: number; failed: number; partial: number;
  skippedCount: number; passRate: number; writeExecuted: number; mediaBytes: number;
  mediaPruned: boolean;
  byPageObject: Record<string, { total: number; passed: number; failed: number; partial: number }>;
  failures: Array<{ caseId: string; caseTitle: string; pageObject: string; failedStep: string; detail: string; finalUrl: string; screenshot: string }>;
  skippedCases: Array<{ caseId: string; caseTitle: string; pageObject: string; reason: string }>;
  cases: Array<{
    caseId: string; caseTitle: string; module: string; pageObject: string; writeFlow: boolean;
    verdict: string; assertions: number; assertionsPassed: number;
    finalUrl: string; pageText: string; orderNos: string[]; seconds: number;
    steps: UiStepResult[]; media: UiMediaInfo;
  }>;
};


export const webuiApi = {
  pages: () => get<UiPage[]>("/ui/pages"),
  elements: (pageId?: string) => get<UiElement[]>(`/ui/elements${pageId ? `?pageId=${encodeURIComponent(pageId)}` : ""}`),
  addElement: (input: { pageId: string; name: string; selectorType: UiElement["selectorType"]; selectorValue: string }) =>
    post<UiElement>("/ui/elements", input),
  removeElement: (id: string) => del<null>(`/ui/elements/${encodeURIComponent(id)}`),
  scripts: () => get<UiScript[]>("/ui/scripts"),
  saveScript: (id: string, content: string) => put<UiScript>(`/ui/scripts/${encodeURIComponent(id)}`, { content }),
  createScript: (name: string, content: string, framework = "Playwright + POM") =>
    post<UiScript>("/ui/scripts", { name, content, framework }),
  runs: () => get<UiRunsPayload>("/ui/runs"),
  batchDetail: (id: string) => get<UiBatchDetail>(`/ui/batches/${encodeURIComponent(id)}`),
  mediaStats: () => get<UiMediaUsage>("/ui/media-stats"),
  execute: (scriptId: string, browser = "Chromium") => post<UiRun>("/ui/runs", { scriptId, browser }),
  /** UI 自动化：功能用例批量编译为可复用 Playwright 脚本 */
  compile: (input: { caseIds?: string[]; overwrite?: boolean }) =>
    post<{
      stats: { total: number; ready: number; partial: number; blocked: number };
      created: number; skipped: number;
      details: Array<{ caseId: string; title: string; total: number; executable: number; unknown: number; ready: boolean }>;
    }>("/ui/compile", input),
  compiledCase: (caseId: string) => get<Record<string, unknown>>(`/ui/compile/${encodeURIComponent(caseId)}`),
  /** 共享浏览器池真实执行（步骤间默认 300ms 节流） */
  runCases: (input: { caseIds?: string[]; delayMs?: number }) =>
    post<{
      total: number; passed: number; failed: number; partial: number;
      results: Array<{
        caseId: string; caseTitle: string; verdict: string; durationMs: number; screenshot: string;
        steps: Array<{ index: number; raw: string; keyword: string; status: string; detail: string }>;
      }>;
    }>("/ui/run-cases", input),
  /** 重新编译全部功能用例（v2：PO 真实操作 + 业务断言） */
  compileAll: () => post<{ stats: { total: number; ready: number; partial: number; blocked: number } }>("/ui/compile-all", {}),
  /** 批量真实执行（后台任务，100+ 条不阻塞） */
  runBatch: (input: { limit: number; maxWrite: number; delayMs?: number; caseIds?: string[]; onlyConfirmed?: boolean }) =>
    post<{ jobId: string; status: string; note: string }>("/ui/run-batch", input),
  /** 轮询批量执行进度/结果 */
  runBatchStatus: (jobId: string) =>
    get<{
      jobId: string; status: "running" | "finished" | "failed";
      index: number; total: number; current: string; error: string;
      result: null | {
        generatedAt: string; target: string; batchId?: string; kind?: string;
        compiled: { total: number; ready: number; partial: number; blocked: number };
        executed: number; passed: number; failed: number; partial: number; skippedCount: number;
        passRate: number; totalSeconds: number; writeExecuted: number;
        byPageObject: Record<string, { total: number; passed: number; failed: number; partial: number }>;
        failures: Array<{ caseId: string; caseTitle: string; pageObject: string; failedStep: string; detail: string; finalUrl: string; screenshot: string }>;
        skippedCases: Array<{ caseId: string; caseTitle: string; pageObject: string; reason: string }>;
        results: Array<{
          caseId: string; caseTitle: string; module: string; pageObject: string; writeFlow: boolean;
          verdict: string; assertions: number; assertionsPassed: number;
          finalUrl: string; pageText: string; orderNos: string[]; screenshot: string;
          seconds: number;
          steps: Array<{ index: number; raw: string; keyword: string; status: string; detail: string }>;
        }>;
      };
    }>(`/ui/run-batch/${encodeURIComponent(jobId)}`),
  poolStatus: () => get<{ browserAlive: boolean; activeContexts: number; idleSeconds: number }>("/ui/pool-status"),
  /** 单条执行：用例索引（选一条来跑，含 PO / 可执行性 / 是否写操作） */
  caseIndex: () => get<{
    total: number; ready: number; writeFlows: number;
    cases: UiCaseIndexItem[];
  }>("/ui/cases"),
  /** 用例-页面绑定体检 */
  bindings: (params?: { kind?: string; q?: string; onlyNeedsReview?: boolean }) => {
    const qs = new URLSearchParams();
    if (params?.kind) qs.set("kind", params.kind);
    if (params?.q) qs.set("q", params.q);
    if (params?.onlyNeedsReview) qs.set("onlyNeedsReview", "true");
    const s = qs.toString();
    return get<UiBindingsPayload>(`/ui/bindings${s ? `?${s}` : ""}`);
  },
  /** 人工确认/修改绑定（写用例文档，下次编译立刻生效） */
  writeBindings: (input: { items: Array<{ caseId: string; pageId?: string | null; poName?: string | null }>; clear?: boolean }) =>
    post<{ updated: number; caseIds: string[]; errors: Array<{ caseId: string; error: string }> }>("/ui/bindings", input),
  /** 页面视角覆盖反查 */
  coveragePages: () => get<{ total: number; pagesWithPo: number; covered: number; items: UiPageCoverageRow[] }>("/ui/coverage/pages"),
  /** 绑定选择器选项（页面 + 页面→PO + PO 全集） */
  bindingOptions: () => get<{
    pages: Array<{ pageId: string; name: string; path: string; domain: string; pos: string[] }>;
    poNames: string[];
  }>("/ui/bindings/options"),
  /** 四层质量指标 */
  quality: () => get<UiQualityPayload>("/ui/quality"),
  /** 用例去重体检：哪些用例是同一件事被登记多次，合并后剩多少（只读） */
  dedup: () => get<UiDedupPayload>("/ui/dedup"),
  /** 执行去重合并：副本归档、需求与模块聚合到主用例（可回滚） */
  dedupApply: (input?: { primaryIds?: string[] }) =>
    post<{ projectId: string; appliedAt: string; groupsMerged: number; casesArchived: number; before: number; after: number }>(
      "/ui/dedup/apply", input ?? {}),
  /** 回滚去重 */
  dedupRestore: () => post<{ restored: number; primariesCleared: number }>("/ui/dedup/restore", {}),
  /** 单条执行：真实跑一条，同步返回逐步回放证据（写操作需 force） */
  runOne: (input: { caseId: string; delayMs?: number; force?: boolean }) =>
    post<UiRunOneResult>("/ui/run-one", input),
  recorderSteps: () => get<RecorderStep[]>("/ui/recorder"),
  addRecorderStep: (step: Omit<RecorderStep, "id">) => post<RecorderStep[]>("/ui/recorder", step),
  clearRecorder: () => del<RecorderStep[]>("/ui/recorder"),
};
