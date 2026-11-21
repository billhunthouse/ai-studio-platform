import { del, get, post, put } from "./http";
import type { RecorderStep, UiElement, UiPage, UiRun, UiScript } from "./types";

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
  runs: () => get<UiRun[]>("/ui/runs"),
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
  poolStatus: () => get<{ browserAlive: boolean; activeContexts: number; idleSeconds: number }>("/ui/pool-status"),
  recorderSteps: () => get<RecorderStep[]>("/ui/recorder"),
  addRecorderStep: (step: Omit<RecorderStep, "id">) => post<RecorderStep[]>("/ui/recorder", step),
  clearRecorder: () => del<RecorderStep[]>("/ui/recorder"),
};
