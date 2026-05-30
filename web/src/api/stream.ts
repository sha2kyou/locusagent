import type { ChatChunk } from "./types";
import { ApiError, redirectToLogin } from "./client";

export interface ChatRequestBody {
  messages: { role: string; content: string }[];
  stream: true;
  session_id?: string;
  model?: string;
}

export interface StreamHandlers {
  onMessage: (chunk: ChatChunk) => void;
  onDone?: () => void;
  onRetry?: (attempt: number, retryAfterSec: number) => void;
}

const MAX_RETRIES = 5;

async function sleepWithAbort(ms: number, signal?: AbortSignal): Promise<void> {
  if (!signal) {
    await new Promise<void>((resolve) => {
      window.setTimeout(resolve, ms);
    });
    return;
  }
  if (signal.aborted) throw new DOMException("Aborted", "AbortError");
  await new Promise<void>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      signal.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      window.clearTimeout(timer);
      signal.removeEventListener("abort", onAbort);
      reject(new DOMException("Aborted", "AbortError"));
    };
    signal.addEventListener("abort", onAbort, { once: true });
  });
}

/**
 * 调用 POST /api/workspace/chat/completions 并解析 SSE 流。
 * 移植自老前端 streamChatCompletion：fetch + ReadableStream，按 \n\n 切事件，
 * 取 data: 行，[DONE] 结束，其余 JSON.parse 交给 onMessage。
 */
export async function streamChatCompletion(
  body: ChatRequestBody,
  handlers: StreamHandlers,
  opts: { signal?: AbortSignal } = {},
): Promise<void> {
  let attempt = 0;

  for (;;) {
    const res = await fetch("/api/workspace/chat/completions", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "Content-Type": "application/json",
        Accept: "text/event-stream",
      },
      body: JSON.stringify(body),
      signal: opts.signal,
    });

    if (res.status === 401) {
      redirectToLogin();
      throw new ApiError("未登录", { status: 401, code: "unauthenticated" });
    }

    // 容器启动中：503 + Retry-After，自动重试
    if (res.status === 503 && attempt < MAX_RETRIES) {
      const retryAfter = Number(res.headers.get("Retry-After")) || 2;
      attempt += 1;
      handlers.onRetry?.(attempt, retryAfter);
      await sleepWithAbort(retryAfter * 1000, opts.signal);
      continue;
    }

    if (!res.ok || !res.body) {
      const data = await res.json().catch(() => null);
      const err = (data as { error?: { code?: string; message?: string; detail?: unknown } })?.error;
      throw new ApiError(err?.message || `请求失败 (${res.status})`, {
        status: res.status,
        code: err?.code,
        detail: err?.detail,
        data,
      });
    }

    const reader = res.body.getReader();
    const decoder = new TextDecoder();
    let buffer = "";

    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });

      let sep: number;
      while ((sep = buffer.indexOf("\n\n")) !== -1) {
        const rawEvent = buffer.slice(0, sep);
        buffer = buffer.slice(sep + 2);

        const dataLines = rawEvent
          .split("\n")
          .filter((line) => line.startsWith("data:"))
          .map((line) => line.slice(5).trimStart());
        if (dataLines.length === 0) continue;

        const raw = dataLines.join("");
        if (raw === "[DONE]") {
          handlers.onDone?.();
          return;
        }
        try {
          handlers.onMessage(JSON.parse(raw) as ChatChunk);
        } catch {
          // 忽略无法解析的分片
        }
      }
    }

    handlers.onDone?.();
    return;
  }
}
