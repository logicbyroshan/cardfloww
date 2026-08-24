import React, { useState, useEffect, useRef } from 'react';
import {
  GraduationCap,
  CreditCard,
  Printer,
  Sparkles,
  Wifi,
  ExternalLink,
  ChevronRight,
  CheckCircle2,
} from 'lucide-react';
import { bannersApi } from '../../services/api';

const DEFAULT_BANNERS = [
  {
    id: 'banner-pvc-lanyard',
    type: 'product',
    tag: 'SUPPLIES & ACCESSORIES',
    title: 'PVC Cards & Lanyards',
    subtitle: 'Premium ID Supplies',
    bullets: [
      'Blank PVC CR80 Cards',
      'Custom Satin Lanyards',
      'Retractable Badge Reels',
      'Bulk Wholesale Pricing',
    ],
    desc: 'HD thermal-printable blank PVC cards, multi-color satin lanyards, reels & ID clips for high-volume printing.',
    cta: 'View Catalog',
    accent: '#3b82f6',
    ratio: '1:1.6',
    bg: 'linear-gradient(135deg, #1e3a8a 0%, #1e40af 60%, #0f172a 100%)',
    border: '#3b82f6',
    tagBg: 'rgba(59, 130, 246, 0.3)',
    tagColor: '#93c5fd',
    btnBg: '#2563eb',
    image_url: '/banners/banner_pvc_cards_tall.svg',
    target_url: 'https://cardflow.in/supplies',
    Icon: CreditCard,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-card-printers',
    type: 'product',
    tag: 'PRINTING HARDWARE',
    title: 'Dual-Sided Card Printers',
    subtitle: 'High-Speed 300 DPI',
    bullets: [
      'Auto Duplex Dual-Sided',
      '140+ Cards / Hour Speed',
      'Direct USB & LAN Network',
      '2-Year Official Warranty',
    ],
    desc: 'Industrial 300DPI direct-to-card printers with automatic duplex badge printing and rapid card output.',
    cta: 'Explore Models',
    accent: '#06b6d4',
    ratio: '1:1.6',
    bg: 'linear-gradient(135deg, #0e7490 0%, #083344 60%, #020617 100%)',
    border: '#06b6d4',
    tagBg: 'rgba(6, 182, 212, 0.3)',
    tagColor: '#67e8f9',
    btnBg: '#0891b2',
    image_url: '/banners/banner_printers_tall.svg',
    target_url: 'https://cardflow.in/printers',
    Icon: Printer,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-vidyamaxx-1',
    type: 'vidyamaxx',
    tag: '⭐ OUR SCHOOL SOFTWARE',
    title: 'VidyaMaxx ERP',
    subtitle: 'School Management Suite',
    bullets: [
      'Fees & Live Attendance',
      'Auto Student ID Sync',
      'Bus GPS & Parent App',
      'Exams & Report Cards',
    ],
    desc: 'Complete School & Campus ERP: Admissions, Student Biometrics, Automated Fees Collection, Bus GPS Tracking & Parent Mobile App.',
    cta: 'Open VidyaMaxx',
    accent: '#f97316',
    ratio: '1:1.6',
    bg: 'linear-gradient(135deg, #ea580c 0%, #9a3412 50%, #1e1b4b 100%)',
    border: '#f97316',
    tagBg: 'rgba(249, 115, 22, 0.4)',
    tagColor: '#fed7aa',
    btnBg: '#ea580c',
    glow: '0 0 16px rgba(249, 115, 22, 0.45)',
    image_url: '/banners/banner_vidyamaxx_orange_tall.svg',
    target_url: 'https://vidyamaxx.com',
    Icon: GraduationCap,
    is_vidyamaxx: true,
  },
  {
    id: 'banner-ai-studio',
    type: 'product',
    tag: 'AI SMART SUITE',
    title: 'AI Photo Studio',
    subtitle: 'Auto BG & Face Crop',
    bullets: [
      '1-Click BG Remover',
      'Face Alignment & Center',
      '4K Ultra HD AI Upscaling',
      'Batch 1,000+ Photos/Min',
    ],
    desc: 'Automated AI face detection, photo alignment, background removal & ultra-sharp upscaling for student identity cards.',
    cta: 'Try AI Suite',
    accent: '#a855f7',
    ratio: '1:1.6',
    bg: 'linear-gradient(135deg, #6b21a8 0%, #4c1d95 60%, #0f172a 100%)',
    border: '#a855f7',
    tagBg: 'rgba(168, 85, 247, 0.3)',
    tagColor: '#d8b4fe',
    btnBg: '#9333ea',
    image_url: '/banners/banner_ai_studio_tall.svg',
    target_url: 'https://cardflow.in/ai-studio',
    Icon: Sparkles,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-rfid-scanner',
    type: 'product',
    tag: 'IOT HARDWARE',
    title: 'RFID Gate Readers',
    subtitle: 'Tap Gate Attendance',
    bullets: [
      'Instant RFID & NFC Tap',
      'Real-Time Cloud Logging',
      'Instant Parent SMS Alerts',
      'Plug & Play USB / WiFi',
    ],
    desc: 'Contactless smart attendance gate readers with instant cloud database sync and real-time student tap logging.',
    cta: 'Get Hardware',
    accent: '#10b981',
    ratio: '1:1.6',
    bg: 'linear-gradient(135deg, #047857 0%, #064e3b 60%, #022c22 100%)',
    border: '#10b981',
    tagBg: 'rgba(16, 185, 129, 0.3)',
    tagColor: '#6ee7b7',
    btnBg: '#059669',
    image_url: '/banners/banner_rfid_tall.svg',
    target_url: 'https://cardflow.in/rfid',
    Icon: Wifi,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-vidyamaxx-2',
    type: 'vidyamaxx',
    tag: '⭐ VIDYAMAXX ERP',
    title: 'VidyaMaxx ERP',
    subtitle: 'Next-Gen School Solution',
    bullets: [
      'Fees & Live Attendance',
      'Auto Student ID Sync',
      'Bus GPS & Parent App',
      'Exams & Report Cards',
    ],
    desc: 'All-in-one Campus Solution: Student Admissions, Online Fees, Live Bus Tracking, Timetables & Parent Notifications.',
    cta: 'Free School Demo',
    accent: '#f97316',
    ratio: '1:1.6',
    bg: 'linear-gradient(135deg, #ea580c 0%, #9a3412 50%, #1e1b4b 100%)',
    border: '#f97316',
    tagBg: 'rgba(249, 115, 22, 0.4)',
    tagColor: '#fed7aa',
    btnBg: '#ea580c',
    glow: '0 0 16px rgba(249, 115, 22, 0.45)',
    image_url: '/banners/banner_vidyamaxx_orange_tall.svg',
    target_url: 'https://vidyamaxx.com',
    Icon: GraduationCap,
    is_vidyamaxx: true,
  },
];

export default function SidebarAdCard() {
  const [banners, setBanners] = useState(DEFAULT_BANNERS);
  const [currentIndex, setCurrentIndex] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [showModal, setShowModal] = useState(false);
  const [imgError, setImgError] = useState({});
  const timerRef = useRef(null);

  // Fetch banners from API on mount
  useEffect(() => {
    let mounted = true;
    bannersApi.getBanners().then((res) => {
      if (mounted && res && res.success && Array.isArray(res.banners) && res.banners.length > 0) {
        const merged = res.banners.map((b, idx) => {
          const fallback = DEFAULT_BANNERS[idx % DEFAULT_BANNERS.length] || DEFAULT_BANNERS[0];
          return {
            ...fallback,
            ...b,
            Icon: fallback.Icon,
            bullets: fallback.bullets,
          };
        });
        setBanners(merged);
      }
    });
    return () => {
      mounted = false;
    };
  }, []);

  const total = banners.length;
  const currentAd = banners[currentIndex % (total || 1)] || DEFAULT_BANNERS[0];
  const Icon = currentAd.Icon || GraduationCap;

  // Auto-rotation every 5 seconds (pauses on mouse hover)
  useEffect(() => {
    if (isPaused || total <= 1) return;

    timerRef.current = setInterval(() => {
      setCurrentIndex((prev) => (prev + 1) % total);
    }, 5000);

    return () => clearInterval(timerRef.current);
  }, [isPaused, total]);

  const handleBannerClick = () => {
    setShowModal(true);
  };

  const handleImageError = (id) => {
    setImgError((prev) => ({ ...prev, [id]: true }));
  };

  const hasImage = currentAd.image_url && !imgError[currentAd.id];

  return (
    <>
      <div
        className="sidebar-ad-card-container"
        style={{
          padding: '0 4px',
          marginBottom: '8px',
          boxSizing: 'border-box',
          width: '100%',
        }}
        onMouseEnter={() => setIsPaused(true)}
        onMouseLeave={() => setIsPaused(false)}
      >
        <div
          onClick={handleBannerClick}
          style={{
            position: 'relative',
            width: '100%',
            cursor: 'pointer',
            borderRadius: '8px',
            overflow: 'hidden',
            boxSizing: 'border-box',
            border: `1.5px solid ${currentAd.is_vidyamaxx ? '#f97316' : currentAd.accent || 'rgba(255, 255, 255, 0.18)'}`,
            boxShadow: currentAd.glow || '0 4px 14px rgba(0,0,0,0.4)',
            transition: 'all 0.25s ease',
            background: currentAd.bg || '#1e1e2e',
          }}
          title={`${currentAd.title} — Click to view`}
        >
          {/* Tall Vertical Skyscraper Banner (Aspect ratio ~1:1.6, height ~230px) */}
          {hasImage ? (
            <div
              style={{
                width: '100%',
                aspectRatio: '160 / 250',
                maxHeight: '250px',
                overflow: 'hidden',
                position: 'relative',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              <img
                src={currentAd.image_url}
                alt={currentAd.title}
                onError={() => handleImageError(currentAd.id)}
                style={{
                  width: '100%',
                  height: '100%',
                  objectFit: 'contain',
                  display: 'block',
                  borderRadius: '7px',
                }}
              />
            </div>
          ) : (
            /* Fallback Vector Vertical Poster Card */
            <div
              style={{
                width: '100%',
                aspectRatio: '160 / 250',
                padding: '12px 10px',
                boxSizing: 'border-box',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              {/* Top Badge */}
              <div style={{ textAlign: 'center' }}>
                <span
                  style={{
                    fontSize: '8px',
                    fontWeight: 800,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: currentAd.tagBg,
                    color: currentAd.tagColor,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                    display: 'inline-block',
                  }}
                >
                  {currentAd.tag}
                </span>
              </div>

              {/* Icon Box & Titles */}
              <div style={{ textAlign: 'center', margin: '6px 0 4px 0' }}>
                <div
                  style={{
                    width: '36px',
                    height: '36px',
                    borderRadius: '8px',
                    background: 'rgba(255, 255, 255, 0.18)',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    marginBottom: '6px',
                  }}
                >
                  <Icon size={18} color="#ffffff" />
                </div>
                <div
                  style={{
                    fontSize: '12px',
                    fontWeight: 800,
                    color: '#ffffff',
                    lineHeight: 1.2,
                  }}
                >
                  {currentAd.title}
                </div>
                <div
                  style={{
                    fontSize: '8.5px',
                    fontWeight: 600,
                    color: currentAd.is_vidyamaxx ? '#fed7aa' : '#94a3b8',
                    marginTop: '2px',
                  }}
                >
                  {currentAd.subtitle}
                </div>
              </div>

              {/* Bullet Features */}
              <div
                style={{
                  background: 'rgba(0, 0, 0, 0.25)',
                  borderRadius: '6px',
                  padding: '6px 8px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '4px',
                }}
              >
                {(currentAd.bullets || []).map((b, i) => (
                  <div
                    key={i}
                    style={{
                      fontSize: '8px',
                      color: currentAd.is_vidyamaxx ? '#ffedd5' : '#e2e8f0',
                      fontWeight: 600,
                      display: 'flex',
                      alignItems: 'center',
                      gap: '4px',
                      lineHeight: 1.2,
                    }}
                  >
                    <span style={{ color: currentAd.accent, fontSize: '9px' }}>•</span>
                    <span>{b}</span>
                  </div>
                ))}
              </div>

              {/* Bottom CTA Button */}
              <div style={{ marginTop: '6px' }}>
                <span
                  style={{
                    width: '100%',
                    padding: '6px 0',
                    borderRadius: '5px',
                    background: currentAd.is_vidyamaxx ? '#ffffff' : currentAd.btnBg,
                    color: currentAd.is_vidyamaxx ? '#c2410c' : '#ffffff',
                    fontSize: '9.5px',
                    fontWeight: 800,
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '4px',
                    boxShadow: '0 2px 8px rgba(0,0,0,0.3)',
                  }}
                >
                  <span>{currentAd.cta}</span>
                  <ChevronRight size={11} />
                </span>
              </div>
            </div>
          )}

          {/* Dots Indicator Overlay at Bottom Center */}
          <div
            style={{
              position: 'absolute',
              bottom: '4px',
              left: '50%',
              transform: 'translateX(-50%)',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
              background: 'rgba(0, 0, 0, 0.55)',
              padding: '2px 6px',
              borderRadius: '8px',
              backdropFilter: 'blur(4px)',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {banners.map((ad, idx) => (
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
                      ? ad.accent || '#f97316'
                      : 'rgba(255, 255, 255, 0.4)',
                  border: 'none',
                  padding: 0,
                  cursor: 'pointer',
                  transition: 'all 0.2s ease',
                }}
                title={`Banner ${idx + 1}`}
              />
            ))}
          </div>
        </div>
      </div>

      {/* Interactive Detail Modal on Click */}
      {showModal && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            zIndex: 999999,
            background: 'rgba(0, 0, 0, 0.75)',
            backdropFilter: 'blur(8px)',
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
              background: '#181824',
              border: `1.5px solid ${currentAd.is_vidyamaxx ? '#f97316' : currentAd.accent}`,
              borderRadius: '12px',
              padding: '22px',
              color: '#ffffff',
              boxShadow: '0 20px 50px rgba(0,0,0,0.75)',
              position: 'relative',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Modal Header */}
            <div style={{ display: 'flex', alignItems: 'center', gap: '10px', marginBottom: '12px' }}>
              <div
                style={{
                  width: '40px',
                  height: '40px',
                  borderRadius: '8px',
                  background: currentAd.tagBg,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                }}
              >
                <Icon size={22} color={currentAd.accent} />
              </div>
              <div>
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 800,
                    padding: '2px 6px',
                    borderRadius: '4px',
                    background: currentAd.tagBg,
                    color: currentAd.tagColor,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}
                >
                  {currentAd.tag}
                </span>
                <h3 style={{ margin: '3px 0 0 0', fontSize: '15px', fontWeight: 800 }}>{currentAd.title}</h3>
              </div>
            </div>

            <p style={{ fontSize: '12.5px', color: '#cbd5e1', lineHeight: 1.5, margin: '0 0 14px 0' }}>
              {currentAd.desc}
            </p>

            {/* Feature Highlights in Modal */}
            <div
              style={{
                background: 'rgba(0, 0, 0, 0.3)',
                borderRadius: '8px',
                padding: '10px 12px',
                marginBottom: '16px',
                border: '1px solid rgba(255, 255, 255, 0.08)',
              }}
            >
              <div style={{ fontSize: '10px', fontWeight: 700, color: '#94a3b8', marginBottom: '6px', textTransform: 'uppercase' }}>
                Key Highlights
              </div>
              {(currentAd.bullets || []).map((bullet, idx) => (
                <div key={idx} style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#e2e8f0', marginBottom: '4px' }}>
                  <CheckCircle2 size={13} color={currentAd.accent} />
                  <span>{bullet}</span>
                </div>
              ))}
            </div>

            {currentAd.is_vidyamaxx && (
              <div
                style={{
                  padding: '10px 12px',
                  borderRadius: '6px',
                  background: 'rgba(249, 115, 22, 0.12)',
                  border: '1px solid rgba(249, 115, 22, 0.35)',
                  marginBottom: '16px',
                  fontSize: '11.5px',
                  color: '#fed7aa',
                  lineHeight: 1.4,
                }}
              >
                <strong>VidyaMaxx ERP</strong> links seamlessly with CardFlow to automate student identity badge production with zero manual data entry.
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                style={{
                  padding: '7px 15px',
                  borderRadius: '5px',
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
                  if (currentAd.target_url) {
                    window.open(currentAd.target_url, '_blank');
                  }
                }}
                style={{
                  padding: '7px 18px',
                  borderRadius: '5px',
                  border: 'none',
                  background: currentAd.btnBg || '#ea580c',
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
