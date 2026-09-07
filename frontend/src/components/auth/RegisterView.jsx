import React, { useState } from 'react';
import { Loader2, ArrowLeft } from 'lucide-react';

export default function RegisterView({ onSwitchTab, onLoginSuccess }) {
  const [orgName, setOrgName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');

    setTimeout(() => {
      setLoading(false);
      if (onLoginSuccess) {
        onLoginSuccess({ username: email, role: 'manager' });
      } else {
        onSwitchTab?.('login');
      }
    }, 800);
  };

  return (
    <>
      <div className="auth-form-header">
        <h1 className="auth-title">Create Account</h1>
        <p className="auth-subtitle">Join CardFlow multi-tenant identity workspace</p>
      </div>

      <form onSubmit={handleSubmit} className="auth-cosmic-form">
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        <div className="auth-input-group">
          <input
            type="text"
            required
            autoFocus
            value={orgName}
            onChange={(e) => setOrgName(e.target.value)}
            placeholder="Institution / Organization Name"
            className="auth-cosmic-input"
          />
        </div>

        <div className="auth-input-group">
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Official Email Address"
            className="auth-cosmic-input"
            autoComplete="email"
          />
        </div>

        <div className="auth-input-group">
          <input
            type="password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="auth-cosmic-input"
            autoComplete="new-password"
          />
        </div>

        <button type="submit" disabled={loading} className="auth-cosmic-submit-btn" style={{ marginTop: '6px' }}>
          {loading ? (
            <>
              <Loader2 size={16} className="auth-btn-spinner" />
              <span>Creating Account…</span>
            </>
          ) : (
            <span>Create Free Account</span>
          )}
        </button>
      </form>

      <div className="auth-cosmic-footer">
        <span>Already have an account? </span>
        <button
          type="button"
          className="auth-join-btn"
          onClick={() => onSwitchTab?.('login')}
        >
          Sign In
        </button>
      </div>
    </>
  );
}
