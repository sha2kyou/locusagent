import { Thread } from "./Thread";

/** 系统快捷键唤起的精简对话界面 */
export function QuickThread() {
  return (
    <div className="flex min-h-0 flex-1 flex-col overflow-hidden">
      <Thread variant="quick" />
    </div>
  );
}
