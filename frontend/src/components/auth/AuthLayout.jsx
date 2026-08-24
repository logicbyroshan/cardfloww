import React, { useState, useEffect } from 'react';
import {
  Sparkles,
  CheckCircle2,
  ChevronLeft,
  ChevronRight,
  Zap,
  Smartphone,
  ExternalLink,
} from 'lucide-react';
import './Auth.css';

const PRODUCTS = [
  {
    id: 'school_id',
    name: 'Student ID Cards',
    category: 'STUDENT IDENTITY',
    title: 'Smart School & College ID Cards',
    tagline: 'High-durability PVC with automated photo crop, student QR & barcode tracking.',
    image: '/products/id_card_school.webp',
    accentColor: '#38bdf8',
    stats: '300 DPI Sublimation • CR80 PVC Standard',
    bullets: [
      'Automated Face Detection & Photo Cropping',
      'Multi-Class & Section Batch Printing',
      'Tamper-Proof Waterproof High-Gloss Lamination',
      'Instant QR Code & Barcode Data Verification',
    ],
  },
  {
    id: 'lanyards',
    name: 'Custom Lanyards',
    category: 'BRANDED ACCESSORIES',
    title: 'Premium Satin & Woven Lanyards',
    tagline: 'Custom double-sided heat-transfer lanyards with premium zinc-alloy clips.',
    image: '/products/lanyard_premium.webp',
    accentColor: '#a855f7',
    stats: '16mm / 20mm / 25mm • Silk Satin',
    bullets: [
      'Multi-Color Fade-Proof Sublimation Printing',
      'Durable Zinc-Alloy Dog Hook & Safety Breakaway',
      'Custom School & Institution Logo Printing',
      'Matching Color-Coded Card Holders Included',
    ],
  },
  {
    id: 'corporate_badge',
    name: 'Corporate Badges',
    category: 'ENTERPRISE ACCESS',
    title: 'Corporate Executive & Access Badges',
    tagline: 'Smart RFID and NFC enabled access badges with delegated manager approvals.',
    image: '/products/id_card_corporate.webp',
    accentColor: '#34d399',
    stats: '13.56 MHz RFID • NFC Integrated',
    bullets: [
      'Manager Multi-Level Status Approval Pipeline',
      'Smart Door & Attendance Access Control Sync',
      'Matte Executive & Metallic Gloss Finish Options',
      'Real-Time Automated Reprint & Dispatch Queue',
    ],
  },
  {
    id: 'pvc_cards',
    name: 'Bulk PVC Printing',
    category: 'PRODUCTION ENGINE',
    title: 'High-Velocity Card Printing Hub',
    tagline: 'Process thousands of student records with 1-click Excel sync and automated PDF layout.',
    image: '/products/id_card_pvc.webp',
    accentColor: '#f59e0b',
    stats: '1,000+ Cards / Min • Zero Defect',
    bullets: [
      '1-Click CSV & Excel Spreadsheet Auto-Mapping',
      'Multi-Page Print-Ready PDF & High-Res ZIP Exports',
      'Automated Missing Photo & Duplicate Record Alerts',
      'Multi-Tenant End-to-End Encryption & Backups',
    ],
  },
  {
    id: 'lanyard_3d',
    name: 'Clip-Lock Lanyards',
    category: 'PREMIUM FITTINGS',
    title: 'Heavy-Duty 3D Clip-Lock Lanyards',
    tagline: 'Industrial-grade lanyards designed for hospitals, factories, and universities.',
    image: '/products/lanyard_3d.webp',
    accentColor: '#ec4899',
    stats: 'Reinforced Nylon • Heavy-Duty Swivel',
    bullets: [
      'Ergonomic Comfort-Wear Soft-Touch Fabric',
      'Quick-Release Safety Buckle for High Activity',
      'Weather-Proof & Sweat-Resistant Material',
      'Compatible with Standard CR80 Card Pouches',
    ],
  },
];

const AUTO_INTERVAL = 3600; // 3.6s per product slide

/* ─────────────────────────────────────────────────────────────
   Product Showcase / Advertisement Hero (Left Side)
   Grand, expansive, auto-switching magazine-grade hero canvas
───────────────────────────────────────────────────────────── */
function ProductShowcase() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [progress, setProgress] = useState(0);

  // Reliable continuous auto-scrolling timer with live progress animation
  useEffect(() => {
    setProgress(0);
    const stepMs = 30;
    const totalSteps = AUTO_INTERVAL / stepMs;
    let step = 0;

    const timer = setInterval(() => {
      step += 1;
      const pct = Math.min(100, (step / totalSteps) * 100);
      setProgress(pct);

      if (step >= totalSteps) {
        step = 0;
        setActiveIndex((prev) => (prev + 1) % PRODUCTS.length);
        setProgress(0);
      }
    }, stepMs);

    return () => clearInterval(timer);
  }, [activeIndex]);

  const handleNext = () => {
    setActiveIndex((prev) => (prev + 1) % PRODUCTS.length);
    setProgress(0);
  };

  const handlePrev = () => {
    setActiveIndex((prev) => (prev - 1 + PRODUCTS.length) % PRODUCTS.length);
    setProgress(0);
  };

  const activeProduct = PRODUCTS[activeIndex];

  return (
    <div className="auth-showcase-stage">
      {/* Dynamic Ambient Background Glow */}
      <div
        className="showcase-glow-aurora"
        style={{
          background: `radial-gradient(circle, ${activeProduct.accentColor}35 0%, rgba(99, 102, 241, 0.15) 45%, transparent 70%)`,
        }}
      />

      {/* 1. Header Section (Centered) */}
      <div className="showcase-header">
        <div className="showcase-badge">
          <Sparkles size={14} color={activeProduct.accentColor} />
          <span>CardFlow Enterprise Products & Printing Suite</span>
        </div>

        <h1 className="showcase-headline">
          Smart ID Cards, Badges & <span className="showcase-headline-gradient">Custom Lanyards</span>
        </h1>

        <p className="showcase-lead">
          The all-in-one identity platform trusted by 250+ schools, colleges, and corporate organizations for automated
          student verification, custom satin lanyards, and zero-defect bulk printing.
        </p>
      </div>

      {/* 2. MASSIVE HERO BIG PRODUCT VISUAL & SPECS DISPLAY */}
      <div className="showcase-content-grid" key={activeProduct.id}>
        {/* Large Prominent 3D Product Visual Stage */}
        <div className="showcase-hero-image-wrap">
          <div
            className="showcase-image-aurora"
            style={{ background: `radial-gradient(circle, ${activeProduct.accentColor}45 0%, transparent 70%)` }}
          />
          <img
            key={activeProduct.image}
            src={activeProduct.image}
            alt={activeProduct.title}
            className="showcase-hero-image"
          />
          <div className="showcase-image-reflection" />
        </div>

        {/* Product Details & Feature List */}
        <div className="showcase-details-pane">
          <div className="showcase-category-tag" style={{ color: activeProduct.accentColor }}>
            <span
              style={{
                display: 'inline-block',
                width: '8px',
                height: '8px',
                borderRadius: '50%',
                backgroundColor: activeProduct.accentColor,
                boxShadow: `0 0 12px ${activeProduct.accentColor}`,
                marginRight: '8px',
              }}
            />
            {activeProduct.category}
          </div>

          <h2 className="showcase-product-title">{activeProduct.title}</h2>
          <p className="showcase-product-tagline">{activeProduct.tagline}</p>

          <div className="showcase-spec-pill">
            <Zap size={14} color={activeProduct.accentColor} />
            <span>{activeProduct.stats}</span>
          </div>

          {/* Bullet Points */}
          <div className="showcase-bullets-list">
            {activeProduct.bullets.map((bullet, i) => (
              <div key={i} className="showcase-bullet-row">
                <CheckCircle2 size={16} color="#34d399" className="bullet-check-icon" />
                <span>{bullet}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* 3. CENTER BADGE + 3-DOTS AUTO-SCROLLING CAROUSEL CONTROLS */}
      <div className="showcase-carousel-control-bar">
        {/* Left Dot / Prev */}
        <button
          type="button"
          className="carousel-side-dot-btn"
          onClick={handlePrev}
          aria-label="Previous Product"
        >
          <span className="carousel-dot-circle" />
        </button>

        {/* Center Active Product Badge with Live Progress Fill */}
        <div
          className="carousel-center-badge"
          style={{ borderColor: `${activeProduct.accentColor}77` }}
        >
          <div
            className="carousel-active-fill"
            style={{
              width: `${progress}%`,
              backgroundColor: activeProduct.accentColor,
              boxShadow: `0 0 12px ${activeProduct.accentColor}`,
            }}
          />
          <span className="carousel-center-label">
            <Sparkles size={13} color={activeProduct.accentColor} />
            <span>{activeProduct.name}</span>
          </span>
        </div>

        {/* Right Dot / Next */}
        <button
          type="button"
          className="carousel-side-dot-btn"
          onClick={handleNext}
          aria-label="Next Product"
        >
          <span className="carousel-dot-circle" />
        </button>
      </div>

      {/* 4. EDGE-TO-EDGE 100% FULL-WIDTH OPEN TRUST & TELEMETRY STRIP */}
      <div className="showcase-stats-strip-fullwidth">
        <div className="stat-unit-full">
          <div className="stat-value">150,000+</div>
          <div className="stat-label">ID Cards Printed</div>
        </div>
        <div className="stat-bar" />
        <div className="stat-unit-full">
          <div className="stat-value">250+</div>
          <div className="stat-label">Institutional Clients</div>
        </div>
        <div className="stat-bar" />
        <div className="stat-unit-full">
          <div className="stat-value">1-Click</div>
          <div className="stat-label">Excel Bulk Sync</div>
        </div>
        <div className="stat-bar" />
        <div className="stat-unit-full">
          <div className="stat-value">99.9%</div>
          <div className="stat-label">Print Uptime</div>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────
   Main Auth Split-Layout (Open, Full-Height, Boxless Right Panel)
───────────────────────────────────────────────────────────── */
export default function AuthLayout({ children }) {
  return (
    <div className="auth-fullscreen-layout">
      {/* ── LEFT SIDE: Hero Product Advertisement Showcase ── */}
      <aside className="auth-left-column">
        <ProductShowcase />
      </aside>

      {/* ── RIGHT SIDE: Full-Height Seamless Auth Form (Boxless) ── */}
      <main className="auth-right-column">
        <div className="auth-column-inner">
          {/* Brand Header with Clean Logo */}
          <div className="auth-brand-masthead">
            <img
              src="/cardflow_logo_brand.png"
              alt="CardFlow"
              className="auth-masthead-logo"
              onError={(e) => {
                e.target.style.display = 'none';
              }}
            />
            <span className="auth-masthead-sub">Enterprise ID Card & Printing Workspace</span>
          </div>

          {/* Clean Auth Form Body (Spacious & Centered) */}
          <div className="auth-form-body">{children}</div>

          {/* Mobile App Promotion Footer */}
          <div className="auth-column-footer">
            <div className="auth-mobile-divider">
              <span className="auth-divider-line" />
              <span className="auth-divider-text">Continue with our Mobile App</span>
              <span className="auth-divider-line" />
            </div>

            <a
              href="https://play.google.com/store/apps/details?id=com.adarshid.app"
              target="_blank"
              rel="noopener noreferrer"
              className="google-play-badge"
              title="Get CardFlow on Google Play"
            >
              <svg viewBox="0 0 512 512" width="24" height="24" className="play-store-svg" aria-hidden="true">
                <path d="M325.3 234.3L104.6 13l280.8 161.2-60.1 59.9z" fill="#00e676" />
                <path d="M47 38.1c-2.3 5.4-3.5 11.4-3.5 17.9v400c0 6.5 1.2 12.5 3.5 17.9l219.1-218.4L47 38.1z" fill="#00b0ff" />
                <path d="M325.3 277.7l60.1 59.9L104.6 499l220.7-221.3z" fill="#ff3d00" />
                <path d="M465.1 234.3l-79.7-45.8-60.1 67.5 60.1 67.5 80.1-46.1c16.3-9.4 16.3-33.7-.4-43.1z" fill="#ffd600" />
              </svg>
              <div className="play-badge-text">
                <span className="play-badge-lead">GET IT ON</span>
                <span className="play-badge-title">Google Play</span>
              </div>
            </a>
          </div>
        </div>
      </main>
    </div>
  );
}
