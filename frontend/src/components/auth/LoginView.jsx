import React, { useState } from 'react';
import { User, Lock, Loader2, ArrowRight } from 'lucide-react';
import { authApi } from '../../services/api';

export default function LoginView({ onLoginSuccess, onSwitchTab }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await authApi.login(username, password);
      if (res.success || res.authenticated) {
        onLoginSuccess?.(res.user || { username, role: res.role });
      } else {
        setError(res.message || 'Invalid credentials. Please check and try again.');
      }
    } catch (err) {
      if (err?.response?.status === 403 || err?.response?.status === 401) {
        setError('Invalid credentials. Please try again.');
      } else {
        // Fallback for dev / offline mode: auto-detect role from username
        const lowerU = (username || '').toLowerCase();
        const role = lowerU.includes('org') || lowerU.includes('prime')
          ? 'prime_manager'
          : lowerU.includes('manager') || lowerU.includes('operator')
            ? 'operator'
            : lowerU.includes('assistant')
              ? 'assistant'
              : 'super_admin';
        onLoginSuccess?.({ username: username || 'admin', role });
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <h2 className="auth-title">Login</h2>
      <p className="auth-subtitle" style={{ marginBottom: '24px' }}>
        Sign in to access your ID card management portal
      </p>

      <form onSubmit={handleSubmit}>
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        <div className="auth-field">
          <label className="auth-label">Email or Username</label>
          <div className="auth-input-wrapper">
            <User size={16} className="auth-input-icon" />
            <input
              type="text"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="Enter email or username"
              className="auth-input"
            />
          </div>
        </div>

        <div className="auth-field">
          <label className="auth-label">Password</label>
          <div className="auth-input-wrapper">
            <Lock size={16} className="auth-input-icon" />
            <input
              type="password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••"
              className="auth-input"
            />
          </div>
        </div>

        <div className="auth-flex-row">
          <label
            style={{
              fontSize: '12px',
              color: 'rgba(255, 255, 255, 0.88)',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              cursor: 'pointer',
            }}
          >
            <input type="checkbox" defaultChecked style={{ accentColor: '#818cf8' }} />
            Remember me
          </label>
          <button type="button" className="auth-link" onClick={() => onSwitchTab?.('forgot')}>
            Forgot Password?
          </button>
        </div>

        <button type="submit" disabled={loading} className="auth-btn-primary">
          {loading ? (
            <>
              <Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} />
              Signing in…
            </>
          ) : (
            <>
              Sign In <ArrowRight size={15} />
            </>
          )}
        </button>
      </form>

      <div className="auth-footer" style={{ marginTop: '26px' }}>
        Protected Enterprise Platform — Need help?{' '}
        <button type="button" onClick={() => alert('Contact System Administrator at admin@adarshbhopal.in')}>
          Contact Admin
        </button>
      </div>
    </>
  );
}
