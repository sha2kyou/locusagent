import { ChatProvider } from "@/features/chat/ChatProvider";
import { QuickThread } from "@/features/chat/QuickThread";
import { desktopDragRegionProps, useQuickChatHtmlClass } from "@/lib/desktop-app";

export function QuickChatRoute() {
  useQuickChatHtmlClass();

  return (
    <div className="flex h-dvh flex-col overflow-hidden bg-background">
      <div
        {...desktopDragRegionProps()}
        className="pointer-events-auto fixed top-0 right-0 left-0 z-[60] h-10 bg-transparent"
        aria-hidden
      />
      <div className="apod-quick-chat-body flex min-h-0 flex-1 flex-col overflow-hidden">
        <ChatProvider mode="quick">
          <QuickThread />
        </ChatProvider>
      </div>
    </div>
  );
}
