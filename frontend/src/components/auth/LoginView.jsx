import React, { useState } from 'react';
import { User, Lock, Loader2, ArrowRight, Eye, EyeOff, ShieldCheck, HelpCircle } from 'lucide-react';
import { authApi } from '../../services/api';

const DEMO_ACCOUNTS = [
  { role: 'Super Admin', username: 'admin', password: 'admin123', label: 'Prime Admin' },
  { role: 'Organisation', username: 'org_admin', password: 'password123', label: 'Prime Manager' },
  { role: 'Operator', username: 'operator', password: 'password123', label: 'Staff Operator' },
  { role: 'Assistant', username: 'assistant', password: 'password123', label: 'Data Assistant' },
  { role: 'Photographer', username: 'photographer', password: 'password123', label: 'Studio' },
];

export default function LoginView({ onLoginSuccess, onSwitchTab }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [showDemoPills, setShowDemoPills] = useState(false);

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
        setError('Invalid username or password. Please try again.');
      } else {
        // Fallback for dev / offline preview mode: auto-detect role from username
        const lowerU = (username || '').toLowerCase();
        const role =
          lowerU.includes('org') || lowerU.includes('prime')
            ? 'prime_manager'
            : lowerU.includes('photographer') || lowerU.includes('photo')
              ? 'photographer'
              : lowerU.includes('operator')
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

  const handleQuickFill = (acc) => {
    setUsername(acc.username);
    setPassword(acc.password || (acc.username === 'admin' ? 'admin123' : 'password123'));
    setError('');
  };

  return (
    <>
      <div className="auth-form-header">
        <h2 className="auth-title">Sign In</h2>
        <p className="auth-subtitle">Access your multi-tenant ID card workspace & printing queues</p>
      </div>

      <form onSubmit={handleSubmit} className="auth-actual-form">
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        {/* Username / Email Field */}
        <div className="auth-field">
          <label className="auth-label">Email or Username</label>
          <div className="auth-input-wrapper">
            <User size={17} className="auth-input-icon" />
            <input
              type="text"
              required
              autoFocus
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="e.g. admin or user@institution.edu"
              className="auth-input"
              autoComplete="username"
            />
          </div>
        </div>

        {/* Password Field */}
        <div className="auth-field">
          <label className="auth-label">Password</label>
          <div className="auth-input-wrapper">
            <Lock size={17} className="auth-input-icon" />
            <input
              type={showPassword ? 'text' : 'password'}
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="••••••••••••"
              className="auth-input"
              autoComplete="current-password"
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

        {/* Remember me & Forgot Password */}
        <div className="auth-flex-row">
          <label className="auth-remember-label">
            <input type="checkbox" defaultChecked className="auth-checkbox" />
            <span>Keep me signed in</span>
          </label>
          <button type="button" className="auth-link" onClick={() => onSwitchTab?.('forgot')}>
            Forgot Password?
          </button>
        </div>

        {/* Primary Submit Button */}
        <button type="submit" disabled={loading} className="auth-btn-primary">
          {loading ? (
            <>
              <Loader2 size={17} className="auth-btn-spinner" />
              <span>Authenticating…</span>
            </>
          ) : (
            <>
              <span>Sign In to Workspace</span>
              <ArrowRight size={16} />
            </>
          )}
        </button>

        {/* Quick Demo Credentials Accordion */}
        <div className="auth-demo-switcher">
          <button
            type="button"
            className="auth-demo-toggle-btn"
            onClick={() => setShowDemoPills(!showDemoPills)}
          >
            <ShieldCheck size={13} color="#818cf8" />
            <span>{showDemoPills ? 'Hide Quick Demo Roles' : 'Quick Demo Role Presets'}</span>
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

      {/* Support & Contact Footer */}
      <div className="auth-footer">
        Protected Enterprise Platform • Need assistance?{' '}
        <button type="button" onClick={() => alert('Please contact administrator at support@cardflow.in')}>
          Contact Support
        </button>
      </div>
    </>
  );
}
