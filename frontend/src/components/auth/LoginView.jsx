import React, { useState } from 'react';
import { Loader2, ShieldCheck } from 'lucide-react';
import { authApi } from '../../services/api';

const DEMO_ACCOUNTS = [
  { role: 'Prime Admin', username: 'admin', password: 'admin123', label: 'Platform Owner' },
  { role: 'Prime Manager', username: 'org_admin', password: 'password123', label: 'School / Org Owner' },
  { role: 'Staff Operator', username: 'operator_demo', password: 'password123', label: 'Print Operator' },
  { role: 'Data Assistant', username: 'stxavier_assistant', password: 'password123', label: 'Class Assistant' },
  { role: 'Studio Studio', username: 'photo_demo', password: 'password123', label: 'Photographer' },
];

export default function LoginView({ onLoginSuccess, onSwitchTab }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [rememberMe, setRememberMe] = useState(true);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showDemoPills, setShowDemoPills] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    setLoading(true);
    setError('');
    try {
      const res = await authApi.login(username, password, rememberMe);
      if (res.success || res.authenticated) {
        onLoginSuccess?.(res.user || { username, role: res.role });
      } else {
        setError(res.message || 'Invalid credentials. Please check and try again.');
      }
    } catch (err) {
      if (err?.response?.status === 403 || err?.response?.status === 401 || err?.response?.status === 400) {
        setError(err.response?.data?.message || 'Invalid username or password.');
      } else {
        setError(err?.response?.data?.message || 'Unable to connect to authentication server.');
      }
    } finally {
      setLoading(false);
    }
  };

  const handleQuickFill = (acc) => {
    setUsername(acc.username);
    setPassword(acc.password || 'password123');
    setError('');
  };

  return (
    <>
      <div className="auth-form-header">
        <h1 className="auth-title">Sign In</h1>
        <p className="auth-subtitle">Keep it all together and you'll be fine</p>
      </div>

      <form onSubmit={handleSubmit} className="auth-cosmic-form">
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        {/* Email or Phone Field */}
        <div className="auth-input-group">
          <input
            type="text"
            required
            autoFocus
            value={username}
            onChange={(e) => setUsername(e.target.value)}
            placeholder="Email or Phone"
            className="auth-cosmic-input"
            autoComplete="username"
          />
        </div>

        {/* Password Field with Show/Hide text toggle */}
        <div className="auth-input-group auth-password-group">
          <input
            type={showPassword ? 'text' : 'password'}
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password"
            className="auth-cosmic-input"
            autoComplete="current-password"
          />
          <button
            type="button"
            className="auth-show-btn"
            onClick={() => setShowPassword(!showPassword)}
          >
            {showPassword ? 'Hide' : 'Show'}
          </button>
        </div>

        {/* Forgot Password link */}
        <div className="auth-forgot-row">
          <button
            type="button"
            className="auth-forgot-link"
            onClick={() => onSwitchTab?.('forgot')}
          >
            Forgot Password
          </button>
        </div>

        {/* Sign In Primary Button */}
        <button type="submit" disabled={loading} className="auth-cosmic-submit-btn">
          {loading ? (
            <>
              <Loader2 size={16} className="auth-btn-spinner" />
              <span>Signing In…</span>
            </>
          ) : (
            <span>Sign In</span>
          )}
        </button>

        {/* or Divider */}
        <div className="auth-cosmic-divider">
          <span>or</span>
        </div>

        {/* Sign in with Apple */}
        <button
          type="button"
          className="auth-apple-btn"
          onClick={() => {
            // For testing/quick-access, fills with admin or notifies user
            setUsername('admin');
            setPassword('admin123');
            setError('');
          }}
          title="Sign in with Apple (fills demo credentials)"
        >
          <svg viewBox="0 0 170 170" width="15" height="15" fill="currentColor" aria-hidden="true">
            <path d="M150.37 130.25c-2.45 5.66-5.35 10.87-8.71 15.66-4.58 6.53-8.33 11.05-11.22 13.56-4.48 4.12-9.28 6.23-14.42 6.35-3.69 0-8.14-1.05-13.32-3.18-5.19-2.12-9.97-3.17-14.34-3.17-4.58 0-9.49 1.05-14.75 3.17-5.26 2.13-9.5 3.24-12.74 3.35-4.35.13-9.16-1.9-14.42-6.08-3.69-3.08-7.77-7.98-12.24-14.7-6.53-9.82-11.66-21.08-15.39-33.77-3.73-12.69-5.6-24.7-5.6-36.03 0-14.28 3.59-26.24 10.77-35.88 7.18-9.64 16.27-14.59 27.27-14.85 4.79 0 10.23 1.25 16.32 3.75 6.09 2.5 10.05 3.82 11.89 3.96 1.63-.14 5.72-1.5 12.28-4.08 6.56-2.58 12.18-3.8 16.86-3.65 12.48.64 22.84 5.39 31.08 14.26-10.99 6.64-16.38 15.82-16.18 27.53.2 9.54 3.99 17.51 11.37 23.91 7.38 6.4 16.03 10.15 25.96 11.26-2.22 6.78-4.79 13.56-7.72 20.34zM119.22 31.84c0-7.23 2.61-13.99 7.83-20.28 5.22-6.29 11.69-10.15 19.41-11.56.22 1.09.33 2.18.33 3.27 0 7.13-2.72 13.94-8.15 20.44-5.43 6.5-12.01 10.37-19.74 11.6-.22-1.09-.33-2.18-.33-3.47z" />
          </svg>
          <span>Sign in with Apple</span>
        </button>

        {/* Quick Demo Roles Presets */}
        <div className="auth-demo-switcher">
          <button
            type="button"
            className="auth-demo-toggle-btn"
            onClick={() => setShowDemoPills(!showDemoPills)}
          >
            <ShieldCheck size={13} color="#c084fc" />
            <span>{showDemoPills ? 'Hide Demo Role Quick Fill' : 'Quick Demo Role Presets'}</span>
          </button>

          {showDemoPills && (
            <div className="auth-demo-pills-grid">
              {DEMO_ACCOUNTS.map((acc, idx) => (
                <button
                  key={idx}
                  type="button"
                  className="auth-demo-pill"
                  onClick={() => handleQuickFill(acc)}
                >
                  <span className="demo-pill-role">{acc.role}</span>
                  <span className="demo-pill-user">@{acc.username}</span>
                </button>
              ))}
            </div>
          )}
        </div>
      </form>
    </>
  );
}
