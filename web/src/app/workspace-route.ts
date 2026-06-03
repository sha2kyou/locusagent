export function isChatRoutePath(pathname: string): boolean {
  const { path } = stripWorkspacePrefix(pathname);
  return path === "/chat" || path.startsWith("/chat/");
}

export function stripWorkspacePrefix(pathname: string): { workspaceId: string | null; path: string } {
  const m = pathname.match(/^\/w\/([^/]+)(\/.*)?$/);
  if (!m) return { workspaceId: null, path: pathname || "/" };
  return { workspaceId: m[1] || null, path: m[2] || "/" };
}

export function withWorkspacePrefix(path: string, workspaceId: string | null | undefined): string {
  const normalized = path.startsWith("/") ? path : `/${path}`;
  const wid = String(workspaceId || "").trim();
  if (!wid) return normalized;
  return `/w/${wid}${normalized === "/" ? "" : normalized}`;
}
