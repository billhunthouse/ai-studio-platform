import { del, download, get, post, put, upload } from "./http";
import type { CaseReviewItem, CaseRunReport, TestCase } from "./types";

export interface ImportResult {
  created: number;
  updated: number;
  errors: string[];
}

export const testcasesApi = {
  list: (requirementId?: string) =>
    get<TestCase[]>(`/testcases${requirementId ? `?requirementId=${encodeURIComponent(requirementId)}` : ""}`),
  create: (input: Omit<TestCase, "id" | "updatedAt" | "version" | "status">) =>
    post<TestCase>("/testcases", input),
  update: (id: string, body: Partial<TestCase>) =>
    put<TestCase>(`/testcases/${encodeURIComponent(id)}`, body),
  remove: (id: string) => del<null>(`/testcases/${encodeURIComponent(id)}`),
  engines: () => get<{
    engines: Array<{ value: "internal" | "external" | "agent"; label: string; available: boolean; desc: string }>;
    externalReady: boolean;
    model: string;
  }>("/testcases/engines"),
  generate: (input: {
    source: string;
    requirementId?: string;
    engine: "internal" | "external";
    strategies: string[];
    rag: boolean;
    model?: string;
    relatedRequirementIds?: string[];
  }) => post<TestCase[]>("/testcases/generate", input),
  /** 资深测试工程师 AGENT：方法论驱动的专业用例生成（requirementId 空为全量补缺） */
  agentGenerate: (input: { requirementId?: string; dryRun?: boolean; overwrite?: boolean }) =>
    post<{ message: string; output: string; totalCases: number }>("/testcases/agent/generate", input),
  submitReview: (cases: TestCase[]) => post<number>("/testcases/review", { cases }),
  /** 运行用例：API 用例真实执行；功能用例传 manualVerdict 记录人工结果 */
  run: (id: string, opts?: { force?: boolean; manualVerdict?: "通过" | "失败" | "阻塞"; manualNote?: string }) =>
    post<CaseRunReport>(`/testcases/${encodeURIComponent(id)}/run`, opts ?? {}),
  reviewQueue: () => get<CaseReviewItem[]>("/testcases/reviews"),
  review: (caseId: string, action: "通过" | "驳回", comment: string) =>
    post<CaseReviewItem[]>(`/testcases/reviews/${encodeURIComponent(caseId)}`, { action, comment }),
  exportXlsx: () => download("/testcases/export.xlsx"),
  importXlsx: (file: File) => {
    const form = new FormData();
    form.append("file", file);
    return upload<ImportResult>("/testcases/import.xlsx", form);
  },
};
