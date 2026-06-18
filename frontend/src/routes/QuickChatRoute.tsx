import { ChatProvider } from "@/features/chat/ChatProvider";
import { QuickThread } from "@/features/chat/QuickThread";
import { DesktopWindowDragOverlay } from "@/app/DesktopTitlebarSpacer";
import { useQuickChatHtmlClass } from "@/lib/desktop-app";

export function QuickChatRoute() {
  useQuickChatHtmlClass();

  return (
    <div className="flex h-dvh flex-col bg-background">
      <DesktopWindowDragOverlay />
      <div className="apod-quick-chat-body flex min-h-0 flex-1 flex-col">
        <ChatProvider mode="quick">
          <QuickThread />
        </ChatProvider>
      </div>
    </div>
  );
}
