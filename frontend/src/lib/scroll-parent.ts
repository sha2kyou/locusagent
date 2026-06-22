export function findScrollParent(el: HTMLElement | null): HTMLElement | null {
  let node: HTMLElement | null = el;
  while (node) {
    const style = window.getComputedStyle(node);
    const overflowY = style.overflowY;
    if (overflowY === "auto" || overflowY === "scroll" || overflowY === "overlay") {
      return node;
    }
    node = node.parentElement;
  }
  return null;
}

const DEFAULT_BOTTOM_THRESHOLD = 48;

export function isScrollAtBottom(el: HTMLElement, threshold = DEFAULT_BOTTOM_THRESHOLD): boolean {
  return el.scrollHeight - el.scrollTop - el.clientHeight <= threshold;
}

export function scrollContainerToBottom(el: HTMLElement, behavior: ScrollBehavior = "instant") {
  el.scrollTo({ top: el.scrollHeight, behavior });
}

/** 折叠/展开等导致内容高度变化时，保留视口锚点；若原本在底部则继续贴底。 */
export function preserveScrollOnLayoutChange(triggerEl: HTMLElement, change: () => void) {
  const scroller = findScrollParent(triggerEl);
  if (!scroller) {
    change();
    return;
  }
  const wasAtBottom = isScrollAtBottom(scroller);
  const distanceFromBottom = scroller.scrollHeight - scroller.scrollTop - scroller.clientHeight;
  change();
  const apply = () => {
    if (wasAtBottom) {
      scrollContainerToBottom(scroller, "instant");
    } else {
      scroller.scrollTop = scroller.scrollHeight - scroller.clientHeight - distanceFromBottom;
    }
  };
  apply();
  requestAnimationFrame(apply);
}
