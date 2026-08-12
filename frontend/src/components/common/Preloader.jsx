import React, { useState, useEffect } from 'react';

const LOADING_STEPS = [
  'Initializing CardFlow Core…',
  'Verifying Security Protocols…',
  'Loading Organization Engine…',
  'System Ready',
];

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
  const [stepIndex, setStepIndex] = useState(0);

  useEffect(() => {
    if (phase === 'done') {
      onFinished?.();
      return;
    }

    try {
      sessionStorage.setItem('cf_has_preloaded', 'true');
    } catch (_) {}

    // Animate progress 0 -> 100%
    const startTime = Date.now();
    const duration = 1200;

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(100, Math.floor((elapsed / duration) * 100));
      setProgress(pct);

      if (pct < 30) setStepIndex(0);
      else if (pct < 65) setStepIndex(1);
      else if (pct < 90) setStepIndex(2);
      else setStepIndex(3);

      if (elapsed >= duration) {
        clearInterval(interval);
        setPhase('fadeout');
        setTimeout(() => {
          setPhase('done');
          onFinished?.();
        }, 550);
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
        alignItems: 'center',
        justifyContent: 'center',
        background: 'linear-gradient(135deg, #0b1329 0%, #002b66 50%, #1e1e2e 100%)',
        opacity: isFadeOut ? 0 : 1,
        transform: isFadeOut ? 'scale(1.04)' : 'scale(1)',
        filter: isFadeOut ? 'blur(10px)' : 'blur(0px)',
        transition:
          'opacity 0.55s cubic-bezier(0.4, 0, 0.2, 1), transform 0.55s cubic-bezier(0.4, 0, 0.2, 1), filter 0.55s ease',
        overflow: 'hidden',
        pointerEvents: isFadeOut ? 'none' : 'auto',
      }}
    >
      {/* Background Mesh Grid Lines Pattern */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(to right, rgba(255, 255, 255, 0.05) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.05) 1px, transparent 1px)
          `,
          backgroundSize: '48px 48px',
          opacity: 0.6,
          pointerEvents: 'none',
        }}
      />

      {/* Glowing Ambient Radial Blobs */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden' }}>
        <div
          style={{
            position: 'absolute',
            top: '15%',
            left: '25%',
            width: '450px',
            height: '450px',
            borderRadius: '50%',
            background:
              'radial-gradient(circle, rgba(0, 180, 255, 0.4) 0%, rgba(37, 99, 235, 0.2) 50%, transparent 70%)',
            filter: 'blur(80px)',
            animation: 'preloaderPulseGlow 4s ease-in-out infinite alternate',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: '15%',
            right: '25%',
            width: '500px',
            height: '500px',
            borderRadius: '50%',
            background:
              'radial-gradient(circle, rgba(139, 92, 246, 0.35) 0%, rgba(6, 182, 212, 0.2) 50%, transparent 70%)',
            filter: 'blur(90px)',
            animation: 'preloaderPulseGlow 5s ease-in-out infinite alternate-reverse',
          }}
        />
      </div>

      {/* Main Glassmorphic Container Card */}
      <div
        style={{
          position: 'relative',
          zIndex: 2,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          padding: '40px 48px',
          borderRadius: '24px',
          background: 'rgba(15, 23, 42, 0.75)',
          backdropFilter: 'blur(24px)',
          WebkitBackdropFilter: 'blur(24px)',
          border: '1px solid rgba(255, 255, 255, 0.18)',
          boxShadow: '0 30px 70px -15px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.25)',
          maxWidth: '440px',
          width: '90%',
          animation: 'preloaderCardAppear 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        }}
      >
        {/* Animated Brand Logo Container */}
        <div
          style={{
            position: 'relative',
            width: '120px',
            height: '60px',
            marginBottom: '20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'rgba(255, 255, 255, 0.06)',
            borderRadius: '16px',
            border: '1px solid rgba(255, 255, 255, 0.15)',
            padding: '8px 16px',
            boxShadow: '0 8px 24px rgba(0, 0, 0, 0.3), inset 0 1px 0 rgba(255, 255, 255, 0.2)',
          }}
        >
          <img
            src="/static/cardflow_logo_brand.png"
            onError={(e) => {
              if (!e.target.src.endsWith('/favicon.png')) {
                e.target.src = '/static/favicon.png';
              }
            }}
            alt="CardFlow Logo"
            style={{
              maxHeight: '40px',
              maxWidth: '100px',
              width: '100%',
              objectFit: 'contain',
              filter: 'drop-shadow(0 2px 8px rgba(0, 180, 255, 0.5))',
            }}
          />
        </div>

        {/* Title */}
        <h1
          style={{
            fontFamily: "'Saira Semi Condensed', sans-serif",
            fontSize: '24px',
            fontWeight: 800,
            background: 'linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #93c5fd 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '0.05em',
            margin: '0 0 4px 0',
            textTransform: 'uppercase',
            lineHeight: 1.2,
          }}
        >
          CardFlow System
        </h1>

        {/* Tagline Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '3px 12px',
            borderRadius: '20px',
            background: 'rgba(0, 180, 255, 0.15)',
            border: '1px solid rgba(0, 180, 255, 0.35)',
            color: '#7dd3fc',
            fontSize: '11px',
            fontWeight: 700,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            marginBottom: '24px',
          }}
        >
          <span
            style={{
              width: '6px',
              height: '6px',
              borderRadius: '50%',
              background: '#00b4ff',
              boxShadow: '0 0 8px #00b4ff',
            }}
          />
          Enterprise ID Card Management
        </div>

        {/* Progress Track & Counter */}
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '11px',
              color: '#94a3b8',
              fontWeight: 600,
            }}
          >
            <span>{LOADING_STEPS[stepIndex]}</span>
            <span style={{ color: '#60a5fa', fontWeight: 700 }}>{progress}%</span>
          </div>

          <div
            style={{
              width: '100%',
              height: '5px',
              background: 'rgba(255, 255, 255, 0.08)',
              borderRadius: '10px',
              overflow: 'hidden',
              position: 'relative',
              boxShadow: 'inset 0 1px 2px rgba(0, 0, 0, 0.5)',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${progress}%`,
                background: 'linear-gradient(90deg, #2563eb 0%, #8b5cf6 50%, #06b6d4 100%)',
                borderRadius: '10px',
                transition: 'width 0.04s linear',
                boxShadow: '0 0 12px rgba(37, 99, 235, 0.8)',
              }}
            />
          </div>
        </div>
      </div>

      <style>{`
        @keyframes preloaderPulseGlow {
          0% { transform: scale(1); opacity: 0.6; }
          100% { transform: scale(1.15); opacity: 0.95; }
        }
        @keyframes preloaderCardAppear {
          0% { opacity: 0; transform: scale(0.94) translateY(12px); }
          100% { opacity: 1; transform: scale(1) translateY(0); }
        }
        @keyframes preloaderLogoFloat {
          0%, 100% { transform: translateY(0px); }
          50% { transform: translateY(-3px); }
        }
      `}</style>
    </div>
  );
}
