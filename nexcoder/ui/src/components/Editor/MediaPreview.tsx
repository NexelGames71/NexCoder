import React, { useEffect, useMemo, useState } from 'react';
import {
  AlertCircle,
  FileArchive,
  FileAudio,
  FileText,
  FileVideo,
  Type,
} from 'lucide-react';
import { OpenFile } from '../../types';
import { readFileBase64 } from '../../services/bridge';
import { FilePreviewKind } from '../../utils/fileIcons';
import './MediaPreview.css';

interface MediaPreviewProps {
  file: OpenFile;
  kind: Exclude<FilePreviewKind, 'text' | 'image'>;
}

function formatBytes(bytes: number | null): string {
  if (bytes === null || !Number.isFinite(bytes)) return '';
  if (bytes < 1024) return `${bytes} B`;
  const units = ['KB', 'MB', 'GB'];
  let value = bytes / 1024;
  let unit = units[0];
  for (let index = 1; index < units.length && value >= 1024; index += 1) {
    value /= 1024;
    unit = units[index];
  }
  return `${value >= 10 ? value.toFixed(1) : value.toFixed(2)} ${unit}`;
}

const KIND_LABELS: Record<MediaPreviewProps['kind'], string> = {
  audio: 'Audio',
  video: 'Video',
  pdf: 'PDF document',
  font: 'Font',
  binary: 'Binary file',
};

export default function MediaPreview({ file, kind }: MediaPreviewProps) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [mimeType, setMimeType] = useState('');
  const [size, setSize] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const fontFamily = useMemo(
    () => `NexCoderPreview_${file.path.replace(/[^a-z0-9]/gi, '_')}`,
    [file.path],
  );

  useEffect(() => {
    let cancelled = false;
    setDataUrl(null);
    setMimeType('');
    setSize(null);
    setError(null);

    if (kind === 'binary') return () => { cancelled = true; };

    readFileBase64(file.path)
      .then((response) => {
        if (cancelled) return;
        if (!response?.success || !response.data_url) {
          setError(response?.error || `Could not load ${KIND_LABELS[kind].toLowerCase()}.`);
          return;
        }
        setDataUrl(response.data_url);
        setMimeType(String(response.mime_type || ''));
        setSize(typeof response.size === 'number' ? response.size : null);
      })
      .catch((reason) => {
        if (!cancelled) setError(String(reason));
      });

    return () => { cancelled = true; };
  }, [file.path, kind]);

  const icon = kind === 'audio'
    ? <FileAudio size={34} />
    : kind === 'video'
      ? <FileVideo size={34} />
      : kind === 'font'
        ? <Type size={34} />
        : kind === 'pdf'
          ? <FileText size={34} />
          : <FileArchive size={34} />;

  return (
    <div className="media-preview">
      <div className="media-preview-toolbar">
        <span className="media-preview-name">{file.name}</span>
        <span>{KIND_LABELS[kind]}</span>
        {size !== null && <span>{formatBytes(size)}</span>}
        {mimeType && <span>{mimeType}</span>}
      </div>

      <div className={`media-preview-stage media-preview-${kind}`}>
        {error ? (
          <div className="media-preview-message error" role="alert">
            <AlertCircle size={22} />
            <strong>Preview unavailable</strong>
            <span>{error}</span>
          </div>
        ) : kind === 'binary' ? (
          <div className="media-preview-message">
            {icon}
            <strong>{file.name}</strong>
            <span>This file is binary and cannot be safely displayed as source text.</span>
          </div>
        ) : !dataUrl ? (
          <div className="media-preview-message">
            {icon}
            <span>Loading {KIND_LABELS[kind].toLowerCase()}...</span>
          </div>
        ) : kind === 'audio' ? (
          <div className="media-audio-card">
            <FileAudio size={48} />
            <strong>{file.name}</strong>
            <audio controls preload="metadata" src={dataUrl}>
              Your system cannot play this audio format.
            </audio>
          </div>
        ) : kind === 'video' ? (
          <video className="media-video-player" controls preload="metadata" src={dataUrl}>
            Your system cannot play this video format.
          </video>
        ) : kind === 'pdf' ? (
          <object className="media-pdf-viewer" data={dataUrl} type="application/pdf">
            <div className="media-preview-message">
              <FileText size={34} />
              <strong>PDF preview is unavailable in this runtime.</strong>
            </div>
          </object>
        ) : (
          <>
            <style>{`@font-face { font-family: '${fontFamily}'; src: url('${dataUrl}'); }`}</style>
            <div className="media-font-sample" style={{ fontFamily }}>
              <span className="media-font-title">Aa Bb Cc 123</span>
              <span>The quick brown fox jumps over the lazy dog.</span>
              <span>ABCDEFGHIJKLMNOPQRSTUVWXYZ</span>
              <span>abcdefghijklmnopqrstuvwxyz</span>
              <span>0123456789 !@#$%^&amp;*()</span>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
