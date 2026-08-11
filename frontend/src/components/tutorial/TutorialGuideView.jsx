import React, { useState } from 'react';
import {
  FileText, CheckSquare, Printer, UserPlus, MoreHorizontal,
  Globe, Film, Play, MoreVertical, Maximize2, ExternalLink
} from 'lucide-react';

const VIDEO_PLAYLIST = [
  {
    id: 'upload',
    title: '1. How to Upload Excel Data & Photos',
    author: 'CardFlow System Guide',
    duration: '3:15',
    embedUrl: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0',
    desc: 'Learn how to format excel files and batch upload student photos.',
    thumbBg: 'linear-gradient(135deg, #1e3a8a 0%, #3b82f6 100%)',
    thumbLabel: 'DATA UPLOAD',
  },
  {
    id: 'verify',
    title: '2. How to Verify & Approve Cards',
    author: 'CardFlow System Guide',
    duration: '2:40',
    embedUrl: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0',
    desc: 'Step-by-step guide to review pending cards and approve print batches.',
    thumbBg: 'linear-gradient(135deg, #065f46 0%, #10b981 100%)',
    thumbLabel: 'VERIFY & APPROVE',
  },
  {
    id: 'reprint',
    title: '3. How to Process Reprint Requests',
    author: 'CardFlow System Guide',
    duration: '4:10',
    embedUrl: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0',
    desc: 'Handle physical card damage or lost card replacement requests.',
    thumbBg: 'linear-gradient(135deg, #9a3412 0%, #f97316 100%)',
    thumbLabel: 'REPRINT QUEUE',
  },
  {
    id: 'assistant',
    title: '4. How to Create Assistant Accounts',
    author: 'CardFlow System Guide',
    duration: '2:05',
    embedUrl: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0',
    desc: 'Set up staff assistant credentials and assign specific table permissions.',
    thumbBg: 'linear-gradient(135deg, #5b21b6 0%, #8b5cf6 100%)',
    thumbLabel: 'ASSISTANT ROLES',
  },
  {
    id: 'export',
    title: '5. How to Export Print-Ready PDFs',
    duration: '3:50',
    author: 'CardFlow System Guide',
    embedUrl: 'https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ?rel=0',
    desc: 'Generate high-res 300 DPI PDF bundles or ZIP image archives.',
    thumbBg: 'linear-gradient(135deg, #831843 0%, #ec4899 100%)',
    thumbLabel: 'PDF EXPORTS',
  },
];

// PDF documents mapping for each tab (User can specify exact path string or URL here in code)
const TAB_PDF_MAP = {
  'check-update': null, // Set to '/docs/check_and_update_data.pdf' or PDF URL
  'reprint': null,      // Set to '/docs/how_to_reprint.pdf' or PDF URL
  'assistant': null,    // Set to '/docs/create_assistant.pdf' or PDF URL
  'others': null,       // Set to '/docs/others_guide.pdf' or PDF URL
};

export default function TutorialGuideView() {
  const [activeTab, setActiveTab] = useState('check-update');
  const [lang, setLang] = useState('en');
  const [activeVideo, setActiveVideo] = useState(VIDEO_PLAYLIST[0]);

  const getTabLabel = (id) => {
    switch (id) {
      case 'check-update': return lang === 'hi' ? 'डेटा जाँचे & बदलें' : 'Check & Update Data';
      case 'reprint': return lang === 'hi' ? 'Reprint गाइड' : 'How to Reprint';
      case 'assistant': return lang === 'hi' ? 'Assistant गाइड' : 'Create Assistant';
      case 'others': return lang === 'hi' ? 'अन्य सुविधाएँ' : 'Others';
      default: return id;
    }
  };

  const pdfUrl = TAB_PDF_MAP[activeTab];

  return (
    <div style={{ width: '100%', height: '100%', padding: 0, margin: 0, background: '#ffffff', overflow: 'hidden' }}>
      
      {/* ── Full-Viewport 0-Gap Grid: Left Direct PDF Viewer (1fr) | Right YouTube Video Library (340px) ── */}
      <div style={{
        display: 'grid', gridTemplateColumns: '1fr 340px', gap: 0,
        width: '100%', height: '100%', background: '#ffffff',
        border: 'none', borderRadius: 0, overflow: 'hidden'
      }}>

        {/* ── LEFT COLUMN: Direct PDF Viewer (No Double Nested Apps) ── */}
        <div style={{ overflowY: 'hidden', display: 'flex', flexDirection: 'column', borderRight: '1px solid #e2e8f0' }}>
          
          {/* Top Bar Navigation Tabs — pill container UI standard */}
          <div className="action-bar" style={{ background: '#1e1e2e', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', height: '50px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxSizing: 'border-box', flexShrink: 0 }}>
            <div className="status-tabs">
              {[
                { id: 'check-update', Icon: CheckSquare },
                { id: 'reprint',      Icon: Printer },
                { id: 'assistant',    Icon: UserPlus },
                { id: 'others',       Icon: MoreHorizontal },
              ].map(({ id, Icon }) => {
                const isActive = activeTab === id;
                return (
                  <button
                    key={id}
                    onClick={() => setActiveTab(id)}
                    className={`status-tab${isActive ? ' active' : ''}`}
                  >
                    <Icon size={13} />
                    <span>{getTabLabel(id)}</span>
                  </button>
                );
              })}
            </div>

            {/* Language Switcher */}
            <button
              onClick={() => setLang((prev) => (prev === 'hi' ? 'en' : 'hi'))}
              style={{
                display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '0 12px', height: '28px',
                borderRadius: '5px', border: '1px solid rgba(255, 255, 255, 0.18)', background: 'rgba(255, 255, 255, 0.08)',
                color: '#ffffff', fontSize: '11px', fontWeight: 600, cursor: 'pointer',
                fontFamily: 'var(--font-family)'
              }}
            >
              <Globe size={13} style={{ color: '#38bdf8' }} />
              <span>{lang === 'hi' ? 'English' : 'Hindi'}</span>
            </button>
          </div>

          {/* ── PDF Container Canvas (Renders PDF iframe if path is linked, or clean Document Placeholder Frame) ── */}
          <div style={{ flex: 1, width: '100%', height: '100%', overflow: 'hidden', background: '#f8fafc', padding: pdfUrl ? 0 : '24px' }}>
            {pdfUrl ? (
              <iframe
                src={pdfUrl}
                title={`PDF Guide - ${getTabLabel(activeTab)}`}
                style={{ width: '100%', height: '100%', border: 'none', display: 'block' }}
              />
            ) : (
              /* Clean Document Canvas Frame (No SPA Fallback Double Nesting) */
              <div style={{
                width: '100%', height: '100%', background: '#ffffff',
                border: '1px solid #cbd5e1', borderRadius: '10px',
                display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                padding: '40px 24px', textAlign: 'center', boxShadow: '0 4px 16px rgba(0,0,0,0.04)'
              }}>
                <div style={{
                  width: '64px', height: '64px', borderRadius: '16px', background: '#eff6ff',
                  color: 'rgb(0, 80, 210)', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  marginBottom: '16px', boxShadow: '0 4px 14px rgba(0, 80, 210, 0.15)'
                }}>
                  <FileText size={32} />
                </div>

                <h3 style={{ margin: '0 0 6px', fontSize: '18px', fontWeight: 800, color: '#0f172a' }}>
                  PDF Design Document Viewer
                </h3>
                <span style={{ fontSize: '12px', fontWeight: 700, color: 'rgb(0, 80, 210)', background: '#eff6ff', padding: '3px 10px', borderRadius: '6px', marginBottom: '16px' }}>
                  Category: {getTabLabel(activeTab)}
                </span>

                <p style={{ margin: '0 0 20px', fontSize: '13px', color: '#64748b', maxWidth: '480px', lineHeight: 1.6 }}>
                  Link your custom design PDF file for this tab in <code>TAB_PDF_MAP</code> inside <code>TutorialGuideView.jsx</code>:
                </p>

                <div style={{ background: '#0f172a', color: '#38bdf8', padding: '12px 20px', borderRadius: '8px', fontSize: '12px', fontFamily: 'monospace', textAlign: 'left' }}>
                  <code>TAB_PDF_MAP['{activeTab}'] = '/docs/{activeTab}_guide.pdf';</code>
                </div>
              </div>
            )}
          </div>

        </div>

        {/* ── RIGHT COLUMN: Embedded Video Player & YouTube Playlist (340px Fixed) ── */}
        <div style={{ width: '340px', height: '100%', overflowY: 'auto', background: '#ffffff', display: 'flex', flexDirection: 'column' }}>
          
          {/* Top Embedded Video Player Card */}
          <div style={{ background: '#0f172a', padding: '16px', color: '#ffffff' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '10px' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#38bdf8', textTransform: 'uppercase', letterSpacing: '0.05em', display: 'flex', alignItems: 'center', gap: '4px' }}>
                <Film size={13} /> Active Tutorial Video
              </span>
              <span style={{ fontSize: '10px', background: 'rgba(255,255,255,0.15)', color: '#ffffff', padding: '1px 6px', borderRadius: '4px', fontWeight: 600 }}>
                {activeVideo.duration}
              </span>
            </div>

            {/* Embedded Video Iframe */}
            <div style={{ position: 'relative', width: '100%', paddingTop: '56.25%', borderRadius: '8px', overflow: 'hidden', background: '#000000' }}>
              <iframe
                src={activeVideo.embedUrl}
                title={activeVideo.title}
                allow="accelerometer; autoplay; clipboard-write; encrypted-media; gyroscope; picture-in-picture"
                allowFullScreen
                style={{ position: 'absolute', top: 0, left: 0, width: '100%', height: '100%', border: 'none' }}
              />
            </div>

            <h4 style={{ margin: '12px 0 4px', fontSize: '13px', fontWeight: 700, color: '#ffffff' }}>
              {activeVideo.title}
            </h4>
            <p style={{ margin: 0, fontSize: '11px', color: '#94a3b8', lineHeight: 1.4 }}>
              {activeVideo.desc}
            </p>
          </div>

          {/* YouTube Style Playlist Library with Small Thumbnail Previews */}
          <div style={{ padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px', flex: 1 }}>
            <div style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span>Tutorial Video Library</span>
              <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>{VIDEO_PLAYLIST.length} Videos</span>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              {VIDEO_PLAYLIST.map((video) => {
                const isSelected = activeVideo.id === video.id;
                return (
                  <div
                    key={video.id}
                    onClick={() => setActiveVideo(video)}
                    style={{
                      display: 'flex', gap: '10px', padding: '6px', borderRadius: '8px',
                      background: isSelected ? '#eff6ff' : 'transparent',
                      border: isSelected ? '1px solid #bfdbfe' : '1px solid transparent',
                      cursor: 'pointer', transition: 'background 0.15s'
                    }}
                    onMouseEnter={(e) => { if (!isSelected) e.currentTarget.style.background = '#f8fafc'; }}
                    onMouseLeave={(e) => { if (!isSelected) e.currentTarget.style.background = 'transparent'; }}
                  >
                    {/* Small Video Thumbnail Box (96px x 56px) */}
                    <div style={{
                      width: '96px', height: '56px', borderRadius: '6px',
                      background: video.thumbBg, flexShrink: 0, position: 'relative',
                      display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
                      color: '#ffffff', overflow: 'hidden', boxShadow: '0 1px 4px rgba(0,0,0,0.15)'
                    }}>
                      <div style={{
                        width: '24px', height: '24px', borderRadius: '50%',
                        background: 'rgba(0,0,0,0.45)', backdropFilter: 'blur(2px)',
                        display: 'flex', alignItems: 'center', justifyContent: 'center'
                      }}>
                        <Play size={11} fill="#ffffff" color="#ffffff" style={{ marginLeft: '1px' }} />
                      </div>
                      <span style={{ fontSize: '8px', fontWeight: 800, textTransform: 'uppercase', letterSpacing: '0.5px', marginTop: '2px', opacity: 0.9 }}>
                        {video.thumbLabel}
                      </span>
                      {/* Duration overlay pill on bottom right */}
                      <span style={{
                        position: 'absolute', bottom: '2px', right: '3px',
                        background: 'rgba(0, 0, 0, 0.8)', color: '#ffffff',
                        fontSize: '9px', fontWeight: 700, padding: '1px 4px', borderRadius: '3px'
                      }}>
                        {video.duration}
                      </span>
                    </div>

                    {/* Video Info (Right) */}
                    <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', justifyContent: 'center' }}>
                      <h5 style={{
                        margin: '0 0 2px', fontSize: '12px', fontWeight: isSelected ? 700 : 600,
                        color: isSelected ? '#1e40af' : '#0f172a',
                        display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
                        overflow: 'hidden', textOverflow: 'ellipsis', lineHeight: 1.3
                      }}>
                        {video.title}
                      </h5>
                      <span style={{ fontSize: '10px', color: '#64748b' }}>
                        {video.author}
                      </span>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', paddingRight: '2px', color: '#94a3b8' }}>
                      <MoreVertical size={14} />
                    </div>

                  </div>
                );
              })}
            </div>

          </div>

        </div>

      </div>
    </div>
  );
}
