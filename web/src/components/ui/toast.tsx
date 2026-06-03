import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { CheckCircle2, Info, X, XCircle } from "lucide-react";
import { cn } from "@/lib/utils";

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
      <div className="pointer-events-none fixed bottom-auto left-auto right-4 top-4 z-100 flex w-[min(22rem,calc(100vw-2rem))] flex-col gap-2">
        {toasts.map((t) => (
          <div
            key={t.id}
            className={cn(
              "pointer-events-auto flex items-center gap-2.5 rounded-lg border border-border-strong bg-card py-2.5 pl-3.5 pr-2 text-sm text-card-foreground shadow-xl backdrop-blur-0",
              "apod-enter-up",
            )}
          >
            {icons[t.type]}
            <span className="flex-1">{t.message}</span>
            <button
              type="button"
              className="inline-flex size-6 shrink-0 items-center justify-center rounded-md text-muted-foreground transition hover:bg-secondary hover:text-foreground"
              onClick={() => removeToast(t.id)}
              aria-label="关闭"
              title="关闭"
            >
              <X className="size-3.5" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}
