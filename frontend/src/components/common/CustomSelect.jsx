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
  height = '28px',
}) {
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
          height: style.height || height,
          padding: '0 10px',
          border: open ? '1px solid #2563eb' : '1px solid #cbd5e1',
          borderRadius: '6px',
          background: disabled ? '#f1f5f9' : '#ffffff',
          fontSize: '12px',
          fontWeight: 500,
          color: selectedOpt ? '#0f172a' : '#64748b',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          gap: '8px',
          cursor: disabled ? 'not-allowed' : 'pointer',
          outline: 'none',
          boxShadow: open
            ? '0 0 0 3px rgba(37, 99, 235, 0.12), 0 1px 2px rgba(0,0,0,0.05)'
            : '0 1px 2px rgba(0,0,0,0.04)',
          transition: 'all 0.15s ease',
          boxSizing: 'border-box',
        }}
      >
        <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
          {selectedOpt ? selectedOpt.label : placeholder}
        </span>
        <ChevronDown
          size={14}
          style={{
            color: '#64748b',
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
            top: 'calc(100% + 5px)',
            left: 0,
            right: 0,
            zIndex: 99999,
            background: '#ffffff',
            border: '1px solid #e2e8f0',
            borderRadius: '8px',
            boxShadow: '0 10px 25px -5px rgba(0,0,0,0.15), 0 8px 10px -6px rgba(0,0,0,0.1)',
            maxHeight: '230px',
            overflowY: 'auto',
            padding: '5px',
            display: 'flex',
            flexDirection: 'column',
            gap: '3px',
            boxSizing: 'border-box',
          }}
        >
          {normalizedOptions.length === 0 ? (
            <div style={{ padding: '8px 12px', fontSize: '12px', color: '#94a3b8', textAlign: 'center' }}>
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
                    padding: '7px 10px',
                    borderRadius: '6px',
                    fontSize: '12px',
                    fontWeight: isSelected ? 600 : 400,
                    color: isSelected ? '#1d4ed8' : '#334155',
                    background: isSelected ? '#eff6ff' : 'transparent',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                    gap: '8px',
                    border: 'none',
                    textAlign: 'left',
                    cursor: 'pointer',
                    transition: 'all 0.12s ease',
                    boxSizing: 'border-box',
                  }}
                  onMouseEnter={(e) => {
                    if (!isSelected) e.currentTarget.style.background = '#f8fafc';
                  }}
                  onMouseLeave={(e) => {
                    if (!isSelected) e.currentTarget.style.background = 'transparent';
                  }}
                >
                  <span style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {opt.label}
                  </span>
                  {isSelected && <Check size={13} style={{ color: '#2563eb', flexShrink: 0 }} />}
                </button>
              );
            })
          )}
        </div>
      )}
    </div>
  );
}

