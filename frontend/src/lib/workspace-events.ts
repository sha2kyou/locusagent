const WORKSPACES_CHANGED_EVENT = "locus-agent:workspaces-changed";

/** 工作区列表有增删改时通知侧栏等其它区域刷新。 */
export function notifyWorkspacesChanged(): void {
  window.dispatchEvent(new Event(WORKSPACES_CHANGED_EVENT));
}

export function subscribeWorkspacesChanged(handler: () => void): () => void {
  window.addEventListener(WORKSPACES_CHANGED_EVENT, handler);
  return () => window.removeEventListener(WORKSPACES_CHANGED_EVENT, handler);
}
