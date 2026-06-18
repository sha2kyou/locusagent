import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { Button } from "@/components/ui/button";

function reloadPage(): void {
  window.location.reload();
}

export function AppErrorPage({
  detail,
}: {
  /** 仅开发环境展示的技术细节 */
  detail?: string;
}) {
  const { t } = useTranslation();

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center bg-background px-6 py-12">
      <div className="flex w-full max-w-md flex-col items-center gap-5 text-center">
        <div className="flex size-12 items-center justify-center rounded-full bg-destructive/10 text-destructive">
          <AlertTriangle className="size-6" aria-hidden />
        </div>
        <div className="space-y-2">
          <h1 className="text-lg font-semibold tracking-tight text-foreground">
            {t("appError.title")}
          </h1>
          <p className="text-sm leading-relaxed text-muted-foreground">
            {t("appError.description")}
          </p>
        </div>
        {import.meta.env.DEV && detail ? (
          <pre className="max-h-40 w-full overflow-auto rounded-lg border border-border bg-surface/60 p-3 text-left text-[11px] leading-relaxed text-muted-foreground">
            {detail}
          </pre>
        ) : null}
        <Button variant="primary" size="md" onClick={reloadPage}>
          {t("appError.refresh")}
        </Button>
      </div>
    </div>
  );
}

export function formatThrownError(error: unknown): string | undefined {
  if (error instanceof Error) {
    return error.stack ?? error.message;
  }
  if (typeof error === "string") return error;
  if (error && typeof error === "object" && "message" in error) {
    const message = (error as { message?: unknown }).message;
    if (typeof message === "string") return message;
  }
  return undefined;
}
