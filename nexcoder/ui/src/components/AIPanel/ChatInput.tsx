import React, { KeyboardEvent, ChangeEvent, ClipboardEvent, useEffect, useMemo, useRef, useState } from 'react';
import { Send, Plus, ShieldCheck, Eye, ListPlus, Pencil, Trash2, CornerUpRight, ImagePlus, X, ImageIcon, FileText, Copy, Check } from 'lucide-react';
import { QueuedPrompt, useChatStore } from '../../store/useChatStore';
import { ImageAttachment, PromptAttachment, TextAttachment } from '../../types';
import { useAgentStore } from '../../store/useAgentStore';
import { useAgentRunStore } from '../../store/useAgentRunStore';
import { useProjectStore } from '../../store/useProjectStore';
import { writeFile } from '../../services/bridge';
import ActiveSkillChip from './ActiveSkillChip';
import ModelSelector, { modelSupportsVision } from '../TopBar/ModelSelector';
import ImageAttachmentCard from './ImageAttachmentCard';
import { FileNode } from '../../types';

interface ChatInputProps {
  input: string;
  attachments: PromptAttachment[];
  onChange: (val: string) => void;
  onAttachmentsChange: (attachments: PromptAttachment[]) => void;
  onSend: () => void;
  onOpenSkillPicker: () => void;
  onStop: () => void;
  onUseQueuedPrompt: (prompt: QueuedPrompt) => void;
  onEditQueuedPrompt: (prompt: QueuedPrompt) => void;
  onDeleteQueuedPrompt: (id: string) => void;
  isStopping: boolean;
  skillFilter?: string;
  editingPrompt?: boolean;
  onCancelEdit?: () => void;
  rewindError?: string;
}

export default function ChatInput({
  input,
  attachments,
  onChange,
  onAttachmentsChange,
  onSend,
  onOpenSkillPicker,
  onStop,
  onUseQueuedPrompt,
  onEditQueuedPrompt,
  onDeleteQueuedPrompt,
  isStopping,
  skillFilter: _skillFilter,
  editingPrompt = false,
  onCancelEdit,
  rewindError,
}: ChatInputProps) {
  const { isStreaming, activeMode, queuedPrompts } = useChatStore();
  const { settings, updateSetting } = useAgentStore();
  const { projectPath, fileTree } = useProjectStore();
  const contextUsage = useAgentRunStore((state) => state.lastContextUsage);
  const selectedVisionSupport = modelSupportsVision(settings.aiModel);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [attachmentError, setAttachmentError] = useState('');
  const [copiedQueuedPromptId, setCopiedQueuedPromptId] = useState<string | null>(null);
  const [fileMention, setFileMention] = useState<{
    start: number;
    end: number;
    query: string;
  } | null>(null);
  const [selectedMentionIndex, setSelectedMentionIndex] = useState(0);
  const imageAttachments = attachments.filter((attachment): attachment is ImageAttachment =>
    attachment.kind !== 'text');
  const textAttachments = attachments.filter((attachment): attachment is TextAttachment =>
    attachment.kind === 'text');

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;

    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 132)}px`;
  }, [input, attachments.length, attachmentError, rewindError, editingPrompt]);

  const projectFiles = useMemo(() => {
    const normalizedRoot = projectPath?.replace(/\\/g, '/').replace(/\/$/, '') || '';
    const rows: Array<{ name: string; path: string; relativePath: string; size: number }> = [];
    const walk = (nodes: FileNode[]) => {
      for (const node of nodes) {
        if (node.type === 'directory') {
          walk(node.children || []);
          continue;
        }
        const normalizedPath = node.path.replace(/\\/g, '/');
        const relativePath = normalizedRoot && normalizedPath.startsWith(`${normalizedRoot}/`)
          ? normalizedPath.slice(normalizedRoot.length + 1)
          : normalizedPath;
        rows.push({
          name: node.name,
          path: node.path,
          relativePath,
          size: node.size || 0,
        });
      }
    };
    walk(fileTree);
    return rows.sort((a, b) => a.relativePath.localeCompare(b.relativePath));
  }, [fileTree, projectPath]);

  const mentionMatches = useMemo(() => {
    if (!fileMention) return [];
    const query = fileMention.query.trim().toLowerCase().replace(/\\/g, '/');
    const scored = projectFiles
      .map((file) => {
        const path = file.relativePath.toLowerCase();
        const name = file.name.toLowerCase();
        if (!query) return { file, score: 3 };
        if (name === query || path === query) return { file, score: 0 };
        if (name.startsWith(query)) return { file, score: 1 };
        if (path.startsWith(query)) return { file, score: 2 };
        if (name.includes(query)) return { file, score: 4 };
        if (path.includes(query)) return { file, score: 5 };
        return null;
      })
      .filter(Boolean) as Array<{ file: { name: string; path: string; relativePath: string; size: number }; score: number }>;
    return scored
      .sort((a, b) => a.score - b.score || a.file.relativePath.localeCompare(b.file.relativePath))
      .slice(0, 10)
      .map((item) => item.file);
  }, [fileMention, projectFiles]);

  useEffect(() => {
    setSelectedMentionIndex(0);
  }, [fileMention?.query]);

  const detectFileMention = (value: string, caret: number | null | undefined) => {
    if (caret == null) {
      setFileMention(null);
      return;
    }
    const beforeCaret = value.slice(0, caret);
    const match = /(?:^|\s)@([^\s@]*)$/.exec(beforeCaret);
    if (!match) {
      setFileMention(null);
      return;
    }
    const query = match[1] || '';
    const atIndex = beforeCaret.length - query.length - 1;
    setFileMention({ start: atIndex, end: caret, query });
  };

  const copyQueuedPrompt = async (prompt: QueuedPrompt) => {
    try {
      await navigator.clipboard?.writeText(prompt.content);
      setCopiedQueuedPromptId(prompt.id);
      window.setTimeout(() => setCopiedQueuedPromptId(null), 1200);
    } catch (error) {
      console.error('Could not copy queued prompt', error);
    }
  };

  const addImageFiles = async (files: File[]) => {
    const allowed = new Set(['image/png', 'image/jpeg', 'image/webp', 'image/gif']);
    const available = Math.max(0, 4 - imageAttachments.length);
    if (files.length > available) {
      setAttachmentError('You can attach up to 4 images per prompt.');
      return;
    }
    const next: ImageAttachment[] = [];
    for (const file of files) {
      if (!allowed.has(file.type)) {
        setAttachmentError('Use a PNG, JPEG, WebP, or GIF image.');
        return;
      }
      if (file.size > 5 * 1024 * 1024) {
        setAttachmentError(`${file.name} is larger than 5 MB.`);
        return;
      }
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error(`Could not read ${file.name}`));
        reader.readAsDataURL(file);
      });
      next.push({
        kind: 'image',
        id: `image_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
        name: file.name,
        mimeType: file.type,
        size: file.size,
        dataUrl,
      });
    }
    const total = [...imageAttachments, ...next].reduce((sum, item) => sum + item.size, 0);
    if (total > 10 * 1024 * 1024) {
      setAttachmentError('Attached images must total 10 MB or less.');
      return;
    }
    setAttachmentError('');
    onAttachmentsChange([...attachments, ...next]);
  };

  const savePastedTextAsFile = async (text: string) => {
    if (!projectPath) {
      setAttachmentError('Open a project before attaching large pasted text as a file.');
      return false;
    }
    const stamp = new Date().toISOString().replace(/[:.]/g, '-');
    const name = `pasted-text-${stamp}.txt`;
    const path = `.nexcoder/pasted-prompts/${name}`;
    const result = await writeFile(path, text);
    if (!result?.success) {
      setAttachmentError(result?.error || 'Could not save pasted text as a file.');
      return false;
    }
    const attachment: TextAttachment = {
      kind: 'text',
      id: `text_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      name,
      mimeType: 'text/plain',
      size: new Blob([text]).size,
      path,
    };
    setAttachmentError('');
    onAttachmentsChange([...attachments, attachment]);
    return true;
  };

  const addTextFileReference = (
    file: { name: string; path: string; relativePath: string; size: number },
  ) => {
    const alreadyAttached = attachments.some((attachment) =>
      attachment.kind === 'text' && attachment.path === file.path);
    const nextAttachment: TextAttachment = {
      kind: 'text',
      id: `text_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
      name: file.name,
      mimeType: 'text/plain',
      size: file.size,
      path: file.path,
    };
    if (!alreadyAttached) {
      onAttachmentsChange([...attachments, nextAttachment]);
    }
    setAttachmentError('');
  };

  const mentionTokenForPath = (path: string) =>
    /\s/.test(path) ? `@"${path.replace(/"/g, '\\"')}"` : `@${path}`;

  const selectMentionFile = (
    file: { name: string; path: string; relativePath: string; size: number },
  ) => {
    if (!fileMention) return;
    const mention = mentionTokenForPath(file.relativePath);
    const nextInput = `${input.slice(0, fileMention.start)}${mention} ${input.slice(fileMention.end)}`;
    onChange(nextInput);
    addTextFileReference(file);
    setFileMention(null);
    requestAnimationFrame(() => {
      const textarea = textareaRef.current;
      if (!textarea) return;
      const caret = fileMention.start + mention.length + 1;
      textarea.focus();
      textarea.setSelectionRange(caret, caret);
    });
  };

  const handlePaste = (event: ClipboardEvent<HTMLTextAreaElement>) => {
    const items = Array.from(event.clipboardData?.items || []);
    const imageFiles = items
      .filter((item) => item.kind === 'file' && item.type.startsWith('image/'))
      .map((item) => item.getAsFile())
      .filter(Boolean) as File[];
    if (imageFiles.length > 0) {
      event.preventDefault();
      void addImageFiles(imageFiles);
      return;
    }

    const text = event.clipboardData?.getData('text/plain') || '';
    const isLargePaste = text.length >= 4000 || text.split(/\r\n|\r|\n/).length >= 80;
    if (!isLargePaste) return;
    event.preventDefault();
    void savePastedTextAsFile(text);
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (fileMention && mentionMatches.length > 0) {
      if (e.key === 'ArrowDown') {
        e.preventDefault();
        setSelectedMentionIndex((index) => Math.min(index + 1, mentionMatches.length - 1));
        return;
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault();
        setSelectedMentionIndex((index) => Math.max(index - 1, 0));
        return;
      }
      if (e.key === 'Enter' || e.key === 'Tab') {
        e.preventDefault();
        selectMentionFile(mentionMatches[selectedMentionIndex]);
        return;
      }
      if (e.key === 'Escape') {
        e.preventDefault();
        setFileMention(null);
        return;
      }
    }

    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      onSend();
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    onChange(val);
    detectFileMention(val, e.target.selectionStart);
    if (val === '/') {
      onOpenSkillPicker();
    }
  };

  const getPlaceholder = () => {
    if (isStreaming) {
      return 'Type a follow-up and press Enter to queue it...';
    }
    switch (activeMode) {
      case 'plan':
        return 'Describe the feature to plan — nothing gets modified... (/ to change skill)';
      case 'terminal':
        return 'Describe a command-line task (build, git, tooling)... (/ to change skill)';
      case 'edit':
        return 'Describe changes to make in active file... (/ to change skill)';
      case 'agent':
        return 'Give the agent a task... (/ to change skill)';
      case 'scan':
        return 'Scan the project and create a codebase map...';
      case 'debug':
        return 'Paste stack trace or ask to diagnose... (/ to change skill)';
      case 'review':
        return 'Ask to review active file or code section... (/ to change skill)';
      default:
        return 'Ask NexCoder anything... (/ to change skill)';
    }
  };

  // Dropping a file from the explorer (or OS) onto the composer inserts
  // its path as an @mention so the user can reference it in the task.
  const [dragOver, setDragOver] = useState(false);
  const handleDrop = (e: React.DragEvent) => {
    e.preventDefault();
    setDragOver(false);
    const droppedFiles = Array.from(e.dataTransfer.files || []);
    const imageFiles = droppedFiles.filter((file) => file.type.startsWith('image/'));
    if (imageFiles.length) {
      void addImageFiles(imageFiles);
      return;
    }
    const internal = e.dataTransfer.getData('application/x-nexcoder-path');
    const paths: string[] = [];
    if (internal) paths.push(internal);
    else if (e.dataTransfer.files?.length) {
      for (const f of Array.from(e.dataTransfer.files)) paths.push(f.name);
    }
    if (!paths.length) return;
    const matchedFiles = paths
      .map((path) => projectFiles.find((file) =>
        file.path === path || file.relativePath === path || file.name === path))
      .filter(Boolean) as Array<{ name: string; path: string; relativePath: string; size: number }>;
    if (matchedFiles.length > 0) {
      const newAttachments = matchedFiles
        .filter((file) => !attachments.some((attachment) =>
          attachment.kind === 'text' && attachment.path === file.path))
        .map((file): TextAttachment => ({
          kind: 'text',
          id: `text_${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 8)}`,
          name: file.name,
          mimeType: 'text/plain',
          size: file.size,
          path: file.path,
        }));
      if (newAttachments.length > 0) {
        onAttachmentsChange([...attachments, ...newAttachments]);
      }
    }
    const mention = (matchedFiles.length > 0 ? matchedFiles.map((file) => file.relativePath) : paths)
      .map((p) => mentionTokenForPath(p))
      .join(' ');
    onChange(input ? `${input.replace(/\s*$/, '')} ${mention} ` : `${mention} `);
    document.getElementById('ai-chat-input')?.focus();
  };

  return (
    <div className="chat-input-area">
      {queuedPrompts.length > 0 && (
        <div className="composer-queue" aria-label="Queued follow-up prompts">
          <div className="composer-queue-header">
            <span>Queued</span>
            <span>{queuedPrompts.length}</span>
          </div>
          {queuedPrompts.map((prompt) => (
            <div className="queued-prompt-chip" key={prompt.id}>
              {prompt.attachments.length > 0 && (
                <span className="queued-prompt-image-count" title={`${prompt.attachments.length} image attachment(s)`}>
                  <ImageIcon size={11} /> {prompt.attachments.length}
                </span>
              )}
              <span className="queued-prompt-text" title={prompt.content}>
                {prompt.content}
              </span>
              <div className="queued-prompt-actions">
                <button
                  type="button"
                  className="queue-steer-btn"
                  onClick={() => onUseQueuedPrompt(prompt)}
                  disabled={isStopping}
                  title={isStreaming ? 'Steer the active agent with this prompt' : 'Run this prompt now'}
                >
                  <CornerUpRight size={11} />
                  {isStreaming ? 'Steer' : 'Run'}
                </button>
                <button
                  type="button"
                  className="queue-icon-btn"
                  onClick={() => void copyQueuedPrompt(prompt)}
                  title="Copy queued prompt"
                  aria-label="Copy queued prompt"
                >
                  {copiedQueuedPromptId === prompt.id ? <Check size={11} /> : <Copy size={11} />}
                </button>
                <button
                  type="button"
                  className="queue-icon-btn"
                  onClick={() => onEditQueuedPrompt(prompt)}
                  title="Edit queued prompt"
                  aria-label="Edit queued prompt"
                >
                  <Pencil size={11} />
                </button>
                <button
                  type="button"
                  className="queue-icon-btn queue-delete-btn"
                  onClick={() => onDeleteQueuedPrompt(prompt.id)}
                  title="Delete queued prompt"
                  aria-label="Delete queued prompt"
                >
                  <Trash2 size={11} />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
      <div
        className={`chat-input-box ${dragOver ? 'drag-over' : ''}`}
        onDragOver={(e) => {
          if (e.dataTransfer.types.includes('application/x-nexcoder-path')
              || e.dataTransfer.types.includes('Files')) {
            e.preventDefault(); setDragOver(true);
          }
        }}
        onDragLeave={() => setDragOver(false)}
        onDrop={handleDrop}
      >
        {editingPrompt && (
          <div className="composer-editing-banner">
            <div>
              <strong>Editing prompt</strong>
              <span>Resending restores the project and chat to this point.</span>
            </div>
            <button type="button" onClick={onCancelEdit} title="Cancel editing" aria-label="Cancel editing">
              <X size={12} />
            </button>
          </div>
        )}
        {imageAttachments.length > 0 && (
          <div className="composer-attachments" aria-label="Attached images">
            {imageAttachments.map((attachment) => (
              <ImageAttachmentCard
                key={attachment.id}
                attachment={attachment}
                variant="composer"
                onRemove={() => onAttachmentsChange(
                  attachments.filter((item) => item.id !== attachment.id))}
              />
            ))}
          </div>
        )}
        {textAttachments.length > 0 && (
          <div className="composer-file-attachments" aria-label="Attached text files">
            {textAttachments.map((attachment) => (
              <div className="composer-file-chip" key={attachment.id} title={attachment.path}>
                <FileText size={13} />
                <span>{attachment.name}</span>
                <button
                  type="button"
                  onClick={() => onAttachmentsChange(
                    attachments.filter((item) => item.id !== attachment.id))}
                  title={`Remove ${attachment.name}`}
                  aria-label={`Remove ${attachment.name}`}
                >
                  <X size={11} />
                </button>
              </div>
            ))}
          </div>
        )}
        {rewindError && <div className="composer-attachment-error">{rewindError}</div>}
        {attachmentError && <div className="composer-attachment-error">{attachmentError}</div>}
        {imageAttachments.length > 0 && selectedVisionSupport === false && (
          <div className="composer-attachment-error">
            {settings.aiModel} is text-only. Select a model marked Vision before sending.
          </div>
        )}
        {fileMention && mentionMatches.length > 0 && (
          <div className="file-mention-picker" role="listbox" aria-label="File references">
            {mentionMatches.map((file, index) => (
              <button
                type="button"
                key={file.path}
                className={`file-mention-option ${index === selectedMentionIndex ? 'selected' : ''}`}
                onMouseDown={(event) => {
                  event.preventDefault();
                  selectMentionFile(file);
                }}
                role="option"
                aria-selected={index === selectedMentionIndex}
              >
                <FileText size={13} />
                <span className="file-mention-name">{file.name}</span>
                <span className="file-mention-path">{file.relativePath}</span>
              </button>
            ))}
          </div>
        )}
        <textarea
          ref={textareaRef}
          className="chat-textarea"
          value={input}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          onSelect={(event) => detectFileMention(input, event.currentTarget.selectionStart)}
          onPaste={handlePaste}
          placeholder={getPlaceholder()}
          id="ai-chat-input"
          rows={1}
          aria-label="Agent message"
        />

        <div className="chat-input-bottom">
          <div className="chat-input-left">
            <input
              ref={fileInputRef}
              type="file"
              accept="image/png,image/jpeg,image/webp,image/gif"
              multiple
              className="composer-file-input"
              onChange={(event) => {
                void addImageFiles(Array.from(event.target.files || []));
                event.target.value = '';
              }}
            />
            <button
              type="button"
              className="chat-action-btn"
              onClick={() => fileInputRef.current?.click()}
              title="Attach screenshots or images"
              aria-label="Attach screenshots or images"
            >
              <ImagePlus size={14} />
            </button>
            <button
              className="chat-action-btn skill-add-btn"
              onClick={onOpenSkillPicker}
              title="Add skill (or type /)"
              disabled={isStreaming}
            >
              <Plus size={14} />
            </button>
            <ActiveSkillChip onClick={onOpenSkillPicker} />
            <label className="tool-access-control" title="Autonomy: which commands run without asking">
              {settings.autonomy === 'read_only' ? <Eye size={10} /> : <ShieldCheck size={10} />}
              <select
                value={settings.autonomy}
                onChange={(event) => updateSetting('autonomy', event.target.value as 'read_only' | 'ask' | 'risky_only' | 'full_auto')}
                disabled={isStreaming}
                aria-label="Agent autonomy level"
              >
                <option value="read_only">Read only</option>
                <option value="ask">Ask every time</option>
                <option value="risky_only">Ask for risky</option>
                <option value="full_auto">Full auto</option>
              </select>
            </label>
          </div>

          <div className="chat-input-right">
            <ModelSelector compact disabled={isStreaming} />

            {isStreaming && input.trim() && (
              <button
                type="button"
                className="chat-queue-btn"
                onClick={onSend}
                title="Queue follow-up prompt"
                aria-label="Queue follow-up prompt"
              >
                <ListPlus size={12} />
              </button>
            )}

            <button
              className={`chat-send-btn ${isStreaming ? 'chat-stop-btn' : ''} ${isStopping ? 'is-stopping' : ''}`}
              onClick={isStreaming ? onStop : onSend}
              disabled={isStreaming
                ? isStopping
                : ((!input.trim() && !attachments.length)
                  || (imageAttachments.length > 0 && selectedVisionSupport === false))}
              title={isStreaming ? (isStopping ? 'Stopping agent...' : 'Stop the agent') : (editingPrompt ? 'Rewind and resend prompt' : 'Send message')}
              aria-label={isStreaming ? (isStopping ? 'Stopping agent' : 'Stop agent') : (editingPrompt ? 'Rewind and resend prompt' : 'Send message')}
            >
              {isStreaming ? (
                <span className="stop-icon" />
              ) : (
                <Send size={11} />
              )}
            </button>
          </div>
        </div>

        {contextUsage && (
          <div className="composer-context-meter"
               title="Estimated context usage of the last agent turn; compaction runs automatically near the limit">
            <div className="context-meter-bar">
              <div
                className={`context-meter-fill ${contextUsage.percent > 85 ? 'hot' : contextUsage.percent > 60 ? 'warm' : ''}`}
                style={{ width: `${Math.min(100, contextUsage.percent)}%` }}
              />
            </div>
            <span className="context-meter-label">
              context ~{(contextUsage.tokens / 1000).toFixed(1)}k / {(contextUsage.budget / 1000).toFixed(0)}k ({contextUsage.percent}%)
            </span>
          </div>
        )}
      </div>
    </div>
  );
}
