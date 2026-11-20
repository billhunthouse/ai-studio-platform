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
    };
    userStories: Array<{ role: string; want: string; benefit: string; as_json: string }>;
    features: Array<{
      id: string; name: string; behavior: string;
      entry: string | string[]; apis: string[]; precondition: string;
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
    exceptions: Array<{ id: string; scenario: string; evidence: string }>;
    acceptance: Array<{ id: string; text: string; checked: boolean }>;
    coverage: {
      coveredLayers: string[]; missingLayers: string[];
      coverageCount: number; total: number; note: string;
    };
    codeEvidence: Array<{
      entryPoint: string; filePath: string; commit: string; service: string;
    }>;
    flows: string[];
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

export const prdApi = {
  get: (id: string) => get<PrdResponse>(`/prd/${encodeURIComponent(id)}`),
  status: () => get<PrdStatus>("/prd/status"),
  regenerate: () => post<{ message: string; output: string }>("/prd/regenerate", {}),
};
