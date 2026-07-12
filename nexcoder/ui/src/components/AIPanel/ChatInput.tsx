import React, { KeyboardEvent, ChangeEvent } from 'react';
import { Send, Plus, Cpu, ShieldCheck, Eye } from 'lucide-react';
import { useChatStore } from '../../store/useChatStore';
import { useAgentStore } from '../../store/useAgentStore';
import ActiveSkillChip from './ActiveSkillChip';

const MODEL_LABELS: Record<string, string> = {
  'qwen2.5-coder': 'Qwen 3B',
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

  return (
    <div className="chat-input-area">
      <div className="chat-input-box">
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
            <label className="tool-access-control" title="Choose which tools the agent may execute">
              {settings.toolAccess === 'read_only' ? <Eye size={10} /> : <ShieldCheck size={10} />}
              <select
                value={settings.toolAccess}
                onChange={(event) => updateSetting('toolAccess', event.target.value as 'full' | 'read_only')}
                disabled={isStreaming}
                aria-label="Agent tool access"
              >
                <option value="full">Full access</option>
                <option value="read_only">Read only</option>
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
              onClick={onSend}
              disabled={isStreaming || !input.trim()}
              title={isStreaming ? "Streaming..." : "Send Message"}
            >
              {isStreaming ? (
                <span className="stop-icon" />
              ) : (
                <Send size={11} />
              )}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
