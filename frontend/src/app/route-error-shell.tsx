import type { ReactNode } from "react";
import { AppLocaleProvider } from "@/lib/use-app-locale";
import { ThemeProvider } from "@/app/theme";
import { RouteErrorPage } from "./RouteErrorPage";

/** 路由 errorElement 外壳：保证错误页具备主题与 i18n */
export function RouteErrorShell({ children }: { children?: ReactNode }) {
  return (
    <AppLocaleProvider>
      <ThemeProvider>{children ?? <RouteErrorPage />}</ThemeProvider>
    </AppLocaleProvider>
  );
}

export const routeErrorElement = <RouteErrorShell />;
