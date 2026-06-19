export type FilePreviewKind = "markdown" | "code" | "image" | "pdf" | "text" | "unsupported";

const MARKDOWN_EXT = new Set(["md", "markdown"]);
const IMAGE_EXT = new Set(["jpg", "jpeg", "png", "gif", "webp", "bmp", "svg", "ico"]);
const CODE_EXT = new Set([
  "js",
  "mjs",
  "cjs",
  "ts",
  "tsx",
  "jsx",
  "py",
  "rb",
  "go",
  "rs",
  "java",
  "kt",
  "swift",
  "c",
  "cc",
  "cpp",
  "h",
  "hpp",
  "cs",
  "php",
  "sh",
  "bash",
  "zsh",
  "fish",
  "ps1",
  "json",
  "yaml",
  "yml",
  "toml",
  "xml",
  "html",
  "htm",
  "css",
  "scss",
  "less",
  "sql",
  "lua",
  "r",
  "vue",
  "svelte",
  "dockerfile",
  "makefile",
  "ini",
  "env",
  "graphql",
  "proto",
]);

const EXT_TO_LANG: Record<string, string> = {
  js: "javascript",
  mjs: "javascript",
  cjs: "javascript",
  ts: "typescript",
  tsx: "tsx",
  jsx: "jsx",
  py: "python",
  rb: "ruby",
  sh: "bash",
  bash: "bash",
  zsh: "bash",
  fish: "fish",
  ps1: "powershell",
  yml: "yaml",
  htm: "html",
  cc: "cpp",
  hpp: "cpp",
  cs: "csharp",
  dockerfile: "dockerfile",
  makefile: "makefile",
};

export function fileBaseName(filename: string): string {
  const normalized = filename.replace(/\\/g, "/");
  const base = normalized.split("/").pop() ?? normalized;
  return base;
}

export function fileExtension(filename: string): string {
  const base = fileBaseName(filename);
  const lower = base.toLowerCase();
  if (lower === "dockerfile") return "dockerfile";
  if (lower === "makefile") return "makefile";
  const dot = base.lastIndexOf(".");
  if (dot < 0) return "";
  return base.slice(dot + 1).toLowerCase();
}

export function highlightLanguage(filename: string): string {
  const ext = fileExtension(filename);
  return EXT_TO_LANG[ext] ?? (ext || "text");
}

export function filePreviewKind(filename: string, mimeType?: string | null): FilePreviewKind {
  const mime = (mimeType ?? "").toLowerCase();
  if (mime.startsWith("image/")) return "image";
  if (mime === "application/pdf") return "pdf";

  const ext = fileExtension(filename);
  if (ext === "pdf") return "pdf";
  if (MARKDOWN_EXT.has(ext)) return "markdown";
  if (IMAGE_EXT.has(ext)) return "image";
  if (CODE_EXT.has(ext)) return "code";
  if (ext) return "text";
  return "text";
}

const BINARY_PREVIEW_EXT = new Set([
  "zip",
  "gz",
  "gzip",
  "bz2",
  "xz",
  "7z",
  "rar",
  "tar",
  "tgz",
  "exe",
  "dll",
  "so",
  "dylib",
  "dmg",
  "pkg",
  "deb",
  "rpm",
  "msi",
  "doc",
  "docx",
  "xls",
  "xlsx",
  "ppt",
  "pptx",
  "woff",
  "woff2",
  "ttf",
  "otf",
  "eot",
  "mp3",
  "mp4",
  "avi",
  "mov",
  "wav",
  "webm",
  "bin",
  "dat",
  "iso",
]);

/** 是否可在 UI 内联预览（与附件来源无关，仅看文件名/MIME）。 */
export function isFilePreviewable(filename: string, mimeType?: string | null): boolean {
  const mime = (mimeType ?? "").toLowerCase();
  if (mime.startsWith("image/")) return true;
  if (mime === "application/pdf") return true;
  if (mime.includes("zip") || mime.includes("msword") || mime.includes("officedocument")) return false;

  const ext = fileExtension(filename);
  if (BINARY_PREVIEW_EXT.has(ext)) return false;

  const kind = filePreviewKind(filename, mimeType);
  return kind === "image" || kind === "pdf" || kind === "markdown" || kind === "code" || kind === "text";
}

export function buildDataUrl(mimeType: string, contentBase64: string): string {
  return `data:${mimeType};base64,${contentBase64}`;
}
