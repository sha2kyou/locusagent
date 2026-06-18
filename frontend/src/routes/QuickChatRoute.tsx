import { ChatProvider } from "@/features/chat/ChatProvider";
import { QuickThread } from "@/features/chat/QuickThread";
import { DesktopWindowDragOverlay } from "@/app/DesktopTitlebarSpacer";
import { useDesktopAppHtmlClass, useQuickChatHtmlClass } from "@/lib/desktop-app";

export function QuickChatRoute() {
  useDesktopAppHtmlClass();
  useQuickChatHtmlClass();

  return (
    <div className="flex h-dvh flex-col bg-background">
      <DesktopWindowDragOverlay />
      <div className="flex min-h-0 flex-1 flex-col pt-10">
        <ChatProvider mode="quick">
          <QuickThread />
        </ChatProvider>
      </div>
    </div>
  );
}
