import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { AlertTriangle } from "lucide-react";
import { Modal } from "./modal";
import { Button } from "./button";
import { Input } from "./field";
import { useImeEnterGuard } from "@/lib/ime-enter";

interface ConfirmOptions {
  title?: string;
  body: ReactNode;
  confirmText?: string;
  cancelText?: string;
  danger?: boolean;
}
interface PromptOptions {
  title?: string;
  body?: ReactNode;
  defaultValue?: string;
  placeholder?: string;
  confirmText?: string;
  cancelText?: string;
}

interface DialogApi {
  confirm: (opts: ConfirmOptions) => Promise<boolean>;
  prompt: (opts: PromptOptions) => Promise<string | null>;
}

const DialogContext = createContext<DialogApi | null>(null);

export function useDialogs() {
  const ctx = useContext(DialogContext);
  if (!ctx) throw new Error("useDialogs must be used within DialogProvider");
  return ctx;
}

export function DialogProvider({ children }: { children: ReactNode }) {
  const { t } = useTranslation();
  const [confirmState, setConfirmState] = useState<ConfirmOptions | null>(null);
  const [promptState, setPromptState] = useState<PromptOptions | null>(null);
  const [promptValue, setPromptValue] = useState("");
  const resolver = useRef<((v: unknown) => void) | null>(null);
  const { onCompositionStart, onCompositionEnd, shouldBlockEnter } = useImeEnterGuard();

  const confirm = useCallback((opts: ConfirmOptions) => {
    setConfirmState(opts);
    return new Promise<boolean>((resolve) => {
      resolver.current = resolve as (v: unknown) => void;
    });
  }, []);

  const prompt = useCallback((opts: PromptOptions) => {
    setPromptState(opts);
    setPromptValue(opts.defaultValue ?? "");
    return new Promise<string | null>((resolve) => {
      resolver.current = resolve as (v: unknown) => void;
    });
  }, []);

  const settleConfirm = (v: boolean) => {
    resolver.current?.(v);
    resolver.current = null;
    setConfirmState(null);
  };
  const settlePrompt = (v: string | null) => {
    resolver.current?.(v);
    resolver.current = null;
    setPromptState(null);
  };

  return (
    <DialogContext.Provider value={{ confirm, prompt }}>
      {children}

      <Modal
        open={!!confirmState}
        onClose={() => settleConfirm(false)}
        title={confirmState?.title ?? t("common.dialog.confirmTitle")}
        description={confirmState?.danger ? undefined : confirmState?.body}
        showClose={false}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => settleConfirm(false)}>
              {confirmState?.cancelText ?? t("common.actions.cancel")}
            </Button>
            <Button
              variant={confirmState?.danger ? "danger" : "primary"}
              onClick={() => settleConfirm(true)}
            >
              {confirmState?.confirmText ?? t("common.actions.confirm")}
            </Button>
          </>
        }
      >
        {confirmState?.danger && confirmState.body ? (
          <div className="flex gap-3 rounded-lg border border-destructive/30 bg-destructive/10 p-3 text-sm">
            <AlertTriangle className="mt-0.5 size-5 shrink-0 text-destructive" aria-hidden />
            <p className="text-foreground leading-relaxed">{confirmState.body}</p>
          </div>
        ) : null}
      </Modal>

      <Modal
        open={!!promptState}
        onClose={() => settlePrompt(null)}
        title={promptState?.title ?? t("common.dialog.promptTitle")}
        description={promptState?.body}
        showClose={false}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => settlePrompt(null)}>
              {promptState?.cancelText ?? t("common.actions.cancel")}
            </Button>
            <Button variant="primary" onClick={() => settlePrompt(promptValue)}>
              {promptState?.confirmText ?? t("common.actions.confirm")}
            </Button>
          </>
        }
      >
        <Input
          autoFocus
          value={promptValue}
          placeholder={promptState?.placeholder}
          onChange={(e) => setPromptValue(e.target.value)}
          onCompositionStart={onCompositionStart}
          onCompositionEnd={onCompositionEnd}
          onKeyDown={(e) => {
            if (shouldBlockEnter(e)) {
              e.preventDefault();
              return;
            }
            if (e.key === "Enter") settlePrompt(promptValue);
          }}
        />
      </Modal>
    </DialogContext.Provider>
  );
}
