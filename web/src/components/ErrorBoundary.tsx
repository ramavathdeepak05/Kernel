import { Component, type ErrorInfo, type ReactNode } from "react";

interface Props {
  children: ReactNode;
  fallback?: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
}

export class ErrorBoundary extends Component<Props, State> {
  constructor(props: Props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error): State {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // In production, this would go to Sentry or similar
    if (import.meta.env.DEV) {
      console.error("ErrorBoundary caught:", error, info.componentStack);
    }
  }

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) return this.props.fallback;
      return (
        <div style={{ padding: 40, textAlign: "center" }}>
          <h2 style={{ fontSize: 20, fontWeight: 600, marginBottom: 12 }}>
            Something went wrong
          </h2>
          <p style={{ color: "#64748b", marginBottom: 20 }}>
            An unexpected error occurred. Please refresh the page or contact support if the problem persists.
          </p>
          <button
            onClick={() => window.location.reload()}
            style={{
              padding: "8px 20px",
              borderRadius: 6,
              border: "none",
              background: "#1D9E75",
              color: "#fff",
              fontWeight: 500,
              cursor: "pointer",
            }}
          >
            Refresh Page
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}
