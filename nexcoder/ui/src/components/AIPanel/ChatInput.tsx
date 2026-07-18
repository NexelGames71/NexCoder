import React, { KeyboardEvent, ChangeEvent, useState } from 'react';
import { Send, Plus, Cpu, ShieldCheck, Eye } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { useAgentStore } from '../../store/useAgentStore';
import { useAgentRunStore } from '../../store/useAgentRunStore';
import { agentCancelV2 } from '../../services/bridge';
import ActiveSkillChip from './ActiveSkillChip';

const MODEL_LABELS: Record<string, string> = {
  'qwen2.5-coder': 'Qwen 3B',
  'qwen3-coder-30b-a3b-instruct-q4_k_m': 'Qwen3 Coder 30B A3B',
  'qwen2.5-coder-7b-instruct-q6_k': 'Qwen 2.5 Coder 7B Q6',
  'qwen2.5-coder-7b-instruct-q4_k_m': 'Qwen 2.5 Coder 7B',
  'yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF': 'Gemma4 12B',
};

interface ChatInputProps {
  input: string;
  onChange: (val: string) => void;
  onSend: () => void;
  onOpenSkillPicker: () => void;
  skillFilter?: string;
}

export default function ChatInput({ input, onChange, onSend, onOpenSkillPicker, skillFilter }: ChatInputProps) {
  const { isStreaming, activeMode } = useChatStore();
  const { settings, updateSetting } = useAgentStore();
  const contextUsage = useAgentRunStore((state) => state.lastContextUsage);

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      if (isStreaming) return;
      onSend();
    }
  };

  const handleChange = (e: ChangeEvent<HTMLTextAreaElement>) => {
    const val = e.target.value;
    onChange(val);
    if (val === '/') {
      onOpenSkillPicker();
    }
  };

  const getPlaceholder = () => {
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
    const internal = e.dataTransfer.getData('application/x-nexcoder-path');
    const paths: string[] = [];
    if (internal) paths.push(internal);
    else if (e.dataTransfer.files?.length) {
      for (const f of Array.from(e.dataTransfer.files)) paths.push(f.name);
    }
    if (!paths.length) return;
    const mention = paths.map((p) => `@${p}`).join(' ');
    onChange(input ? `${input.replace(/\s*$/, '')} ${mention} ` : `${mention} `);
    document.getElementById('ai-chat-input')?.focus();
  };

  return (
    <div className="chat-input-area">
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
        <textarea
          className="chat-textarea"
          value={input}
          onChange={handleChange}
          onKeyDown={handleKeyDown}
          placeholder={getPlaceholder()}
          disabled={isStreaming}
          id="ai-chat-input"
        />

        <div className="chat-input-bottom">
          <div className="chat-input-left">
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
            <div className="model-selector-chip">
              <Cpu size={10} style={{ opacity: 0.7 }} />
              <span>{MODEL_LABELS[settings.aiModel] || settings.aiModel}</span>
            </div>

            <button
              className="chat-send-btn"
              onClick={isStreaming ? () => agentCancelV2() : onSend}
              disabled={!isStreaming && !input.trim()}
              title={isStreaming ? "Stop the agent" : "Send Message"}
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
