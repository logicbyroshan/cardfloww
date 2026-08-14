import React, { useState, useEffect, useCallback } from 'react';
import { Search, Bell, ChevronDown, Home, LogOut, Heart, Clock } from 'lucide-react';
import { dashboardApi } from '../../services/api';

/*
  Exact replica of base.html <header class="topbar">:
  - Left: Welcome message + Blue Heart + Live Time & Date Badge
  - Right: Presence pills + Global Search + User Profile Dropdown
*/

const PAGE_LABELS = {
  dashboard: 'Manage Dashboard',
  cards: 'Tables',
  reprints: 'Reprint Queue',
  organisations: 'Manage Organisation',
  clients: 'Manage Manager',
  staff: 'Manage Operator',
  assistants: 'Manage Assistant',
  photographers: 'Manage Photographer',
  schema: 'Tables',
  panel: 'Manage CardFlow',

  tutorial: 'Tutorial',
  settings: 'Settings',
  pro: 'Manage Pro Features',
};

export default function Header({
  activeTab = 'dashboard',
  searchQuery,
  setSearchQuery,
  currentUser,
  userRole,
  onLogout,
}) {
  const [unreadCount, setUnreadCount] = useState(0);
  const [showUserMenu, setShowUserMenu] = useState(false);
  const [presenceStats, setPresenceStats] = useState({ desktop: 0, mobile: 0, never: 0 });
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formattedDate = time.toLocaleDateString('en-US', {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const formattedTime = time.toLocaleTimeString('en-US', { hour12: false });

  const fetchUnread = useCallback(async () => {
    try {
      const data = await dashboardApi.getUnreadCount();
      setUnreadCount(data.count ?? data.unread_count ?? 0);

      const statsData = await dashboardApi.getStats?.();
      if (statsData) {
        const s = statsData.stats || statsData;
        setPresenceStats({
          desktop: s.desktop_active_users ?? s.desktop_active ?? 0,
          mobile: s.mobile_active_users ?? s.mobile_active ?? 0,
          never: s.never_active_users ?? s.never_active ?? 0,
        });
      }
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    fetchUnread();
    const t = setInterval(fetchUnread, 60_000);
    return () => clearInterval(t);
  }, [fetchUnread]);

  const displayName =
    currentUser?.org_name ||
    currentUser?.name ||
    currentUser?.full_name ||
    (currentUser?.first_name ? `${currentUser.first_name} ${currentUser.last_name || ''}`.trim() : null) ||
    currentUser?.username ||
    (userRole === 'super_admin' ? 'System Admin' : 'User');

  const pageLabel = PAGE_LABELS[activeTab] || activeTab;

  return (
    <header
      className="topbar"
      id="topbar"
      style={{
        height: '50px',
        background: '#1e1e2e',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        color: '#ffffff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '0 16px',
        boxSizing: 'border-box',
      }}
    >
      {/* Left: Brand Logo + Live Time & Date Badge + Animated Blue Heart + Welcome + Name */}
      <div className="nav-left" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
        <img
          src="/cardflow_logo_brand.png"
          onError={(e) => {
            if (!e.target.src.includes('/static/cardflow_logo_brand.png')) {
              e.target.src = '/static/cardflow_logo_brand.png';
            }
          }}
          alt="CardFlow"
          style={{
            height: '26px',
            maxWidth: '120px',
            objectFit: 'contain',
            filter: 'drop-shadow(0 2px 8px rgba(59, 130, 246, 0.45)) brightness(1.15)',
          }}
        />

        {/* 1. Live Date & Time Button Badge */}
        <div
          style={{
            padding: '0 12px',
            height: '28px',
            minWidth: '175px',
            borderRadius: '5px',
            border: '1px solid rgba(59, 130, 246, 0.35)',
            background: 'linear-gradient(135deg, #1e3a8a 0%, #1e293b 100%)',
            color: '#ffffff',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            fontSize: '11px',
            fontWeight: 600,
            boxSizing: 'border-box',
            boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
            fontVariantNumeric: 'tabular-nums',
            fontFeatureSettings: '"tnum"',
          }}
        >
          <Clock size={12} style={{ color: '#60a5fa', flexShrink: 0 }} />
          <span style={{ color: '#bfdbfe', whiteSpace: 'nowrap' }}>{formattedDate}</span>
          <span
            style={{
              color: '#ffffff',
              fontWeight: 700,
              fontVariantNumeric: 'tabular-nums',
              fontFeatureSettings: '"tnum"',
              minWidth: '58px',
              textAlign: 'center',
              display: 'inline-block',
            }}
          >
            {formattedTime}
          </span>
        </div>

        {/* 2. Animated Blue Heart + Welcome + Name */}
        <div
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: '6px',
            fontSize: '13px',
            fontWeight: 600,
            color: '#f1f5f9',
          }}
        >
          <Heart size={14} fill="#3b82f6" color="#3b82f6" className="heart-pulse-anim" />
          <span>Welcome</span>
          <strong style={{ color: '#60a5fa', fontWeight: 700 }}>{displayName}</strong>
        </div>
      </div>

      {/* Right: active user status pills + global search + notification bell */}
      <div className="nav-right" style={{ display: 'flex', alignItems: 'center', gap: '8px', marginLeft: 'auto' }}>
        {/* Status Pills matching dark navbar theme */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', fontWeight: 600 }}>
          <span
            style={{
              padding: '0 10px',
              height: '28px',
              borderRadius: '5px',
              border: '1px solid #10b981',
              background: '#064e3b',
              color: '#a7f3d0',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              boxSizing: 'border-box',
            }}
          >
            <span
              style={{
                width: '6px',
                height: '6px',
                borderRadius: '50%',
                background: '#34d399',
                boxShadow: '0 0 6px #34d399',
              }}
            />
            Live Working Users: <strong style={{ color: '#ffffff' }}>0</strong>
          </span>
          <span
            style={{
              padding: '0 10px',
              height: '28px',
              borderRadius: '5px',
              border: '1px solid #2563eb',
              background: '#1e3a8a',
              color: '#93c5fd',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              boxSizing: 'border-box',
            }}
          >
            Total Desktop Active: <strong style={{ color: '#ffffff' }}>{presenceStats.desktop}</strong>
          </span>
          <span
            style={{
              padding: '0 10px',
              height: '28px',
              borderRadius: '5px',
              border: '1px solid #ea580c',
              background: '#7c2d12',
              color: '#fdba74',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              boxSizing: 'border-box',
            }}
          >
            Total Mobile Active: <strong style={{ color: '#ffffff' }}>{presenceStats.mobile}</strong>
          </span>
          <span
            style={{
              padding: '0 10px',
              height: '28px',
              borderRadius: '5px',
              border: '1px solid #475569',
              background: '#1e293b',
              color: '#cbd5e1',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '5px',
              boxSizing: 'border-box',
            }}
          >
            Total Never Active: <strong style={{ color: '#ffffff' }}>{presenceStats.never}</strong>
          </span>
        </div>
      </div>
    </header>
  );
}
