import React, { useEffect, useRef, useState } from 'react';

interface ExplorerNameDialogProps {
  title: string;
  label: string;
  initialValue: string;
  confirmLabel: string;
  onCancel: () => void;
  onConfirm: (value: string) => void;
}

export default function ExplorerNameDialog({
  title,
  label,
  initialValue,
  confirmLabel,
  onCancel,
  onConfirm,
}: ExplorerNameDialogProps) {
  const [value, setValue] = useState(initialValue);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    inputRef.current?.focus();
    inputRef.current?.select();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onCancel();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [onCancel]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    const next = value.trim();
    if (next) onConfirm(next);
  };

  return (
    <div className="explorer-dialog-backdrop" onMouseDown={onCancel}>
      <form className="explorer-name-dialog" onSubmit={submit} onMouseDown={(event) => event.stopPropagation()}>
        <div className="explorer-name-dialog-title">{title}</div>
        <label className="explorer-name-dialog-label">
          <span>{label}</span>
          <input
            ref={inputRef}
            className="input"
            value={value}
            onChange={(event) => setValue(event.target.value)}
          />
        </label>
        <div className="explorer-name-dialog-actions">
          <button type="button" className="btn btn-ghost" onClick={onCancel}>
            Cancel
          </button>
          <button type="submit" className="btn btn-primary" disabled={!value.trim()}>
            {confirmLabel}
          </button>
        </div>
      </form>
    </div>
  );
}
