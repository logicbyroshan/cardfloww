import React from 'react';
import {
  Home,
  Users,
  UserCog,
  UsersRound,
  Camera,
  SlidersHorizontal,
  Gem,
  BookOpen,
  GitBranch,
  LogOut,
  ShieldCheck,
  Building,
} from 'lucide-react';

/*
  Exact replica of templates/partials/sidebar.html
  Menu items and sections match the Django template 1-to-1.
*/

// Role-gated nav structure — mirrors original role boundaries
const NAV_CONFIG = {
  super_admin: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Admin Management',
      items: [
        { id: 'staff', label: 'Manage Operator', Icon: UserCog },
        { id: 'photographers', label: 'Manage Photographer', Icon: Camera },
      ],
    },
    {
      section: 'Client Management',
      items: [{ id: 'organisations', label: 'Manage Organisation', Icon: Building }],
    },
    {
      section: 'CardFlow Management',
      items: [
        { id: 'panel', label: 'Manage CardFlow', Icon: SlidersHorizontal },
        { id: 'pro', label: 'Manage Pro Features', Icon: Gem },
      ],
    },
  ],
  operator: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Client Management',
      items: [{ id: 'organisations', label: 'Manage Organisation', Icon: Building }],
    },
    {
      section: 'CardFlow Management',
      items: [{ id: 'panel', label: 'Manage CardFlow', Icon: SlidersHorizontal }],
    },
  ],
  client: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Management',
      items: [{ id: 'staff', label: 'Manage Assistant', Icon: UserCog }],
    },
    {
      section: 'ID Card Management',
      items: [
        { id: 'cards', label: 'Tables', Icon: ShieldCheck },
        { id: 'settings', label: 'Settings', Icon: UserCog },
      ],
    },
  ],
  assistant: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'ID Card Management',
      items: [{ id: 'cards', label: 'Tables', Icon: ShieldCheck }],
    },
  ],
  photographer: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'ID Card Management',
      items: [{ id: 'cards', label: 'Tables', Icon: Camera }],
    },
  ],
};

const ROLE_COLORS = {
  super_admin: { bg: 'linear-gradient(145deg, #7c3aed, #6d28d9)', color: '#ede9fe' },
  pro_user: { bg: 'linear-gradient(145deg, #7c3aed, #6d28d9)', color: '#ede9fe' },
  operator: { bg: 'linear-gradient(145deg, #2563eb, #1d4ed8)', color: '#dbeafe' },
  admin_staff: { bg: 'linear-gradient(145deg, #2563eb, #1d4ed8)', color: '#dbeafe' },
  prime_manager: { bg: 'linear-gradient(145deg, #059669, #047857)', color: '#d1fae5' },
  manager: { bg: 'linear-gradient(145deg, #0d9488, #0f766e)', color: '#ccfbf1' },
  guest_prime_manager: { bg: 'linear-gradient(145deg, #65a30d, #4d7c0f)', color: '#ecfccb' },
  assistant: { bg: 'linear-gradient(145deg, #0891b2, #0e7490)', color: '#cffafe' },
  photographer: { bg: 'linear-gradient(145deg, #d97706, #b45309)', color: '#fef3c7' },
  // Compat aliases
  client: { bg: 'linear-gradient(145deg, #059669, #047857)', color: '#d1fae5' },
  client_staff: { bg: 'linear-gradient(145deg, #0891b2, #0e7490)', color: '#cffafe' },
};

const ROLE_LABELS = {
  super_admin: 'Super Admin',
  pro_user: 'Pro Admin',
  operator: 'Operator',
  admin_staff: 'Operator',
  prime_manager: 'Prime Manager',
  manager: 'Manager',
  guest_prime_manager: 'Guest Prime Manager',
  assistant: 'Assistant',
  photographer: 'Photographer',
  // Compat aliases
  client: 'Prime Manager',
  client_staff: 'Assistant',
};

const APP_VERSION = 'v5.0.0';

export default function Sidebar({ activeTab, setActiveTab, userRole = 'super_admin', currentUser, onLogout }) {
  const normalizedRole = String(userRole || '').toLowerCase();
  const roleKey =
    normalizedRole === 'admin' || normalizedRole === 'pro_user'
      ? 'super_admin'
      : normalizedRole === 'admin_staff'
        ? 'operator'
        : normalizedRole === 'client_staff'
          ? 'assistant'
          : normalizedRole === 'client'
            ? 'prime_manager'
            : normalizedRole === 'guest_user'
              ? 'guest_prime_manager'
              : NAV_CONFIG[normalizedRole]
                ? normalizedRole
                : 'super_admin';
  const navConfig = NAV_CONFIG[roleKey] || NAV_CONFIG.super_admin;

  const displayName = currentUser?.first_name
    ? `${currentUser.first_name} ${currentUser.last_name || ''}`.trim()
    : currentUser?.username || currentUser?.email || 'Admin';

  const initials = displayName.slice(0, 2).toUpperCase();
  const roleLabel = ROLE_LABELS[roleKey] || roleKey;

  return (
    <aside className="sidebar" id="sidebar">
      {/* ── Header / Logo ── */}
      <div
        className="sidebar-header"
        style={{
          padding: '8px 12px',
          height: '50px',
          minHeight: '50px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '100%',
          borderBottom: '1px solid rgba(255, 255, 255, 0.06)',
          background: '#1e1e2e',
          boxSizing: 'border-box',
        }}
      >
        <div className="logo-flare-container">
          <img
            src="/static/cardflow_logo_brand.png"
            onError={(e) => {
              if (!e.target.src.endsWith('/cardflow_logo_brand.png')) {
                e.target.src = '/cardflow_logo_brand.png';
              }
            }}
            alt="CardFlow"
            style={{
              maxHeight: '34px',
              maxWidth: '160px',
              width: '100%',
              objectFit: 'contain',
              background: 'transparent',
            }}
          />
        </div>
      </div>

      {/* ── Navigation ── */}
      <nav aria-label="Main navigation">
        {navConfig.map((entry, idx) => {
          if (entry.section) {
            return (
              <React.Fragment key={idx}>
                <div className="nav-section">
                  <div className="nav-section-line" />
                  <span className="nav-section-title">{entry.section}</span>
                  <div className="nav-section-line" />
                </div>
                {entry.items.map((item) => {
                  const Icon = item.Icon;
                  return (
                    <button
                      key={item.id}
                      onClick={() => setActiveTab(item.id)}
                      className={`nav-item${activeTab === item.id ? ' active' : ''}`}
                    >
                      <Icon size={13} />
                      <span>{item.label}</span>
                    </button>
                  );
                })}
              </React.Fragment>
            );
          }
          const Icon = entry.Icon;
          return (
            <button
              key={entry.id}
              onClick={() => setActiveTab(entry.id)}
              className={`nav-item${activeTab === entry.id ? ' active' : ''}`}
            >
              <Icon size={13} />
              <span>{entry.label}</span>
            </button>
          );
        })}
      </nav>

      {/* ── Footer — matches sidebar.html ── */}
      <div className="sidebar-footer">
        {/* Tutorial link */}
        <div className="sidebar-actions">
          <button
            onClick={() => setActiveTab('tutorial')}
            className={`nav-item${activeTab === 'tutorial' ? ' active' : ''}`}
          >
            <BookOpen size={13} />
            <span>Tutorial</span>
          </button>
        </div>

        {/* User tile — clicking goes to Profile / Settings */}
        <div
          className="sidebar-user"
          style={{ width: 'calc(100% - 12px)', cursor: 'pointer' }}
          onClick={() => setActiveTab('settings')}
          title="Go to Profile / Settings"
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && setActiveTab('settings')}
        >
          {/* Avatar */}
          <div
            style={{
              width: '28px',
              height: '28px',
              borderRadius: '4px',
              background: 'linear-gradient(135deg, #f97316, #ea580c)',
              color: '#fff',
              fontSize: '11px',
              fontWeight: 700,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              flexShrink: 0,
            }}
          >
            {initials}
          </div>

          {/* Name + Role */}
          <div style={{ minWidth: 0, flex: 1 }}>
            <span
              style={{
                fontSize: '12px',
                fontWeight: 600,
                color: '#fff',
                display: 'block',
                overflow: 'hidden',
                textOverflow: 'ellipsis',
                whiteSpace: 'nowrap',
              }}
            >
              {displayName || 'System Admin'}
            </span>
            <span style={{ fontSize: '10px', color: '#f97316', fontWeight: 600, display: 'block' }}>{roleLabel}</span>
          </div>
        </div>
      </div>
    </aside>
  );
}
