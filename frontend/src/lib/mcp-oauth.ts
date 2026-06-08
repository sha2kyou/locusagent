import { listMcp } from "@/api/endpoints";

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms));

/** 外部浏览器授权完成后，轮询 MCP 列表直到 oauth_connected 或超时。 */
export async function pollMcpOAuthConnected(
  serverName: string,
  opts?: { timeoutMs?: number; intervalMs?: number },
): Promise<boolean> {
  const timeoutMs = opts?.timeoutMs ?? 5 * 60_000;
  const intervalMs = opts?.intervalMs ?? 2_000;
  const deadline = Date.now() + timeoutMs;

  while (Date.now() < deadline) {
    try {
      const { items } = await listMcp({ sync: true });
      const item = items.find((s) => s.name === serverName);
      if (item?.oauth_connected) return true;
    } catch {
      // 轮询期间忽略 transient 错误
    }
    await sleep(intervalMs);
  }
  return false;
}
