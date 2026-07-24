import React, { useEffect, useState } from 'react';
import { createPortal } from 'react-dom';
import { Expand, ImageIcon, X } from 'lucide-react';
import { ImageAttachment } from '../../types';

interface ImageAttachmentCardProps {
  attachment: ImageAttachment;
  variant?: 'chat' | 'composer';
  onRemove?: () => void;
}

function ImageLightbox({ attachment, onClose }: {
  attachment: ImageAttachment;
  onClose: () => void;
}) {
  useEffect(() => {
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = 'hidden';
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === 'Escape') onClose();
    };
    window.addEventListener('keydown', onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener('keydown', onKeyDown);
    };
  }, [onClose]);

  if (!attachment.dataUrl) return null;
  return createPortal(
    <div
      className="image-lightbox-backdrop"
      role="presentation"
      onMouseDown={(event) => {
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div className="image-lightbox" role="dialog" aria-modal="true" aria-label={attachment.name}>
        <div className="image-lightbox-header">
          <span title={attachment.name}>{attachment.name}</span>
          <button type="button" onClick={onClose} aria-label="Close image viewer" title="Close">
            <X size={16} />
          </button>
        </div>
        <div className="image-lightbox-body">
          <img src={attachment.dataUrl} alt={attachment.name} />
        </div>
      </div>
    </div>,
    document.body,
  );
}

export default function ImageAttachmentCard({
  attachment,
  variant = 'chat',
  onRemove,
}: ImageAttachmentCardProps) {
  const [open, setOpen] = useState(false);
  const available = Boolean(attachment.dataUrl);
  const unavailableTitle = 'Preview unavailable after restoring chat history. Reattach the image to send it again.';

  return (
    <>
      <div className={`image-attachment-card image-attachment-${variant}`} title={available ? attachment.name : unavailableTitle}>
        <button
          type="button"
          className="image-attachment-preview"
          onClick={() => available && setOpen(true)}
          disabled={!available}
          aria-label={available ? `View ${attachment.name}` : unavailableTitle}
        >
          {available ? (
            <img src={attachment.dataUrl} alt={attachment.name} />
          ) : (
            <span className="image-attachment-placeholder"><ImageIcon size={20} /></span>
          )}
          {available && <span className="image-attachment-expand"><Expand size={12} /></span>}
        </button>
        {onRemove && (
          <button
            type="button"
            className="image-attachment-remove"
            onClick={onRemove}
            title={`Remove ${attachment.name}`}
            aria-label={`Remove ${attachment.name}`}
          >
            <X size={11} />
          </button>
        )}
      </div>
      {open && <ImageLightbox attachment={attachment} onClose={() => setOpen(false)} />}
    </>
  );
}
