import { useEffect, useState } from "react";
import { PanelLeft } from "lucide-react";
import { ChatProvider } from "@/features/chat/ChatProvider";
import { SessionSidebar } from "@/features/chat/SessionSidebar";
import { Thread } from "@/features/chat/Thread";
import { useShell } from "@/app/AppShell";

export function ChatRoute() {
  const { setMobileAction } = useShell();
  const [sessionsOpen, setSessionsOpen] = useState(false);

  useEffect(() => {
    setMobileAction(
      <button
        type="button"
        onClick={() => setSessionsOpen(true)}
        aria-label="会话列表"
        className="inline-flex size-9 items-center justify-center rounded-lg text-muted-foreground hover:bg-secondary hover:text-foreground"
      >
        <PanelLeft className="size-5" />
      </button>,
    );
    return () => setMobileAction(null);
  }, [setMobileAction]);

  return (
    <ChatProvider>
      <div className="flex h-full">
        <SessionSidebar mobileOpen={sessionsOpen} onClose={() => setSessionsOpen(false)} />
        <div className="min-w-0 flex-1">
          <Thread />
        </div>
      </div>
    </ChatProvider>
  );
}
