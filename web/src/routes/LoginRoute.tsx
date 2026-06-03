import { BrandMark } from "@/app/Brand";

export function LoginRoute() {
  return (
    <div className="relative flex h-full items-center justify-center overflow-hidden p-4">
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.12]"
        style={{
          background:
            "radial-gradient(55% 45% at 50% 0%, var(--brand), transparent 70%)",
        }}
      />
      <div className="relative flex w-full max-w-sm flex-col items-center gap-4 rounded-2xl border border-border-strong bg-card p-9 text-center shadow-2xl">
        <BrandMark className="size-14" />
        <div className="space-y-1">
          <h1 className="text-2xl font-semibold tracking-tight">AgentPod</h1>
          <p className="text-sm text-muted-foreground">
            自托管 AgentPod · 每用户独立环境
          </p>
        </div>
        <a
          href="/api/oauth/github/login"
          className="mt-1 inline-flex w-full items-center justify-center gap-2 rounded-full bg-brand py-3 text-sm font-semibold text-brand-foreground transition hover:brightness-105 active:translate-y-px"
        >
          <svg width="18" height="18" viewBox="0 0 16 16" fill="currentColor">
            <path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82.64-.18 1.32-.27 2-.27.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.013 8.013 0 0 0 16 8c0-4.42-3.58-8-8-8z" />
          </svg>
          使用 GitHub 登录
        </a>
        <p className="text-xs text-muted-foreground/80">
          仅申请 <code className="rounded bg-secondary px-1.5 py-0.5">read:user</code> 权限，不读取仓库
        </p>
      </div>
    </div>
  );
}
