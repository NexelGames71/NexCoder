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
    appendToLastMessage,
    setStreaming,
    clearChat,
    clearScanSteps,
    addScanStep,
    updateTaskStatus,
    addTaskStep,
    addTaskStepItem,
    addTaskChangedFile,
    addPendingDiff,
    setTaskFinalAnswer,
    setTaskPlan,
    setSkills,
    setActiveMode,
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
  // Track active task id so we can update it
  const activeTaskIdRef = useRef<string | null>(null);
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

  // â”€â”€ Wire bridge signals â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
  useEffect(() => {
    const bridge = getBridge();
    if (!bridge) return;

    const onChunk = (chunk: string) => {
      appendToLastMessage(chunk);
    };

    const onStatus = (statusJson: string) => {
      try {
        const { status, message, id, action, timeline_item } = JSON.parse(statusJson);
        const taskId = id || activeTaskIdRef.current;
        if (status === 'plan_update' && taskId) {
          setTaskPlan(taskId, JSON.parse(message));
          return;
        }
        if (status === 'scanning' && taskId) {
          addScanStep(taskId, message);
        }
        if (taskId) {
          if (timeline_item) {
            addTaskStepItem(taskId, timeline_item);
            return;
          }
          const taskStatus = status === 'error' ? 'error' : status === 'awaiting_approval' ? 'awaiting_approval' : 'running';
          const label = action ? `${action}: ${message}` : message;
          updateTaskStatus(taskId, taskStatus, label);
          addTaskStep(taskId, label, taskStatus);
        }
      } catch { /* ignore parse errors */ }
    };

    const onDiff = (diffJson: string) => {
      try {
        const diff = JSON.parse(diffJson);
        addPendingDiff(diff);
        const taskId = activeTaskIdRef.current;
        if (taskId && diff.file) {
          addTaskChangedFile(taskId, diff.file, diff.action || 'modify');
          const stepLabel = diff.operation === 'move'
            ? `Staged move: ${diff.source} -> ${diff.file}`
            : diff.action === 'mkdir'
              ? `Staged folder: ${diff.file}`
              : diff.action === 'rmdir'
                ? `Staged folder cleanup: ${diff.file}`
                : `Generated patch for ${diff.file}`;
          addTaskStep(taskId, stepLabel, 'awaiting_approval');
          updateTaskStatus(taskId, 'awaiting_approval', 'Waiting for approval');
        }
      } catch { /* ignore parse errors */ }
    };

    const onComplete = (resultJson: string) => {
      try {
        const result = JSON.parse(resultJson);
        setStreaming(false);
        if (result.session_id) {
          setActiveSessionId(result.session_id);
        }
        // Mark last message as no longer streaming
        useChatStore.setState((state) => {
          const updated = [...state.messages];
          if (updated.length > 0) {
            const last = updated[updated.length - 1];
            if (last.role === 'assistant') {
              updated[updated.length - 1] = { ...last, isStreaming: false };
            }
          }
          return { messages: updated };
        });
        if (activeTaskIdRef.current) {
          // Contract failures get a dedicated banner so the user sees that
          // the model failed to follow the agent contract, not just a
          // generic error. The last_response is included so they can
          // see what the model actually said.
          const isContractFailure = result.error_kind === 'agent_contract_failure';
          const errorLabel = isContractFailure
            ? `Agent contract failed after ${result.attempts ?? '?'} attempt(s). Last response: ${(result.last_response || '').slice(0, 200) || '(empty)'}`
            : (result.error || 'Done');
          // Attach the structured final_answer (and task_type) the
          // runner produced, when present, so the chat message can
          // render the FinalAnswerCard in addition to the streamed
          // text. Read-only task types (question / scan / review)
          // always include this object.
          const taskType = result.task_type || result.mode;
          const finalAnswer = result.final_answer || null;
          if (finalAnswer) {
            setTaskFinalAnswer(activeTaskIdRef.current, finalAnswer, taskType);
          }
          if (result.plan) {
            setTaskPlan(activeTaskIdRef.current, result.plan);
          }
          const hasPendingPatch = result.success && Number(result.patches || 0) > 0;
          if (hasPendingPatch) {
            updateTaskStatus(activeTaskIdRef.current, 'awaiting_approval', 'Waiting for approval');
            addTaskStep(activeTaskIdRef.current, 'Patch ready for review', 'awaiting_approval');
          } else {
            updateTaskStatus(activeTaskIdRef.current, result.success ? 'complete' : 'error', result.success ? 'Done' : errorLabel);
            addTaskStep(activeTaskIdRef.current, result.success ? 'Final report complete' : errorLabel, result.success ? 'complete' : 'error');
          }
          activeTaskIdRef.current = null;
        }
      } catch { setStreaming(false); }
    };

    // Qt signals are exposed with snake_case names on the bridge object
    if (bridge.agent_stream) bridge.agent_stream.connect(onChunk);
    if (bridge.agent_status) bridge.agent_status.connect(onStatus);
    if (bridge.agent_diff) bridge.agent_diff.connect(onDiff);
    if (bridge.agent_complete) bridge.agent_complete.connect(onComplete);

    return () => {
      if (bridge.agent_stream) bridge.agent_stream.disconnect(onChunk);
      if (bridge.agent_status) bridge.agent_status.disconnect(onStatus);
      if (bridge.agent_diff) bridge.agent_diff.disconnect(onDiff);
      if (bridge.agent_complete) bridge.agent_complete.disconnect(onComplete);
    };
  }, [appendToLastMessage, addScanStep, updateTaskStatus, addTaskStep, addTaskStepItem, addTaskChangedFile, addPendingDiff, setStreaming, setTaskFinalAnswer, setTaskPlan, setActiveSessionId]);


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
    activeTaskIdRef.current = null;
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
    };
    const contextJson = (editorContext.active_file || editorContext.selection)
      ? JSON.stringify(editorContext)
      : '';

    useAgentRunStore.getState().start(userMessage.id);
    try {
      const result = await agentRunV2(task, skillId, mode, contextJson);
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
