import React from 'react';
import { Loader2 } from 'lucide-react';

const SIZES = {
  sm: {
    height: '28px',
    padding: '0 10px',
    fontSize: '11.5px',
    fontWeight: 600,
    borderRadius: '4px',
    gap: '5px',
    iconSize: 13,
  },
  md: {
    height: '36px',
    padding: '0 16px',
    fontSize: '13px',
    fontWeight: 600,
    borderRadius: '6px',
    gap: '6px',
    iconSize: 15,
  },
  lg: {
    height: '42px',
    padding: '0 20px',
    fontSize: '14px',
    fontWeight: 700,
    borderRadius: '8px',
    gap: '8px',
    iconSize: 18,
  },
  'icon-sm': {
    width: '28px',
    height: '28px',
    padding: '0',
    fontSize: '11.5px',
    fontWeight: 600,
    borderRadius: '4px',
    gap: '0',
    iconSize: 13,
  },
  'icon-md': {
    width: '36px',
    height: '36px',
    padding: '0',
    fontSize: '13px',
    fontWeight: 600,
    borderRadius: '6px',
    gap: '0',
    iconSize: 16,
  },
};

const VARIANTS = {
  primary: {
    bg: '#2563eb',
    color: '#ffffff',
    border: '1px solid #2563eb',
    hoverBg: '#1d4ed8',
    hoverBorder: '#1d4ed8',
    activeBg: '#1e40af',
  },
  secondary: {
    bg: '#ffffff',
    color: '#334155',
    border: '1px solid #cbd5e1',
    hoverBg: '#f8fafc',
    hoverBorder: '#94a3b8',
    activeBg: '#f1f5f9',
  },
  danger: {
    bg: '#ef4444',
    color: '#ffffff',
    border: '1px solid #ef4444',
    hoverBg: '#dc2626',
    hoverBorder: '#dc2626',
    activeBg: '#b91c1c',
  },
  success: {
    bg: '#10b981',
    color: '#ffffff',
    border: '1px solid #10b981',
    hoverBg: '#059669',
    hoverBorder: '#059669',
    activeBg: '#047857',
  },
  warning: {
    bg: '#f59e0b',
    color: '#ffffff',
    border: '1px solid #f59e0b',
    hoverBg: '#d97706',
    hoverBorder: '#d97706',
    activeBg: '#b45309',
  },
  neutral: {
    bg: 'rgba(255, 255, 255, 0.08)',
    color: '#ffffff',
    border: '1px solid rgba(255, 255, 255, 0.15)',
    hoverBg: 'rgba(255, 255, 255, 0.14)',
    hoverBorder: 'rgba(255, 255, 255, 0.25)',
    activeBg: 'rgba(255, 255, 255, 0.2)',
  },
  ghost: {
    bg: 'transparent',
    color: 'inherit',
    border: '1px solid transparent',
    hoverBg: 'rgba(0, 0, 0, 0.05)',
    hoverBorder: 'transparent',
    activeBg: 'rgba(0, 0, 0, 0.1)',
  },
  outline: {
    bg: 'transparent',
    color: '#2563eb',
    border: '1px solid #2563eb',
    hoverBg: '#eff6ff',
    hoverBorder: '#2563eb',
    activeBg: '#dbeafe',
  },
};

export default function Button({
  children,
  variant = 'primary',
  size = 'sm',
  icon = null,
  iconPosition = 'start',
  loading = false,
  disabled = false,
  active = false,
  type = 'button',
  onClick,
  title,
  className = '',
  style = {},
  id,
  ...props
}) {
  const [isHovered, setIsHovered] = React.useState(false);
  const [isActive, setIsActive] = React.useState(false);

  const sizeCfg = SIZES[size] || SIZES.sm;
  const variantCfg = VARIANTS[variant] || VARIANTS.primary;
  const isDisabled = disabled || loading;

  let bg = variantCfg.bg;
  let color = variantCfg.color;
  let border = variantCfg.border;

  if (active) {
    bg = variantCfg.activeBg || variantCfg.hoverBg;
  } else if (isHovered && !isDisabled) {
    bg = variantCfg.hoverBg;
    border = variantCfg.hoverBorder || border;
  }
  if (isActive && !isDisabled) {
    bg = variantCfg.activeBg || bg;
  }

  const baseStyle = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    height: sizeCfg.height,
    width: sizeCfg.width || 'auto',
    padding: sizeCfg.padding,
    fontSize: sizeCfg.fontSize,
    fontWeight: sizeCfg.fontWeight,
    borderRadius: sizeCfg.borderRadius,
    background: isDisabled ? (variant === 'neutral' ? 'rgba(255, 255, 255, 0.04)' : '#f1f5f9') : bg,
    color: isDisabled ? (variant === 'neutral' ? 'rgba(255, 255, 255, 0.35)' : '#94a3b8') : color,
    border: isDisabled ? '1px solid rgba(0, 0, 0, 0.08)' : border,
    cursor: isDisabled ? 'not-allowed' : 'pointer',
    gap: sizeCfg.gap,
    lineHeight: 1,
    boxSizing: 'border-box',
    whiteSpace: 'nowrap',
    userSelect: 'none',
    transition: 'all 0.15s ease',
    fontFamily: 'var(--font-family)',
    opacity: isDisabled && variant !== 'neutral' && variant !== 'secondary' ? 0.65 : 1,
    outline: 'none',
    ...style,
  };

  const renderIcon = () => {
    if (loading) {
      return (
        <Loader2
          size={sizeCfg.iconSize}
          style={{ animation: 'spin 1s linear infinite', flexShrink: 0 }}
        />
      );
    }
    if (icon) {
      return React.isValidElement(icon)
        ? React.cloneElement(icon, {
            size: icon.props?.size || sizeCfg.iconSize,
            style: { flexShrink: 0, ...(icon.props?.style || {}) },
          })
        : icon;
    }
    return null;
  };

  return (
    <button
      id={id}
      type={type}
      disabled={isDisabled}
      onClick={onClick}
      title={title}
      className={`cf-btn ${className}`}
      style={baseStyle}
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => {
        setIsHovered(false);
        setIsActive(false);
      }}
      onMouseDown={() => setIsActive(true)}
      onMouseUp={() => setIsActive(false)}
      {...props}
    >
      {iconPosition === 'start' && renderIcon()}
      {children}
      {iconPosition === 'end' && renderIcon()}
    </button>
  );
}
