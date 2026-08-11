import React from 'react';
import { AlertTriangle, X, ShieldAlert, Check } from 'lucide-react';

export default function OldVersionWarningModal({ isOpen, warningData, onClose, onConfirmOverwrite }) {
  if (!isOpen || !warningData) return null;

  const { incoming_version, current_version, root_token } = warningData.data || {};

  return (
    <div className="center-modal-overlay">
      <div
        className="center-modal-panel"
        style={{ width: '480px', height: 'auto', maxHeight: '90vh', padding: '1.75rem', position: 'relative' }}
      >
        <button
          onClick={onClose}
          style={{
            position: 'absolute',
            top: '1.25rem',
            right: '1.25rem',
            background: 'transparent',
            border: 'none',
            color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          <X size={20} />
        </button>

        <div
          style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', textAlign: 'center', gap: '1rem' }}
        >
          <div
            style={{
              width: '56px',
              height: '56px',
              borderRadius: '50%',
              background: 'rgba(245, 158, 11, 0.15)',
              color: 'var(--accent-amber)',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <ShieldAlert size={30} />
          </div>

          <div>
            <h3 style={{ fontSize: '1.25rem', fontWeight: 700, marginBottom: '0.35rem' }}>
              Older Image Version Detected
            </h3>
            <p style={{ fontSize: '0.85rem', color: 'var(--text-secondary)' }}>
              The file you are uploading is version{' '}
              <strong style={{ color: 'var(--accent-amber)' }}>v{incoming_version}</strong>, but the current active
              image on this card is version{' '}
              <strong style={{ color: 'var(--accent-emerald)' }}>v{current_version}</strong>.
            </p>
          </div>

          <div
            style={{
              width: '100%',
              background: 'rgba(15, 23, 42, 0.6)',
              border: '1px solid var(--border-color)',
              borderRadius: 'var(--radius-md)',
              padding: '0.85rem',
              fontSize: '0.8rem',
              textAlign: 'left',
            }}
          >
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
              <span style={{ color: 'var(--text-muted)' }}>Root Token:</span>
              <span style={{ fontFamily: 'monospace', fontWeight: 600, color: 'var(--text-primary)' }}>
                {root_token || 'N/A'}
              </span>
            </div>
            <div style={{ display: 'flex', justifyContent: 'space-between' }}>
              <span style={{ color: 'var(--text-muted)' }}>Action:</span>
              <span style={{ color: 'var(--accent-amber)', fontWeight: 600 }}>Requires Confirmation</span>
            </div>
          </div>

          <div style={{ display: 'flex', gap: '0.75rem', width: '100%', marginTop: '0.5rem' }}>
            <button
              onClick={onClose}
              style={{
                flex: 1,
                padding: '0.75rem',
                borderRadius: 'var(--radius-md)',
                background: 'var(--bg-elevated)',
                border: '1px solid var(--border-color)',
                color: 'var(--text-primary)',
                fontWeight: 600,
                cursor: 'pointer',
              }}
            >
              Cancel Upload
            </button>
            <button
              onClick={onConfirmOverwrite}
              style={{
                flex: 1,
                padding: '0.75rem',
                borderRadius: 'var(--radius-md)',
                background: 'var(--accent-amber)',
                border: 'none',
                color: '#000',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.4rem',
              }}
            >
              <Check size={16} />
              <span>Confirm & Overwrite</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
