import { useRef, type CompositionEvent, type KeyboardEvent } from "react";

/** 中文等 IME 输入时，阻止 Enter 触发发送/提交。 */
export function useImeEnterGuard() {
  const composingRef = useRef(false);
  const justEndedCompositionRef = useRef(false);

  const onCompositionStart = () => {
    composingRef.current = true;
    justEndedCompositionRef.current = false;
  };

  const onCompositionEnd = (_e: CompositionEvent) => {
    composingRef.current = false;
    // Safari / 部分 IME：compositionend 后紧跟的 Enter 仍用于上字
    justEndedCompositionRef.current = true;
    window.requestAnimationFrame(() => {
      justEndedCompositionRef.current = false;
    });
  };

  const shouldBlockEnter = (e: KeyboardEvent): boolean => {
    if (e.key !== "Enter" || e.shiftKey) return false;
    return (
      e.nativeEvent.isComposing ||
      composingRef.current ||
      justEndedCompositionRef.current ||
      e.keyCode === 229
    );
  };

  return { onCompositionStart, onCompositionEnd, shouldBlockEnter };
}
