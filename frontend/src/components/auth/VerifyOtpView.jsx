import React, { useState, useRef } from 'react';
import { ArrowLeft, Loader2, KeyRound } from 'lucide-react';

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
      onVerifySuccess ? onVerifySuccess() : onSwitchTab?.('reset-password');
    }, 800);
  };

  return (
    <>
      <div style={{ textAlign: 'center', marginBottom: '16px' }}>
        <div
          style={{
            width: '42px',
            height: '42px',
            borderRadius: '12px',
            background: 'rgba(255, 255, 255, 0.15)',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            marginBottom: '10px',
          }}
        >
          <KeyRound size={22} color="#ffffff" />
        </div>
      </div>

      <h2 className="auth-title" style={{ textAlign: 'center' }}>
        Two-Factor Verification
      </h2>
      <p className="auth-subtitle" style={{ textAlign: 'center', marginBottom: '20px' }}>
        Enter the 6-digit verification code sent to your registered email/phone
      </p>

      <form onSubmit={handleSubmit}>
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        <div className="auth-otp-row">
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
              className="auth-otp-input"
              autoFocus={idx === 0}
            />
          ))}
        </div>

        <button type="submit" disabled={loading} className="auth-btn-primary">
          {loading ? (
            <>
              <Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} />
              Verifying Code…
            </>
          ) : (
            'Verify & Continue'
          )}
        </button>
      </form>

      <div style={{ marginTop: '24px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <button
          type="button"
          className="auth-link"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          onClick={() => onSwitchTab?.('login')}
        >
          <ArrowLeft size={14} /> Back to Sign In
        </button>

        <button type="button" className="auth-link" onClick={() => setError('Resent OTP to registered contact.')}>
          Resend OTP
        </button>
      </div>
    </>
  );
}
