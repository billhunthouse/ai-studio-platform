import { get, post } from "./http";

/** 产品文档 AGENT 还原出的 PRD（10 章节） */
export interface PrdDoc {
  schemaVersion: string;
  generatedBy: string;
  generatedAt: string;
  sections: {
    overview: {
      id: string; title: string; module: string; priority: string; status: string;
      owner: string; version: string; background: string; goal: string;
      sourceDoc: string; description: string;
      problem?: string; businessValue?: string; consequence?: string;
    };
    userStories: Array<{ role: string; want: string; benefit: string; as_json: string }>;
    features: Array<{
      id: string; name: string; behavior: string;
      entry: string | string[]; apis: string[]; precondition: string;
      role?: string; trigger?: string; rules?: string[]; postcondition?: string;
      exceptions?: string[]; relatedApis?: string[]; relatedData?: string[];
      kind?: "functional" | "constraint";
      preconditionDetail?: { data: string; permission: string; env: string };
    }>;
    businessRules: Array<{ text: string; evidence: string }>;
    apis: Array<{
      id: string; method: string; path: string; summary: string; auth: string;
      service: string; source: string; specRef: string;
      params: Array<Record<string, unknown>>;
      bodyFields: Array<Record<string, unknown>>;
      response: Record<string, unknown>;
    }>;
    dataModel: Array<{
      id: string; name: string; database: string; schema: string;
      primaryKey: unknown; columnCount: number; source: string;
      columns: Array<{ name: string; type: string; nullable: boolean; comment: string }>;
    }>;
    exceptions: Array<{
      id: string; scenario: string; evidence?: string;
      category?: string; feedback?: string; rollback?: string;
      retryable?: string; covered?: boolean;
    }>;
    acceptance: Array<{
      id: string; text: string; checked: boolean;
      frId?: string; type?: string;
      given?: string; when?: string; then?: string[];
      anchors?: string[];
    }>;
    coverage: {
      coveredLayers: string[]; missingLayers: string[];
      coverageCount: number; total: number; note: string;
      /** 各层覆盖实体（id/name），供前端跳转到追溯详情页 */
      layerEntities?: Record<string, Array<{ id: string; name: string }>>;
    };
    codeEvidence: Array<{
      id?: string; entryPoint: string; filePath: string; commit: string; service: string;
    }>;
    flows: string[];
    /** ---- 以下为规范化（v2 schema）新增章节，老文档可能缺失 ---- */
    docInfo?: {
      docId: string; version: string; previousVersion?: string;
      author: string; reviewers: string[]; status: string; source: string; domain: string;
      changeLog: Array<{ version: string; at: string; author: string; summary: string }>;
    };
    scope?: { inScope: string[]; outOfScope: string[]; assumptions: string[] };
    roles?: Array<{ role: string; entry: string; operations: string[]; dataScope: string }>;
    glossary?: Array<{ term: string; definition: string; aliases: string[]; forbidden: string[] }>;
    stateMachine?: Array<{
      from: string; event: string; to: string; actor: string; effect: string; illegal: string;
    }>;
    nfr?: Array<{ category: string; metric: string; target: string; measure: string }>;
    dataDictionary?: {
      tables: Array<{
        table: string; primaryKey: unknown; source: string; fieldCount: number;
        fields: Array<{
          name: string; type: string; required: boolean; range: string; default: string;
          unique: boolean; masked: boolean; note: string; audit: boolean;
        }>;
      }>;
      invariants: string[];
    };
    dependencies?: Array<{ name: string; type: string; assumption: string; fallback: string }>;
    openIssues?: Array<{ issue: string; owner: string; deadline: string; severity: string }>;
    quality?: {
      score: number; passed: number; total: number; grade: string;
      attributes: Array<{ name: string; pass: boolean; note: string }>;
      gates: Array<{ rule: string; pass: boolean; detail: string }>;
      gatesPassed: number; gatesTotal: number;
    };
    traceability?: {
      rows: Array<{ layer: string; count: number; items: string[]; status: string }>;
      layerCoverage: number; caseCount: number; caseVerified: number;
      verified: boolean; constraint?: boolean;
    };
  };
  counts: { pages: number; apis: number; code: number; tables: number; columns: number };
}

export interface PrdResponse {
  requirementId: string;
  domain: string;
  coverage: number;
  generatedAt: string;
  doc: PrdDoc;
}

export interface PrdStatus {
  total: number;
  restored: number;
  rate: number;
  missing: string[];
}

/** 需求覆盖率总览（四维口径，见 docs/需求文档规范.md §9-10） */
export interface PrdCoverage {
  requirementTotal: number;
  /** 主指标：有用例关联的需求 ÷ 需求总数 */
  requirementCoverage: number;
  /** 有用例「执行通过」的需求 ÷ 需求总数 */
  verifiedCoverage: number;
  docCoverage: number;
  traceCoverage: number;
  traceLinkedRate: number;
  /** 命中 ≥2 级断言锚点的 AC 占比 */
  acAnchorRate: number;
  detail: {
    withCase: number; verified: number; docRestored: number; caseExecutedReqs: number;
    traceFull: number; traceLinked: number;
    acTotal: number; acStrong: number;
    caseTotal: number; caseExecuted: number; casePassed: number; caseNotRun: number;
  };
  layerCoverage: Record<string, number>;
  quality: {
    average: number; min: number; max: number;
    distribution: Record<string, number>;
    gatesPassed: number; gatesTotal: number;
  };
  byPriority: CoverGroupRow[];
  byDomain: CoverGroupRow[];
  gaps: Array<{
    id: string; title: string; priority: string; domain: string;
    missing: string[]; caseCount: number; passed: number; score: number;
  }>;
}

export interface CoverGroupRow {
  priority?: string;
  domain?: string;
  total: number;
  withCase: number;
  verified: number;
  traceFull: number;
  caseRate: number;
  verifyRate: number;
  traceRate: number;
}

/* ---------------- 需求回归执行计划 ---------------- */

export type BatchKind = "baseline" | "smoke" | "auto" | "manual" | "force" | "retest" | "residual" | "judge" | "closeout";

export interface PlanRequirement {
  id: string; title: string; priority: string; domain: string; chain: string;
  caseCount: number; apiCount: number; manualCount: number; knownFailed: number;
}

export interface PlanBatch {
  id: string;
  kind: BatchKind;
  track: "自动化" | "人工";
  name: string;
  chain: string;
  domain: string;
  requirements: PlanRequirement[];
  caseCount: number;
  apiCount: number;
  manualCount: number;
  estimatedMinutes: number;
  dependsOn: string[];
  status: string;
  entry: string;
  exit: string;
  checklist: string[];
  needsForce?: boolean;
  reuse?: boolean;
  progress: { executed: number; passed: number; failed: number; skipped: number; remaining: number; rate: number };
}

export interface PrdRegressionPlan {
  generatedAt: string;
  projectId: string;
  version: string;
  objective: {
    from: {
      requirements: number; unverified: number; verifiedRate: number;
      cases: number; executed: number; p0: number; p0Unverified: number;
    };
    target: { verifiedRequirements: number; verifiedRate: number; p0Rate: number; s1Open: number };
    statement: string;
  };
  environment: {
    target: { reachable: boolean; endpoint: string; detail: string; expect?: string };
    dataBaseline: Array<{ name: string; table: string; count: number; note: string }>;
    identities: Array<{ role: string; account: string; scope: string }>;
    executor: string;
  };
  scope: {
    requirementTotal: number; unverifiedRequirements: number; caseTotal: number;
    apiCases: number; manualCases: number; smokeCases: number; knownFailed: number;
    deleteCases: number; residualCases: number; unjudgeableCases: number;
    concurrencyCases: number; autoMinutes: number; manualMinutes: number;
  };
  chains: Array<{ code: string; domain: string; name: string; why: string; requirements: number; cases: number }>;
  batches: PlanBatch[];
  totals: {
    batches: number; execBatches: number; autoBatches: number; manualBatches: number;
    uniqueCases: number; judgeCases: number;
    estimatedMinutes: number; estimatedHours: number; criticalPathHours: number;
  };
  schedule: Array<{
    day: string; date: string; weekday: string;
    autoBatches: string[]; manualBatches: string[];
    autoMinutes: number; manualMinutes: number; note: string;
  }>;
  exitCriteria: Array<{ item: string; target: string; measure: string }>;
  risks: Array<{ risk: string; impact: string; mitigation: string }>;
}

export interface PlanCase {
  id: string; title: string; priority: string; type: string;
  caseType: "api" | "functional"; relatedApi: string; requirementId: string;
  verdict: string; at: string;
}

export interface PlanJob {
  jobId: string; batchId: string; status: "running" | "done" | "failed";
  total: number; done: number; passed: number; failed: number; skipped: number;
  current: { caseId: string; title: string } | null;
  startedAt: string; finishedAt: string; rate: number; error?: string;
  results: Array<{ caseId: string; title: string; verdict: string; detail: string; http?: number | null }>;
}

export const prdApi = {
  get: (id: string) => get<PrdResponse>(`/prd/${encodeURIComponent(id)}`),
  status: () => get<PrdStatus>("/prd/status"),
  coverage: () => get<PrdCoverage>("/prd/coverage"),
  regenerate: () => post<{ message: string; output: string }>("/prd/regenerate", {}),
  regressionPlan: () => get<PrdRegressionPlan>("/prd/regression-plan"),
  planCases: (batchId: string, limit = 60) =>
    get<{ batch: PlanBatch; items: PlanCase[]; total: number; truncated: boolean }>(
      `/prd/regression-plan/cases?batchId=${encodeURIComponent(batchId)}&limit=${limit}`),
  runPlanBatch: (batchId: string, limit = 0, force = false) =>
    post<{ jobId: string; batchId: string; total: number }>("/prd/regression-plan/run", { batchId, limit, force }),
  planJob: (jobId: string) => get<PlanJob>(`/prd/regression-plan/run/${jobId}`),
};
