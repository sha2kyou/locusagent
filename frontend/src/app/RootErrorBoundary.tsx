import { Component, type ErrorInfo, type ReactNode } from "react";
import { AppErrorPage, formatThrownError } from "./AppErrorPage";

interface Props {
  children: ReactNode;
}

interface State {
  error: unknown;
}

/** 捕获 Router 外层（Provider 等）的渲染错误 */
export class RootErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: unknown): State {
    return { error };
  }

  componentDidCatch(error: unknown, info: ErrorInfo): void {
    console.error("[RootErrorBoundary]", error, info.componentStack);
  }

  render(): ReactNode {
    if (this.state.error) {
      return <AppErrorPage detail={formatThrownError(this.state.error)} />;
    }
    return this.props.children;
  }
}
