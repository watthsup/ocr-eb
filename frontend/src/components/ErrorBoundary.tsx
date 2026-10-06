import { Component, type ErrorInfo, type ReactNode } from 'react';
import { AlertOctagon, RotateCcw } from 'lucide-react';

interface Props {
  children: ReactNode;
  /** Changing this key resets the boundary (e.g. a new job id). */
  resetKey?: string | number;
}
interface State {
  error: Error | null;
}

export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null };

  static getDerivedStateFromError(error: Error): Partial<State> {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error('Dashboard render error', error, info.componentStack);
  }

  componentDidUpdate(prevProps: Props): void {
    if (prevProps.resetKey !== this.props.resetKey && this.state.error) {
      this.setState({ error: null });
    }
  }

  render(): ReactNode {
    if (!this.state.error) return this.props.children;
    return (
      <div className="ui-card">
        <div className="boundary">
          <AlertOctagon size={36} color="#C41230" />
          <h4 style={{ fontFamily: 'var(--font-heading)' }}>The results view hit an unexpected error</h4>
          <p className="muted small">The job data is intact — you can retry rendering or switch tabs.</p>
          <pre>{this.state.error.message}</pre>
          <button type="button" className="btn btn-outline btn-sm" onClick={() => this.setState({ error: null })}>
            <RotateCcw size={14} /> Try again
          </button>
        </div>
      </div>
    );
  }
}
