import React, { useState } from 'react';
import { User, Mail, Lock, Building, Loader2, ArrowLeft } from 'lucide-react';

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
      <h2 className="auth-title">Create Account</h2>
      <p className="auth-subtitle" style={{ marginBottom: '20px' }}>
        Register your organization for CardFlow Enterprise Platform
      </p>

      <form onSubmit={handleSubmit}>
        {error && (
          <div className="auth-error-box">
            <span>{error}</span>
          </div>
        )}

        <div className="auth-field">
          <label className="auth-label">Organization Name</label>
          <div className="auth-input-wrapper">
            <Building size={16} className="auth-input-icon" />
            <input
              type="text"
              required
              autoFocus
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              placeholder="Adarsh Public School"
              className="auth-input"
            />
          </div>
        </div>

        <div className="auth-field">
          <label className="auth-label">Email Address</label>
          <div className="auth-input-wrapper">
            <Mail size={16} className="auth-input-icon" />
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="admin@adarsh.edu.in"
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

        <button type="submit" disabled={loading} className="auth-btn-primary">
          {loading ? (
            <>
              <Loader2 size={16} style={{ animation: 'spin 0.8s linear infinite' }} />
              Registering Account…
            </>
          ) : (
            'Create Free Account'
          )}
        </button>
      </form>

      <div style={{ marginTop: '20px', textAlign: 'center' }}>
        <button
          type="button"
          className="auth-link"
          style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}
          onClick={() => onSwitchTab?.('login')}
        >
          <ArrowLeft size={14} /> Already have an account? Sign In
        </button>
      </div>
    </>
  );
}
