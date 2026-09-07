import React, { useState } from 'react';
import { Loader2, CheckCircle2 } from 'lucide-react';
import { authApi } from '../../services/api';

export default function ForgotPasswordView({ onSwitchTab }) {
  const [email, setEmail] = useState('');
  const [loading, setLoading] = useState(false);
  const [successMsg, setSuccessMsg] = useState('');
  const [error, setError] = useState('');

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    setSuccessMsg('');

    try {
      if (authApi.requestPasswordReset) {
        await authApi.requestPasswordReset(email);
      }
      setSuccessMsg(`Password reset instructions sent to ${email}`);
    } catch (err) {
      setError('Unable to send reset email. Please verify your email address.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="auth-form-header">
        <h1 className="auth-title">Reset Password</h1>
        <p className="auth-subtitle">Enter your registered email to receive a recovery code</p>
      </div>

      {successMsg ? (
        <div className="auth-success-box" style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} color="#4ade80" />
            <strong style={{ color: '#ffffff' }}>Instructions Sent</strong>
          </div>
          <span style={{ fontSize: '12.5px', lineHeight: '1.4' }}>{successMsg}</span>
          <button
            type="button"
            className="auth-cosmic-submit-btn"
            style={{ marginTop: '10px', height: '40px', fontSize: '13px' }}
            onClick={() => onSwitchTab?.('otp')}
          >
            Enter Verification Code
          </button>
        </div>
      ) : (
        <form onSubmit={handleSubmit} className="auth-cosmic-form">
          {error && (
            <div className="auth-error-box">
              <span>{error}</span>
            </div>
          )}

          <div className="auth-input-group">
            <input
              type="email"
              required
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="Account Email Address"
              className="auth-cosmic-input"
              autoComplete="email"
            />
          </div>

          <button type="submit" disabled={loading} className="auth-cosmic-submit-btn" style={{ marginTop: '6px' }}>
            {loading ? (
              <>
                <Loader2 size={16} className="auth-btn-spinner" />
                <span>Sending Code…</span>
              </>
            ) : (
              <span>Send Recovery Code</span>
            )}
          </button>
        </form>
      )}

      <div className="auth-cosmic-footer">
        <span>Remember your credentials? </span>
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
