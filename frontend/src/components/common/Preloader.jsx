import React, { useState, useEffect } from 'react';
import { Shield, Sparkles, Cpu, Layers, CheckCircle2 } from 'lucide-react';

const LOADING_STEPS = [
  { label: 'Initializing CardFlow Enterprise Engine…', tag: 'BOOT_CORE' },
  { label: 'Connecting Multi-Tenant Identity Matrix…', tag: 'AUTH_SYNC' },
  { label: 'Loading Real-Time Schema & Print Queue…', tag: 'QUEUE_INIT' },
  { label: 'System Verified • Launching Workspace…', tag: 'READY' },
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

    const startTime = Date.now();
    const duration = 1400; // Smooth 1.4s load time

    const interval = setInterval(() => {
      const elapsed = Date.now() - startTime;
      const pct = Math.min(100, Math.floor((elapsed / duration) * 100));
      setProgress(pct);

      if (pct < 28) setStepIndex(0);
      else if (pct < 60) setStepIndex(1);
      else if (pct < 88) setStepIndex(2);
      else setStepIndex(3);

      if (elapsed >= duration) {
        clearInterval(interval);
        setPhase('fadeout');
        setTimeout(() => {
          setPhase('done');
          onFinished?.();
        }, 600);
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
        background: 'radial-gradient(ellipse at 50% 30%, #1e1b4b 0%, #0f172a 45%, #050814 100%)',
        opacity: isFadeOut ? 0 : 1,
        transform: isFadeOut ? 'scale(1.05)' : 'scale(1)',
        filter: isFadeOut ? 'blur(12px)' : 'blur(0px)',
        transition:
          'opacity 0.6s cubic-bezier(0.4, 0, 0.2, 1), transform 0.6s cubic-bezier(0.4, 0, 0.2, 1), filter 0.6s ease',
        overflow: 'hidden',
        pointerEvents: isFadeOut ? 'none' : 'auto',
        fontFamily: "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif",
      }}
    >
      {/* ── Background Geometric Blueprint Grid ── */}
      <div
        style={{
          position: 'absolute',
          inset: 0,
          backgroundImage: `
            linear-gradient(to right, rgba(99, 102, 241, 0.07) 1px, transparent 1px),
            linear-gradient(to bottom, rgba(99, 102, 241, 0.07) 1px, transparent 1px)
          `,
          backgroundSize: '54px 54px',
          opacity: 0.8,
          pointerEvents: 'none',
        }}
      />

      {/* ── Glowing Aurora Ambient Blobs ── */}
      <div style={{ position: 'absolute', inset: 0, pointerEvents: 'none', overflow: 'hidden' }}>
        <div
          style={{
            position: 'absolute',
            top: '20%',
            left: '28%',
            width: '600px',
            height: '600px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(99, 102, 241, 0.35) 0%, rgba(56, 189, 248, 0.15) 50%, transparent 70%)',
            filter: 'blur(100px)',
            animation: 'preloaderOrbFloat 6s ease-in-out infinite alternate',
          }}
        />
        <div
          style={{
            position: 'absolute',
            bottom: '15%',
            right: '25%',
            width: '650px',
            height: '650px',
            borderRadius: '50%',
            background: 'radial-gradient(circle, rgba(168, 85, 247, 0.3) 0%, rgba(236, 72, 153, 0.12) 50%, transparent 70%)',
            filter: 'blur(110px)',
            animation: 'preloaderOrbFloat 7s ease-in-out infinite alternate-reverse',
          }}
        />
      </div>

      {/* ── Holographic Centerpiece & Telemetry Card ── */}
      <div
        style={{
          position: 'relative',
          zIndex: 10,
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          textAlign: 'center',
          maxWidth: '620px',
          width: '92%',
          padding: '48px 40px',
          borderRadius: '32px',
          background: 'linear-gradient(135deg, rgba(30, 41, 59, 0.75) 0%, rgba(15, 23, 42, 0.9) 100%)',
          backdropFilter: 'blur(30px) saturate(180%)',
          WebkitBackdropFilter: 'blur(30px) saturate(180%)',
          border: '1px solid rgba(255, 255, 255, 0.16)',
          boxShadow: `
            0 35px 80px -15px rgba(0, 0, 0, 0.8),
            0 0 50px rgba(99, 102, 241, 0.25),
            inset 0 1px 1px rgba(255, 255, 255, 0.3)
          `,
          animation: 'preloaderCardRise 0.7s cubic-bezier(0.16, 1, 0.3, 1) forwards',
        }}
      >
        {/* Holographic Glowing Badge Emblem */}
        <div
          style={{
            position: 'relative',
            width: '180px',
            height: '110px',
            borderRadius: '20px',
            marginBottom: '28px',
            background: 'linear-gradient(135deg, rgba(99, 102, 241, 0.25) 0%, rgba(56, 189, 248, 0.15) 50%, rgba(168, 85, 247, 0.25) 100%)',
            border: '1px solid rgba(255, 255, 255, 0.3)',
            boxShadow: '0 20px 40px rgba(0, 0, 0, 0.4), inset 0 0 25px rgba(99, 102, 241, 0.3)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            overflow: 'hidden',
          }}
        >
          {/* Laser Scanner Beam */}
          <div
            style={{
              position: 'absolute',
              top: 0,
              left: 0,
              right: 0,
              height: '3px',
              background: 'linear-gradient(90deg, transparent, #38bdf8, #818cf8, #38bdf8, transparent)',
              boxShadow: '0 0 15px #38bdf8, 0 0 25px #818cf8',
              animation: 'preloaderLaserScan 2.4s cubic-bezier(0.4, 0, 0.2, 1) infinite',
            }}
          />

          {/* Lanyard Hole Mock Clip */}
          <div
            style={{
              position: 'absolute',
              top: '8px',
              left: '50%',
              transform: 'translateX(-50%)',
              width: '32px',
              height: '6px',
              borderRadius: '4px',
              background: 'rgba(255, 255, 255, 0.2)',
              border: '1px solid rgba(255, 255, 255, 0.3)',
            }}
          />

          {/* Brand Logo */}
          <img
            src="/cardflow_logo_brand.png"
            onError={(e) => {
              e.target.style.display = 'none';
            }}
            alt="CardFlow"
            style={{
              maxHeight: '44px',
              maxWidth: '140px',
              width: '100%',
              objectFit: 'contain',
              filter: 'drop-shadow(0 4px 12px rgba(0, 0, 0, 0.6))',
              zIndex: 2,
            }}
          />

          {/* Holographic Watermark Chips */}
          <div
            style={{
              position: 'absolute',
              bottom: '8px',
              right: '10px',
              fontSize: '8px',
              fontWeight: 800,
              letterSpacing: '0.12em',
              color: 'rgba(255, 255, 255, 0.5)',
              fontFamily: 'monospace',
            }}
          >
            RFID•NFC
          </div>
        </div>

        {/* System Title */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '8px' }}>
          <Shield size={20} color="#38bdf8" />
          <h1
            style={{
              fontSize: '26px',
              fontWeight: 800,
              letterSpacing: '0.04em',
              background: 'linear-gradient(135deg, #ffffff 0%, #cbd5e1 45%, #93c5fd 100%)',
              WebkitBackgroundClip: 'text',
              WebkitTextFillColor: 'transparent',
              margin: 0,
              lineHeight: 1.2,
            }}
          >
            CARDFLOW ENTERPRISE
          </h1>
          <Sparkles size={18} color="#c084fc" />
        </div>

        {/* Subtitle / System Tag */}
        <p
          style={{
            fontSize: '13px',
            color: '#94a3b8',
            fontWeight: 500,
            margin: '0 0 28px 0',
            letterSpacing: '0.02em',
          }}
        >
          High-Velocity ID Card Generation & Multi-Tenant Management Platform
        </p>

        {/* Dynamic Telemetry Status Bar */}
        <div
          style={{
            width: '100%',
            padding: '16px 20px',
            borderRadius: '16px',
            background: 'rgba(15, 23, 42, 0.65)',
            border: '1px solid rgba(255, 255, 255, 0.1)',
            boxShadow: 'inset 0 2px 4px rgba(0, 0, 0, 0.4)',
            marginBottom: '22px',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '10px',
              fontSize: '13px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', color: '#e2e8f0', fontWeight: 600 }}>
              <span
                style={{
                  width: '8px',
                  height: '8px',
                  borderRadius: '50%',
                  background: progress === 100 ? '#4ade80' : '#38bdf8',
                  boxShadow: progress === 100 ? '0 0 10px #4ade80' : '0 0 10px #38bdf8',
                  animation: 'preloaderPulseDot 1.5s infinite',
                }}
              />
              <span>{LOADING_STEPS[stepIndex].label}</span>
            </div>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <span
                style={{
                  fontSize: '10px',
                  padding: '2px 6px',
                  borderRadius: '6px',
                  background: 'rgba(99, 102, 241, 0.25)',
                  color: '#a5b4fc',
                  fontWeight: 700,
                  fontFamily: 'monospace',
                }}
              >
                {LOADING_STEPS[stepIndex].tag}
              </span>
              <span style={{ color: '#38bdf8', fontWeight: 800, fontSize: '14px', minWidth: '40px', textAlign: 'right' }}>
                {progress}%
              </span>
            </div>
          </div>

          {/* Premium Multi-Layered Progress Bar */}
          <div
            style={{
              position: 'relative',
              width: '100%',
              height: '8px',
              borderRadius: '999px',
              background: 'rgba(255, 255, 255, 0.08)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                height: '100%',
                width: `${progress}%`,
                background: 'linear-gradient(90deg, #3b82f6 0%, #6366f1 35%, #a855f7 70%, #38bdf8 100%)',
                borderRadius: '999px',
                transition: 'width 0.06s linear',
                boxShadow: '0 0 16px rgba(56, 189, 248, 0.8), 0 0 30px rgba(99, 102, 241, 0.6)',
              }}
            />
          </div>
        </div>

        {/* Feature Pills / Telemetry Badges */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '12px',
            flexWrap: 'wrap',
          }}
        >
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              color: '#94a3b8',
              background: 'rgba(255, 255, 255, 0.04)',
              padding: '6px 12px',
              borderRadius: '999px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            <Cpu size={13} color="#38bdf8" />
            <span>Multi-Threaded Rendering</span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              color: '#94a3b8',
              background: 'rgba(255, 255, 255, 0.04)',
              padding: '6px 12px',
              borderRadius: '999px',
              border: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            <Layers size={13} color="#c084fc" />
            <span>21 Active Schemas</span>
          </div>

          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
              fontSize: '11px',
              color: '#4ade80',
              background: 'rgba(74, 222, 128, 0.1)',
              padding: '6px 12px',
              borderRadius: '999px',
              border: '1px solid rgba(74, 222, 128, 0.25)',
            }}
          >
            <CheckCircle2 size={13} color="#4ade80" />
            <span>SSL 256-bit Encrypted</span>
          </div>
        </div>
      </div>

      {/* Embedded High-Performance Animations */}
      <style>{`
        @keyframes preloaderOrbFloat {
          0% { transform: translate(0px, 0px) scale(1); }
          100% { transform: translate(30px, -25px) scale(1.12); }
        }
        @keyframes preloaderCardRise {
          0% { opacity: 0; transform: scale(0.92) translateY(24px); }
          100% { opacity: 1; transform: scale(1) translateY(0px); }
        }
        @keyframes preloaderLaserScan {
          0% { top: -5%; opacity: 0; }
          15% { opacity: 1; }
          85% { opacity: 1; }
          100% { top: 105%; opacity: 0; }
        }
        @keyframes preloaderPulseDot {
          0%, 100% { opacity: 1; transform: scale(1); }
          50% { opacity: 0.5; transform: scale(0.85); }
        }
      `}</style>
    </div>
  );
}
