/** Dev-only harness: mounts AIPanel inside an error boundary so render
 *  crashes surface as readable text (#aipanel-error). Not part of the app. */
import React from 'react';
import ReactDOM from 'react-dom/client';
import AIPanel from './components/AIPanel/AIPanel';

class Boundary extends React.Component<{ children: React.ReactNode }, { err: string | null }> {
  state = { err: null as string | null };
  static getDerivedStateFromError(e: unknown) {
    const anyE = e as any;
    return { err: String(anyE?.stack || anyE?.message || anyE).slice(0, 900) };
  }
  render() {
    return this.state.err
      ? React.createElement('pre', { id: 'aipanel-error' }, this.state.err)
      : this.props.children;
  }
}

const el = document.createElement('div');
el.id = 'aipanel-dev-root';
document.body.appendChild(el);
ReactDOM.createRoot(el).render(
  React.createElement(Boundary, null, React.createElement(AIPanel)),
);
