import React, { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { Sparkles, Trash2, Code, ListChecks, ChevronDown, ChevronUp, MessageSquareText, X, FileArchive } from 'lucide-react';
import { QueuedPrompt, useChatStore } from '../../store/useChatStore';
import { selectActiveFile, useEditorStateStore } from '../../store/useEditorStateStore';
import { useProjectStore } from '../../store/useProjectStore';
import { useAgentStore } from '../../store/useAgentStore';
import {
  countDiagnostics,
  flattenDiagnostics,
  useDiagnosticsStore,
} from '../../store/useDiagnosticsStore';
import ChatMessage from './ChatMessage';
import ChatInput from './ChatInput';
import SkillPicker from './SkillPicker';
import {
  agentCancelV2,
  agentRewindToPrompt,
  agentRunV2,
  agentSteerV2,
  getBridge,
  fetchSkills,
  onAgentEvent,
  approvePlanAndExecute,
} from '../../services/bridge';
import AgentRunPanel from './AgentRunPanel';
import ChatHistoryPanel from '../Sidebar/ChatHistoryPanel';
import ArtifactsPanel from './ArtifactsPanel';
import { useAgentRunStore } from '../../store/useAgentRunStore';
import { useArtifactStore } from '../../store/useArtifactStore';
import { usePlanStore } from '../../store/usePlanStore';
import { ImageAttachment, PromptAttachment } from '../../types';
import { createRunArtifacts } from '../../utils/artifactGeneration';
import './AIPanel.css';

export default function AIPanel() {
  const {
    messages,
    activeMode,
    activeSkill,
    isStreaming,
    setStreaming,
    clearChat,
    setSkills,
    setActiveMode,
    setActiveSessionId,
    enqueuePrompt,
    removeQueuedPrompt,
    rewindMessagesFrom,
  } = useChatStore();

  const activeFile = useEditorStateStore(selectActiveFile);
  const activeSelection = useEditorStateStore((s) => s.activeSelection);
  const diagnosticsByPath = useDiagnosticsStore((s) => s.byPath);
  const diagnosticCounts = useMemo(
    () => countDiagnostics(diagnosticsByPath), [diagnosticsByPath]);
  // Live plan for the pinned card. The todos array reference only
  // changes on todo_updated events, so these subscriptions stay cheap.
  const activeTodos = useAgentRunStore(
    (s) => (s.activeRunId ? s.runs[s.activeRunId]?.todos : undefined));
  const activeRunLive = useAgentRunStore(
    (s) => (s.activeRunId ? !!s.runs[s.activeRunId]?.runActive : false));
  const [planCollapsed, setPlanCollapsed] = useState(false);
  const projectPath = useProjectStore((s) => s.projectPath);
  const { settings } = useAgentStore();
  const [input, setInput] = useState('');
  const [attachments, setAttachments] = useState<PromptAttachment[]>([]);
  const [showSkillPicker, setShowSkillPicker] = useState(false);
  const [showChatHistory, setShowChatHistory] = useState(false);
  const [showArtifacts, setShowArtifacts] = useState(false);
  const [skillFilter, setSkillFilter] = useState('');
  const [isStopping, setIsStopping] = useState(false);
  const [editingMessageId, setEditingMessageId] = useState<string | null>(null);
  const [editingAttachmentCount, setEditingAttachmentCount] = useState(0);
  const [rewindError, setRewindError] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const previousProjectRef = useRef<string | null>(projectPath);
  const stoppedByUserRef = useRef(false);
  const stopRequestInFlightRef = useRef(false);
  const queueTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const launchPromptRef = useRef<(prompt: QueuedPrompt) => Promise<void>>(
    async () => undefined,
  );
  const artifactRunKeysRef = useRef<Set<string>>(new Set());

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

  const defaultAgentMode = useAgentStore((s) => s.settings.defaultAgentMode);

  useEffect(() => {
    scrollToBottom();
  }, [messages, isStreaming]);

  useEffect(() => {
    useChatStore.getState().setActiveMode(defaultAgentMode);
  }, [defaultAgentMode]);

  useEffect(() => {
    const previousProject = previousProjectRef.current;
    if (previousProject && projectPath && previousProject !== projectPath) {
      useChatStore.getState().clearChat();
      usePlanStore.getState().reset();
      setAttachments([]);
      setEditingMessageId(null);
      setEditingAttachmentCount(0);
      setRewindError('');
    }
    previousProjectRef.current = projectPath;
    void useArtifactStore.getState().hydrateProject(projectPath);
  }, [projectPath]);

  useEffect(() => {
    if (!projectPath) return;
    const chat = useChatStore.getState();
    const prompts = new Map(chat.messages
      .filter((message) => message.role === 'user')
      .map((message) => [message.id, message.content]));
    for (const [runId, run] of Object.entries(useAgentRunStore.getState().runs)) {
      const key = `${projectPath}:${runId}:${run.status}:${run.finalText.length}:${run.mutatedFiles.join('|')}`;
      if (run.runActive || artifactRunKeysRef.current.has(key)) continue;
      artifactRunKeysRef.current.add(key);
      const artifacts = createRunArtifacts({
        runId,
        run,
        projectPath,
        prompt: prompts.get(runId) || '',
      });
      for (const artifact of artifacts) {
        useArtifactStore.getState().upsertArtifact(artifact);
      }
    }
  }, [projectPath, messages, activeRunLive]);

  // ── Agent v2 event stream ──────────────────────────────────────────
  useEffect(() => {
    onAgentEvent((eventJson: string) => {
      try {
        useAgentRunStore.getState().handleEvent(JSON.parse(eventJson));
      } catch { /* ignore parse errors */ }
    });
  }, []);

  // ── Load skill catalog from backend on mount ───────────────────────
  useEffect(() => {
    let cancelled = false;
    fetchSkills()
      .then((result) => {
        if (cancelled || !result) return;
        const flat = Object.values(result.skills_by_category).flat();
        if (flat.length > 0) {
          useChatStore.getState().setSkills(flat);
        }
      })
      .catch(() => {/* leave the store empty; the picker will use its own fallback */});
    return () => {
      cancelled = true;
    };
  }, []);

  const launchPrompt = useCallback(async (prompt: QueuedPrompt) => {
    const chat = useChatStore.getState();
    const rawTask = prompt.content.trim();
    const isPlanCommand = /^\/plan(?:\s|$)/i.test(rawTask);
    const effectiveMode = isPlanCommand ? 'plan' : prompt.mode;
    chat.clearScanSteps();
    chat.addMessage({
      id: prompt.id,
      role: 'user',
      content: prompt.content,
      timestamp: prompt.createdAt,
      mode: effectiveMode,
      attachments: prompt.attachments,
      clientPromptId: prompt.id,
    });
    chat.setStreaming(true);
    setIsStopping(false);
    setShowSkillPicker(false);

    // Slash command (/commit fix the bug) wins; otherwise use the skill
    // captured when the prompt was queued.
    const knownIds = new Set(chat.skills.map((skill) => skill.id));
    let task = isPlanCommand
      ? rawTask.replace(/^\/plan(?:\s+)?/i, '').trim()
        || 'Create an implementation plan for the current project and wait for approval.'
      : prompt.content;
    let skillId = prompt.skillId || '';
    const trimmed = task.trim();
    if (trimmed.startsWith('/')) {
      const [first, ...rest] = trimmed.slice(1).split(' ');
      if (knownIds.has(first)) {
        skillId = first;
        task = rest.join(' ').trim()
          || 'Follow the skill instructions on the current project state.';
      }
    }

    // Capture editor/session context when the queued prompt actually starts,
    // so it follows what the user is looking at now rather than stale state.
    const editorState = useEditorStateStore.getState();
    const selectedFile = selectActiveFile(editorState);
    const currentFile = selectedFile && (!selectedFile.kind || selectedFile.kind === 'file') ? selectedFile : null;
    const selection = editorState.activeSelection;
    const diagnosticEntries = flattenDiagnostics(diagnosticsByPath, projectPath).slice(0, 40);
    const diagnosticCounts = countDiagnostics(diagnosticsByPath);
    const imageAttachments = prompt.attachments.filter((attachment): attachment is ImageAttachment =>
      attachment.kind !== 'text');
    const textAttachments = prompt.attachments.filter((attachment) =>
      attachment.kind === 'text');
    const editorContext = {
      active_file: currentFile?.path || null,
      selection: selection && selection.text.trim()
        ? {
            path: selection.path,
            start_line: selection.startLine,
            end_line: selection.endLine,
            text: selection.text,
          }
        : null,
      session_id: chat.activeSessionId || null,
      client_prompt_id: prompt.id,
      diagnostics: diagnosticEntries.map(({ path, shortPath, diagnostic }) => ({
        path,
        relative_path: shortPath,
        line: (diagnostic.range?.start?.line ?? 0) + 1,
        column: (diagnostic.range?.start?.character ?? 0) + 1,
        severity: diagnostic.severity ?? 3,
        source: diagnostic.source || null,
        code: diagnostic.code ?? null,
        message: diagnostic.message,
      })),
      diagnostic_counts: diagnosticCounts,
      text_attachments: textAttachments.map((attachment) => ({
        id: attachment.id,
        name: attachment.name,
        mime_type: attachment.mimeType,
        size: attachment.size,
        path: attachment.path,
      })),
      attachments: imageAttachments.map((attachment) => ({
        id: attachment.id,
        name: attachment.name,
        mime_type: attachment.mimeType,
        size: attachment.size,
        data_url: attachment.dataUrl,
      })),
    };
    const contextJson = (editorContext.active_file || editorContext.selection
        || editorContext.session_id || editorContext.attachments.length
        || editorContext.text_attachments.length
        || editorContext.diagnostics.length)
      ? JSON.stringify(editorContext)
      : '';

    useAgentRunStore.getState().start(prompt.id);
    try {
      const result = await agentRunV2(task, skillId, effectiveMode, contextJson);
      if (result?.session_id) {
        useChatStore.getState().setActiveSessionId(result.session_id);
      }
      if (result?.success === false) {
        useAgentRunStore.getState().handleEvent({
          type: 'run_error',
          payload: { error: result.error || 'The agent could not start.' },
        });
        useChatStore.getState().setStreaming(false);
      }
    } catch (error) {
      console.error(error);
      useAgentRunStore.getState().handleEvent({
        type: 'run_error', payload: { error: String(error) },
      });
      useChatStore.getState().setStreaming(false);
    }
  }, [diagnosticsByPath, projectPath]);

  useEffect(() => {
    launchPromptRef.current = launchPrompt;
  }, [launchPrompt]);

  useEffect(() => {
    const handleLoadComposer = (event: Event) => {
      const detail = (event as CustomEvent<{
        content?: string;
        mode?: string;
        skillId?: string | null;
        send?: boolean;
      }>).detail || {};
      const content = String(detail.content || '').trim();
      if (!content) return;
      const mode = detail.mode || 'agent';
      setActiveMode(mode);
      setEditingMessageId(null);
      setEditingAttachmentCount(0);
      setRewindError('');
      setAttachments([]);
      setShowSkillPicker(false);

      if (detail.send) {
        const prompt: QueuedPrompt = {
          id: `prompt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
          content,
          mode,
          skillId: detail.skillId ?? useChatStore.getState().activeSkill,
          createdAt: Date.now(),
          attachments: [],
        };
        setInput('');
        if (useChatStore.getState().isStreaming) {
          useChatStore.getState().enqueuePrompt(prompt);
        } else {
          void launchPromptRef.current(prompt);
        }
        return;
      }

      setInput(content);
      window.setTimeout(() => document.getElementById('ai-chat-input')?.focus(), 0);
    };
    window.addEventListener('nexcoder:load-chat-composer', handleLoadComposer);
    return () => window.removeEventListener('nexcoder:load-chat-composer', handleLoadComposer);
  }, [setActiveMode]);

  useEffect(() => {
    const handleToggleChats = () => {
      window.nexcoder?.showAIPanel?.();
      setShowChatHistory((value) => !value);
      setShowArtifacts(false);
    };
    window.addEventListener('nexcoder:toggle-agent-chats', handleToggleChats);
    return () => window.removeEventListener('nexcoder:toggle-agent-chats', handleToggleChats);
  }, []);

  useEffect(() => {
    const handleToggleArtifacts = () => {
      window.nexcoder?.showAIPanel?.();
      setShowArtifacts((value) => !value);
      setShowChatHistory(false);
    };
    window.addEventListener('nexcoder:toggle-agent-artifacts', handleToggleArtifacts);
    return () => window.removeEventListener('nexcoder:toggle-agent-artifacts', handleToggleArtifacts);
  }, []);

  useEffect(() => {
    const handleFocusRun = (event: Event) => {
      const runId = String((event as CustomEvent<{ runId?: string }>).detail?.runId || '');
      if (!runId) return;
      const target = Array.from(document.querySelectorAll('[data-agent-run-id]'))
        .find((node) => node instanceof HTMLElement && node.dataset.agentRunId === runId);
      if (target instanceof HTMLElement) {
        target.scrollIntoView({ behavior: 'smooth', block: 'center' });
        target.classList.add('agent-run-focus-pulse');
        window.setTimeout(() => target.classList.remove('agent-run-focus-pulse'), 1300);
      }
    };
    window.addEventListener('nexcoder:focus-agent-run', handleFocusRun);
    return () => window.removeEventListener('nexcoder:focus-agent-run', handleFocusRun);
  }, []);

  // Run completion owns queue advancement. A user-initiated stop pauses the
  // queue, otherwise the next follow-up starts after the worker fully exits.
  useEffect(() => {
    const bridge = getBridge();
    if (!bridge) return;

    const onComplete = (resultJson: string) => {
      try {
        const result = JSON.parse(resultJson);
        if (result.session_id) {
          setActiveSessionId(result.session_id);
        }
      } catch { /* completion still resets the local run state */ }

      setStreaming(false);
      setIsStopping(false);
      stopRequestInFlightRef.current = false;
      const pauseQueue = stoppedByUserRef.current;
      stoppedByUserRef.current = false;
      if (pauseQueue) return;

      queueTimerRef.current = setTimeout(() => {
        const chat = useChatStore.getState();
        if (chat.isStreaming) return;
        const next = chat.dequeuePrompt();
        if (next) void launchPromptRef.current(next);
      }, 100);
    };

    const signal = bridge.agent_complete;
    if (typeof signal?.connect !== 'function') return;
    signal.connect(onComplete);
    return () => {
      signal.disconnect(onComplete);
      if (queueTimerRef.current) clearTimeout(queueTimerRef.current);
    };
  }, [setStreaming, setActiveSessionId]);

  const handleSend = async () => {
    const typedContent = input.trim();
    if (!typedContent && !attachments.length) return;
    const chat = useChatStore.getState();
    const editingMessage = editingMessageId
      ? chat.messages.find((message) => message.id === editingMessageId)
      : undefined;
    if (editingMessage) {
      if (chat.isStreaming) {
        setRewindError('Stop the active agent before editing an earlier prompt.');
        return;
      }
      if (attachments.length < editingAttachmentCount) {
        setRewindError('Reattach the original image before resending this prompt.');
        return;
      }
      if (!chat.activeSessionId) {
        setRewindError('This chat has no saved session checkpoint to restore.');
        return;
      }
      const index = chat.messages.findIndex((message) => message.id === editingMessage.id);
      if (index < 0) {
        setRewindError('The prompt is no longer available in this chat.');
        return;
      }
      setRewindError('');
      const userOrdinal = chat.messages
        .slice(0, index + 1)
        .filter((message) => message.role === 'user').length - 1;
      const result = await agentRewindToPrompt(chat.activeSessionId, {
        client_prompt_id: editingMessage.clientPromptId || editingMessage.id,
        content: editingMessage.content,
        user_ordinal: userOrdinal,
      });
      if (result?.success === false) {
        setRewindError(result.error || 'Could not restore the project to this prompt.');
        return;
      }
      const removedRunIds = rewindMessagesFrom(editingMessage.id);
      useAgentRunStore.getState().removeRuns(removedRunIds);
      setEditingMessageId(null);
      setEditingAttachmentCount(0);
    }
    setRewindError('');
    const hasImageAttachments = attachments.some((attachment) => attachment.kind !== 'text');
    const hasTextAttachments = attachments.some((attachment) => attachment.kind === 'text');
    const content = typedContent || (
      hasTextAttachments && !hasImageAttachments
        ? 'Use the attached text file as context for this task.'
        : 'Analyze the attached image, diagnose the visible problem, and fix it in this project.'
    );
    const activePlan = usePlanStore.getState().activePlan;
    const approvalMatch = content.trim().match(
      /^(?:approve(?:\s+revision\s+(\d+))?|proceed|approve\s+and\s+(?:execute|proceed)|start\s+implementation)[.!]?$/i,
    );
    const explicitApproval = Boolean(approvalMatch);
    if (!editingMessage && !attachments.length && explicitApproval
        && activePlan?.status === 'awaiting_approval') {
      const requestedRevision = approvalMatch?.[1]
        ? Number(approvalMatch[1]) : activePlan.revision;
      if (requestedRevision !== activePlan.revision) {
        usePlanStore.getState().setError(
          `Revision ${requestedRevision} is stale. Review and approve revision ${activePlan.revision}.`,
        );
        return;
      }
      const approvalMessageId = `prompt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`;
      chat.addMessage({
        id: approvalMessageId,
        role: 'user',
        content,
        timestamp: Date.now(),
        mode: 'plan',
        clientPromptId: approvalMessageId,
      });
      setInput('');
      usePlanStore.getState().setBusy(true);
      const result = await approvePlanAndExecute(activePlan.id, activePlan.revision);
      if (!result?.success) {
        usePlanStore.getState().setError(result?.error || 'Could not approve the plan.');
        return;
      }
      usePlanStore.getState().setPlan(result.plan);
      useChatStore.getState().setStreaming(true);
      return;
    }
    const mode = isScanPrompt(content) ? ('scan' as const) : activeMode;
    const prompt: QueuedPrompt = {
      id: `prompt_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      content,
      mode,
      skillId: activeSkill,
      createdAt: Date.now(),
      attachments,
    };
    setInput('');
    setAttachments([]);
    setShowSkillPicker(false);
    if (useChatStore.getState().isStreaming) {
      enqueuePrompt(prompt);
      return;
    }
    await launchPrompt(prompt);
  };

  const handleStop = async () => {
    if (stopRequestInFlightRef.current
        || !useChatStore.getState().isStreaming) return;
    stopRequestInFlightRef.current = true;
    stoppedByUserRef.current = true;
    setIsStopping(true);
    try {
      const result = await agentCancelV2();
      if (result?.success === false) {
        stopRequestInFlightRef.current = false;
        stoppedByUserRef.current = false;
        setIsStopping(false);
      }
    } catch (error) {
      console.error(error);
      stopRequestInFlightRef.current = false;
      stoppedByUserRef.current = false;
      setIsStopping(false);
    }
  };

  const handleUseQueuedPrompt = async (prompt: QueuedPrompt) => {
    if (!useChatStore.getState().isStreaming) {
      removeQueuedPrompt(prompt.id);
      void launchPrompt(prompt);
      return;
    }
    try {
      const imageAttachments = prompt.attachments.filter((attachment): attachment is ImageAttachment =>
        attachment.kind !== 'text');
      const textAttachments = prompt.attachments.filter((attachment) => attachment.kind === 'text');
      const steerText = textAttachments.length
        ? `${prompt.content}\n\nAttached text file(s): ${textAttachments.map((item) => item.path).join(', ')}`
        : prompt.content;
      const result = await agentSteerV2(steerText, imageAttachments.map((attachment) => ({
        id: attachment.id,
        name: attachment.name,
        mime_type: attachment.mimeType,
        size: attachment.size,
        data_url: attachment.dataUrl,
      })), prompt.id);
      if (result?.success) {
        const activeRunId = useAgentRunStore.getState().activeRunId;
        if (activeRunId) {
          useAgentRunStore.getState().addSteeringPrompt(activeRunId, {
            id: prompt.id,
            text: prompt.content,
            attachments: prompt.attachments,
          });
        }
        removeQueuedPrompt(prompt.id);
      }
    } catch (error) {
      console.error(error);
    }
  };

  const handleEditQueuedPrompt = (prompt: QueuedPrompt) => {
    removeQueuedPrompt(prompt.id);
    setEditingMessageId(null);
    setEditingAttachmentCount(0);
    setRewindError('');
    setInput(prompt.content);
    setAttachments(prompt.attachments);
    setTimeout(() => document.getElementById('ai-chat-input')?.focus(), 0);
  };

  const handleEditMessage = (message: typeof messages[number]) => {
    if (useChatStore.getState().isStreaming || message.isSteering) return;
    const messageAttachments = message.attachments || [];
    const availableAttachments = messageAttachments.filter((attachment) =>
      attachment.kind === 'text' || attachment.dataUrl);
    setEditingMessageId(message.id);
    setEditingAttachmentCount(messageAttachments.length);
    setInput(message.content);
    setAttachments(availableAttachments);
    setRewindError(messageAttachments.length > availableAttachments.length
      ? 'This restored prompt does not retain every image. Reattach missing images before resending.'
      : '');
    setTimeout(() => document.getElementById('ai-chat-input')?.focus(), 0);
  };

  const handleCancelEdit = () => {
    setEditingMessageId(null);
    setEditingAttachmentCount(0);
    setRewindError('');
    setInput('');
    setAttachments([]);
  };

  return (
    <div className="aipanel-container h-full">
      <div className="aipanel-header">
        <div className="aipanel-header-title">
          <Sparkles size={16} style={{ color: 'var(--accent-purple)' }} />
          <span>NexCoder AI</span>
        </div>
        <div className="aipanel-header-actions">
          <button
            className={`btn btn-ghost btn-icon tooltip ${showChatHistory ? 'active' : ''}`}
            data-tooltip={showChatHistory ? 'Hide agent chats' : 'Show agent chats'}
            onClick={() => {
              setShowChatHistory((value) => !value);
              setShowArtifacts(false);
            }}
          >
            {showChatHistory ? <X size={14} /> : <MessageSquareText size={14} />}
          </button>
          <button
            className={`btn btn-ghost btn-icon tooltip ${showArtifacts ? 'active' : ''}`}
            data-tooltip={showArtifacts ? 'Hide artifacts' : 'Show artifacts'}
            onClick={() => {
              setShowArtifacts((value) => !value);
              setShowChatHistory(false);
            }}
          >
            {showArtifacts ? <X size={14} /> : <FileArchive size={14} />}
          </button>
          <button className="btn btn-ghost btn-icon tooltip" data-tooltip="Clear chat"
                  onClick={() => {
                    clearChat();
                    setAttachments([]);
                    setInput('');
                    setEditingMessageId(null);
                    setEditingAttachmentCount(0);
                    setRewindError('');
                    useAgentRunStore.getState().reset();
                  }}>
            <Trash2 size={14} />
          </button>
        </div>
      </div>

      {showChatHistory && (
        <div className="ai-chat-history-dock">
          <ChatHistoryPanel />
        </div>
      )}

      {showArtifacts && (
        <div className="ai-artifacts-dock">
          <ArtifactsPanel />
        </div>
      )}

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

      {diagnosticCounts.total > 0 && (
        <div style={{ padding: '0 var(--space-4) var(--space-2) var(--space-4)' }}>
          <div className="ai-problems-context">
            <ListChecks size={12} />
            <span>
              Problems: {diagnosticCounts.total}
              {diagnosticCounts.errors > 0
                ? ` · ${diagnosticCounts.errors} errors`
                : ''}
              {diagnosticCounts.warnings > 0
                ? ` · ${diagnosticCounts.warnings} warnings`
                : ''}
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
            <div key={msg.id} data-agent-run-id={msg.id} className="agent-run-anchor">
              <ChatMessage
                message={msg}
                isLatest={index === messages.length - 1}
                onEdit={!isStreaming ? handleEditMessage : undefined}
              />
              {/* Each agent run renders beneath the prompt that started it,
                  so earlier responses stay in the conversation history. */}
              <AgentRunPanel runId={msg.id} />
            </div>
          ))
        )}
        <div ref={messagesEndRef} />
      </div>

      {/* Live plan — pinned above the composer while the run is active,
          updating in place as the agent completes steps. */}
      {activeRunLive && (activeTodos?.length ?? 0) > 0 && (
        <div className="agent-plan-pinned">
          <div className="agent-plan-header" onClick={() => setPlanCollapsed((c) => !c)}>
            <ListChecks size={12} />
            <span>
              Plan · {(activeTodos ?? []).filter((t) => t.status === 'completed').length}
              /{(activeTodos ?? []).length} done
            </span>
            {planCollapsed ? <ChevronUp size={12} /> : <ChevronDown size={12} />}
          </div>
          {!planCollapsed && (
            <div className="agent-plan-body">
              {(activeTodos ?? []).map((todo) => (
                <div key={todo.id} className={`agent-run-todo agent-run-todo-${todo.status}`}>
                  <span className="todo-mark">
                    {todo.status === 'completed' ? '✓' : todo.status === 'in_progress' ? '›' : '○'}
                  </span>
                  <span>{todo.content}</span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}

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
          attachments={attachments}
          onChange={(val) => {
            setInput(val);
            // Keep filter in sync if picker is open
            if (showSkillPicker && val.startsWith('/')) {
              setSkillFilter(val.slice(1));
            }
          }}
          onSend={handleSend}
          onAttachmentsChange={setAttachments}
          onOpenSkillPicker={openSkillPicker}
          onStop={handleStop}
          onUseQueuedPrompt={handleUseQueuedPrompt}
          onEditQueuedPrompt={handleEditQueuedPrompt}
          onDeleteQueuedPrompt={removeQueuedPrompt}
          isStopping={isStopping}
          skillFilter={skillFilter}
          editingPrompt={Boolean(editingMessageId)}
          onCancelEdit={handleCancelEdit}
          rewindError={rewindError}
        />
      </div>
    </div>
  );
}
