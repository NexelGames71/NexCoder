import React, { useEffect, useMemo, useState } from 'react';
import { Archive, ArchiveRestore, MessageSquarePlus, Trash2 } from 'lucide-react';
import { createSession, archiveSession, deleteSession, getBridge, listSessions, loadSession } from '../../services/bridge';
import { useChatStore } from '../../store/useChatStore';
import { useProjectStore } from '../../store/useProjectStore';
import { ChatMessage, SessionMetadata, StoredSessionMessage } from '../../types';

function formatDate(value: string) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toLocaleString([], { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' });
}

function toChatMessage(message: StoredSessionMessage, index: number): ChatMessage {
  const created = new Date(message.created_at).getTime();
  const role = message.role === 'user' || message.role === 'assistant' || message.role === 'system'
    ? message.role
    : 'assistant';
  return {
    id: `${message.created_at || Date.now()}-${index}`,
    role,
    content: message.content,
    timestamp: Number.isNaN(created) ? Date.now() : created,
  };
}

export default function ChatHistoryPanel() {
  const { projectPath } = useProjectStore();
  const {
    sessions,
    activeSessionId,
    activeMode,
    clearChat,
    removeSession,
    setActiveSessionId,
    setMessages,
    setSessions,
    upsertSession,
  } = useChatStore();
  const [query, setQuery] = useState('');
  const [showArchived, setShowArchived] = useState(false);
  const [loading, setLoading] = useState(false);

  const refresh = async () => {
    if (!projectPath) {
      setSessions([]);
      return;
    }
    setLoading(true);
    try {
      const res = await listSessions(projectPath);
      if (res?.success) setSessions(res.sessions || []);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    refresh();
  }, [projectPath]);

  // New runs create/update sessions on disk — refresh the list when a
  // run completes so the chat shows up without a manual Refresh.
  useEffect(() => {
    const signal = getBridge()?.agent_complete;
    if (typeof signal?.connect !== 'function') return;
    const onComplete = () => { refresh(); };
    signal.connect(onComplete);
    return () => signal.disconnect(onComplete);
  }, [projectPath]);

  const visibleSessions = useMemo(() => {
    const lower = query.trim().toLowerCase();
    return sessions.filter((session) => {
      if (!!session.archived !== showArchived) return false;
      if (!lower) return true;
      return [
        session.title,
        session.mode,
        session.status,
        session.session_id,
      ].some((value) => String(value || '').toLowerCase().includes(lower));
    });
  }, [query, sessions, showArchived]);

  const handleNewChat = async () => {
    clearChat();
    if (!projectPath) return;
    const res = await createSession(projectPath, 'New session', activeMode || 'ask');
    if (res?.success && res.metadata) {
      upsertSession(res.metadata);
      setActiveSessionId(res.metadata.session_id);
    }
  };

  const handleLoad = async (session: SessionMetadata) => {
    if (!projectPath) return;
    const res = await loadSession(projectPath, session.session_id);
    if (!res?.success) return;
    const messages = (res.messages || []).map((message: StoredSessionMessage, index: number) => toChatMessage(message, index));
    setMessages(messages);
    setActiveSessionId(session.session_id);
    if (res.metadata) upsertSession(res.metadata);
  };

  const handleArchive = async (session: SessionMetadata, archived: boolean) => {
    if (!projectPath) return;
    const res = await archiveSession(projectPath, session.session_id, archived);
    if (res?.success && res.metadata) upsertSession(res.metadata);
  };

  const handleDelete = async (session: SessionMetadata) => {
    if (!projectPath) return;
    const confirmed = window.confirm(`Delete chat "${session.title}"? This removes the saved session from disk.`);
    if (!confirmed) return;
    const res = await deleteSession(projectPath, session.session_id);
    if (res?.success) removeSession(session.session_id);
  };

  return (
    <div className="sidebar-panel">
      <div className="sidebar-header">
        <span>Chats</span>
        <button className="btn btn-ghost btn-icon" title="New chat" onClick={handleNewChat}>
          <MessageSquarePlus size={14} />
        </button>
      </div>
      <div className="file-tree-filter">
        <input
          className="input"
          placeholder="Jump in chats"
          value={query}
          onChange={(event) => setQuery(event.target.value)}
        />
      </div>
      <div className="chat-history-tabs">
        <button className={!showArchived ? 'active' : ''} onClick={() => setShowArchived(false)}>Active</button>
        <button className={showArchived ? 'active' : ''} onClick={() => setShowArchived(true)}>Archived</button>
        <button onClick={refresh}>{loading ? 'Loading' : 'Refresh'}</button>
      </div>
      <div className="chat-history-list">
        {visibleSessions.length === 0 && (
          <div className="chat-history-empty">
            {projectPath ? 'No chats found.' : 'Open a project to see chat history.'}
          </div>
        )}
        {visibleSessions.map((session) => (
          <div
            key={session.session_id}
            className={`chat-history-item ${activeSessionId === session.session_id ? 'active' : ''}`}
            onClick={() => handleLoad(session)}
          >
            <div className="chat-history-main">
              <div className="chat-history-title">{session.title || 'Untitled chat'}</div>
              <div className="chat-history-meta">
                <span>{session.mode}</span>
                <span>{session.message_count} messages</span>
                <span>{formatDate(session.updated_at)}</span>
              </div>
            </div>
            <div className="chat-history-actions" onClick={(event) => event.stopPropagation()}>
              <button
                className="btn btn-ghost btn-icon"
                title={session.archived ? 'Unarchive chat' : 'Archive chat'}
                onClick={() => handleArchive(session, !session.archived)}
              >
                {session.archived ? <ArchiveRestore size={13} /> : <Archive size={13} />}
              </button>
              <button
                className="btn btn-ghost btn-icon"
                title="Delete chat"
                onClick={() => handleDelete(session)}
              >
                <Trash2 size={13} />
              </button>
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
