import { DESKTOP_GATEWAY_ORIGIN } from "@/lib/desktop-app";

function appOrigins(): Set<string> {
  const origins = new Set<string>();
  if (typeof window !== "undefined" && window.location.origin) {
    origins.add(window.location.origin);
  }
  origins.add(DESKTOP_GATEWAY_ORIGIN);
  return origins;
}

/** 是否应在系统浏览器打开（非应用内路由 / 非同源 API）。 */
export function isExternalNavigationUrl(raw: string | null | undefined): boolean {
  if (!raw) return false;
  const href = raw.trim();
  if (!href || href.startsWith("#")) return false;
  if (href.startsWith("javascript:")) return false;
  if (href.startsWith("blob:")) return false;
  if (href.startsWith("/") && !href.startsWith("//")) return false;

  let url: URL;
  try {
    url = new URL(href, typeof window !== "undefined" ? window.location.href : DESKTOP_GATEWAY_ORIGIN);
  } catch {
    return false;
  }

  if (url.protocol === "mailto:" || url.protocol === "tel:") return true;
  if (url.protocol !== "http:" && url.protocol !== "https:") return false;

  return !appOrigins().has(url.origin);
}

/** 在系统默认浏览器中打开 URL。 */
export async function openExternalUrl(url: string): Promise<void> {
  const target = url.trim();
  if (!target) return;
  const { openUrl } = await import("@tauri-apps/plugin-opener");
  await openUrl(target);
}

type WindowWithApod = Window & { __apodExternalLinks?: boolean };

/** 拦截页面内外链与 window.open，统一走系统浏览器。 */
export function installExternalLinkHandling(): () => void {
  if (typeof window === "undefined") return () => {};
  const win = window as WindowWithApod;
  if (win.__apodExternalLinks) return () => {};
  win.__apodExternalLinks = true;

  const onClick = (event: MouseEvent) => {
    if (event.defaultPrevented || event.button !== 0) return;
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey) return;

    const target = event.target;
    if (!(target instanceof Element)) return;
    const anchor = target.closest("a[href]");
    if (!(anchor instanceof HTMLAnchorElement)) return;
    if (anchor.hasAttribute("download")) return;
    if (anchor.dataset.apodInternal === "true") return;

    const href = anchor.getAttribute("href");
    if (!isExternalNavigationUrl(href)) return;

    event.preventDefault();
    event.stopPropagation();
    void openExternalUrl(href!);
  };

  const originalOpen = window.open.bind(window);
  window.open = ((url?: string | URL, target?: string, features?: string) => {
    const raw = typeof url === "string" ? url : url?.toString() ?? "";
    if (raw && isExternalNavigationUrl(raw)) {
      void openExternalUrl(raw);
      return null;
    }
    return originalOpen(url, target, features);
  }) as typeof window.open;

  document.addEventListener("click", onClick, true);
  return () => {
    document.removeEventListener("click", onClick, true);
    window.open = originalOpen;
    delete win.__apodExternalLinks;
  };
}
