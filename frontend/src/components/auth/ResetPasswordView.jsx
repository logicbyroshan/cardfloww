import React, { useState } from 'react';
import { Lock, Loader2, ArrowLeft, CheckCircle2 } from 'lucide-react';

export default function ResetPasswordView({ onSwitchTab }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [success, setSuccess] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = (e) => {
    e.preventDefault();
    if (password.length < 6) {
      setError('Password must be at least 6 characters long.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match. Please re-enter.');
      return;
    }

    setLoading(true);
    setError('');

    setTimeout(() => {
      setLoading(false);
      setSuccess(true);
    }, 800);
  };

  return (
    <>
      <h2 className="auth-title">Reset Password</h2>
      <p className="auth-subtitle" style={{ marginBottom: '22px' }}>
        Create a new, strong password for your CardFlow account
      </p>

      {success ? (
        <div className="auth-success-box" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} color="#4ade80" />
            <strong style={{ color: '#ffffff' }}>Password Updated!</strong>
          </div>
          <span style={{ fontSize: '12px' }}>
            Your password has been reset successfully. You can now sign in with your new password.
          </span>
          <button
            type="button"
            className="auth-btn-primary"
            style={{ marginTop: '10px', height: '38px' }}
            onClick={() => onSwitchTab?.('login')}
          >
            Back to Sign In
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit}>
          {error && (
            <div className="auth-error-box">
              <span>{error}</span>
            </div>
          )}

          <div className="auth-field">
            <label className="auth-label">New Password</label>
            <div className="auth-input-wrapper">
              <Lock size={16} className="auth-input-icon" />
              <input
                type="password"
                required
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••"
                className="auth-input"
              />
            </div>
          </div>

          <div className="auth-field">
            <label className="auth-label">Confirm New Password</label>
            <div className="auth-input-wrapper">
              <Lock size={16} className="auth-input-icon" />
              <input
                type="password"
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••"
                className="auth-input"
              />
            </div>
          </div>

          <button type="submit" disabled={loading} className="auth-btn-primary">
            {loading ? (
              <>
                <Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} />
                Updating Password…
              </>
            ) : (
              'Reset Password'
            )}
          </button>
        </form>
      )}

      {!success && (
        <div style={{ marginTop: '24px', textAlign: 'center' }}>
          <button
            type="button"
            className="auth-link"
            style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
            onClick={() => onSwitchTab?.('login')}
          >
            <ArrowLeft size={14} /> Back to Sign In
          </button>
        </div>
      )}
    </>
  );
}
