import React, { useState, useEffect } from 'react';

const LOADING_STEPS = [
  'Initializing CardFlow Core…',
  'Verifying Security Protocols…',
  'Loading Organization Engine…',
  'System Ready'
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
        backgroundColor: '#06080e',
        opacity: isFadeOut ? 0 : 1,
        transform: isFadeOut ? 'scale(1.04)' : 'scale(1)',
        filter: isFadeOut ? 'blur(10px)' : 'blur(0px)',
        transition: 'opacity 0.55s cubic-bezier(0.4, 0, 0.2, 1), transform 0.55s cubic-bezier(0.4, 0, 0.2, 1), filter 0.55s ease',
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
            linear-gradient(to right, rgba(255, 255, 255, 0.03) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(255, 255, 255, 0.03) 1px, transparent 1px)
          `,
          backgroundSize: '40px 40px',
          opacity: 0.8,
          pointerEvents: 'none',
        }}
      />

      {/* Glowing Ambient Radial Blobs */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden' }}>
        <div
          style={{
            position: 'absolute',
            top: '20%',
            left: '30%',
            width: '400px',
            height: '400px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(37, 99, 235, 0.35) 0%, rgba(99, 102, 241, 0.15) 50%, transparent 70%)',
            filter: 'blur(80px)',
            animation: 'preloaderPulseGlow 4s ease-in-out infinite alternate',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: '20%',
            right: '30%',
            width: '450px',
            height: '450px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(139, 92, 246, 0.3) 0%, rgba(6, 182, 212, 0.15) 50%, transparent 70%)',
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
          padding: '40px 50px',
          borderRadius: '24px',
          background: 'rgba(15, 23, 42, 0.55)',
          backdropFilter: 'blur(20px)',
          WebkitBackdropFilter: 'blur(20px)',
          border: '1px solid rgba(255, 255, 255, 0.12)',
          boxShadow: '0 25px 60px -15px rgba(0, 0, 0, 0.7), inset 0 1px 0 rgba(255, 255, 255, 0.15)',
          maxWidth: '420px',
          width: '90%',
          animation: 'preloaderCardAppear 0.6s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        }}
      >
        {/* Animated Logo Shield Wrapper */}
        <div
          style={{
            position: 'relative',
            width: '96px',
            height: '96px',
            marginBottom: '24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          {/* Outer Rotating Conic Ring */}
          <div
            style={{
              position: 'absolute',
              inset: '-5px',
              borderRadius: '50%',
              background: 'conic-gradient(from 0deg, #2563eb, #8b5cf6, #06b6d4, #3b82f6, #2563eb)',
              opacity: 0.85,
              filter: 'blur(4px)',
              animation: 'spin 3s linear infinite',
            }}
          />

          {/* Inner Glossy Sphere Container */}
          <div
            style={{
              position: 'absolute',
              inset: 0,
              borderRadius: '50%',
              background: 'linear-gradient(145deg, #0b1329 0%, #060913 100%)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              border: '1px solid rgba(255, 255, 255, 0.15)',
              boxShadow: 'inset 0 2px 10px rgba(59, 130, 246, 0.3), 0 8px 24px rgba(0, 0, 0, 0.6)',
            }}
          >
            <img
              src="/Cardflow 1.png"
              alt="CardFlow Logo"
              style={{
                width: '60px',
                height: '60px',
                objectFit: 'contain',
                filter: 'drop-shadow(0 4px 12px rgba(37,99,235,0.7))',
                animation: 'preloaderLogoFloat 3s ease-in-out infinite',
              }}
            />
          </div>
        </div>

        {/* Title */}
        <h1
          style={{
            fontFamily: '"Saira Semi Condensed", sans-serif',
            fontSize: '26px',
            fontWeight: 800,
            background: 'linear-gradient(135deg, #ffffff 0%, #cbd5e1 50%, #93c5fd 100%)',
            WebkitBackgroundClip: 'text',
            WebkitTextFillColor: 'transparent',
            letterSpacing: '0.06em',
            margin: '0 0 6px 0',
            textTransform: 'uppercase',
            lineHeight: 1.2,
          }}
        >
          CardFlow ID System
        </h1>

        {/* Tagline Badge */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            padding: '3px 12px',
            borderRadius: '20px',
            background: 'rgba(37, 99, 235, 0.15)',
            border: '1px solid rgba(59, 130, 246, 0.35)',
            color: '#bfdbfe',
            fontSize: '10px',
            fontWeight: 700,
            letterSpacing: '0.1em',
            textTransform: 'uppercase',
            marginBottom: '28px',
          }}
        >
          <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#3b82f6', boxShadow: '0 0 8px #3b82f6' }} />
          Enterprise ID Card Suite
        </div>

        {/* Progress Track & Counter */}
        <div style={{ width: '100%', display: 'flex', flexDirection: 'column', gap: '8px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8', fontWeight: 600 }}>
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
