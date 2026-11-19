import { get, post } from "./http";

export interface TraceRelation {
  relationId: string;
  relType: string;
  directionLabel?: string;
  src: { type: string; id: string; name?: string };
  dst: { type: string; id: string; name?: string };
  type?: string;
  id?: string;
  name?: string;
  source: string;
  confidence: number;
  status: string;
  note?: string;
  createdAt?: string | null;
  validFromRelease?: string | null;
  validToRelease?: string | null;
}

export interface TraceOverview {
  requirementTotal: number;
  coverageRate: number;
  pendingRelationCount: number;
  staleRelationCount: number;
}

export interface MatrixRow {
  id: string;
  title: string;
  priority: string;
  status: string;
  page: number;
  api: number;
  code_artifact: number;
  table: number;
  coverage: number;
  missing: string[];
}

export interface ImpactItem {
  hop: number;
  type: string;
  id: string;
  name: string;
  relType: string;
}

export interface TraceEntityDetail {
  entity: Record<string, unknown>;
  relations: { upstream: TraceRelation[]; downstream: TraceRelation[] };
}

export const traceApi = {
  overview: () => get<TraceOverview>("/trace/overview"),
  matrix: () => get<{ columns: string[]; rows: MatrixRow[] }>("/trace/matrix"),
  pending: (status = "proposed") => get<{
    total: number; staleCount: number; items: TraceRelation[];
  }>(`/trace/relations/pending?status=${encodeURIComponent(status)}`),
  entity: (entityType: string, entityId: string) =>
    get<TraceEntityDetail>(
      `/trace/entity?entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`
    ),
  impactForward: (entityType: string, entityId: string, maxHops = 3) =>
    get<{ root: { type: string; id: string }; affectedCount: number;
          items: ImpactItem[]; crossDatabaseWarning: boolean }>(
      `/trace/impact/forward?entity_type=${encodeURIComponent(entityType)}` +
      `&entity_id=${encodeURIComponent(entityId)}&max_hops=${maxHops}`
    ),
  impactBackward: (entityType: string, entityId: string, maxHops = 3) =>
    get<{ root: { type: string; id: string }; upstreamRequirements: ImpactItem[];
          allAffectedCount: number; items: ImpactItem[] }>(
      `/trace/impact/backward?entity_type=${encodeURIComponent(entityType)}` +
      `&entity_id=${encodeURIComponent(entityId)}&max_hops=${maxHops}`
    ),
  confirmRelation: (rid: string) => post<{ status: string }>(`/trace/relations/${rid}/confirm`),
  rejectRelation: (rid: string, reason: string) =>
    post<{ status: string }>(`/trace/relations/${rid}/reject`, { reason }),
  batchConfirm: (ids: string[]) =>
    post<{ confirmed: number }>("/trace/relations/batch-confirm", { ids }),
  relations: (entityType: string, entityId: string, direction = "both") =>
    get<{ total: number; items: TraceRelation[] }>(
      `/trace/relations?direction=${direction}` +
      `&entity_type=${encodeURIComponent(entityType)}&entity_id=${encodeURIComponent(entityId)}`
    ),
  apis: () => get<Array<{ id: string; method: string; path: string; summary: string;
    service: string; source: string; upstreamRequirementCount: number }>>("/trace/apis"),
  tables: () => get<Array<{ id: string; database: string; service: string; name: string;
    columnCount: number; upstreamRequirementCount: number }>>("/trace/tables"),
};
