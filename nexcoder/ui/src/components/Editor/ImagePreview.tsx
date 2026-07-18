import React, { useEffect, useState } from 'react';
import { ZoomIn, ZoomOut, Maximize2, AlertCircle } from 'lucide-react';
import { OpenFile } from '../../types';
import { readFileBase64 } from '../../services/bridge';
import './ImagePreview.css';

/** Renders an image file in the editor surface: checkerboard backdrop,
 *  zoom controls, and natural-size readout. SVGs whose content is already
 *  loaded render inline; everything else loads as a base64 data URL. */
export default function ImagePreview({ file }: { file: OpenFile }) {
  const [dataUrl, setDataUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [zoom, setZoom] = useState(1);
  const [dims, setDims] = useState<{ w: number; h: number } | null>(null);

  useEffect(() => {
    let cancelled = false;
    setDataUrl(null); setError(null); setZoom(1); setDims(null);
    // SVG is text — if the file content is already loaded, render it inline.
    if (file.path.toLowerCase().endsWith('.svg') && file.content) {
      const encoded = btoa(unescape(encodeURIComponent(file.content)));
      setDataUrl(`data:image/svg+xml;base64,${encoded}`);
      return;
    }
    readFileBase64(file.path)
      .then((res) => {
        if (cancelled) return;
        if (res?.success && res.data_url) setDataUrl(res.data_url);
        else setError(res?.error || 'Could not load image.');
      })
      .catch((e) => { if (!cancelled) setError(String(e)); });
    return () => { cancelled = true; };
  }, [file.path, file.content]);

  return (
    <div className="image-preview">
      <div className="image-preview-toolbar">
        <span className="image-preview-name">{file.name}</span>
        {dims && <span className="image-preview-dims">{dims.w} × {dims.h}</span>}
        <span className="image-preview-spacer" />
        <button className="btn btn-ghost btn-icon" title="Zoom out"
          onClick={() => setZoom((z) => Math.max(0.1, +(z - 0.25).toFixed(2)))}>
          <ZoomOut size={14} />
        </button>
        <span className="image-preview-zoom">{Math.round(zoom * 100)}%</span>
        <button className="btn btn-ghost btn-icon" title="Zoom in"
          onClick={() => setZoom((z) => Math.min(8, +(z + 0.25).toFixed(2)))}>
          <ZoomIn size={14} />
        </button>
        <button className="btn btn-ghost btn-icon" title="Reset zoom"
          onClick={() => setZoom(1)}>
          <Maximize2 size={14} />
        </button>
      </div>
      <div className="image-preview-canvas">
        {error ? (
          <div className="image-preview-error">
            <AlertCircle size={18} /> {error}
          </div>
        ) : dataUrl ? (
          <img
            src={dataUrl}
            alt={file.name}
            style={{ transform: `scale(${zoom})` }}
            onLoad={(e) => setDims({
              w: e.currentTarget.naturalWidth, h: e.currentTarget.naturalHeight })}
          />
        ) : (
          <div className="image-preview-loading">Loading image…</div>
        )}
      </div>
    </div>
  );
}
