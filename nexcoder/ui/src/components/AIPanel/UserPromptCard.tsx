import React, { useState } from 'react';
import { Check, Copy, FileText, Pencil } from 'lucide-react';
import { ImageAttachment, PromptAttachment } from '../../types';
import ImageAttachmentCard from './ImageAttachmentCard';

interface UserPromptCardProps {
  text: string;
  attachments?: PromptAttachment[];
  onEdit?: () => void;
  compact?: boolean;
}

async function copyText(value: string) {
  if (navigator.clipboard?.writeText) {
    await navigator.clipboard.writeText(value);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = value;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  textarea.remove();
}

export default function UserPromptCard({
  text,
  attachments = [],
  onEdit,
  compact = false,
}: UserPromptCardProps) {
  const [copied, setCopied] = useState(false);
  const imageAttachments = attachments.filter((attachment): attachment is ImageAttachment =>
    attachment.kind !== 'text');
  const textAttachments = attachments.filter((attachment) => attachment.kind === 'text');
  const handleCopy = async () => {
    try {
      await copyText(text);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1200);
    } catch (error) {
      console.error('Could not copy prompt', error);
    }
  };

  return (
    <div className={`user-prompt-card ${compact ? 'user-prompt-card-compact' : ''}`}>
      {imageAttachments.length > 0 && (
        <div className="user-prompt-images" aria-label="Prompt image attachments">
          {imageAttachments.map((attachment) => (
            <ImageAttachmentCard key={attachment.id} attachment={attachment} variant="chat" />
          ))}
        </div>
      )}
      {textAttachments.length > 0 && (
        <div className="user-prompt-files" aria-label="Prompt file attachments">
          {textAttachments.map((attachment) => (
            <span key={attachment.id} className="user-prompt-file-chip" title={attachment.path}>
              <FileText size={12} />
              <span>{attachment.name}</span>
            </span>
          ))}
        </div>
      )}
      {text && <div className="chat-bubble chat-bubble-user">{text}</div>}
      <div className="user-prompt-actions">
        <button type="button" onClick={handleCopy} title="Copy prompt" aria-label="Copy prompt">
          {copied ? <Check size={12} /> : <Copy size={12} />}
        </button>
        {onEdit && (
          <button type="button" onClick={onEdit} title="Edit and resend prompt" aria-label="Edit and resend prompt">
            <Pencil size={12} />
          </button>
        )}
      </div>
    </div>
  );
}
