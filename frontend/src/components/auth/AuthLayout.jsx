import React from 'react';
import './Auth.css';

/**
 * 3D Product Background Floating Assets:
 * Floating 3D Lanyard & ID Badge, Visiting Cards stack, Executive Diary/Notebook, and RFID Smart Badges
 * floating on CardFlow's indigo/violet radial glow background.
 */
function Auth3DProducts() {
  return (
    <>
      {/* 3D Lanyard & ID Card Badge (Top-Left / Left) */}
      <div className="auth-bg-product top-left-lanyard">
        <img
          src="/3d_lanyard.png"
          alt="3D ID Card & Lanyard"
          style={{
            width: '260px',
            height: 'auto',
            filter: 'drop-shadow(0 15px 30px rgba(0, 0, 0, 0.5)) mix-blend-mode(screen)',
          }}
        />
      </div>

      {/* 3D Executive Corporate Diary / Notebook (Top-Right) */}
      <div className="auth-bg-product top-right-diary">
        <img
          src="/3d_diary.png"
          alt="3D Corporate Diary"
          style={{
            width: '280px',
            height: 'auto',
            filter: 'drop-shadow(0 18px 35px rgba(0, 0, 0, 0.55))',
          }}
        />
      </div>

      {/* 3D Stack of Visiting Cards / Business Cards (Bottom-Left) */}
      <div className="auth-bg-product bottom-left-cards">
        <img
          src="/3d_cards.png"
          alt="3D Visiting Cards"
          style={{
            width: '290px',
            height: 'auto',
            filter: 'drop-shadow(0 20px 40px rgba(0, 0, 0, 0.6))',
          }}
        />
      </div>

      {/* Floating Vector 3D Smart Badge / Keycard (Bottom-Right) */}
      <div className="auth-bg-product bottom-right-badge">
        <svg viewBox="0 0 200 280" fill="none" style={{ width: '190px', height: 'auto' }}>
          <defs>
            <linearGradient id="badgeBg" x1="0%" y1="0%" x2="100%" y2="100%">
              <stop offset="0%" stopColor="#818cf8" />
              <stop offset="50%" stopColor="#6366f1" />
              <stop offset="100%" stopColor="#312e81" />
            </linearGradient>
            <filter id="badgeShadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="4" dy="14" stdDeviation="10" floodColor="#08031a" floodOpacity="0.6" />
            </filter>
          </defs>
          {/* Card Body */}
          <rect
            x="15"
            y="20"
            width="170"
            height="240"
            rx="16"
            fill="url(#badgeBg)"
            filter="url(#badgeShadow)"
            stroke="rgba(255,255,255,0.3)"
            strokeWidth="2"
          />
          {/* Lanyard Hole Clip */}
          <rect x="85" y="32" width="30" height="8" rx="4" fill="#1e1b4b" opacity="0.8" />
          {/* Photo Avatar Placeholder */}
          <rect
            x="60"
            y="55"
            width="80"
            height="85"
            rx="10"
            fill="rgba(255,255,255,0.2)"
            stroke="rgba(255,255,255,0.4)"
          />
          <circle cx="100" cy="85" r="22" fill="#ffffff" opacity="0.8" />
          <path d="M 75 130 C 75 112 125 112 125 130 Z" fill="#ffffff" opacity="0.8" />
          {/* Text Lines */}
          <rect x="50" y="155" width="100" height="10" rx="5" fill="#ffffff" opacity="0.9" />
          <rect x="65" y="173" width="70" height="7" rx="3.5" fill="#a78bfa" />
          {/* Barcode Strip */}
          <rect x="40" y="200" width="120" height="22" rx="4" fill="rgba(255,255,255,0.95)" />
          <line x1="50" y1="206" x2="50" y2="216" stroke="#0f172a" strokeWidth="3" />
          <line x1="57" y1="206" x2="57" y2="216" stroke="#0f172a" strokeWidth="1.5" />
          <line x1="64" y1="206" x2="64" y2="216" stroke="#0f172a" strokeWidth="4" />
          <line x1="73" y1="206" x2="73" y2="216" stroke="#0f172a" strokeWidth="2" />
          <line x1="81" y1="206" x2="81" y2="216" stroke="#0f172a" strokeWidth="1" />
          <line x1="88" y1="206" x2="88" y2="216" stroke="#0f172a" strokeWidth="3.5" />
          <line x1="97" y1="206" x2="97" y2="216" stroke="#0f172a" strokeWidth="2" />
          <line x1="105" y1="206" x2="105" y2="216" stroke="#0f172a" strokeWidth="4" />
          <line x1="114" y1="206" x2="114" y2="216" stroke="#0f172a" strokeWidth="1.5" />
          <line x1="122" y1="206" x2="122" y2="216" stroke="#0f172a" strokeWidth="3" />
          <line x1="130" y1="206" x2="130" y2="216" stroke="#0f172a" strokeWidth="2" />
          <line x1="140" y1="206" x2="140" y2="216" stroke="#0f172a" strokeWidth="4" />
          <line x1="148" y1="206" x2="148" y2="216" stroke="#0f172a" strokeWidth="2" />
        </svg>
      </div>
    </>
  );
}

export default function AuthLayout({ children }) {
  return (
    <div className="auth-wrapper">
      {/* Radiant Glowing Background Core */}
      <div className="auth-ambient-glow" />

      {/* Floating 3D Product Background Graphics (ID Card, Lanyard, Visiting Cards, Diary) */}
      <Auth3DProducts />

      {/* Centered Single Frosted Glass Form Card */}
      <div className="auth-card">
        {/* Brand Logo Header (Using cardflow_logo_brand.png directly as in sidebar) */}
        <div className="auth-header">
          <img
            src="/cardflow_logo_brand.png"
            alt="CardFlow"
            style={{
              maxHeight: '48px',
              maxWidth: '220px',
              width: '100%',
              objectFit: 'contain',
              margin: '0 auto 8px',
              display: 'block',
              filter: 'drop-shadow(0 2px 10px rgba(0,0,0,0.35))',
            }}
          />
        </div>

        {/* Child View Form */}
        {children}
      </div>
    </div>
  );
}
