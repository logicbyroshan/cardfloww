import React, { useEffect } from 'react';
import { X } from 'lucide-react';

const MODAL_WIDTHS = {
  sm: '440px',
  md: '540px',
  lg: '640px',
  xl: '800px',
};

export default function Modal({
  isOpen,
  onClose,
  title,
  icon = null,
  size = 'md',
  children,
  footer = null,
  headerBg = '#1e293b',
  headerColor = '#ffffff',
  className = '',
  style = {},
  bodyStyle = {},
  closeOnEsc = true,
  closeOnOverlayClick = true,
}) {
  useEffect(() => {
    if (!isOpen || !closeOnEsc) return;
    const handleKeyDown = (e) => {
      if (e.key === 'Escape') onClose?.();
    };
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isOpen, closeOnEsc, onClose]);

  if (!isOpen) return null;

  const width = MODAL_WIDTHS[size] || MODAL_WIDTHS.md;

  return (
    <div
      className="center-modal-overlay"
      onClick={closeOnOverlayClick ? (e) => {
        if (e.target === e.currentTarget) onClose?.();
      } : undefined}
    >
      <div
        className={`center-modal-panel modal-${size} ${className}`}
        style={{
          width,
          maxWidth: '92vw',
          height: 'auto',
          maxHeight: '90vh',
          borderRadius: '8px',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          background: '#ffffff',
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.35)',
          ...style,
        }}
      >
        {/* Standardized Modal Header */}
        {title && (
          <div
            style={{
              height: '48px',
              minHeight: '48px',
              background: headerBg,
              color: headerColor,
              padding: '0 18px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
              boxSizing: 'border-box',
              flexShrink: 0,
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
              {icon && (
                <div style={{ display: 'flex', alignItems: 'center', flexShrink: 0 }}>
                  {React.isValidElement(icon)
                    ? React.cloneElement(icon, { size: icon.props?.size || 16 })
                    : icon}
                </div>
              )}
              <h3
                style={{
                  margin: 0,
                  fontSize: '13.5px',
                  fontWeight: 700,
                  color: headerColor,
                  letterSpacing: '0.02em',
                  fontFamily: 'var(--font-family)',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                  whiteSpace: 'nowrap',
                }}
              >
                {title}
              </h3>
            </div>
            <button
              type="button"
              onClick={onClose}
              title="Close (Esc)"
              style={{
                background: 'transparent',
                border: 'none',
                color: headerColor === '#ffffff' ? '#94a3b8' : '#64748b',
                cursor: 'pointer',
                padding: '4px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                borderRadius: '4px',
                transition: 'color 0.15s ease',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.color = '#ffffff')}
              onMouseLeave={(e) =>
                (e.currentTarget.style.color = headerColor === '#ffffff' ? '#94a3b8' : '#64748b')
              }
            >
              <X size={16} />
            </button>
          </div>
        )}

        {/* Scrollable Body */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '20px',
            boxSizing: 'border-box',
            ...bodyStyle,
          }}
        >
          {children}
        </div>

        {/* Optional Standardized Footer */}
        {footer && (
          <div
            style={{
              padding: '12px 18px',
              background: '#f8fafc',
              borderTop: '1px solid #e2e8f0',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'flex-end',
              gap: '8px',
              boxSizing: 'border-box',
              flexShrink: 0,
            }}
          >
            {footer}
          </div>
        )}
      </div>
    </div>
  );
}
