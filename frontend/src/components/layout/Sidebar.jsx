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

// Role-gated nav structure — exact per role requirements
const NAV_CONFIG = {
  prime_admin: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Admin Management',
      items: [
        { id: 'operators', label: 'Manage Operator', Icon: UserCog },
        { id: 'photographers', label: 'Manage Photographer', Icon: Camera },
      ],
    },
    {
      section: 'Client Management',
      items: [
        { id: 'organisations', label: 'Manage Organisation', Icon: Building },
      ],
    },
    {
      section: 'CardFlow Management',
      items: [
        { id: 'panel', label: 'Manage CardFlow', Icon: SlidersHorizontal },
        { id: 'pro', label: 'Manage Pro Features', Icon: Gem },
      ],
    },
  ],

  super_admin: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Admin Management',
      items: [
        { id: 'operators', label: 'Manage Operator', Icon: UserCog },
        { id: 'photographers', label: 'Manage Photographer', Icon: Camera },
      ],
    },
    {
      section: 'Client Management',
      items: [
        { id: 'organisations', label: 'Manage Organisation', Icon: Building },
      ],
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
      section: 'Admin Management',
      items: [{ id: 'photographers', label: 'Manage Photographer', Icon: Camera }],
    },
    {
      section: 'Client Management',
      items: [{ id: 'organisations', label: 'Manage Organisation', Icon: Building }],
    },
    {
      section: 'CardFlow Management',
      items: [{ id: 'panel', label: 'Manage CardFlow', Icon: SlidersHorizontal }],
    },
  ],

  prime_manager: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Organisation Management',
      items: [
        { id: 'assistants', label: 'Manage Assistant', Icon: UsersRound },
        { id: 'cards', label: 'Manage Tables', Icon: ShieldCheck },
      ],
    },
  ],

  super_manager: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Organisation Management',
      items: [
        { id: 'assistants', label: 'Manage Assistant', Icon: UsersRound },
        { id: 'cards', label: 'Manage Tables', Icon: ShieldCheck },
      ],
    },
  ],

  manager: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'Organisation Management',
      items: [
        { id: 'assistants', label: 'Manage Assistant', Icon: UsersRound },
        { id: 'cards', label: 'Manage Tables', Icon: ShieldCheck },
      ],
    },
  ],

  assistant: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'ID Card Management',
      items: [
        { id: 'cards', label: 'Manage Tables', Icon: ShieldCheck },
      ],
    },
  ],

  photographer: [
    { id: 'dashboard', label: 'Manage Dashboard', Icon: Home },
    {
      section: 'ID Card Management',
      items: [{ id: 'cards', label: 'Manage Tables', Icon: Camera }],
    },
  ],
};

const ROLE_COLORS = {
  prime_admin: { bg: 'linear-gradient(145deg, #0ea5e9, #0284c7)', color: '#e0f2fe' },
  super_admin: { bg: 'linear-gradient(145deg, #7c3aed, #6d28d9)', color: '#ede9fe' },
  operator: { bg: 'linear-gradient(145deg, #2563eb, #1d4ed8)', color: '#dbeafe' },
  prime_manager: { bg: 'linear-gradient(145deg, #059669, #047857)', color: '#d1fae5' },
  super_manager: { bg: 'linear-gradient(145deg, #0d9488, #0f766e)', color: '#ccfbf1' },
  manager: { bg: 'linear-gradient(145deg, #0d9488, #0f766e)', color: '#ccfbf1' },
  assistant: { bg: 'linear-gradient(145deg, #0891b2, #0e7490)', color: '#cffafe' },
  photographer: { bg: 'linear-gradient(145deg, #d97706, #b45309)', color: '#fef3c7' },
};

const ROLE_LABELS = {
  prime_admin: 'Prime Admin',
  super_admin: 'Super Admin',
  operator: 'Operator',
  prime_manager: 'Prime Manager',
  super_manager: 'Super Manager',
  manager: 'Super Manager',
  assistant: 'Assistant',
  photographer: 'Photographer',
};

const APP_VERSION = 'v5.0.0';

export default function Sidebar({
  activeTab,
  setActiveTab,
  userRole = 'super_admin',
  currentUser,
  onLogout,
  impersonatedUser,
  onExitImpersonation,
}) {
  const normalizedRole = String(userRole || '').toLowerCase();
  let roleKey = 'super_admin';
  if (normalizedRole === 'prime_admin' || normalizedRole === 'pro_user') {
    roleKey = 'prime_admin';
  } else if (normalizedRole === 'super_admin' || normalizedRole === 'admin') {
    roleKey = 'super_admin';
  } else if (normalizedRole === 'operator' || normalizedRole === 'admin_staff') {
    roleKey = 'operator';
  } else if (normalizedRole === 'prime_manager' || normalizedRole === 'client') {
    roleKey = 'prime_manager';
  } else if (normalizedRole === 'super_manager' || normalizedRole === 'manager') {
    roleKey = 'super_manager';
  } else if (normalizedRole === 'assistant' || normalizedRole === 'client_staff') {
    roleKey = 'assistant';
  } else if (normalizedRole === 'photographer') {
    roleKey = 'photographer';
  }

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
          background: 'transparent',
          boxShadow: 'none',
          boxSizing: 'border-box',
        }}
      >
        <div className="logo-flare-container" style={{ display: 'flex', alignItems: 'center', gap: '8px', background: 'transparent' }}>
          <img
            src="/cardflow_logo_brand.png"
            onError={(e) => {
              if (!e.target.src.includes('/static/cardflow_logo_brand.png')) {
                e.target.src = '/static/cardflow_logo_brand.png';
              }
            }}
            alt="CardFlow"
            style={{
              maxHeight: '34px',
              maxWidth: '160px',
              width: 'auto',
              objectFit: 'contain',
              background: 'transparent',
              filter: 'drop-shadow(0 2px 10px rgba(0, 180, 255, 0.45)) brightness(1.15) contrast(1.05)',
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

      {/* ── Footer ── */}
      <div className="sidebar-footer">
        {/* Impersonation Indicator — compact box placed directly on top of Tutorial */}
        {impersonatedUser && (
          <div
            className="sidebar-impersonate-badge"
            title={`Active Impersonation: ${impersonatedUser.name} (${impersonatedUser.role || impersonatedUser.email})`}
          >
            <div className="sidebar-impersonate-content">
              <div className="sidebar-impersonate-label">
                <span className="sidebar-impersonate-dot" />
                <UserCog size={11} />
                <span>IMPERSONATING</span>
              </div>
              <div className="sidebar-impersonate-name">
                {impersonatedUser.name || impersonatedUser.username || 'User'}
              </div>
            </div>
            {onExitImpersonation && (
              <button
                type="button"
                onClick={(e) => {
                  e.stopPropagation();
                  onExitImpersonation();
                }}
                className="sidebar-impersonate-exit-btn"
                title="Exit Impersonation Session"
              >
                <LogOut size={10} />
                <span>Exit</span>
              </button>
            )}
          </div>
        )}

        {/* Tutorial link */}
        <div className="sidebar-actions">
          <button
            onClick={() => setActiveTab('tutorial')}
            className={`nav-item${activeTab === 'tutorial' ? ' active' : ''}`}
            id="sidebar-tutorial-btn"
          >
            <BookOpen size={13} />
            <span>Tutorial</span>
          </button>
        </div>

        {/* User tile — clicking goes to Profile / Settings */}
        <div
          className="sidebar-user"
          onClick={() => setActiveTab('settings')}
          title="Go to Profile / Settings"
          role="button"
          tabIndex={0}
          onKeyDown={(e) => e.key === 'Enter' && setActiveTab('settings')}
          id="sidebar-user-tile"
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
