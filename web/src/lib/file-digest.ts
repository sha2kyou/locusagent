/** SHA-256 hex digest for attachment pending dedup (must match server payload hash). */

export async function sha256HexBytes(data: BufferSource): Promise<string> {
  const hash = await crypto.subtle.digest("SHA-256", data);
  return Array.from(new Uint8Array(hash))
    .map((b) => b.toString(16).padStart(2, "0"))
    .join("");
}

export async function sha256HexFile(file: File): Promise<string> {
  return sha256HexBytes(await file.arrayBuffer());
}

export async function sha256HexText(text: string): Promise<string> {
  return sha256HexBytes(new TextEncoder().encode(text));
}
