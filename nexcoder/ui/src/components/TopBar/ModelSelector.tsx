import React, { useState } from 'react';
import { Cpu, ChevronDown } from 'lucide-react';
import { useAgentStore } from '../../store/useAgentStore';

// Preferred model for NexCoder agent tasks. Qwen2.5-Coder-7B-Instruct
// Q6_K is the quality-focused local default. Q4_K_M remains available
// for machines with less free GPU or unified memory.
const QWEN_CODER_7B = 'qwen2.5-coder-7b-instruct-q6_k';

const MODELS = [
  {
    id: QWEN_CODER_7B,
    name: 'Qwen2.5-Coder-7B-Instruct (Q6_K, recommended)',
    icon: Cpu,
  },
  {
    id: 'qwen2.5-coder-7b-instruct-q4_k_m',
    name: 'Qwen2.5-Coder-7B-Instruct (Q4_K_M, lower memory)',
    icon: Cpu,
  },
  {
    id: 'yuxinlu1/gemma-4-12B-agentic-fable5-composer2.5-v2-3.5x-tau2-GGUF',
    name: 'Gemma4-12B v2 Agentic (GGUF)',
    icon: Cpu,
  },
  { id: 'qwen2.5-coder', name: 'Qwen2.5-Coder-3B (Local)', icon: Cpu },
  { id: 'nexa-fast', name: 'Nexa Fast (Local)', icon: Cpu },
  { id: 'nexa-pro', name: 'Nexa Pro (Local)', icon: Cpu },
  { id: 'gpt-4o', name: 'GPT-4o (Cloud Fallback)', icon: Cpu },
  { id: 'claude-3.5-sonnet', name: 'Claude 3.5 Sonnet', icon: Cpu },
];

export default function ModelSelector() {
  const { settings, updateSetting } = useAgentStore();
  const [isOpen, setIsOpen] = useState(false);

  const selectedModel = MODELS.find(m => m.id === settings.aiModel) || MODELS[0];

  const handleSelect = (modelId: string) => {
    updateSetting('aiModel', modelId);
    setIsOpen(false);
  };

  return (
    <div className="dropdown">
      <button 
        className="btn btn-ghost" 
        onClick={() => setIsOpen(!isOpen)}
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          background: 'var(--bg-input)',
          border: '1px solid var(--border)',
          padding: '4px 12px',
          height: '28px',
          borderRadius: 'var(--radius-md)',
          color: 'var(--text-primary)',
          fontSize: 'var(--font-size-xs)'
        }}
      >
        <selectedModel.icon size={12} style={{ color: 'var(--accent-purple)' }} />
        <span>{selectedModel.name}</span>
        <ChevronDown size={10} style={{ color: 'var(--text-secondary)' }} />
      </button>

      {isOpen && (
        <>
          <div 
            style={{ position: 'fixed', top: 0, bottom: 0, left: 0, right: 0, zIndex: 99 }} 
            onClick={() => setIsOpen(false)} 
          />
          <div className="dropdown-menu" style={{ top: 'calc(100% + 4px)', left: 0, minWidth: '220px', zIndex: 100 }}>
            {MODELS.map((model) => (
              <button
                key={model.id}
                className={`dropdown-item ${settings.aiModel === model.id ? 'active' : ''}`}
                onClick={() => handleSelect(model.id)}
                style={{ fontSize: 'var(--font-size-xs)' }}
              >
                <model.icon size={12} style={{ marginRight: 'var(--space-2)' }} />
                {model.name}
              </button>
            ))}
          </div>
        </>
      )}
    </div>
  );
}
