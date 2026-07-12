import React, { useState } from 'react';
import { X, Mail, Lock, User, Loader2 } from 'lucide-react';
import { appwriteLogin, appwriteRegister } from '../../services/bridge';
import './LoginScreen.css';

interface LoginScreenProps {
  onClose: () => void;
  onLoginSuccess: (user: any) => void;
}

export default function LoginScreen({ onClose, onLoginSuccess }: LoginScreenProps) {
  const [isRegister, setIsRegister] = useState(false);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [name, setName] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!email || !password) return;

    setLoading(true);
    setError('');

    try {
      const result = isRegister
        ? await appwriteRegister(email, password, name)
        : await appwriteLogin(email, password);

      if (!result?.success) {
        setError(result?.error || 'Authentication failed');
        return;
      }

      const user = result.user || result.session || {};
      onLoginSuccess({
        id: user.$id || user.userId || email,
        email: user.email || email,
        name: user.name || name || email.split('@')[0],
      });
      onClose();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="login-overlay">
      <div className="login-container">
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <button className="btn btn-ghost btn-icon" onClick={onClose}>
            <X size={16} />
          </button>
        </div>

        <div className="login-header">
          <div className="login-logo">N</div>
          <h2 style={{ fontSize: 'var(--font-size-xl)', fontWeight: '700', color: 'var(--text-primary)' }}>
            {isRegister ? 'Create Nexa Account' : 'Sign in to Nexa'}
          </h2>
          <p style={{ fontSize: 'var(--font-size-xs)', color: 'var(--text-secondary)' }}>
            Sync your workspaces, agent tasks, and chat history.
          </p>
        </div>

        {error && (
          <div style={{ background: 'var(--accent-red-dim)', color: 'var(--accent-red)', padding: 'var(--space-2)', borderRadius: 'var(--radius-md)', fontSize: 'var(--font-size-xs)' }}>
            {error}
          </div>
        )}

        <form className="login-form" onSubmit={handleSubmit}>
          {isRegister && (
            <div className="form-group">
              <label className="form-label">Full Name</label>
              <div style={{ position: 'relative' }}>
                <input
                  className="input"
                  type="text"
                  placeholder="John Doe"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                  style={{ paddingLeft: 'var(--space-6)' }}
                />
                <User size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
              </div>
            </div>
          )}

          <div className="form-group">
            <label className="form-label">Email Address</label>
            <div style={{ position: 'relative' }}>
              <input
                className="input"
                type="email"
                placeholder="you@nexa.ai"
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                style={{ paddingLeft: 'var(--space-6)' }}
              />
              <Mail size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label">Password</label>
            <div style={{ position: 'relative' }}>
              <input
                className="input"
                type="password"
                placeholder="••••••••"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                style={{ paddingLeft: 'var(--space-6)' }}
              />
              <Lock size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: 'var(--text-tertiary)' }} />
            </div>
          </div>

          <button className="btn btn-primary w-full" type="submit" disabled={loading} style={{ marginTop: 'var(--space-2)' }}>
            {loading ? <Loader2 size={14} className="spin" /> : (isRegister ? 'Sign Up' : 'Sign In')}
          </button>
        </form>

        <div style={{ textAlign: 'center', fontSize: 'var(--font-size-xs)' }}>
          <span style={{ color: 'var(--text-secondary)' }}>
            {isRegister ? 'Already have an account? ' : "Don't have an account? "}
          </span>
          <button
            className="btn btn-ghost"
            onClick={() => setIsRegister(!isRegister)}
            style={{ padding: 0, textDecoration: 'underline', color: 'var(--accent-purple)', fontSize: 'var(--font-size-xs)' }}
          >
            {isRegister ? 'Sign In' : 'Sign Up'}
          </button>
        </div>
      </div>
    </div>
  );
}
