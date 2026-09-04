import React, { useState, useRef, useEffect } from 'react';
import { ChevronDown, Check } from 'lucide-react';

export default function CustomSelect({
  value,
  onChange,
  options = [],
  placeholder = 'Select option...',
  disabled = false,
  style = {},
  className = '',
  id,
  size = 'sm',
  height,
  dark = false,
}) {
  const isSmall = size === 'sm';
  const effectiveHeight = style.height || height || (isSmall ? '28px' : '36px');
  const fontSize = isSmall ? '11.5px' : '13px';
  const borderRadius = isSmall ? '4px' : '6px';
  const [open, setOpen] = useState(false);
  const containerRef = useRef(null);

  useEffect(() => {
    const handleClickOutside = (e) => {
      if (containerRef.current && !containerRef.current.contains(e.target)) {
        setOpen(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Normalize options (array of objects {value, label} or strings)
  const normalizedOptions = options.map((opt) => {
    if (typeof opt === 'object' && opt !== null) {
      return { value: opt.value, label: opt.label !== undefined ? opt.label : String(opt.value) };
    }
    return { value: opt, label: String(opt) };
  });

  const selectedOpt = normalizedOptions.find((o) => String(o.value) === String(value));

  return (
    <div
      ref={containerRef}
      id={id}
      className={`custom-select-container ${className}`}
      style={{ position: 'relative', display: 'inline-block', width: '100%', ...style }}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((prev) => !prev)}
        style={{
          width: '100%',
          height: effectiveHeight,
          padding: isSmall ? '0 8px' : '0 12px',
          border: open
            ? '1px solid #3b82f6'
            : dark
            ? '1px solid rgba(255, 255, 255, 0.18)'
            : '1px solid #cbd5e1',
          borderRadius,
          background: disabled
            ? dark
              ? 'rgba(255, 255, 255, 0.04)'
              : '#f1f5f9'
            : dark
            ? 'rgba(255, 255, 255, 0.08)'
            : '#ffffff',
          fontSize,
          fontWeight: 600,
          color: selectedOpt
            ? dark
              ? '#ffffff'
              : '#0f172a'
            : dark
            ? '#94a3b8'
            : '#64748b',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          cursor: disabled ? 'not-allowed' : 'pointer',
          outline: 'none',
          boxShadow: open
            ? dark
              ? '0 0 0 2px rgba(59, 130, 246, 0.3)'
              : '0 0 0 3px rgba(37, 99, 235, 0.12), 0 1px 2px rgba(0,0,0,0.05)'
            : 'none',
          transition: 'all 0.15s ease',
          boxSizing: 'border-box',
          fontFamily: 'var(--font-family, inherit)',
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selectedOpt ? selectedOpt.label : placeholder}
        </span>
        <ChevronDown
          size={13}
          style={{
            color: dark ? '#94a3b8' : '#64748b',
            transform: open ? 'rotate(180deg)' : 'rotate(0deg)',
            transition: 'transform 0.15s ease',
            flexShrink: 0,
          }}
        />
      </button>

      {open && !disabled && (
        <div
          style={{
            position: 'absolute',
            top: 'calc(100% + 4px)',
            left: 0,
            right: 0,
            zIndex: 99999,
            background: dark ? '#181825' : '#ffffff',
            border: dark ? '1px solid rgba(255, 255, 255, 0.18)' : '1px solid #e2e8f0',
            borderRadius: '6px',
            boxShadow: dark
              ? '0 12px 28px rgba(0,0,0,0.7), 0 4px 10px rgba(0,0,0,0.4)'
              : '0 10px 25px -5px rgba(0,0,0,0.15), 0 8px 10px -6px rgba(0,0,0,0.1)',
            maxHeight: '230px',
            overflowY: 'auto',
            padding: '4px',
            display: 'flex',
            flexDirection: 'column',
            gap: '2px',
            boxSizing: 'border-box',
          }}
        >
          {normalizedOptions.length === 0 ? (
            <div style={{ padding: '8px 12px', fontSize: '11px', color: '#94a3b8', textAlign: 'center' }}>
              No options available
            </div>
          ) : (
            normalizedOptions.map((opt) => {
              const isSelected = String(opt.value) === String(value);
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => {
                    onChange(opt.value);
                    setOpen(false);
                  }}
                  style={{
                    width: '100%',
                    padding: '6px 9px',
                    borderRadius: '4px',
                    fontSize: '11px',
                    fontWeight: isSelected ? 700 : 500,
                    color: isSelected
                      ? '#ffffff'
                      : dark
                      ? '#cbd5e1'
                      : '#334155',
                    background: isSelected
                      ? '#2563eb'
                      : 'transparent',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '8px',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'all 0.12s ease',
                    boxSizing: 'border-box',
                    fontFamily: 'var(--font-family, inherit)',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background = dark ? 'rgba(255, 255, 255, 0.08)' : '#f8fafc';
                      if (dark) e.currentTarget.style.color = '#ffffff';
                    }
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) {
                      e.currentTarget.style.background = 'transparent';
                      if (dark) e.currentTarget.style.color = '#cbd5e1';
                    }
                  }}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {opt.label}
                  </span>
                  {isSelected && <Check size={12} style={{ color: '#ffffff', flexShrink: 0 }} />}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

