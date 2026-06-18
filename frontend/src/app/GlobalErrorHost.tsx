import { useEffect, useState, type ReactNode } from "react";
import { AppErrorPage } from "./AppErrorPage";
import { installAssetLoadErrorHandling } from "./asset-load-errors";
import { RootErrorBoundary } from "./RootErrorBoundary";

/** 统一拦截渲染错误与静态资源 / lazy chunk 加载失败 */
export function GlobalErrorHost({ children }: { children: ReactNode }) {
  const [assetError, setAssetError] = useState<string | null>(null);

  useEffect(() => {
    if (import.meta.env.DEV) return;
    return installAssetLoadErrorHandling(setAssetError);
  }, []);

  if (assetError) {
    return <AppErrorPage detail={assetError} />;
  }

  return <RootErrorBoundary>{children}</RootErrorBoundary>;
}
