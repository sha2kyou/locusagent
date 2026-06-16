import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useTranslation } from "react-i18next";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";
import { floatingPanelClass } from "@/components/ui/surface-styles";

const AUTO_DISMISS_MS = 3400;
const STICKY_DISMISS_MS = 7800;

type ToastType = "info" | "success" | "error";
type ToastOptions = { sticky?: boolean };
interface ToastItem {
  id: number;
  message: string;
  type: ToastType;
  sticky: boolean;
}

const ToastContext = createContext<((message: string, type?: ToastType, options?: ToastOptions) => void) | null>(
  null,
);

export function useToast() {
  const ctx = useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used within ToastProvider");
  return ctx;
}

const icons: Record<ToastType, ReactNode> = {
  info: <Info className="size-4 text-muted-foreground" />,
  success: <CheckCircle2 className="size-4 text-success" />,
  error: <XCircle className="size-4 text-destructive" />,
};

export function ToastProvider({ children }: { children: ReactNode }) {
  const { t: tr } = useTranslation();
  const [toasts, setToasts] = useState<ToastItem[]>([]);
  const timeoutIdsRef = useRef(new Map<number, number>());

  useEffect(() => {
    return () => {
      for (const timerId of timeoutIdsRef.current.values()) window.clearTimeout(timerId);
      timeoutIdsRef.current.clear();
    };
  }, []);

  const removeToast = useCallback((id: number) => {
    const timerId = timeoutIdsRef.current.get(id);
    if (timerId) {
      window.clearTimeout(timerId);
      timeoutIdsRef.current.delete(id);
    }
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const show = useCallback((message: string, type: ToastType = "info", options?: ToastOptions) => {
    const id = Date.now() + Math.random();
    const sticky = !!options?.sticky;
    setToasts((prev) => [...prev, { id, message, type, sticky }]);
    const timerId = window.setTimeout(() => {
      timeoutIdsRef.current.delete(id);
      setToasts((prev) => prev.filter((t) => t.id !== id));
    }, sticky ? STICKY_DISMISS_MS : AUTO_DISMISS_MS);
    timeoutIdsRef.current.set(id, timerId);
  }, []);

  return (
    <ToastContext.Provider value={show}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-100 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((item) => (
          <div
            key={item.id}
            className={cn(
              "pointer-events-auto flex items-start gap-2.5 rounded-xl py-2.5 pl-3.5 pr-2 text-sm",
              floatingPanelClass,
            )}
          >
            <span className="mt-0.5 shrink-0">{icons[item.type]}</span>
            <span className="flex-1 line-clamp-2 break-words leading-snug">{item.message}</span>
            <button
              type="button"
              className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition hover:bg-secondary hover:text-foreground"
              onClick={() => removeToast(item.id)}
              aria-label={tr("common.close")}
              title={tr("common.close")}
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
