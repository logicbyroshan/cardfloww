/**
 * Footer.jsx
 *
 * Global solid black footer component matching topbar aesthetics.
 * Left: Interactive Breadcrumb Navigation with clickable back steps.
 * Right: Modern Data Count / Stats badge.
 */

import React, { useState, useEffect } from 'react';
import {
  ChevronRight,
  Home,
  Layers,
  Table,
  Users,
  UserCheck,
  Shield,
  Settings,
  Sliders,
  HelpCircle,
  Sparkles,
} from 'lucide-react';

export default function Footer({ activeTab, onNavigate, idcardActionsState }) {
  const [dataCountText, setDataCountText] = useState('');

  // Listen for custom data-count updates from any active view component
  useEffect(() => {
    const handleCountUpdate = (e) => {
      if (e.detail?.text) setDataCountText(e.detail.text);
    };
    window.addEventListener('cardflow:data-count', handleCountUpdate);
    return () => window.removeEventListener('cardflow:data-count', handleCountUpdate);
  }, []);

  // Compute breadcrumb segments based on active tab
  const getBreadcrumbs = () => {
    switch (activeTab) {
      case 'dashboard':
        return [{ label: 'CardFlow', isCurrent: true, icon: Home }];
      case 'cards':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Table Group', isCurrent: true, icon: Layers },
        ];
      case 'idcard-actions':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Table Group', tab: 'cards', icon: Layers },
          {
            label: `Table Actions (${(idcardActionsState?.status || 'pending').toUpperCase()})`,
            isCurrent: true,
            icon: Table,
          },
        ];
      case 'schema':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Table Group', tab: 'cards', icon: Layers },
          { label: 'Table Settings', isCurrent: true, icon: Settings },
        ];
      case 'clients':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Client Management' },
          { label: 'Manage Organisation', isCurrent: true, icon: Users },
        ];
      case 'staff':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Admin Management' },
          { label: 'Manage Operator', isCurrent: true, icon: UserCheck },
        ];
      case 'assistants':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Admin Management' },
          { label: 'Manage Assistant', isCurrent: true, icon: UserCheck },
        ];
      case 'photographers':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Admin Management' },
          { label: 'Manage Photographer', isCurrent: true, icon: UserCheck },
        ];
      case 'panel':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'CardFlow Management' },
          { label: 'Manage CardFlow', isCurrent: true, icon: Sliders },
        ];
      case 'pro':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'CardFlow Management' },
          { label: 'Manage Pro Features', isCurrent: true, icon: Sparkles },
        ];
      case 'tutorial':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Tutorial & Guide', isCurrent: true, icon: HelpCircle },
        ];
      case 'settings':
      case 'profile':
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: 'Profile & Settings', isCurrent: true, icon: Settings },
        ];
      default:
        return [
          { label: 'CardFlow', tab: 'dashboard', icon: Home },
          { label: activeTab, isCurrent: true },
        ];
    }
  };

  const breadcrumbs = getBreadcrumbs();

  return (
    <footer
      style={{
        flexShrink: 0,
        height: '36px',
        background: '#1e1e2e',
        borderTop: '1px solid rgba(255, 255, 255, 0.08)',
        padding: '0 16px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        color: '#94a3b8',
        fontSize: '12px',
        boxSizing: 'border-box',
        zIndex: 100,
      }}
    >
      {/* Left: Interactive Breadcrumbs */}
      <nav aria-label="Breadcrumb" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
        {breadcrumbs.map((item, idx) => {
          const Icon = item.icon;
          return (
            <React.Fragment key={idx}>
              {idx > 0 && <ChevronRight size={13} style={{ color: '#475569', flexShrink: 0 }} />}
              {item.isCurrent ? (
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '5px',
                    padding: '2px 8px',
                    borderRadius: '4px',
                    background: 'rgba(255, 255, 255, 0.1)',
                    color: '#ffffff',
                    fontWeight: 600,
                    fontSize: '11px',
                    letterSpacing: '0.01em',
                  }}
                >
                  {Icon && <Icon size={12} style={{ color: '#38bdf8' }} />}
                  {item.label}
                </span>
              ) : item.tab ? (
                <button
                  type="button"
                  onClick={() => onNavigate?.(item.tab)}
                  style={{
                    background: 'none',
                    border: 'none',
                    padding: '2px 4px',
                    color: '#94a3b8',
                    fontWeight: 500,
                    fontSize: '11px',
                    cursor: 'pointer',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    transition: 'color 0.15s ease',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.color = '#38bdf8')}
                  onMouseLeave={(e) => (e.currentTarget.style.color = '#94a3b8')}
                >
                  {Icon && <Icon size={12} />}
                  {item.label}
                </button>
              ) : (
                <span style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>{item.label}</span>
              )}
            </React.Fragment>
          );
        })}
      </nav>

      {/* Right: Modern Data Count / System Badge */}
      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {dataCountText ? (
          <span
            className="footer-badge"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 10px',
              borderRadius: '4px',
              background: 'rgba(255, 255, 255, 0.1)',
              border: '1px solid rgba(255, 255, 255, 0.18)',
              fontSize: '11px',
              fontWeight: 600,
              color: '#e2e8f0',
              userSelect: 'none',
            }}
          >
            <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#10b981' }} />
            {dataCountText}
          </span>
        ) : (
          <span style={{ fontSize: '11px', color: '#64748b' }}>CardFlow System Active</span>
        )}
      </div>
    </footer>
  );
}
