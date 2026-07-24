import React, { useCallback, useEffect, useState } from 'react';
import { CheckCircle2, ExternalLink, Loader2, X } from 'lucide-react';
import { startWebAuthLogin } from '../../services/bridge';
import './LoginScreen.css';

interface LoginScreenProps {
  onClose: () => void;
  authError?: string | null;
}

export default function LoginScreen({ onClose, authError }: LoginScreenProps) {
  const [loading, setLoading] = useState(false);
  const [loginUrl, setLoginUrl] = useState('');
  const [error, setError] = useState('');

  const startLogin = useCallback(async () => {
    setLoading(true);
    setError('');
    try {
      const result = await startWebAuthLogin();
      if (!result?.success) {
        setError(result?.error || 'Could not start web login.');
        return;
      }
      setLoginUrl(result.url || '');
      if (result.opened === false) {
        setError('Your browser did not open automatically. Use the button below.');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void startLogin();
  }, [startLogin]);

  return (
    <div className="login-overlay">
      <div className="login-container">
        <div className="login-close-row">
          <button className="btn btn-ghost btn-icon" onClick={onClose} aria-label="Close login">
            <X size={16} />
          </button>
        </div>

        <div className="login-header">
          <div className="login-logo">N</div>
          <h2 className="login-title">Sign in on NexCoder Web</h2>
          <p className="login-subtitle">
            Complete login in your browser. NexCoder will return here automatically when authentication finishes.
          </p>
        </div>

        {(error || authError) && (
          <div className="login-error" role="alert">
            {authError || error}
          </div>
        )}

        <div className="login-web-status">
          {loading ? <Loader2 size={16} className="spin" /> : <CheckCircle2 size={16} />}
          <span>{loading ? 'Opening NexCoder Web...' : 'Waiting for browser login callback'}</span>
        </div>

        <div className="login-web-actions">
          <button className="btn btn-primary w-full" type="button" onClick={() => void startLogin()} disabled={loading}>
            {loading ? <Loader2 size={14} className="spin" /> : <ExternalLink size={14} />}
            Open NexCoder Web
          </button>
          {loginUrl && (
            <a className="login-url" href={loginUrl} target="_blank" rel="noreferrer">
              {loginUrl}
            </a>
          )}
        </div>
      </div>
    </div>
  );
}
