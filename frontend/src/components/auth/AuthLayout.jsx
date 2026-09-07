import React from 'react';
import './Auth.css';

export default function AuthLayout({ children }) {
  return (
    <div className="auth-cosmic-viewport">
      {/* High-res Cosmic Deep Space Background */}
      <div className="auth-cosmic-bg" />

      {/* Atmospheric Eclipse Limb Glow & Flare */}
      <div className="auth-cosmic-flare" />
      <div className="auth-cosmic-dust" />

      {/* Centered Floating Glassmorphic Container */}
      <main className="auth-cosmic-stage">
        <div className="auth-cosmic-card">
          {/* Top-Right Neon Purple Glow Sweep matching celestial eclipse */}
          <div className="auth-card-corner-glow" />

          {/* Form Content */}
          <div className="auth-card-content">
            {children}
          </div>
        </div>
      </main>
    </div>
  );
}
