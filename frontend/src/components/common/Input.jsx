import React from 'react';
import { X } from 'lucide-react';

export default function Input({
  value,
  onChange,
  onClear,
  placeholder = '',
  type = 'text',
  size = 'sm',
  variant = 'light',
  icon = null,
  clearable = false,
  disabled = false,
  error = '',
  className = '',
  style = {},
  inputStyle = {},
  id,
  name,
  autoComplete,
  ...props
}) {
  const [isFocused, setIsFocused] = React.useState(false);

  const isDark = variant === 'dark';
  const isSmall = size === 'sm';

  const height = isSmall ? '28px' : '36px';
  const fontSize = isSmall ? '11.5px' : '13px';
  const borderRadius = isSmall ? '4px' : '6px';
  const paddingLeft = icon ? (isSmall ? '26px' : '34px') : (isSmall ? '8px' : '12px');
  const paddingRight = clearable && value ? (isSmall ? '24px' : '30px') : (isSmall ? '8px' : '12px');

  const bg = isDark
    ? isFocused ? 'rgba(255, 255, 255, 0.12)' : 'rgba(255, 255, 255, 0.08)'
    : isFocused ? '#ffffff' : '#ffffff';

  const border = error
    ? '1px solid #ef4444'
    : isFocused
    ? '1px solid #2563eb'
    : isDark
    ? '1px solid rgba(255, 255, 255, 0.18)'
    : '1px solid #cbd5e1';

  const boxShadow = error
    ? '0 0 0 2px rgba(239, 68, 68, 0.2)'
    : isFocused
    ? '0 0 0 2px rgba(37, 99, 235, 0.2)'
    : 'none';

  const textColor = isDark ? '#ffffff' : '#0f172a';
  const placeholderColor = isDark ? '#94a3b8' : '#94a3b8';

  const handleClear = (e) => {
    e.stopPropagation();
    if (onClear) {
      onClear();
    } else if (onChange) {
      onChange({ target: { value: '' } });
    }
  };

  return (
    <div
      className={`cf-input-wrapper ${className}`}
      style={{
        position: 'relative',
        display: 'inline-flex',
        alignItems: 'center',
        width: style.width || '100%',
        height,
        borderRadius,
        border,
        boxShadow,
        background: disabled ? (isDark ? 'rgba(255, 255, 255, 0.04)' : '#f1f5f9') : bg,
        boxSizing: 'border-box',
        transition: 'all 0.15s ease',
        ...style,
      }}
    >
      {icon && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            color: isDark ? '#94a3b8' : '#64748b',
            pointerEvents: 'none',
            flexShrink: 0,
            paddingLeft: isSmall ? '8px' : '10px',
            paddingRight: '6px',
          }}
        >
          {React.isValidElement(icon)
            ? React.cloneElement(icon, { size: icon.props?.size || (isSmall ? 12 : 14) })
            : icon}
        </div>
      )}

      <input
        id={id}
        name={name}
        type={type}
        disabled={disabled}
        value={value ?? ''}
        onChange={onChange}
        placeholder={placeholder}
        autoComplete={autoComplete}
        onFocus={() => setIsFocused(true)}
        onBlur={() => setIsFocused(false)}
        style={{
          flex: 1,
          minWidth: 0,
          height: '100%',
          paddingTop: 0,
          paddingBottom: 0,
          paddingLeft: icon ? 0 : (isSmall ? '8px' : '10px'),
          paddingRight: (clearable && value) ? '4px' : (isSmall ? '8px' : '10px'),
          fontSize,
          fontWeight: 500,
          border: 'none',
          outline: 'none',
          boxShadow: 'none',
          background: 'transparent',
          color: disabled ? '#94a3b8' : textColor,
          boxSizing: 'border-box',
          fontFamily: 'var(--font-family)',
          ...inputStyle,
        }}
        {...props}
      />

      {clearable && value && !disabled && (
        <button
          type="button"
          onClick={handleClear}
          title="Clear"
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            background: 'none',
            border: 'none',
            color: isDark ? '#94a3b8' : '#64748b',
            cursor: 'pointer',
            padding: 0,
            paddingRight: isSmall ? '8px' : '10px',
            paddingLeft: '4px',
            flexShrink: 0,
          }}
        >
          <X size={isSmall ? 12 : 14} />
        </button>
      )}

      {error && (
        <div style={{ position: 'absolute', top: '100%', left: 0, fontSize: '10.5px', color: '#ef4444', marginTop: '2px' }}>
          {error}
        </div>
      )}
    </div>
  );
}
