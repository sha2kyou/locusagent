/** 将浏览器 keydown 转为 Tauri global-hotkey 字符串（如 cmd+shift+K） */

const MODIFIER_KEYS = new Set(["Shift", "Control", "Alt", "Meta", "OS"]);

const MACOS_MODIFIER_LABELS: Record<string, string> = {
  cmd: "⌘",
  ctrl: "⌃",
  alt: "⌥",
  shift: "⇧",
};

const WINDOWS_MODIFIER_LABELS: Record<string, string> = {
  cmd: "Win",
  ctrl: "Ctrl",
  alt: "Alt",
  shift: "Shift",
};

const MACOS_KEY_LABELS: Record<string, string> = {
  Space: "Space",
  Enter: "↩",
  Tab: "⇥",
  Backspace: "⌫",
  Delete: "⌦",
  Escape: "Esc",
  ArrowUp: "↑",
  ArrowDown: "↓",
  ArrowLeft: "←",
  ArrowRight: "→",
};

export function isMacOS(): boolean {
  if (typeof navigator === "undefined") return false;
  return /Mac|iPhone|iPod|iPad/i.test(navigator.platform) || /Mac OS X/i.test(navigator.userAgent);
}

/** 将存储的全局快捷键格式化为当前平台可读样式（macOS 用 ⌘⇧K，其它平台用 Ctrl+Shift+K） */
export function formatGlobalShortcutForDisplay(shortcut: string): string {
  const trimmed = shortcut.trim();
  if (!trimmed) return trimmed;

  const parts = trimmed.split("+").filter(Boolean);
  if (parts.length === 0) return trimmed;

  const mac = isMacOS();
  const modifierLabels = mac ? MACOS_MODIFIER_LABELS : WINDOWS_MODIFIER_LABELS;
  const modifiers: string[] = [];
  let mainKey = "";

  for (const part of parts) {
    const normalized = part.toLowerCase();
    if (normalized in modifierLabels) {
      modifiers.push(modifierLabels[normalized]);
      continue;
    }
    mainKey = mac ? part.toUpperCase() : part;
  }

  if (!mainKey) return trimmed;

  if (mac) {
    const mainLabel = MACOS_KEY_LABELS[mainKey] ?? mainKey;
    return `${modifiers.join("")}${mainLabel}`;
  }

  return [...modifiers, mainKey].join("+");
}

/** 主界面 / 快捷窗：新对话快捷键（macOS ⌘N，其它平台 Ctrl+N） */
export function isNewChatKeyboardShortcut(event: KeyboardEvent): boolean {
  if (event.key.toLowerCase() !== "n" || event.altKey || event.shiftKey) return false;
  return isMacOS() ? event.metaKey && !event.ctrlKey : event.ctrlKey && !event.metaKey;
}

const CODE_TO_HOTKEY: Record<string, string> = {
  Space: "Space",
  Enter: "Enter",
  Tab: "Tab",
  Backspace: "Backspace",
  Delete: "Delete",
  Escape: "Escape",
  ArrowUp: "ArrowUp",
  ArrowDown: "ArrowDown",
  ArrowLeft: "ArrowLeft",
  ArrowRight: "ArrowRight",
  Home: "Home",
  End: "End",
  PageUp: "PageUp",
  PageDown: "PageDown",
  Insert: "Insert",
  Minus: "Minus",
  Equal: "Equal",
  BracketLeft: "BracketLeft",
  BracketRight: "BracketRight",
  Backslash: "Backslash",
  Semicolon: "Semicolon",
  Quote: "Quote",
  Comma: "Comma",
  Period: "Period",
  Slash: "Slash",
  Backquote: "Backquote",
};

function mainKeyFromEvent(event: KeyboardEvent): string | null {
  const { code } = event;
  if (code.startsWith("Key")) return code.slice(3);
  if (code.startsWith("Digit")) return code.slice(5);
  if (/^F\d+$/.test(code)) return code;
  if (code.startsWith("Numpad")) {
    const suffix = code.slice(6);
    if (/^\d$/.test(suffix)) return `Numpad${suffix}`;
    const named: Record<string, string> = {
      Add: "NumpadAdd",
      Subtract: "NumpadSubtract",
      Multiply: "NumpadMultiply",
      Divide: "NumpadDivide",
      Decimal: "NumpadDecimal",
      Enter: "NumpadEnter",
    };
    return named[suffix] ?? null;
  }
  return CODE_TO_HOTKEY[code] ?? null;
}

/** 忽略纯修饰键；至少含一个修饰键 + 主键才返回 */
export function keyboardEventToGlobalShortcut(event: KeyboardEvent): string | null {
  if (MODIFIER_KEYS.has(event.key)) return null;

  const main = mainKeyFromEvent(event);
  if (!main) return null;

  const parts: string[] = [];
  if (event.metaKey) parts.push("cmd");
  if (event.ctrlKey) parts.push("ctrl");
  if (event.altKey) parts.push("alt");
  if (event.shiftKey) parts.push("shift");

  if (parts.length === 0) return null;

  parts.push(main);
  return parts.join("+");
}
