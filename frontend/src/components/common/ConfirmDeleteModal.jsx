import React, { useState } from 'react';
import { AlertTriangle, Trash2, X, ShieldAlert } from 'lucide-react';

export default function ConfirmDeleteModal({ isOpen, onClose, onConfirm, title = "Confirm Permanent Delete", itemDescription = "this item", requiresCode = false, deleteCode = "" }) {
  const [inputCode, setInputCode] = useState('');
  const [error, setError] = useState('');

  if (!isOpen) return null;

  const handleConfirm = () => {
    if (requiresCode && inputCode !== deleteCode) {
      setError('Invalid deletion code entered. Please check and try again.');
      return;
    }
    setError('');
    onConfirm();
    onClose();
  };

  return (
    <div className="center-modal-overlay">
      <div
        className="center-modal-panel"
        style={{ width: '540px', height: 'auto', maxHeight: '90vh', padding: '0', display: 'flex', flexDirection: 'column' }}
      >
        <div style={{ background: '#1e293b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <span style={{ fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <AlertTriangle size={16} style={{ color: '#ef4444' }} /> {title}
          </span>
          <button onClick={onClose} style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        <div style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', gap: '1.25rem', overflowY: 'auto' }}>
          <div style={{ width: '64px', height: '64px', borderRadius: '50%', background: '#fef2f2', color: '#dc2626', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <AlertTriangle size={32} />
          </div>

          <div>
            <h3 style={{ fontSize: '1.3rem', fontWeight: 700, color: '#0f172a', marginBottom: '0.5rem' }}>{title}</h3>
            <p style={{ fontSize: '0.9rem', color: '#64748b', lineHeight: 1.5, maxWidth: '440px' }}>
              Are you sure you want to permanently delete <strong style={{ color: '#0f172a' }}>{itemDescription}</strong>? This action cannot be undone.
            </p>
          </div>

          {requiresCode && (
            <div style={{ width: '100%', maxWidth: '440px', textAlign: 'left' }}>
              <label style={{ display: 'block', fontSize: '0.85rem', fontWeight: 600, color: '#475569', marginBottom: '0.5rem' }}>
                Enter Verification Code: <span style={{ color: '#d97706', fontWeight: 700 }}>{deleteCode}</span>
              </label>
              <input
                type="text"
                value={inputCode}
                onChange={(e) => { setInputCode(e.target.value); setError(''); }}
                placeholder="Type deletion code"
                style={{ width: '100%', padding: '0.65rem 1rem', background: '#f8fafc', border: '1px solid #cbd5e1', borderRadius: '6px', color: '#0f172a', outline: 'none' }}
              />
              {error && <span style={{ fontSize: '0.8rem', color: '#dc2626', marginTop: '0.35rem', display: 'block' }}>{error}</span>}
            </div>
          )}
        </div>

        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'flex-end', gap: '10px' }}>
          <button
            onClick={onClose}
            style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }}
          >
            Cancel
          </button>
          <button
            onClick={handleConfirm}
            style={{ padding: '8px 18px', background: '#dc2626', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px' }}
          >
            Confirm Delete
          </button>
        </div>
      </div>
    </div>
  );
}
