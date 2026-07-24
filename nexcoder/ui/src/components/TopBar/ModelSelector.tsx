import React, { useEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Check, ChevronDown, Cpu, ImageIcon, RefreshCw } from 'lucide-react';
import { useAgentStore } from '../../store/useAgentStore';
import { testModelConnection } from '../../services/bridge';

interface ModelSelectorProps {
  disabled?: boolean;
  compact?: boolean;
}

function modelLabel(id: string): string {
  if (id === 'z-ai/glm-5.2') return 'GLM-5.2';
  if (id === 'nvidia/nemotron-3-ultra-550b-a55b') return 'Nemotron 3 Ultra';
  if (id === 'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning') return 'Nemotron 3 Nano Omni';
  if (id === 'stepfun-ai/step-3.5-flash') return 'Step 3.5 Flash';
  if (id === 'stepfun-ai/step-3.7-flash') return 'Step 3.7 Flash';
  if (id === 'minimaxai/minimax-m3') return 'MiniMax M3';
  if (id === 'nvidia/llama-3.1-nemotron-nano-vl-8b-v1') return 'Nemotron Nano VL';
  const tail = id.split('/').pop() || id;
  return tail.replace(/[-_]+/g, ' ');
}

const VISION_MODELS = new Set([
  'stepfun-ai/step-3.7-flash',
  'minimaxai/minimax-m3',
  'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
  'nvidia/llama-3.1-nemotron-nano-vl-8b-v1',
  'meta/llama-4-maverick-17b-128e-instruct',
  'meta/llama-3.2-90b-vision-instruct',
  'nvidia/nemotron-nano-12b-v2-vl',
]);

// Keep dependable choices visible even when a provider's /models endpoint is
// incomplete, temporarily unavailable, or returns hundreds of unrelated NIMs.
// Every id here has been verified to return HTTP 200 from the chat completions
// endpoint — do not add a model until a live completion request confirms it.
const PINNED_MODELS = [
  'nvidia/nemotron-3-ultra-550b-a55b',
  'z-ai/glm-5.2',
  'stepfun-ai/step-3.7-flash',
  'nvidia/nemotron-3-nano-omni-30b-a3b-reasoning',
  'minimaxai/minimax-m3',
];

/** True/false for known catalog capabilities, null for custom/unknown models. */
export function modelSupportsVision(id: string): boolean | null {
  if (VISION_MODELS.has(id)) return true;
  if (id === 'stepfun-ai/step-3.5-flash') return false;
  return null;
}

/** Provider-backed model selector with a custom-id escape hatch. */
export default function ModelSelector({ disabled = false, compact = false }: ModelSelectorProps) {
  const { settings, updateSetting } = useAgentStore();
  const triggerRef = useRef<HTMLButtonElement>(null);
  const [isOpen, setIsOpen] = useState(false);
  const [models, setModels] = useState<string[]>([]);
  const [customModel, setCustomModel] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [menuPosition, setMenuPosition] = useState({ right: 12, bottom: 48, width: 320 });

  const refresh = async (cancelled?: () => boolean) => {
    setLoading(true);
    setError('');
    try {
      const result = await testModelConnection();
      if (cancelled?.()) return;
      if (!result?.connected) {
        setModels([]);
        setError(result?.error || 'Provider unavailable');
        return;
      }
      const discovered: string[] = (result.models?.data || [])
        .map((item: any) => String(item?.id || '').trim())
        .filter((id: string) => Boolean(id));
      setModels(Array.from(new Set<string>(discovered)).sort((a, b) => a.localeCompare(b)));
    } catch (reason) {
      if (!cancelled?.()) setError(String(reason));
    } finally {
      if (!cancelled?.()) setLoading(false);
    }
  };

  useEffect(() => {
    let cancelled = false;
    refresh(() => cancelled);
    return () => { cancelled = true; };
  }, [settings.aiEndpoint]);

  useEffect(() => {
    if (!isOpen) return undefined;

    const positionMenu = () => {
      const trigger = triggerRef.current;
      if (!trigger) return;
      const bounds = trigger.getBoundingClientRect();
      const viewportPadding = 12;
      setMenuPosition({
        right: Math.max(viewportPadding, window.innerWidth - bounds.right),
        bottom: Math.max(viewportPadding, window.innerHeight - bounds.top + 6),
        width: Math.min(320, window.innerWidth - (viewportPadding * 2)),
      });
    };

    positionMenu();
    window.addEventListener('resize', positionMenu);
    window.addEventListener('scroll', positionMenu, true);
    return () => {
      window.removeEventListener('resize', positionMenu);
      window.removeEventListener('scroll', positionMenu, true);
    };
  }, [compact, isOpen]);

  useEffect(() => {
    if (!isOpen) return undefined;
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setIsOpen(false);
    };
    window.addEventListener('keydown', closeOnEscape);
    return () => window.removeEventListener('keydown', closeOnEscape);
  }, [isOpen]);

  const options = useMemo(() => {
    return Array.from(new Set([
      settings.aiModel,
      ...PINNED_MODELS,
      ...models,
    ].filter(Boolean)));
  }, [models, settings.aiModel]);

  const select = (model: string) => {
    const value = model.trim();
    if (!value) return;
    updateSetting('aiModel', value);
    setCustomModel('');
    setIsOpen(false);
  };

  return (
    <div className="dropdown model-picker">
      <button
        ref={triggerRef}
        className={compact ? 'model-selector-chip model-picker-trigger' : 'btn btn-ghost model-picker-trigger'}
        onClick={() => setIsOpen((open) => !open)}
        disabled={disabled}
        title={`Model: ${settings.aiModel}`}
        aria-label={`Switch model. Current model: ${modelLabel(settings.aiModel)}`}
        aria-expanded={isOpen}
      >
        {!compact && <Cpu size={12} />}
        <span className="model-selector-chip-label">{modelLabel(settings.aiModel)}</span>
        {compact && modelSupportsVision(settings.aiModel) === true && (
          <ImageIcon className="model-selector-chip-vision" size={10} aria-label="Vision model" />
        )}
        <ChevronDown className="model-selector-chip-chevron" size={10} />
      </button>

      {isOpen && createPortal(
        <>
          <div className="model-picker-backdrop" onClick={() => setIsOpen(false)} />
          <div
            className="dropdown-menu model-picker-menu model-picker-menu-portal"
            style={menuPosition}
            role="menu"
            aria-label="Available AI models"
          >
            <div className="model-picker-heading">
              <span>Switch model</span>
              <button className="btn btn-ghost btn-icon" onClick={() => refresh()} title="Refresh models">
                <RefreshCw size={11} className={loading ? 'model-picker-spinning' : ''} />
              </button>
            </div>
            <div className="model-picker-options">
              {options.map((model) => (
                <button
                  key={model}
                  className={`dropdown-item ${settings.aiModel === model ? 'active' : ''}`}
                  onClick={() => select(model)}
                  title={model}
                  role="menuitemradio"
                  aria-checked={settings.aiModel === model}
                >
                  <span className="model-picker-option-name">{modelLabel(model)}</span>
                  {modelSupportsVision(model) === true && (
                    <span className="model-picker-vision-badge" title="Accepts image input">
                      <ImageIcon size={9} /> Vision
                    </span>
                  )}
                  {settings.aiModel === model && <Check size={11} />}
                </button>
              ))}
              {!options.length && !loading && <div className="model-picker-empty">No models returned</div>}
              {loading && <div className="model-picker-empty">Loading models…</div>}
              {error && <div className="model-picker-error">{error}</div>}
            </div>
            <div className="dropdown-separator" />
            <div className="model-picker-custom">
              <input
                className="input"
                value={customModel}
                onChange={(event) => setCustomModel(event.target.value)}
                onKeyDown={(event) => { if (event.key === 'Enter') select(customModel); }}
                placeholder="Custom model id"
                aria-label="Custom model id"
              />
              <button className="btn" onClick={() => select(customModel)} disabled={!customModel.trim()}>
                Use
              </button>
            </div>
          </div>
        </>,
        document.body,
      )}
    </div>
  );
}
