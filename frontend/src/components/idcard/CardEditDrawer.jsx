import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Save, Loader2, AlertCircle } from 'lucide-react';
import ImageUploadSlot from './ImageUploadSlot';
import { cardApi } from '../../services/api';
import { isDropdownField, getOptionsForField } from '../../utils/formatPresets';


export default function CardEditDrawer({ card, onClose, onSave, addToast }) {
  const [formData, setFormData] = useState(
    card?.field_data || {
      NAME: card?.name || 'Student Name',
      FATHER_NAME: 'Father Name',
      CLASS: '10th',
      SECTION: 'A',
      ROLL_NO: '101',
      MOBILE: '9876543210',
      PHOTO: card?.photo || '',
    }
  );

  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState(null);

  // Track original values to only send changed fields
  const original = card?.field_data || {};

  const handleChange = (field, val) => {
    setFormData((prev) => ({ ...prev, [field]: val }));
    setSaveError(null);
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!card?.id) {
      if (onSave) onSave({ ...card, field_data: formData });
      onClose();
      return;
    }
    setSaving(true);
    setSaveError(null);
    const errors = [];
    // Save each changed field via API
    for (const [fieldName, value] of Object.entries(formData)) {
      if (String(value ?? '') !== String(original[fieldName] ?? '')) {
        try {
          await cardApi.updateField(card.id, fieldName, value);
        } catch (err) {
          errors.push(fieldName);
          console.warn(`Failed to save field ${fieldName}:`, err);
        }
      }
    }
    setSaving(false);
    if (errors.length > 0) {
      setSaveError(`Some fields could not be saved: ${errors.join(', ')}`);
      addToast?.(`Partial save — ${errors.length} field(s) failed`, 'warning');
    } else {
      addToast?.('Card details saved successfully', 'success');
      if (onSave) onSave({ ...card, field_data: formData });
      onClose();
    }
  };

  return createPortal(
    <>
      <div className="drawer-overlay-backdrop" onClick={onClose} />
      <aside
        className="side-drawer-panel"
        style={{ width: '640px', maxWidth: '95vw', padding: 0, display: 'flex', flexDirection: 'column' }}
      >
        {/* Fixed Header */}
        <div
          style={{
            background: '#1e293b',
            color: '#ffffff',
            padding: '14px 24px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #334155',
            flexShrink: 0,
          }}
        >
          <div>
            <h3 style={{ fontSize: '1.1rem', fontWeight: 700, margin: 0, color: '#ffffff' }}>
              Card Details #{card?.id || 'New'}
            </h3>
            <span style={{ fontSize: '0.8rem', color: '#94a3b8' }}>ID Card Field Editor &amp; Image History</span>
          </div>
          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
            }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Form Container */}
        <form
          onSubmit={handleSubmit}
          style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, margin: 0 }}
        >
          {/* Scrollable Body */}
          <div
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: '24px',
              display: 'flex',
              flexDirection: 'column',
              gap: '1.25rem',
            }}
          >
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1rem' }}>
              <ImageUploadSlot
                cardId={card?.id}
                fieldName="PHOTO"
                currentPath={formData.PHOTO}
                onUpdate={(field, path) => handleChange(field, path)}
              />
              <ImageUploadSlot
                cardId={card?.id}
                fieldName="SIGNATURE"
                currentPath={formData.SIGNATURE}
                onUpdate={(field, path) => handleChange(field, path)}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>

              {Object.entries(formData).map(([key, val]) => {
                if (['PHOTO', 'SIGNATURE', 'BARCODE', 'QR_CODE'].includes(key)) return null;
                const fieldObj = { name: key };
                const isDropdown = isDropdownField(fieldObj);
                const options = isDropdown ? getOptionsForField(fieldObj) : [];
                const isDuplicate = card?.duplicate_fields?.includes(key);

                return (
                  <div key={key}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '0.35rem' }}>
                      <label
                        style={{
                          display: 'block',
                          fontSize: '0.8rem',
                          fontWeight: 600,
                          color: '#475569',
                          textTransform: 'uppercase',
                        }}
                      >
                        {key.replace(/_/g, ' ')}
                      </label>
                      {isDuplicate && (
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            color: '#b45309',
                            background: '#fef3c7',
                            padding: '1px 6px',
                            borderRadius: '3px',
                            border: '1px solid #fde68a',
                          }}
                        >
                          REPEATING VALUE
                        </span>
                      )}
                    </div>

                    {isDropdown ? (
                      <select
                        value={val || ''}
                        onChange={(e) => handleChange(key, e.target.value)}
                        style={{
                          width: '100%',
                          padding: '0.65rem 1rem',
                          background: '#ffffff',
                          border: isDuplicate ? '1px solid #f59e0b' : '1px solid #cbd5e1',
                          borderRadius: '4px',
                          color: '#0f172a',
                          fontSize: '0.9rem',
                          outline: 'none',
                          boxSizing: 'border-box',
                          cursor: 'pointer',
                        }}
                      >
                        <option value="">-- Select {key.replace(/_/g, ' ')} --</option>
                        {val && !options.includes(val) && (
                          <option value={val}>{val} (Current)</option>
                        )}
                        {options.map((opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ))}
                      </select>
                    ) : (
                      <input
                        type="text"
                        value={val || ''}
                        onChange={(e) => handleChange(key, e.target.value)}
                        style={{
                          width: '100%',
                          padding: '0.65rem 1rem',
                          background: '#ffffff',
                          border: isDuplicate ? '1px solid #f59e0b' : '1px solid #cbd5e1',
                          borderRadius: '4px',
                          color: '#0f172a',
                          fontSize: '0.9rem',
                          outline: 'none',
                          boxSizing: 'border-box',
                        }}
                      />
                    )}

                    {isDuplicate && (
                      <div
                        style={{
                          marginTop: '4px',
                          fontSize: '11px',
                          color: '#b45309',
                          display: 'flex',
                          alignItems: 'center',
                          gap: '4px',
                        }}
                      >
                        <AlertCircle size={12} />
                        <span>This value is shared with another card in this table.</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>


            {saveError && (
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  padding: '10px 14px',
                  background: '#fef2f2',
                  border: '1px solid #fecaca',
                  borderRadius: '6px',
                  color: '#dc2626',
                  fontSize: '12px',
                }}
              >
                <AlertCircle size={14} />
                <span>{saveError}</span>
              </div>
            )}
          </div>

          {/* Sticky Bottom Footer */}
          <div
            style={{
              padding: '14px 24px',
              background: '#f8fafc',
              borderTop: '1px solid #e2e8f0',
              display: 'flex',
              gap: '12px',
              justifyContent: 'flex-end',
              flexShrink: 0,
            }}
          >
            <button
              type="button"
              onClick={onClose}
              disabled={saving}
              style={{
                padding: '8px 18px',
                borderRadius: '4px',
                background: '#ffffff',
                border: '1px solid #cbd5e1',
                color: '#475569',
                fontWeight: 600,
                fontSize: '12px',
                cursor: saving ? 'not-allowed' : 'pointer',
                opacity: saving ? 0.5 : 1,
              }}
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={saving}
              style={{
                padding: '8px 24px',
                borderRadius: '4px',
                background: '#2563eb',
                border: 'none',
                color: '#ffffff',
                fontWeight: 700,
                fontSize: '12px',
                cursor: saving ? 'not-allowed' : 'pointer',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                gap: '0.5rem',
                opacity: saving ? 0.8 : 1,
              }}
            >
              {saving ? <Loader2 size={15} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={15} />}
              <span>{saving ? 'Saving...' : 'Save Card Details'}</span>
            </button>
          </div>
        </form>
      </aside>
    </>,
    document.body
  );
}
