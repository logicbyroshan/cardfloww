import React, { useState, useEffect, useRef } from 'react';
import {
  GraduationCap,
  CreditCard,
  Printer,
  Sparkles,
  Wifi,
  ExternalLink,
  ChevronRight,
  ShieldCheck,
  CheckCircle2,
} from 'lucide-react';

const ADS_DATA = [
  {
    id: 'ad-pvc',
    type: 'product',
    tag: 'SUPPLIES',
    title: 'Smart PVC Cards & Lanyards',
    subtitle: 'Premium ID Card Accessories',
    desc: 'HD thermal-printable blank PVC cards, multi-color satin lanyards & clips.',
    cta: 'View Catalog',
    accent: '#3b82f6',
    bg: 'linear-gradient(135deg, rgba(30, 58, 138, 0.45) 0%, rgba(15, 23, 42, 0.85) 100%)',
    border: 'rgba(59, 130, 246, 0.35)',
    tagBg: 'rgba(59, 130, 246, 0.2)',
    tagColor: '#93c5fd',
    btnBg: '#2563eb',
    Icon: CreditCard,
  },
  {
    id: 'ad-printer',
    type: 'product',
    tag: 'HARDWARE',
    title: 'Dual-Sided Card Printers',
    subtitle: 'High-Speed Thermal Printers',
    desc: 'Industrial 300DPI direct-to-card printers with automatic duplex printing.',
    cta: 'Learn More',
    accent: '#06b6d4',
    bg: 'linear-gradient(135deg, rgba(8, 51, 68, 0.45) 0%, rgba(15, 23, 42, 0.85) 100%)',
    border: 'rgba(6, 182, 212, 0.35)',
    tagBg: 'rgba(6, 182, 212, 0.2)',
    tagColor: '#67e8f9',
    btnBg: '#0891b2',
    Icon: Printer,
  },
  {
    id: 'ad-vidyamaxx-1',
    type: 'vidyamaxx',
    tag: '⭐ OUR SCHOOL SOFTWARE',
    title: 'VidyaMaxx Software',
    subtitle: 'School Management ERP',
    desc: 'Complete School & Campus System: Fees, Live Attendance, Exams & SMS Alerts.',
    cta: 'Explore VidyaMaxx',
    accent: '#f97316',
    bg: 'linear-gradient(135deg, rgba(194, 65, 12, 0.6) 0%, rgba(124, 45, 18, 0.8) 50%, rgba(30, 27, 75, 0.9) 100%)',
    border: 'rgba(249, 115, 22, 0.7)',
    tagBg: 'rgba(249, 115, 22, 0.35)',
    tagColor: '#fdba74',
    btnBg: '#ea580c',
    glow: '0 0 16px rgba(249, 115, 22, 0.35)',
    Icon: GraduationCap,
    isVidyamaxx: true,
  },
  {
    id: 'ad-ai',
    type: 'product',
    tag: 'AI SMART TOOLS',
    title: 'AI Face & Photo Studio',
    subtitle: '1-Click Auto Background Remover',
    desc: 'AI face alignment, background removal & ultra-sharp image enhancement.',
    cta: 'Try AI Suite',
    accent: '#a855f7',
    bg: 'linear-gradient(135deg, rgba(88, 28, 135, 0.45) 0%, rgba(15, 23, 42, 0.85) 100%)',
    border: 'rgba(168, 85, 247, 0.35)',
    tagBg: 'rgba(168, 85, 247, 0.2)',
    tagColor: '#d8b4fe',
    btnBg: '#9333ea',
    Icon: Sparkles,
  },
  {
    id: 'ad-rfid',
    type: 'product',
    tag: 'IOT HARDWARE',
    title: 'RFID & NFC Gate Readers',
    subtitle: 'Automated Tap Attendance',
    desc: 'Touch-free student & staff gate scanners with instant cloud sync.',
    cta: 'Get Quote',
    accent: '#10b981',
    bg: 'linear-gradient(135deg, rgba(6, 78, 59, 0.45) 0%, rgba(15, 23, 42, 0.85) 100%)',
    border: 'rgba(16, 185, 129, 0.35)',
    tagBg: 'rgba(16, 185, 129, 0.2)',
    tagColor: '#6ee7b7',
    btnBg: '#059669',
    Icon: Wifi,
  },
  {
    id: 'ad-vidyamaxx-2',
    type: 'vidyamaxx',
    tag: '⭐ VIDYAMAXX ERP',
    title: 'VidyaMaxx Software',
    subtitle: 'Next-Gen School Solution',
    desc: 'Modern cloud system for Schools & Colleges. Admissions, Fees & Parent Mobile App.',
    cta: 'Free School Demo',
    accent: '#f97316',
    bg: 'linear-gradient(135deg, rgba(194, 65, 12, 0.6) 0%, rgba(124, 45, 18, 0.8) 50%, rgba(30, 27, 75, 0.9) 100%)',
    border: 'rgba(249, 115, 22, 0.7)',
    tagBg: 'rgba(249, 115, 22, 0.35)',
    tagColor: '#fdba74',
    btnBg: '#ea580c',
    glow: '0 0 16px rgba(249, 115, 22, 0.35)',
    Icon: GraduationCap,
    isVidyamaxx: true,
  },
];

export default function SidebarAdCard() {
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const timerRef = useRef(null);

  const currentAd = ADS_DATA[currentIndex];
  const Icon = currentAd.Icon;

  // Auto-rotation every 5 seconds (pauses on hover)
  useEffect(() => {
    if (isPaused) return;

    timerRef.current = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % ADS_DATA.length);
    }, 5000);

    return () => clearInterval(timerRef.current);
  }, [isPaused]);

  const handleCardClick = () => {
    setShowModal(true);
  };

  return (
    <>
      <div
        className="sidebar-ad-card-container"
        style={{
          padding: '0 8px',
          marginBottom: '8px',
          boxSizing: 'border-box',
        }}
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
      >
        <div
          onClick={handleCardClick}
          style={{
            position: 'relative',
            background: currentAd.bg,
            border: `1px solid ${currentAd.border}`,
            borderRadius: '6px',
            padding: '8px 10px',
            cursor: 'pointer',
            overflow: 'hidden',
            boxSizing: 'border-box',
            boxShadow: currentAd.glow || '0 2px 8px rgba(0,0,0,0.3)',
            transition: 'all 0.3s ease',
          }}
          title={`${currentAd.title} — Click to view details`}
        >
          {/* Header Row: Tag Badge & Icon */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginBottom: '5px',
            }}
          >
            <span
              style={{
                fontSize: '9px',
                fontWeight: 700,
                letterSpacing: '0.04em',
                padding: '2px 6px',
                borderRadius: '3px',
                background: currentAd.tagBg,
                color: currentAd.tagColor,
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                textTransform: 'uppercase',
              }}
            >
              {currentAd.tag}
            </span>

            <div
              style={{
                width: '20px',
                height: '20px',
                borderRadius: '4px',
                background: 'rgba(255, 255, 255, 0.1)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: currentAd.accent,
                flexShrink: 0,
              }}
            >
              <Icon size={12} />
            </div>
          </div>

          {/* Title & Subtitle */}
          <div style={{ marginBottom: '4px' }}>
            <div
              style={{
                fontSize: '12px',
                fontWeight: 700,
                color: '#ffffff',
                lineHeight: 1.2,
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {currentAd.title}
            </div>
            <div
              style={{
                fontSize: '10px',
                fontWeight: 500,
                color: currentAd.isVidyamaxx ? '#fdba74' : '#94a3b8',
                lineHeight: 1.2,
                marginTop: '1px',
                whiteSpace: 'nowrap',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
              }}
            >
              {currentAd.subtitle}
            </div>
          </div>

          {/* Action Row: CTA Button & Dots Indicator */}
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              marginTop: '6px',
              paddingTop: '5px',
              borderTop: '1px solid rgba(255, 255, 255, 0.08)',
            }}
          >
            <span
              style={{
                fontSize: '10px',
                fontWeight: 700,
                padding: '2px 8px',
                borderRadius: '3px',
                background: currentAd.btnBg,
                color: '#ffffff',
                display: 'inline-flex',
                alignItems: 'center',
                gap: '3px',
                boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
              }}
            >
              <span>{currentAd.cta}</span>
              <ChevronRight size={10} />
            </span>

            {/* Dots */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '3px',
              }}
              onClick={(e) => e.stopPropagation()}
            >
              {ADS_DATA.map((ad, idx) => (
                <button
                  key={ad.id}
                  type="button"
                  onClick={() => setCurrentIndex(idx)}
                  style={{
                    width: idx === currentIndex ? '12px' : '4px',
                    height: '4px',
                    borderRadius: '2px',
                    background:
                      idx === currentIndex
                        ? ad.accent
                        : 'rgba(255, 255, 255, 0.25)',
                    border: 'none',
                    padding: 0,
                    cursor: 'pointer',
                    transition: 'all 0.2s ease',
                  }}
                  title={`Go to ad ${idx + 1}`}
                />
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* Info / Promo Modal */}
      {showModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999999,
            background: 'rgba(0, 0, 0, 0.7)',
            backdropFilter: 'blur(6px)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            padding: '16px',
          }}
          onClick={() => setShowModal(false)}
        >
          <div
            style={{
              maxWidth: '440px',
              width: '100%',
              background: '#1e1e2e',
              border: `1px solid ${currentAd.accent}`,
              borderRadius: '12px',
              padding: '24px',
              color: '#ffffff',
              boxShadow: '0 20px 50px rgba(0,0,0,0.6)',
              position: 'relative',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '14px' }}>
              <div
                style={{
                  width: '36px',
                  height: '36px',
                  borderRadius: '8px',
                  background: currentAd.tagBg,
                  color: currentAd.accent,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Icon size={20} />
              </div>
              <div>
                <span
                  style={{
                    fontSize: '10px',
                    fontWeight: 700,
                    padding: '2px 6px',
                    borderRadius: '3px',
                    background: currentAd.tagBg,
                    color: currentAd.tagColor,
                    display: 'inline-block',
                    marginBottom: '2px',
                  }}
                >
                  {currentAd.tag}
                </span>
                <h3 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>{currentAd.title}</h3>
              </div>
            </div>

            <p style={{ fontSize: '13px', color: '#cbd5e1', lineHeight: 1.5, margin: '0 0 16px 0' }}>
              {currentAd.desc}
            </p>

            {currentAd.isVidyamaxx && (
              <div
                style={{
                  padding: '10px 12px',
                  borderRadius: '6px',
                  background: 'rgba(249, 115, 22, 0.15)',
                  border: '1px solid rgba(249, 115, 22, 0.4)',
                  marginBottom: '16px',
                  fontSize: '12px',
                  color: '#fdba74',
                }}
              >
                <strong>VidyaMaxx School ERP</strong> connects seamlessly with CardFlow for real-time student ID issuance, bus tracking, and automated fees management.
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '4px',
                  border: '1px solid rgba(255, 255, 255, 0.2)',
                  background: 'transparent',
                  color: '#cbd5e1',
                  fontSize: '12px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
              <button
                type="button"
                onClick={() => {
                  setShowModal(false);
                  if (currentAd.isVidyamaxx) {
                    window.open('https://vidyamaxx.com', '_blank');
                  }
                }}
                style={{
                  padding: '6px 16px',
                  borderRadius: '4px',
                  border: 'none',
                  background: currentAd.btnBg,
                  color: '#ffffff',
                  fontSize: '12px',
                  fontWeight: 700,
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '6px',
                }}
              >
                <span>{currentAd.cta}</span>
                <ExternalLink size={13} />
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
