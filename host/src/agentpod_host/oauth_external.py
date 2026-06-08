"""OAuth 回调页：在外部浏览器完成授权后展示结果。"""

from __future__ import annotations

import html


def _key_icon() -> str:
    return """
<svg viewBox="0 0 24 24" fill="none" aria-hidden="true">
  <circle cx="8" cy="8" r="4" stroke="currentColor" stroke-width="1.75"/>
  <path d="M11 11l9 9" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>
  <path d="M16 16l4 4" stroke="currentColor" stroke-width="1.75" stroke-linecap="round"/>
</svg>"""


def oauth_callback_html(*, ok: bool, server_name: str = "", message: str = "") -> str:
    server = html.escape(server_name or "MCP")
    if ok:
        badge = '<span class="badge badge-ok">完成</span>'
        body = f"已成功完成 <strong>{server}</strong> 的 OAuth 授权，Agent 现在可以连接该 MCP 服务。"
    else:
        badge = '<span class="badge badge-error">失败</span>'
        body = html.escape(message or "授权过程中出现错误，请返回 AgentPod 重试。")
    hint = "请返回 AgentPod 应用继续使用，此页面可以关闭。"

    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <meta name="color-scheme" content="light dark" />
  <title>AgentPod · OAuth 授权</title>
  <link rel="icon" href="/favicon.ico" />
  <link rel="preconnect" href="https://fonts.googleapis.com" />
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
  <link href="https://fonts.googleapis.com/css2?family=Inter:ital,opsz,wght@0,14..32,400;0,14..32,500;0,14..32,600&display=swap" rel="stylesheet" />
  <style>
    :root {{
      --background: #fffefb;
      --foreground: #2e2e2e;
      --surface: #f7f6f4;
      --surface-40: rgba(247, 246, 244, 0.4);
      --surface-30: rgba(247, 246, 244, 0.3);
      --muted: #f5f4f2;
      --muted-foreground: #737373;
      --border: rgba(0, 0, 0, 0.09);
      --brand: #383838;
      --brand-soft: rgba(56, 56, 56, 0.1);
      --destructive: #c73737;
      --destructive-soft: rgba(199, 55, 55, 0.1);
      --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.05);
    }}
    @media (prefers-color-scheme: dark) {{
      :root {{
        --background: #292929;
        --foreground: #ededed;
        --surface: #333333;
        --surface-40: rgba(51, 51, 51, 0.4);
        --surface-30: rgba(51, 51, 51, 0.3);
        --muted: #383838;
        --muted-foreground: #a3a3a3;
        --border: rgba(255, 255, 255, 0.12);
        --brand: #ededed;
        --brand-soft: rgba(237, 237, 237, 0.12);
        --destructive: #f87171;
        --destructive-soft: rgba(248, 113, 113, 0.12);
        --shadow-xs: 0 1px 2px rgba(0, 0, 0, 0.2);
      }}
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      min-height: 100vh;
      background: var(--background);
      color: var(--foreground);
      font-family: "Inter", -apple-system, BlinkMacSystemFont, "PingFang SC", "Helvetica Neue", Arial, sans-serif;
      -webkit-font-smoothing: antialiased;
    }}
    .thread {{
      max-width: 42rem;
      margin: 0 auto;
      padding: 2rem 1rem 3rem;
    }}
    .tool-card {{
      margin: 0.375rem 0;
      overflow: hidden;
      border-radius: 0.75rem;
      border: 1px solid var(--border);
      background: var(--surface-40);
      box-shadow: var(--shadow-xs);
    }}
    .tool-header {{
      display: flex;
      align-items: center;
      gap: 0.5rem;
      padding: 0.625rem 0.875rem;
    }}
    .tool-icon {{
      display: flex;
      width: 1.5rem;
      height: 1.5rem;
      flex-shrink: 0;
      align-items: center;
      justify-content: center;
      border-radius: 0.375rem;
      background: var(--muted);
      color: var(--muted-foreground);
    }}
    .tool-icon svg {{
      width: 0.875rem;
      height: 0.875rem;
    }}
    .tool-title {{
      flex-shrink: 0;
      font-size: 13px;
      font-weight: 500;
      color: var(--foreground);
      white-space: nowrap;
    }}
    .tool-preview {{
      min-width: 0;
      flex: 1;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
      font-size: 11px;
      color: color-mix(in srgb, var(--muted-foreground) 50%, transparent);
    }}
    .badge {{
      flex-shrink: 0;
      border-radius: 9999px;
      padding: 0.125rem 0.375rem;
      font-size: 10px;
      font-weight: 500;
      line-height: 1.2;
    }}
    .badge-ok {{
      background: var(--brand-soft);
      color: var(--brand);
    }}
    .badge-error {{
      background: var(--destructive-soft);
      color: var(--destructive);
    }}
    .tool-body {{
      border-top: 1px solid var(--border);
      background: var(--surface-30);
      padding: 0.75rem 0.875rem;
    }}
    .tool-result {{
      margin: 0;
      font-size: 12px;
      line-height: 1.625;
      color: color-mix(in srgb, var(--foreground) 80%, transparent);
      white-space: pre-wrap;
      word-break: break-word;
    }}
    .tool-result strong {{
      font-weight: 600;
      color: var(--foreground);
    }}
    .tool-hint {{
      margin: 0.75rem 0 0;
      font-size: 11px;
      line-height: 1.5;
      color: var(--muted-foreground);
    }}
  </style>
</head>
<body>
  <main class="thread">
    <article class="tool-card">
      <header class="tool-header">
        <span class="tool-icon">{_key_icon()}</span>
        <span class="tool-title">OAuth 授权</span>
        <span class="tool-preview">{server}</span>
        {badge}
      </header>
      <div class="tool-body">
        <p class="tool-result">{body}</p>
        <p class="tool-hint">{hint}</p>
      </div>
    </article>
  </main>
</body>
</html>"""
