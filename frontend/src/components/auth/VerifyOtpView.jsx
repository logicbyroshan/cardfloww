import React, { useState, useRef } from 'react';
import { Loader2, KeyRound } from 'lucide-react';

export default function VerifyOtpView({ onSwitchTab, onVerifySuccess }) {
  const [otp, setOtp] = useState(['', '', '', '', '', '']);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const inputRefs = useRef([]);

  const handleChange = (index, value) => {
    if (isNaN(value)) return;
    const newOtp = [...otp];
    newOtp[index] = value.slice(-1);
    setOtp(newOtp);

    // Auto-advance cursor
    if (value && index < 5) {
      inputRefs.current[index + 1]?.focus();
    }
  };

  const handleKeyDown = (index, e) => {
    if (e.key === 'Backspace' && !otp[index] && index > 0) {
      inputRefs.current[index - 1]?.focus();
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    const code = otp.join('');
    if (code.length < 6) {
      setError('Please enter the full 6-digit OTP code.');
      return;
    }

    setLoading(true);
    setError('');

    setTimeout(() => {
      setLoading(false);
      if (onVerifySuccess) {
        onVerifySuccess();
      } else {
        onSwitchTab?.('reset-password');
      }
    }, 800);
  };

  return (
    <>
      <div className="auth-form-header" style={{ textAlign: 'center' }}>
        <div
          style={{
            width: '44px',
            height: '44px',
            borderRadius: '12px',
            background: 'rgba(168, 85, 247, 0.15)',
            border: '1px solid rgba(168, 85, 247, 0.3)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '12px',
          }}
        >
          <KeyRound size={22} color="#c084fc" />
        </div>
        <h1 className="auth-title">Enter Verification Code</h1>
        <p className="auth-subtitle">
          Please enter the 6-digit security code sent to your email.
        </p>
      </div>

      <form onSubmit={handleSubmit} className="auth-cosmic-form">
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        <div
          style={{
            display: 'flex',
            justifyContent: 'center',
            gap: '8px',
            margin: '8px 0 16px 0',
          }}
        >
          {otp.map((digit, idx) => (
            <input
              key={idx}
              ref={(el) => (inputRefs.current[idx] = el)}
              type="text"
              inputMode="numeric"
              maxLength={1}
              value={digit}
              onChange={(e) => handleChange(idx, e.target.value)}
              onKeyDown={(e) => handleKeyDown(idx, e)}
              className="auth-cosmic-input"
              style={{
                width: '44px',
                height: '48px',
                textAlign: 'center',
                fontSize: '18px',
                fontWeight: 700,
                padding: 0,
              }}
              autoFocus={idx === 0}
            />
          ))}
        </div>

        <button type="submit" disabled={loading} className="auth-cosmic-submit-btn">
          {loading ? (
            <>
              <Loader2 size={16} className="auth-btn-spinner" />
              <span>Verifying Code…</span>
            </>
          ) : (
            <span>Verify & Continue</span>
          )}
        </button>
      </form>

      <div className="auth-cosmic-footer">
        <span>Wrong account? </span>
        <button
          type="button"
          className="auth-join-btn"
          onClick={() => onSwitchTab?.('login')}
        >
          Back to Sign In
        </button>
      </div>
    </>
  );
}
