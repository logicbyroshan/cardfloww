import React, { useState, useEffect, useRef } from 'react';
import {
  GraduationCap,
  CreditCard,
  Printer,
  Sparkles,
  Wifi,
  ExternalLink,
  ChevronRight,
  Info,
} from 'lucide-react';
import { bannersApi } from '../../services/api';

const DEFAULT_BANNERS = [
  {
    id: 'banner-pvc-lanyard',
    type: 'product',
    tag: 'SUPPLIES & ACCESSORIES',
    title: 'Smart PVC Cards & Lanyards',
    subtitle: 'HD Sublimation Blank Cards & Satin Neckbands',
    desc: 'HD thermal-printable blank PVC cards, multi-color satin lanyards, reels & ID clips.',
    cta: 'View Catalog',
    accent: '#3b82f6',
    ratio: '3:1',
    bg: 'linear-gradient(135deg, #1e3a8a 0%, #0f172a 100%)',
    border: '#3b82f6',
    tagBg: 'rgba(59, 130, 246, 0.25)',
    tagColor: '#93c5fd',
    btnBg: '#2563eb',
    image_url: '/banners/banner_pvc_cards_3x1.svg',
    target_url: 'https://cardflow.in/supplies',
    Icon: CreditCard,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-card-printers',
    type: 'product',
    tag: 'PRINTING HARDWARE',
    title: 'Dual-Sided Card Printers',
    subtitle: 'High-speed 300DPI Direct-to-Card Printing',
    desc: 'Industrial 300DPI direct-to-card printers with automatic duplex badge printing.',
    cta: 'Explore Printers',
    accent: '#06b6d4',
    ratio: '3:1',
    bg: 'linear-gradient(135deg, #083344 0%, #0f172a 100%)',
    border: '#06b6d4',
    tagBg: 'rgba(6, 182, 212, 0.25)',
    tagColor: '#67e8f9',
    btnBg: '#0891b2',
    image_url: '/banners/banner_printers_3x1.svg',
    target_url: 'https://cardflow.in/printers',
    Icon: Printer,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-vidyamaxx-1',
    type: 'vidyamaxx',
    tag: '⭐ OUR SCHOOL SOFTWARE',
    title: 'VidyaMaxx ERP Software',
    subtitle: 'Our Complete School Management Software',
    desc: 'All-in-one School & Campus Management System: Student Admissions, Fees Collection, Live Attendance, Report Cards & Parent App.',
    cta: 'Open VidyaMaxx',
    accent: '#f97316',
    ratio: '3:1',
    bg: 'linear-gradient(135deg, #ea580c 0%, #9a3412 50%, #1e1b4b 100%)',
    border: '#f97316',
    tagBg: 'rgba(249, 115, 22, 0.35)',
    tagColor: '#fed7aa',
    btnBg: '#ea580c',
    glow: '0 0 14px rgba(249, 115, 22, 0.45)',
    image_url: '/banners/banner_vidyamaxx_orange_3x1.svg',
    target_url: 'https://vidyamaxx.com',
    Icon: GraduationCap,
    is_vidyamaxx: true,
  },
  {
    id: 'banner-ai-studio',
    type: 'product',
    tag: 'AI SMART SUITE',
    title: 'AI Face & Photo Studio',
    subtitle: '1-Click Auto Background Remover & Crop',
    desc: 'Automated AI face detection, photo alignment, background removal & ultra-sharp upscaling.',
    cta: 'Try AI Suite',
    accent: '#a855f7',
    ratio: '3:1',
    bg: 'linear-gradient(135deg, #4c1d95 0%, #0f172a 100%)',
    border: '#a855f7',
    tagBg: 'rgba(168, 85, 247, 0.25)',
    tagColor: '#d8b4fe',
    btnBg: '#9333ea',
    image_url: '/banners/banner_ai_studio_3x1.svg',
    target_url: 'https://cardflow.in/ai-studio',
    Icon: Sparkles,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-rfid-scanner',
    type: 'product',
    tag: 'IOT HARDWARE',
    title: 'RFID & NFC Gate Readers',
    subtitle: 'Automated Student Tap Attendance',
    desc: 'Contactless smart attendance gate readers with instant cloud database sync.',
    cta: 'Get Hardware',
    accent: '#10b981',
    ratio: '3:1',
    bg: 'linear-gradient(135deg, #064e3b 0%, #0f172a 100%)',
    border: '#10b981',
    tagBg: 'rgba(16, 185, 129, 0.25)',
    tagColor: '#6ee7b7',
    btnBg: '#059669',
    image_url: '/banners/banner_rfid_3x1.svg',
    target_url: 'https://cardflow.in/rfid',
    Icon: Wifi,
    is_vidyamaxx: false,
  },
  {
    id: 'banner-vidyamaxx-2',
    type: 'vidyamaxx',
    tag: '⭐ VIDYAMAXX ERP',
    title: 'VidyaMaxx ERP Software',
    subtitle: 'Next-Gen School & Campus Solution',
    desc: 'Automate School Administration, Automated Bus GPS Tracking, Timetable Scheduling & Fee Installments.',
    cta: 'Free School Demo',
    accent: '#f97316',
    ratio: '3:1',
    bg: 'linear-gradient(135deg, #ea580c 0%, #9a3412 50%, #1e1b4b 100%)',
    border: '#f97316',
    tagBg: 'rgba(249, 115, 22, 0.35)',
    tagColor: '#fed7aa',
    btnBg: '#ea580c',
    glow: '0 0 14px rgba(249, 115, 22, 0.45)',
    image_url: '/banners/banner_vidyamaxx_orange_3x1.svg',
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
        // Merge API banner items with default icons/styling
        const merged = res.banners.map((b, idx) => {
          const fallback = DEFAULT_BANNERS[idx % DEFAULT_BANNERS.length] || DEFAULT_BANNERS[0];
          return {
            ...fallback,
            ...b,
            Icon: fallback.Icon,
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
    if (currentAd.is_vidyamaxx) {
      setShowModal(true);
    } else {
      setShowModal(true);
    }
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
          padding: '0 6px',
          marginBottom: '6px',
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
            borderRadius: '6px',
            overflow: 'hidden',
            boxSizing: 'border-box',
            border: `1px solid ${currentAd.is_vidyamaxx ? 'rgba(249, 115, 22, 0.7)' : 'rgba(255, 255, 255, 0.14)'}`,
            boxShadow: currentAd.glow || '0 2px 8px rgba(0,0,0,0.3)',
            transition: 'all 0.25s ease',
            background: currentAd.bg || '#1e1e2e',
          }}
          title={`${currentAd.title} — Click to view`}
        >
          {/* Long Web Banner Image (3:1 Aspect Ratio) */}
          {hasImage ? (
            <div
              style={{
                width: '100%',
                aspectRatio: '3 / 1',
                maxHeight: '86px',
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
                  objectFit: 'cover',
                  display: 'block',
                  borderRadius: '5px',
                  transition: 'transform 0.3s ease',
                }}
              />
            </div>
          ) : (
            /* Fallback Vector Banner Graphic in 3:1 Ratio */
            <div
              style={{
                width: '100%',
                aspectRatio: '3 / 1',
                padding: '8px 10px',
                boxSizing: 'border-box',
                display: 'flex',
                flexDirection: 'column',
                justifyContent: 'space-between',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span
                  style={{
                    fontSize: '8.5px',
                    fontWeight: 800,
                    padding: '2px 5px',
                    borderRadius: '3px',
                    background: currentAd.tagBg,
                    color: currentAd.tagColor,
                    letterSpacing: '0.04em',
                    textTransform: 'uppercase',
                  }}
                >
                  {currentAd.tag}
                </span>
                <Icon size={12} color={currentAd.accent} />
              </div>

              <div style={{ margin: '2px 0' }}>
                <div
                  style={{
                    fontSize: '11.5px',
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
                    fontSize: '9.5px',
                    fontWeight: 500,
                    color: currentAd.is_vidyamaxx ? '#fed7aa' : '#94a3b8',
                    lineHeight: 1.2,
                    whiteSpace: 'nowrap',
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                  }}
                >
                  {currentAd.subtitle}
                </div>
              </div>

              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                <span
                  style={{
                    fontSize: '9px',
                    fontWeight: 700,
                    padding: '1px 6px',
                    borderRadius: '3px',
                    background: currentAd.btnBg,
                    color: '#ffffff',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '2px',
                  }}
                >
                  <span>{currentAd.cta}</span>
                  <ChevronRight size={9} />
                </span>
              </div>
            </div>
          )}

          {/* Dots Indicator Overlay at Bottom Right */}
          <div
            style={{
              position: 'absolute',
              bottom: '4px',
              right: '6px',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
              background: 'rgba(0, 0, 0, 0.45)',
              padding: '2px 4px',
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
                  width: idx === currentIndex ? '10px' : '3.5px',
                  height: '3.5px',
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
              maxWidth: '460px',
              width: '100%',
              background: '#181824',
              border: `1px solid ${currentAd.is_vidyamaxx ? '#f97316' : currentAd.accent}`,
              borderRadius: '12px',
              padding: '24px',
              color: '#ffffff',
              boxShadow: '0 20px 50px rgba(0,0,0,0.7)',
              position: 'relative',
            }}
            onClick={(e) => e.stopPropagation()}
          >
            {/* Banner Preview inside Modal */}
            <div
              style={{
                width: '100%',
                aspectRatio: '3 / 1',
                borderRadius: '8px',
                overflow: 'hidden',
                marginBottom: '16px',
                border: '1px solid rgba(255, 255, 255, 0.1)',
              }}
            >
              <img
                src={currentAd.image_url}
                alt={currentAd.title}
                style={{ width: '100%', height: '100%', objectFit: 'cover' }}
              />
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '10px' }}>
              <span
                style={{
                  fontSize: '10px',
                  fontWeight: 800,
                  padding: '2px 8px',
                  borderRadius: '4px',
                  background: currentAd.tagBg,
                  color: currentAd.tagColor,
                  letterSpacing: '0.04em',
                }}
              >
                {currentAd.tag}
              </span>
              <h3 style={{ margin: 0, fontSize: '16px', fontWeight: 800 }}>{currentAd.title}</h3>
            </div>

            <p style={{ fontSize: '13px', color: '#cbd5e1', lineHeight: 1.5, margin: '0 0 16px 0' }}>
              {currentAd.desc}
            </p>

            {currentAd.is_vidyamaxx && (
              <div
                style={{
                  padding: '12px 14px',
                  borderRadius: '8px',
                  background: 'rgba(249, 115, 22, 0.12)',
                  border: '1px solid rgba(249, 115, 22, 0.35)',
                  marginBottom: '18px',
                  fontSize: '12px',
                  color: '#fed7aa',
                  lineHeight: 1.4,
                }}
              >
                <strong>VidyaMaxx School ERP</strong>: Connects directly with CardFlow for automatic student ID generation, timetable management, exam grading, and bus GPS tracking.
              </div>
            )}

            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '8px' }}>
              <button
                type="button"
                onClick={() => setShowModal(false)}
                style={{
                  padding: '7px 16px',
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
                  if (currentAd.target_url) {
                    window.open(currentAd.target_url, '_blank');
                  }
                }}
                style={{
                  padding: '7px 18px',
                  borderRadius: '4px',
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
