import { useCallback, useState } from "react";

/** 复制文本到剪贴板，返回 [copied, copy]，copied 在 1.5s 后复位 */
export function useCopy(): [boolean, (text: string) => void] {
  const [copied, setCopied] = useState(false);
  const copy = useCallback((text: string) => {
    void navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 1500);
  }, []);
  return [copied, copy];
}
