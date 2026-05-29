import { createContext, useCallback, useContext, useRef, useState, type ReactNode } from "react";
import { Modal } from "./modal";
import { Button } from "./button";
import { Input } from "./field";

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
  const [confirmState, setConfirmState] = useState<ConfirmOptions | null>(null);
  const [promptState, setPromptState] = useState<PromptOptions | null>(null);
  const [promptValue, setPromptValue] = useState("");
  const resolver = useRef<((v: unknown) => void) | null>(null);

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
        title={confirmState?.title ?? "确认"}
        description={confirmState?.body}
        showClose={false}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => settleConfirm(false)}>
              {confirmState?.cancelText ?? "取消"}
            </Button>
            <Button
              variant={confirmState?.danger ? "danger" : "primary"}
              onClick={() => settleConfirm(true)}
            >
              {confirmState?.confirmText ?? "确定"}
            </Button>
          </>
        }
      />

      <Modal
        open={!!promptState}
        onClose={() => settlePrompt(null)}
        title={promptState?.title ?? "输入"}
        description={promptState?.body}
        showClose={false}
        size="sm"
        footer={
          <>
            <Button variant="secondary" onClick={() => settlePrompt(null)}>
              {promptState?.cancelText ?? "取消"}
            </Button>
            <Button variant="primary" onClick={() => settlePrompt(promptValue)}>
              {promptState?.confirmText ?? "确定"}
            </Button>
          </>
        }
      >
        <Input
          autoFocus
          value={promptValue}
          placeholder={promptState?.placeholder}
          onChange={(e) => setPromptValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === "Enter") settlePrompt(promptValue);
          }}
        />
      </Modal>
    </DialogContext.Provider>
  );
}
