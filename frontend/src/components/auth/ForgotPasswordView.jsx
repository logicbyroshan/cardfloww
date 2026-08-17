import React, { useState } from 'react';
import { Mail, ArrowLeft, Loader2, CheckCircle2 } from 'lucide-react';
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
      setSuccessMsg(`Password reset link and OTP have been sent to ${email}`);
    } catch (err) {
      setError('Unable to send reset email. Please verify your email address.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <>
      <div className="auth-form-header">
        <h2 className="auth-title">Forgot Password?</h2>
        <p className="auth-subtitle">
          Enter your account email address and we'll send you a password reset link & verification code.
        </p>
      </div>

      {successMsg ? (
        <div className="auth-success-box" style={{ flexDirection: 'column', alignItems: 'flex-start', gap: '10px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <CheckCircle2 size={18} color="#4ade80" />
            <strong style={{ color: '#ffffff' }}>Check your inbox</strong>
          </div>
          <span style={{ fontSize: '12.5px', lineHeight: '1.4' }}>{successMsg}</span>
          <button
            type="button"
            className="auth-btn-primary"
            style={{ marginTop: '8px', height: '42px', fontSize: '13px' }}
            onClick={() => onSwitchTab?.('otp')}
          >
            Enter Verification Code
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
            <label className="auth-label">Account Email Address</label>
            <div className="auth-input-wrapper">
              <Mail size={17} className="auth-input-icon" />
              <input
                type="email"
                required
                autoFocus
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="name@institution.edu"
                className="auth-input"
                autoComplete="email"
              />
            </div>
          </div>

          <button type="submit" disabled={loading} className="auth-btn-primary">
            {loading ? (
              <>
                <Loader2 size={17} className="auth-btn-spinner" />
                <span>Sending Reset Link…</span>
              </>
            ) : (
              <span>Send Reset Link</span>
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
