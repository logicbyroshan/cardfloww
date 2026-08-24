import React, { useState, useEffect } from 'react';

export default function Preloader({ onFinished }) {
  const [phase, setPhase] = useState(() => {
    try {
      if (sessionStorage.getItem('cf_has_preloaded') === 'true') {
        return 'done';
      }
    } catch (_) {}
    return 'animating'; // 'animating' -> 'fadeout' -> 'done'
  });

  const [progress, setProgress] = useState(0);

  useEffect(() => {
    if (phase === 'done') {
      onFinished?.();
      return;
    }

    try {
      sessionStorage.setItem('cf_has_preloaded', 'true');
    } catch (_) {}

    const startTime = Date.now();
    const duration = 1000; // Smooth 1.0s fast, sleek load time

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(100, Math.floor((elapsed / duration) * 100));
      setProgress(pct);

      if (elapsed >= duration) {
        clearInterval(interval);
        setPhase('fadeout');
        setTimeout(() => {
          setPhase('done');
          onFinished?.();
        }, 400);
      }
    }, 20);

    return () => clearInterval(interval);
  }, [phase, onFinished]);

  if (phase === 'done') return null;

  const isFadeOut = phase === 'fadeout';

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        width: '100vw',
        height: '100vh',
        zIndex: 999999,
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#0f172a',
        opacity: isFadeOut ? 0 : 1,
        transition: 'opacity 0.4s ease-out, filter 0.4s ease-out',
        filter: isFadeOut ? 'blur(8px)' : 'blur(0px)',
        pointerEvents: isFadeOut ? 'none' : 'auto',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      {/* Brand Logo with gentle ambient glow */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          gap: '24px',
          animation: 'cfLogoPulse 2s ease-in-out infinite alternate',
        }}
      >
        <img
          src="/cardflow_logo_brand.png"
          onError={(e) => {
            if (!e.target.src.endsWith('/static/cardflow_logo_brand.png')) {
              e.target.src = '/static/cardflow_logo_brand.png';
            }
          }}
          alt="CardFlow"
          style={{
            maxHeight: '48px',
            maxWidth: '190px',
            width: 'auto',
            objectFit: 'contain',
            filter: 'drop-shadow(0 4px 20px rgba(56, 189, 248, 0.35))',
          }}
        />

        {/* Slim glowing animated progress bar */}
        <div
          style={{
            width: '160px',
            height: '3px',
            borderRadius: '3px',
            background: 'rgba(255, 255, 255, 0.1)',
            overflow: 'hidden',
            position: 'relative',
          }}
        >
          <div
            style={{
              width: `${progress}%`,
              height: '100%',
              borderRadius: '3px',
              background: 'linear-gradient(90deg, #3b82f6, #818cf8, #38bdf8)',
              boxShadow: '0 0 10px #38bdf8',
              transition: 'width 0.05s ease-out',
            }}
          />
        </div>

        {/* Status text */}
        <div
          style={{
            fontSize: '11px',
            fontWeight: 600,
            color: '#94a3b8',
            letterSpacing: '0.06em',
            textTransform: 'uppercase',
          }}
        >
          {progress >= 90 ? 'Ready' : 'Loading Workspace…'}
        </div>
      </div>

      <style>{`
        @keyframes cfLogoPulse {
          0% { transform: scale(0.98); opacity: 0.92; }
          100% { transform: scale(1); opacity: 1; }
        }
      `}</style>
    </div>
  );
}
