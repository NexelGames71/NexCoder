import React from 'react';
import { Play, CheckCircle, AlertTriangle, Loader2 } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { formatRelativeTime } from '../../utils/formatters';

export default function TasksPanel() {
  const { tasks } = useChatStore();

  const getStatusIcon = (status: string) => {
    switch (status) {
      case 'complete':
        return <CheckCircle size={14} style={{ color: 'var(--accent-green)' }} />;
      case 'error':
        return <AlertTriangle size={14} style={{ color: 'var(--accent-red)' }} />;
      case 'running':
      case 'generating':
      case 'planning':
        return <Loader2 size={14} className="spin" style={{ color: 'var(--accent-purple)' }} />;
      default:
        return <Play size={14} style={{ color: 'var(--text-secondary)' }} />;
    }
  };

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Agent Tasks</span>
      </div>

      <div className="overflow-auto flex-1" style={{ padding: 'var(--space-3)' }}>
        {tasks.length === 0 ? (
          <p style={{ textAlign: 'center', color: 'var(--text-tertiary)', fontSize: 'var(--font-size-xs)', paddingTop: 'var(--space-6)' }}>
            No agent tasks executed
          </p>
        ) : (
          tasks.map((task) => (
            <div
              key={task.id}
              style={{
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius-md)',
                padding: 'var(--space-3)',
                marginBottom: 'var(--space-2)',
                display: 'flex',
                flexDirection: 'column',
                gap: 'var(--space-1)'
              }}
            >
              <div className="flex items-center justify-between">
                <span className="badge badge-purple" style={{ textTransform: 'uppercase', fontSize: '10px' }}>
                  {task.mode}
                </span>
                <span style={{ fontSize: '10px', color: 'var(--text-tertiary)' }}>
                  {formatRelativeTime(task.timestamp)}
                </span>
              </div>
              <p style={{ fontSize: 'var(--font-size-xs)', fontWeight: '500', color: 'var(--text-primary)', marginTop: 'var(--space-1)' }}>
                {task.message}
              </p>
              <div className="flex items-center gap-2" style={{ marginTop: 'var(--space-2)' }}>
                {getStatusIcon(task.status)}
                <span style={{ fontSize: '10px', color: 'var(--text-secondary)', textTransform: 'capitalize' }}>
                  {task.status.replace('_', ' ')}
                </span>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
}
