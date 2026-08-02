import { Component, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback: ReactNode;
}

interface State {
  hasError: boolean;
}

/** Catches render errors in its subtree so one broken component (e.g. a
 * malformed AI-generated content block) shows a fallback instead of
 * unmounting the whole app with a blank screen — React has no equivalent
 * of a try/catch around render, this is the only mechanism it provides. */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { hasError: false };

  static getDerivedStateFromError() {
    return { hasError: true };
  }

  componentDidCatch(error: unknown, info: { componentStack?: string }) {
    console.error("Render error caught by ErrorBoundary:", error, info.componentStack);
  }

  render() {
    return this.state.hasError ? this.props.fallback : this.props.children;
  }
}
