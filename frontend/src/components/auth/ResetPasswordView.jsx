import React, { useState } from 'react';
import { Lock, Loader2, ArrowLeft, CheckCircle2, Eye, EyeOff } from 'lucide-react';

export default function ResetPasswordView({ onSwitchTab }) {
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
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
      <div className="auth-form-header">
        <h2 className="auth-title">Reset Password</h2>
        <p className="auth-subtitle">Create a new secure password for your CardFlow account.</p>
      </div>

      {success ? (
        <div className="auth-success-box" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} color="#4ade80" />
            <strong style={{ color: '#ffffff' }}>Password Updated!</strong>
          </div>
          <span style={{ fontSize: '12.5px', lineHeight: '1.4' }}>
            Your password has been reset successfully. You can now sign in with your new credentials.
          </span>
          <button
            type="button"
            className="auth-btn-primary"
            style={{ marginTop: '8px', height: '42px', fontSize: '13px' }}
            onClick={() => onSwitchTab?.('login')}
          >
            Sign In Now
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="auth-actual-form">
          {error && (
            <div className="auth-error-box">
              <span>{error}</span>
            </div>
          )}

          <div className="auth-field">
            <label className="auth-label">New Password</label>
            <div className="auth-input-wrapper">
              <Lock size={17} className="auth-input-icon" />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                autoFocus
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="••••••••••••"
                className="auth-input"
                style={{ paddingRight: '42px' }}
              />
              <button
                type="button"
                className="auth-password-toggle"
                onClick={() => setShowPassword(!showPassword)}
                aria-label={showPassword ? 'Hide password' : 'Show password'}
                tabIndex={-1}
              >
                {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
          </div>

          <div className="auth-field">
            <label className="auth-label">Confirm New Password</label>
            <div className="auth-input-wrapper">
              <Lock size={17} className="auth-input-icon" />
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={confirmPassword}
                onChange={(e) => setConfirmPassword(e.target.value)}
                placeholder="••••••••••••"
                className="auth-input"
              />
            </div>
          </div>

          <button type="submit" disabled={loading} className="auth-btn-primary">
            {loading ? (
              <>
                <Loader2 size={17} className="auth-btn-spinner" />
                <span>Updating Password…</span>
              </>
            ) : (
              <span>Update Password</span>
            )}
          </button>
        </form>
      )}

      <div style={{ marginTop: '20px', textAlign: 'center' }}>
        <button
          type="button"
          className="auth-link"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '13px' }}
          onClick={() => onSwitchTab?.('login')}
        >
          <ArrowLeft size={14} />
          <span>Back to Sign In</span>
        </button>
      </div>
    </>
  );
}
