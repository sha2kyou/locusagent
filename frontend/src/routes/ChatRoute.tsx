import { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { PanelLeft } from "lucide-react";
import { ChatProvider } from "@/features/chat/ChatProvider";
import { SessionSidebar } from "@/features/chat/SessionSidebar";
import { Thread } from "@/features/chat/Thread";
import { useShell } from "@/app/AppShell";

export function ChatRoute() {
  const { t } = useTranslation();
  const { setMobileAction } = useShell();
  const [sessionsOpen, setSessionsOpen] = useState(false);

  useEffect(() => {
    setMobileAction(
      <button
        type="button"
        onClick={() => setSessionsOpen(true)}
        aria-label={t("nav.chatList")}
        className="inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <PanelLeft className="size-5" />
      </button>,
    );
    return () => setMobileAction(null);
  }, [setMobileAction, t]);

  return (
    <ChatProvider>
      <div className="flex h-full">
        <SessionSidebar mobileOpen={sessionsOpen} onClose={() => setSessionsOpen(false)} />
        <div className="min-w-0 flex-1 bg-background">
          <Thread />
        </div>
      </div>
    </ChatProvider>
  );
}
