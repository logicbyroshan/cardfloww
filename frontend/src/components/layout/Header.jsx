import React, { useState, useEffect, useCallback } from 'react';
import { Search, Bell, ChevronDown, Home, LogOut, Heart, Clock, MessageSquare } from 'lucide-react';
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
  onOpenActionDrawer,
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
        height: '48px',
        minHeight: '48px',
        background: '#1e1e2e',
        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
        color: '#ffffff',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        padding: '6px 6px',
        boxSizing: 'border-box',
      }}
    >
      {/* Left: Chat Button + Live Time & Date Badge + Animated Blue Heart + Welcome + Name */}
      <div className="nav-left" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
        {/* 0. Chat Button placed before the Date & Time Badge */}
        <button
          type="button"
          onClick={() => onOpenActionDrawer?.('message')}
          className="nav-chat-btn"
          title="Open Messenger / Broadcast Chat"
          style={{
            padding: '4px 8px',
            height: '32px',
            borderRadius: '4px',
            border: '1px solid rgba(99, 102, 241, 0.5)',
            background: 'linear-gradient(135deg, #312e81 0%, #1e1b4b 100%)',
            color: '#e0e7ff',
            display: 'inline-flex',
            alignItems: 'center',
            justifyContent: 'center',
            gap: '6px',
            fontSize: '11.5px',
            fontWeight: 600,
            cursor: 'pointer',
            boxSizing: 'border-box',
            boxShadow: '0 1px 4px rgba(0,0,0,0.3)',
            transition: 'all 0.2s ease',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.9)';
            e.currentTarget.style.boxShadow = '0 0 10px rgba(99, 102, 241, 0.4)';
            e.currentTarget.style.color = '#ffffff';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.borderColor = 'rgba(99, 102, 241, 0.5)';
            e.currentTarget.style.boxShadow = '0 1px 4px rgba(0,0,0,0.3)';
            e.currentTarget.style.color = '#e0e7ff';
          }}
        >
          <MessageSquare size={13} style={{ color: '#818cf8', flexShrink: 0 }} />
          <span>Chat</span>
        </button>

        {/* 1. Live Date & Time Button Badge */}
        <div
          style={{
            padding: '4px 8px',
            height: '32px',
            minWidth: '175px',
            borderRadius: '4px',
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
              padding: '4px 8px',
              height: '32px',
              borderRadius: '4px',
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
              padding: '4px 8px',
              height: '32px',
              borderRadius: '4px',
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
              padding: '4px 8px',
              height: '32px',
              borderRadius: '4px',
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
              padding: '4px 8px',
              height: '32px',
              borderRadius: '4px',
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
