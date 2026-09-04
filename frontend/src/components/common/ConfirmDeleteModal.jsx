import React, { useState } from 'react';
import { AlertTriangle } from 'lucide-react';
import Modal from './Modal';
import Button from './Button';
import Input from './Input';

export default function ConfirmDeleteModal({
  isOpen,
  onClose,
  onConfirm,
  title = 'Confirm Permanent Delete',
  itemDescription = 'this item',
  requiresCode = false,
  deleteCode = '',
}) {
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
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      title={title}
      icon={<AlertTriangle size={16} style={{ color: '#ef4444' }} />}
      size="sm"
      footer={
        <>
          <Button variant="secondary" size="md" onClick={onClose}>
            Cancel
          </Button>
          <Button variant="danger" size="md" onClick={handleConfirm}>
            Confirm Delete
          </Button>
        </>
      }
    >
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          textAlign: 'center',
          gap: '14px',
        }}
      >
        <div
          style={{
            width: '56px',
            height: '56px',
            borderRadius: '50%',
            background: '#fef2f2',
            color: '#dc2626',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
          }}
        >
          <AlertTriangle size={28} />
        </div>

        <div>
          <h4 style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px' }}>{title}</h4>
          <p style={{ fontSize: '12px', color: '#64748b', lineHeight: 1.5, margin: 0 }}>
            Are you sure you want to permanently delete{' '}
            <strong style={{ color: '#0f172a' }}>{itemDescription}</strong>? This action cannot be undone.
          </p>
        </div>

        {requiresCode && (
          <div style={{ width: '100%', textAlign: 'left', marginTop: '4px' }}>
            <label
              style={{
                display: 'block',
                fontSize: '11.5px',
                fontWeight: 600,
                color: '#475569',
                marginBottom: '6px',
              }}
            >
              Enter Verification Code: <span style={{ color: '#d97706', fontWeight: 700 }}>{deleteCode}</span>
            </label>
            <Input
              size="md"
              value={inputCode}
              onChange={(e) => {
                setInputCode(e.target.value);
                setError('');
              }}
              placeholder="Type deletion code"
              error={error}
              style={{ width: '100%' }}
            />
          </div>
        )}
      </div>
    </Modal>
  );
}
