import { del, get, post } from "./http";
import type { ApiDefinitionInput, ApiEndpoint, ApiReport, ApiResponse, ApiSuite, Assertion, HttpMethod } from "./types";

export const apiTestApi = {
  definitions: () => get<ApiEndpoint[]>("/api-defs"),
  create: (input: ApiDefinitionInput) => post<ApiEndpoint>("/api-defs", input),
  remove: (id: string) => del<null>(`/api-defs/${encodeURIComponent(id)}`),
  importYaml: (yaml: string, module = "导入") => post<ApiEndpoint[]>("/api-defs/import", { yaml, module }),
  send: (req: {
    method: HttpMethod; url: string; body: string;
    auth?: "admin" | "customer" | "none";
    headers?: Record<string, string>;
    assertions: Assertion[];
  }) => post<ApiResponse>("/api-defs/send", req),
  /** 真实样本探测：替换路径占位、按契约构造请求体（来自 case_runner 运行引擎） */
  sample: (method: string, path: string) =>
    post<{ filledPath: string; query: string; body: Record<string, unknown> | null; auth: string; notes: string[]; known?: boolean }>(
      "/api-defs/sample", { method, path }),
  suites: () => get<ApiSuite[]>("/api-suites"),
  createSuite: (input: { name: string; cron: string; count: number }) => post<ApiSuite>("/api-suites", input),
  runSuite: (id: string) => post<ApiSuite>(`/api-suites/${encodeURIComponent(id)}/run`),
  reports: () => get<ApiReport[]>("/api-reports"),
};
