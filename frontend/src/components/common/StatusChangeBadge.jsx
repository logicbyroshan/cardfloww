import React from 'react';

const STATUS_CONFIGS = {
  pending: {
    border: '#f97316',
    countColor: '#c2410c',
    hoverBg: '#fff7ed',
  },
  verified: {
    border: '#10b981',
    countColor: '#047857',
    hoverBg: '#ecfdf5',
  },
  approved: {
    border: '#2563eb',
    countColor: '#1d4ed8',
    hoverBg: '#eff6ff',
  },
  printed: {
    border: '#64748b',
    countColor: '#334155',
    hoverBg: '#f8fafc',
  },
  downloaded: {
    border: '#64748b',
    countColor: '#334155',
    hoverBg: '#f8fafc',
  },
  request: {
    border: '#8b5cf6',
    countColor: '#6d28d9',
    hoverBg: '#f5f3ff',
  },
  requested: {
    border: '#8b5cf6',
    countColor: '#6d28d9',
    hoverBg: '#f5f3ff',
  },
  pool: {
    border: '#ef4444',
    countColor: '#b91c1c',
    hoverBg: '#fef2f2',
  },
  deleted: {
    border: '#ef4444',
    countColor: '#b91c1c',
    hoverBg: '#fef2f2',
  },
  reprint: {
    border: '#d97706',
    countColor: '#b45309',
    hoverBg: '#fffbeb',
  },
  confirmed: {
    border: '#059669',
    countColor: '#047857',
    hoverBg: '#ecfdf5',
  },
};

export default function StatusChangeBadge({
  count = 0,
  statusKey = 'pending',
  onClick,
  title = '',
  size = 'normal',
}) {
  const normKey = (statusKey || 'pending').toLowerCase();
  const cfg = STATUS_CONFIGS[normKey] || STATUS_CONFIGS.pending;
  const numCount = Number(count) || 0;
  const isSmall = size === 'small';

  return (
    <button
      onClick={onClick}
      title={title || `${numCount} ${normKey} cards`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        background: '#ffffff',
        border: `1.5px solid ${cfg.border}`,
        borderRadius: '6px',
        padding: isSmall ? '2px 8px' : '3px 12px',
        minWidth: isSmall ? '36px' : '44px',
        height: isSmall ? '22px' : '26px',
        cursor: onClick ? 'pointer' : 'default',
        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
        transition: 'all 0.15s ease-in-out',
        fontFamily: 'var(--font-family)',
        userSelect: 'none',
      }}
      onMouseEnter={(e) => {
        if (onClick) {
          e.currentTarget.style.background = cfg.hoverBg;
          e.currentTarget.style.boxShadow = '0 2px 4px rgba(0,0,0,0.08)';
        }
      }}
      onMouseLeave={(e) => {
        if (onClick) {
          e.currentTarget.style.background = '#ffffff';
          e.currentTarget.style.boxShadow = '0 1px 2px rgba(0,0,0,0.04)';
        }
      }}
    >
      <span
        style={{
          fontSize: isSmall ? '11px' : '12.5px',
          fontWeight: 800,
          color: cfg.countColor,
          lineHeight: 1,
        }}
      >
        {numCount}
      </span>
    </button>
  );
}

export function StatusChangeDeltaPill() {
  return null;
}
