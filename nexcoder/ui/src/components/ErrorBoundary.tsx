import React, { Component, type ErrorInfo, type ReactNode } from 'react';

interface Props {
  children: ReactNode;
}

interface State {
  hasError: boolean;
  error: Error | null;
  errorInfo: ErrorInfo | null;
}

export class ErrorBoundary extends Component<Props, State> {
  public state: State = {
    hasError: false,
    error: null,
    errorInfo: null,
  };

  public static getDerivedStateFromError(error: Error): Partial<State> {
    return { hasError: true, error };
  }

  public componentDidCatch(error: Error, errorInfo: ErrorInfo) {
    console.error('[NexCoder UI ErrorBoundary caught an error]:', error, errorInfo);
    this.setState({ errorInfo });
  }

  public render() {
    if (this.state.hasError) {
      return (
        <div style={{
          height: '100vh',
          width: '100vw',
          backgroundColor: '#0f172a',
          color: '#f8fafc',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          padding: '2rem',
          boxSizing: 'border-box',
          fontFamily: 'system-ui, -apple-system, sans-serif',
        }}>
          <div style={{
            maxWidth: '800px',
            width: '100%',
            backgroundColor: '#1e293b',
            border: '1px solid #334155',
            borderRadius: '12px',
            padding: '2rem',
            boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.5)',
          }}>
            <h2 style={{ color: '#ef4444', marginTop: 0, fontSize: '1.5rem' }}>
              NexCoder Interface Error
            </h2>
            <p style={{ color: '#94a3b8', fontSize: '0.95rem' }}>
              An unexpected render error occurred in the React component tree.
            </p>
            <div style={{
              backgroundColor: '#090d16',
              padding: '1rem',
              borderRadius: '8px',
              overflowX: 'auto',
              fontSize: '0.85rem',
              color: '#f87171',
              fontFamily: 'monospace',
              marginBottom: '1rem',
            }}>
              {this.state.error?.toString() || 'Unknown Error'}
            </div>
            {this.state.errorInfo?.componentStack && (
              <details open style={{ marginTop: '1rem' }}>
                <summary style={{ cursor: 'pointer', color: '#60a5fa', marginBottom: '0.5rem' }}>
                  Component Stack Trace
                </summary>
                <pre style={{
                  backgroundColor: '#090d16',
                  padding: '1rem',
                  borderRadius: '8px',
                  overflowX: 'auto',
                  fontSize: '0.75rem',
                  color: '#cbd5e1',
                  maxHeight: '300px',
                }}>
                  {this.state.errorInfo.componentStack}
                </pre>
              </details>
            )}
            <button
              onClick={() => window.location.reload()}
              style={{
                marginTop: '1.5rem',
                backgroundColor: '#3b82f6',
                color: '#fff',
                border: 'none',
                padding: '0.6rem 1.2rem',
                borderRadius: '6px',
                cursor: 'pointer',
                fontWeight: 600,
              }}
            >
              Reload Interface
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
