import { formatThrownError } from "./AppErrorPage";

/** 构建产物 hash 变更后，浏览器仍请求旧 chunk / 静态资源时的典型报错 */
const CHUNK_LOAD_MESSAGE =
  /failed to fetch dynamically imported module|importing a module script failed|error loading dynamically imported module|loading chunk [\da-f-]+ failed|chunkloaderror|failed to load module script|unable to preload css/i;

export function isAssetLoadError(error: unknown): boolean {
  if (!error) return false;
  if (isAbortError(error)) return false;

  const message = error instanceof Error ? error.message : String(error);
  return CHUNK_LOAD_MESSAGE.test(message);
}

function isAbortError(error: unknown): boolean {
  if (error instanceof DOMException && error.name === "AbortError") return true;
  if (typeof error === "object" && error !== null && "name" in error) {
    return (error as { name?: unknown }).name === "AbortError";
  }
  return false;
}

/** assistant-ui 切换会话时的瞬时索引竞态，可安全恢复 */
export function isRecoverableRenderRace(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error ?? "");
  return /tapClientLookup:\s*Index\s+\d+\s+out of bounds/i.test(message);
}

function assetTargetUrl(target: EventTarget | null): string | undefined {
  if (target instanceof HTMLScriptElement) return target.src || undefined;
  if (target instanceof HTMLLinkElement) return target.href || undefined;
  return undefined;
}

function isStaticAssetTarget(target: EventTarget | null): boolean {
  if (target instanceof HTMLScriptElement) return Boolean(target.src);
  if (target instanceof HTMLLinkElement) {
    return target.rel === "stylesheet" || target.as === "script";
  }
  return false;
}

export function installAssetLoadErrorHandling(onError: (detail: string) => void): () => void {
  const report = (error: unknown, fallback: string) => {
    onError(formatThrownError(error) ?? fallback);
  };

  const onWindowError = (event: ErrorEvent) => {
    if (isStaticAssetTarget(event.target)) {
      event.preventDefault();
      const url = assetTargetUrl(event.target);
      report(event.error, url ? `Asset load failed: ${url}` : "Asset load failed");
      return;
    }
    if (isAssetLoadError(event.error) || (event.message && CHUNK_LOAD_MESSAGE.test(event.message))) {
      event.preventDefault();
      report(event.error ?? event.message, event.message || "Asset load failed");
    }
  };

  const onRejection = (event: PromiseRejectionEvent) => {
    if (!isAssetLoadError(event.reason)) return;
    event.preventDefault();
    report(event.reason, "Chunk load failed");
  };

  window.addEventListener("error", onWindowError, true);
  window.addEventListener("unhandledrejection", onRejection);
  return () => {
    window.removeEventListener("error", onWindowError, true);
    window.removeEventListener("unhandledrejection", onRejection);
  };
}
