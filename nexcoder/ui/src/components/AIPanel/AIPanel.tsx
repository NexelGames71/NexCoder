import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Sparkles, Trash2, Code } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { selectActiveFile, useEditorStateStore } from '../../store/useEditorStateStore';
import { useProjectStore } from '../../store/useProjectStore';
import { useAgentStore } from '../../store/useAgentStore';
import ChatMessage from './ChatMessage';
import ChatInput from './ChatInput';
import SkillPicker from './SkillPicker';
import { agentRunV2, getBridge, fetchSkills, onAgentEvent } from '../../services/bridge';
import AgentRunPanel from './AgentRunPanel';
import { useAgentRunStore } from '../../store/useAgentRunStore';
import './AIPanel.css';

export default function AIPanel() {
  const {
    messages,
    activeMode,
    activeSkill,
    isStreaming,
    addMessage,
    setStreaming,
    clearChat,
    clearScanSteps,
    setSkills,
    setActiveMode,
    activeSessionId,
    setActiveSessionId,
  } = useChatStore();

  const activeFile = useEditorStateStore(selectActiveFile);
  const activeSelection = useEditorStateStore((s) => s.activeSelection);
  const { projectPath } = useProjectStore();
  const { settings } = useAgentStore();
  const [input, setInput] = useState('');
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [skillFilter, setSkillFilter] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const previousProjectRef = useRef<string | null>(projectPath);

  const openSkillPicker = useCallback(() => {
    setSkillFilter('');
    setShowSkillPicker(true);
  }, []);

  const closeSkillPicker = useCallback(() => {
    setShowSkillPicker(false);
    setSkillFilter('');
    // Clear the '/' from the input if picker was opened by slash
    setInput(prev => prev === '/' ? '' : prev);
  }, []);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  const isScanPrompt = (value: string) => {
    const lower = value.toLowerCase();
    return [
      'scan through',
      'scan the project',
      'scan codebase',
      'scan through the project',
      'create a codebase map',
    ].some((phrase) => lower.includes(phrase));
  };

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  useEffect(() => {
    setActiveMode(settings.defaultAgentMode);
  }, [settings.defaultAgentMode, setActiveMode]);

  useEffect(() => {
    const previousProject = previousProjectRef.current;
    if (previousProject && projectPath && previousProject !== projectPath) {
      clearChat();
    }
    previousProjectRef.current = projectPath;
  }, [projectPath, clearChat]);

  // ── Agent v2 event stream ──────────────────────────────────────────
  useEffect(() => {
    onAgentEvent((eventJson: string) => {
      try {
        useAgentRunStore.getState().handleEvent(JSON.parse(eventJson));
      } catch { /* ignore parse errors */ }
    });
  }, []);

  // â”€â”€ Load skill catalog from backend on mount â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((result) => {
        if (cancelled || !result) return;
        const flat = Object.values(result.skills_by_category).flat();
        if (flat.length > 0) {
          setSkills(flat);
        }
      })
      .catch(() => {/* leave the store empty; the picker will use its own fallback */});
    return () => {
      cancelled = true;
    };
  }, [setSkills]);

  // ── Run completion (agent_complete carries the session id) ────────
  useEffect(() => {
    const bridge = getBridge();
    if (!bridge) return;

    const onComplete = (resultJson: string) => {
      try {
        const result = JSON.parse(resultJson);
        setStreaming(false);
        if (result.session_id) {
          setActiveSessionId(result.session_id);
        }
      } catch { setStreaming(false); }
    };

    // Qt signals are exposed with snake_case names on the bridge object
    if (bridge.agent_complete) bridge.agent_complete.connect(onComplete);
    return () => {
      if (bridge.agent_complete) bridge.agent_complete.disconnect(onComplete);
    };
  }, [setStreaming, setActiveSessionId]);


  const handleSend = async () => {
    if (!input.trim()) return;

    clearScanSteps();

    // Every mode runs on the v2 agentic core: events render in
    // AgentRunPanel, not as a streamed chat message or task card.
    // "Scan the project..." phrasing routes to the scan profile.
    const mode = isScanPrompt(input) ? ('scan' as const) : activeMode;

    const userMessage = {
      id: Math.random().toString(),
      role: 'user' as const,
      content: input,
      timestamp: Date.now(),
      mode,
    };

    addMessage(userMessage);
    setInput('');
    setStreaming(true);
    setShowSkillPicker(false);

    // Slash command (/commit fix the bug) wins; otherwise the picker's
    // active skill preloads. Unknown /xyz passes through as plain text.
    const knownIds = new Set(useChatStore.getState().skills.map((s) => s.id));
    let task = userMessage.content;
    let skillId = activeSkill || '';
    const trimmed = task.trim();
    if (trimmed.startsWith('/')) {
      const [first, ...rest] = trimmed.slice(1).split(' ');
      if (knownIds.has(first)) {
        skillId = first;
        task = rest.join(' ').trim()
          || 'Follow the skill instructions on the current project state.';
      }
    }
    // Auto-attach what the user is looking at (active file + selection).
    const selection = useEditorStateStore.getState().activeSelection;
    const editorContext = {
      active_file: activeFile?.path || null,
      selection: selection && selection.text.trim()
        ? {
            path: selection.path,
            start_line: selection.startLine,
            end_line: selection.endLine,
            text: selection.text,
          }
        : null,
      // Chat history: the run appends to this session (or the bridge
      // creates one and returns its id).
      session_id: activeSessionId || null,
    };
    const contextJson = (editorContext.active_file || editorContext.selection
        || editorContext.session_id)
      ? JSON.stringify(editorContext)
      : '';

    useAgentRunStore.getState().start(userMessage.id);
    try {
      const result = await agentRunV2(task, skillId, mode, contextJson);
      if (result && result.session_id && result.session_id !== activeSessionId) {
        setActiveSessionId(result.session_id);
      }
      if (result && result.success === false) {
        // Surface bridge-level refusals (no project open, agent busy)
        // instead of leaving the panel silently empty.
        useAgentRunStore.getState().handleEvent({
          type: 'run_error',
          payload: { error: result.error || 'The agent could not start.' },
        });
        setStreaming(false);
      }
    } catch (e) {
      console.error(e);
      useAgentRunStore.getState().handleEvent({
        type: 'run_error', payload: { error: String(e) },
      });
      setStreaming(false);
    }
  };

  return (
    <div className="aipanel-container h-full">
      <div className="aipanel-header">
        <div className="aipanel-header-title">
          <Sparkles size={16} style={{ color: 'var(--accent-purple)' }} />
          <span>NexCoder AI</span>
        </div>
        <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Clear chat"
                onClick={() => { clearChat(); useAgentRunStore.getState().reset(); }}>
          <Trash2 size={14} />
        </button>
      </div>

      {activeFile && (
        <div style={{ padding: '0 var(--space-4) var(--space-2) var(--space-4)' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', background: 'var(--bg-deep)', padding: 'var(--space-2)', borderRadius: 'var(--radius-md)', border: '1px solid var(--border)' }}>
            <Code size={12} style={{ color: 'var(--accent-purple)' }} />
            <span className="truncate" style={{ fontSize: '10px', color: 'var(--text-secondary)' }}>
              {activeSelection && activeSelection.text.trim()
                ? `Attached: ${activeFile.name} · lines ${activeSelection.startLine}-${activeSelection.endLine} selected`
                : `Active File: ${activeFile.name}`}
            </span>
          </div>
        </div>
      )}

      <div className="chat-messages-list">
        {messages.length === 0 ? (
          <div className="chat-empty-state">
            <Sparkles size={32} style={{ color: 'var(--accent-purple)', opacity: 0.8 }} />
            <p className="chat-empty-title">How can I help with your code?</p>
            <p className="chat-empty-sub">Ask questions, run the agent, or scan your project</p>
            <div className="chat-quick-actions">
              <button type="button" className="chat-quick-action" onClick={() => { setInput('Scan the project and create a codebase map.'); }}>
                Scan codebase
              </button>
              <button type="button" className="chat-quick-action" onClick={() => { useChatStore.getState().setActiveMode('agent'); setInput('Review this project and suggest improvements'); }}>
                Run agent
              </button>
              <button type="button" className="chat-quick-action" onClick={() => setInput('What is this project about?')}>
                Explain project
              </button>
            </div>
          </div>
        ) : (
          messages.map((msg, index) => (
            <React.Fragment key={msg.id}>
              <ChatMessage
                message={msg}
                isLatest={index === messages.length - 1}
              />
              {/* Each agent run renders beneath the prompt that started it,
                  so earlier responses stay in the conversation history. */}
              <AgentRunPanel runId={msg.id} />
            </React.Fragment>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* SkillPicker overlay â€” anchored above the input */}
      <div style={{ position: 'relative' }}>
        {showSkillPicker && (
          <div style={{
            position: 'absolute',
            bottom: '100%',
            left: 0,
            right: 0,
            zIndex: 50,
          }}>
            <SkillPicker
              onClose={closeSkillPicker}
              filter={skillFilter}
            />
          </div>
        )}
        <ChatInput
          input={input}
          onChange={(val) => {
            setInput(val);
            // Keep filter in sync if picker is open
            if (showSkillPicker && val.startsWith('/')) {
              setSkillFilter(val.slice(1));
            }
          }}
          onSend={handleSend}
          onOpenSkillPicker={openSkillPicker}
          skillFilter={skillFilter}
        />
      </div>
    </div>
  );
}
