import { useCallback, useEffect, useState } from "react";

type CollapseEntry = { open: boolean; touched: boolean };

const cache = new Map<string, CollapseEntry>();

function readCollapse(blockId: string, defaultOpen: boolean): boolean {
  const entry = cache.get(blockId);
  if (entry?.touched) return entry.open;
  return defaultOpen;
}

/** 折叠/展开：默认按 defaultOpen，用户手动切换后状态固定，不被后续渲染自动改变。 */
export function usePinnedCollapse(blockId: string, defaultOpen: boolean) {
  const [open, setOpenState] = useState(() => readCollapse(blockId, defaultOpen));

  useEffect(() => {
    setOpenState(readCollapse(blockId, defaultOpen));
  }, [blockId, defaultOpen]);

  const toggle = useCallback(() => {
    setOpenState((prev) => {
      const next = !prev;
      cache.set(blockId, { open: next, touched: true });
      return next;
    });
  }, [blockId]);

  return [open, toggle] as const;
}

/** 进行中强制展开，结束后默认收起；结束后可手动切换。 */
export function useActiveCollapse(blockId: string, active: boolean) {
  const [open, toggleOpen] = usePinnedCollapse(blockId, false);
  const isOpen = active ? true : open;
  return { isOpen, toggleOpen, expandable: !active } as const;
}
