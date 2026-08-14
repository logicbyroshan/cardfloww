import React from 'react';
import { getHourlyChange } from '../../utils/hourlyTracker';

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
  entityId = '',
  onClick,
  title = '',
  size = 'normal',
}) {
  const normKey = (statusKey || 'pending').toLowerCase();
  const cfg = STATUS_CONFIGS[normKey] || STATUS_CONFIGS.pending;
  const numCount = Number(count) || 0;

  // Calculate 1-hour change delta
  const change = getHourlyChange(entityId, normKey, numCount);

  // Configure right-side change pill style
  let changeBg = '#f8fafc';
  let changeColor = '#64748b';
  let changeBorder = '#e2e8f0';
  let changeText = '+0';

  if (change > 0) {
    changeBg = '#ecfdf5';
    changeColor = '#059669';
    changeBorder = '#a7f3d0';
    changeText = `↑+${change}`;
  } else if (change < 0) {
    changeBg = '#fef2f2';
    changeColor = '#dc2626';
    changeBorder = '#fca5a5';
    changeText = `↓${change}`;
  } else {
    changeBg = '#f1f5f9';
    changeColor = '#64748b';
    changeBorder = '#cbd5e1';
    changeText = '+0';
  }

  const isSmall = size === 'small';

  return (
    <button
      onClick={onClick}
      title={title || `${numCount} ${normKey} cards (${changeText} in last 1h)`}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        background: '#ffffff', // Pure white fill
        border: `1.5px solid ${cfg.border}`, // Status color outline
        borderRadius: '6px',
        padding: isSmall ? '2px 6px' : '3px 8px',
        minWidth: isSmall ? '60px' : '74px',
        height: isSmall ? '24px' : '28px',
        cursor: onClick ? 'pointer' : 'default',
        boxShadow: '0 1px 2px rgba(0,0,0,0.04)',
        transition: 'all 0.15s ease-in-out',
        fontFamily: 'var(--font-family)',
        userSelect: 'none',
        gap: '6px',
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
      {/* Left Side: Big Count Number */}
      <span
        style={{
          fontSize: isSmall ? '11px' : '13px',
          fontWeight: 800,
          color: cfg.countColor,
          lineHeight: 1,
        }}
      >
        {numCount}
      </span>

      {/* Right Side: Change Badge (Up/Down Arrow & Color) */}
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          fontSize: isSmall ? '8px' : '9.5px',
          fontWeight: 700,
          color: changeColor,
          background: changeBg,
          border: `1px solid ${changeBorder}`,
          borderRadius: '3px',
          padding: '0 3px',
          height: isSmall ? '14px' : '16px',
          lineHeight: 1,
          whiteSpace: 'nowrap',
        }}
      >
        {changeText}
      </span>
    </button>
  );
}

export function StatusChangeDeltaPill({ entityId, statusKey = 'pending', count = 0, size = 'normal' }) {
  const normKey = (statusKey || 'pending').toLowerCase();
  const cfg = STATUS_CONFIGS[normKey] || STATUS_CONFIGS.pending;
  const numCount = Number(count) || 0;
  const change = getHourlyChange(entityId, normKey, numCount);

  let changeBg = '#f1f5f9';
  let changeColor = '#64748b';
  let changeBorder = '#cbd5e1';
  let changeText = '+0';

  if (change > 0) {
    changeBg = '#ecfdf5';
    changeColor = '#059669';
    changeBorder = '#a7f3d0';
    changeText = `↑+${change}`;
  } else if (change < 0) {
    changeBg = '#fef2f2';
    changeColor = '#dc2626';
    changeBorder = '#fca5a5';
    changeText = `↓${change}`;
  }

  const isSmall = size === 'small';

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: isSmall ? '8px' : '9.5px',
        fontWeight: 700,
        color: changeColor,
        background: changeBg,
        border: `1px solid ${changeBorder}`,
        borderRadius: '3px',
        padding: '0 3.5px',
        height: isSmall ? '14px' : '16px',
        lineHeight: 1,
        whiteSpace: 'nowrap',
      }}
    >
      {changeText}
    </span>
  );
}
