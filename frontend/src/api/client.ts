import type {
  BatchStatus,
  CompareResponse,
  DocumentDetail,
  DocumentMeta,
  LLMConfig,
  MaskActions,
  MaskResponse,
  OllamaStatus,
  SessionStatus,
  Span,
  TypeDefinition,
  VerifyResult,
} from "../types";

declare global {
  interface Window {
    privacyDesk?: {
      apiBase: string;
      token: string;
      setWindowMode?: (mode: "lock" | "workbench") => void;
      fadeWindow?: (direction: "out" | "in") => void;
      onWindowModeApplied?: (callback: (mode: "lock" | "workbench") => void) => () => void;
    };
  }
}

const API_BASE =
  window.privacyDesk?.apiBase ??
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  "http://127.0.0.1:8765";
const APP_TOKEN =
  window.privacyDesk?.token ?? (import.meta.env.VITE_APP_TOKEN as string | undefined) ?? "";

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

function headers(json = true): Record<string, string> {
  const value: Record<string, string> = {};
  if (APP_TOKEN) value["X-App-Token"] = APP_TOKEN;
  if (json) value["Content-Type"] = "application/json";
  return value;
}

/** 把 FastAPI 的字符串或 422 数组 detail 统一成可展示文本。 */
function normalizeDetail(detail: unknown, fallback: string): string {
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    const messages = detail.map((item) => {
      if (item && typeof item === "object" && "msg" in item) {
        const value = (item as { msg?: unknown }).msg;
        if (typeof value === "string") return value;
      }
      return JSON.stringify(item);
    });
    return messages.join("；") || fallback;
  }
  if (detail && typeof detail === "object") return JSON.stringify(detail);
  return fallback;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const response = await fetch(`${API_BASE}/api/v1${path}`, {
    ...init,
    headers: { ...headers(!(init.body instanceof FormData)), ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = normalizeDetail(body.detail, detail);
    } catch {
      /* 非 JSON 错误体 */
    }
    throw new ApiError(response.status, detail);
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export const api = {
  session: {
    status: () => request<SessionStatus>("/session/status"),
    setup: (password: string) =>
      request<SessionStatus>("/session/setup", {
        method: "POST",
        body: JSON.stringify({ password }),
      }),
    unlock: (password: string) =>
      request<SessionStatus>("/session/unlock", {
        method: "POST",
        body: JSON.stringify({ password }),
      }),
    lock: () => request<SessionStatus>("/session/lock", { method: "POST" }),
  },
  documents: {
    list: () => request<DocumentMeta[]>("/documents"),
    get: (id: string) => request<DocumentDetail>(`/documents/${id}`),
    upload: (file: File) => {
      const form = new FormData();
      form.append("file", file);
      return request<DocumentMeta>("/documents", { method: "POST", body: form });
    },
    saveText: (id: string, text: string) =>
      request<{ id: string; length: number }>(`/documents/${id}/content`, {
        method: "PUT",
        body: JSON.stringify({ text }),
      }),
    detect: (id: string, useLlm = true) =>
      request<{ spans: Span[]; mode: string; text_length: number }>(`/documents/${id}/detect`, {
        method: "POST",
        body: JSON.stringify({ use_llm: useLlm }),
      }),
    mask: (id: string, actions: MaskActions, verify = true) =>
      request<MaskResponse>(`/documents/${id}/mask`, {
        method: "POST",
        body: JSON.stringify({ actions, verify }),
      }),
    verify: (id: string) => request<VerifyResult>(`/documents/${id}/verify`, { method: "POST" }),
    compare: (id: string) =>
      request<CompareResponse>(`/documents/${id}/compare`),
    download: async (id: string, kind: "masked" | "report", fmt: string, password?: string) => {
      const query = new URLSearchParams({ kind, fmt });
      if (password) query.set("password", password);
      const response = await fetch(`${API_BASE}/api/v1/documents/${id}/export?${query}`, {
        headers: headers(false),
      });
      if (!response.ok) {
        let detail = response.statusText;
        try {
          detail = normalizeDetail((await response.json()).detail, detail);
        } catch {
          /* 非 JSON 错误体 */
        }
        throw new ApiError(response.status, detail);
      }
      return await response.blob();
    },
  },
  types: {
    list: () => request<TypeDefinition[]>("/types"),
    save: (payload: TypeDefinition) =>
      request<TypeDefinition>(`/types/${payload.code}`, {
        method: "PUT",
        body: JSON.stringify(payload),
      }),
    remove: (code: string) => request<{ deleted: string }>(`/types/${code}`, { method: "DELETE" }),
    test: (type: TypeDefinition, samples: string[]) =>
      request<{ results: Array<{ sample: string; spans: Span[] }> }>("/types/test", {
        method: "POST",
        body: JSON.stringify({ type, samples }),
      }),
  },
  settings: {
    getLlm: () => request<LLMConfig>("/settings/llm"),
    detectEnvKeys: (names: string[]) => {
      const query = new URLSearchParams({ names: names.join(",") });
      return request<LLMConfig>(`/settings/llm/env-keys?${query.toString()}`);
    },
    saveLlm: (config: LLMConfig) =>
      request<LLMConfig>("/settings/llm", { method: "PUT", body: JSON.stringify(config) }),
    testLlm: () =>
      request<{ ok: boolean; mode: string; latency_ms?: number; items?: number; message?: string }>(
        "/settings/llm/test",
        { method: "POST" },
      ),
    ollamaStatus: (url?: string, model?: string) => {
      const query = new URLSearchParams();
      if (url) query.set("url", url);
      if (model) query.set("model", model);
      const suffix = query.toString();
      return request<OllamaStatus>(`/settings/ollama/status${suffix ? `?${suffix}` : ""}`);
    },
  },
  batches: {
    create: (files: File[]) => {
      const form = new FormData();
      files.forEach((file) => form.append("files", file));
      return request<{ id: string; total: number }>("/batches", { method: "POST", body: form });
    },
    get: (id: string) => request<BatchStatus>(`/batches/${id}`),
  },
};

/** 将后端 detail 或普通 Error 统一转为可展示文案 */
export function errorText(exc: unknown): string {
  if (exc instanceof Error && exc.message) return exc.message;
  return "操作失败，请稍后重试";
}

export function saveBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}
