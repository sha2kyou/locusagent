// 统一 fetch 封装：错误解析、JSON/文本自适应。

export class ApiError extends Error {
  status: number;
  code?: string;
  detail?: unknown;
  data?: unknown;

  constructor(message: string, opts: { status: number; code?: string; detail?: unknown; data?: unknown }) {
    super(message);
    this.name = "ApiError";
    this.status = opts.status;
    this.code = opts.code;
    this.detail = opts.detail;
    this.data = opts.data;
  }
}

const WORKSPACE_ID_KEY = "apod-current-workspace-id";

export function getWorkspaceId(): string {
  if (typeof window === "undefined") return "";
  const stored = (window.localStorage.getItem(WORKSPACE_ID_KEY) || "").trim();
  if (stored) return stored;
  const m = window.location.pathname.match(/^\/w\/(ws_[a-z0-9]+)/);
  return m?.[1] || "";
}

export function setWorkspaceId(id: string | null | undefined): void {
  if (typeof window === "undefined") return;
  const value = String(id || "").trim();
  if (!value) {
    window.localStorage.removeItem(WORKSPACE_ID_KEY);
    return;
  }
  window.localStorage.setItem(WORKSPACE_ID_KEY, value);
}

function parseApiError(status: number, data: unknown): ApiError {
  // 容器/代理错误：{ error: { code, message, detail } }
  if (data && typeof data === "object" && "error" in data) {
    const err = (data as { error?: { code?: string; message?: string; detail?: unknown } }).error;
    if (err) {
      return new ApiError(err.message || `请求失败 (${status})`, {
        status,
        code: err.code,
        detail: err.detail,
        data,
      });
    }
  }
  // FastAPI 原生：{ detail: string | array }
  if (data && typeof data === "object" && "detail" in data) {
    const detail = (data as { detail?: unknown }).detail;
    if (typeof detail === "string") {
      return new ApiError(detail, { status, detail, data });
    }
    if (Array.isArray(detail)) {
      const msg = detail.map((d) => (d as { msg?: string })?.msg).filter(Boolean).join("；") || `请求失败 (${status})`;
      return new ApiError(msg, { status, detail, data });
    }
  }
  if (typeof data === "string" && data) {
    return new ApiError(data, { status, data });
  }
  return new ApiError(`请求失败 (${status})`, { status, data });
}

export interface RequestOptions extends RequestInit {
  /** 401 时不抛未登录（用于探测） */
  noAuthRedirect?: boolean;
  /** 请求超时（毫秒），默认 30s */
  timeoutMs?: number;
}

const DEFAULT_API_TIMEOUT_MS = 30_000;

function apiFetchSignal(opts: RequestOptions): AbortSignal | undefined {
  const { signal, timeoutMs = DEFAULT_API_TIMEOUT_MS } = opts;
  if (timeoutMs <= 0) return signal ?? undefined;
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  if (!signal) return timeoutSignal;
  return AbortSignal.any([signal, timeoutSignal]);
}

export async function api<T = unknown>(url: string, opts: RequestOptions = {}): Promise<T> {
  const { noAuthRedirect: _noAuthRedirect, headers, timeoutMs: _t, signal: _s, ...rest } = opts;
  const workspaceId = getWorkspaceId();
  let res: Response;
  try {
    res = await fetch(url, {
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        ...(workspaceId ? { "X-Workspace-Id": workspaceId } : {}),
        ...headers,
      },
      signal: apiFetchSignal(opts),
      ...rest,
    });
  } catch (e) {
    if (e instanceof DOMException && e.name === "TimeoutError") {
      throw new ApiError("请求超时，请稍后重试", { status: 408, code: "timeout" });
    }
    throw e;
  }

  const ct = res.headers.get("content-type") || "";
  const data: unknown = ct.includes("json")
    ? await res.json().catch(() => null)
    : await res.text();

  if (!res.ok) {
    throw parseApiError(res.status, data);
  }
  return data as T;
}

export const apiGet = <T = unknown>(url: string, opts?: RequestOptions) =>
  api<T>(url, { ...opts, method: "GET" });

export const apiSend = <T = unknown>(
  url: string,
  method: "POST" | "PUT" | "DELETE",
  body?: unknown,
  opts?: RequestOptions,
) =>
  api<T>(url, {
    ...opts,
    method,
    body: body === undefined ? undefined : JSON.stringify(body),
  });
