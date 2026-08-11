import React, { useState } from 'react';
import { X, Download, FileSpreadsheet, FileText, Archive, Printer, Image as ImageIcon } from 'lucide-react';
import CustomSelect from '../common/CustomSelect';

export default function CardDownloadsModal({ isOpen, onClose }) {
  const [format, setFormat] = useState('excel');
  const [photoColumn, setPhotoColumn] = useState('PHOTO');

  if (!isOpen) return null;

  return (
    <div className="center-modal-overlay">
      <div
        className="center-modal-panel"
        style={{
          width: '560px',
          height: 'auto',
          maxHeight: '90vh',
          padding: '0',
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        <div
          style={{
            background: '#1e293b',
            color: '#fff',
            height: '46px',
            minHeight: '46px',
            padding: '0 16px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <span style={{ fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Download size={16} style={{ color: '#10b981' }} /> Download / Export Cards
          </span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <div
          style={{
            flex: 1,
            padding: '24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '1.25rem',
            overflowY: 'auto',
          }}
        >
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#475569',
                marginBottom: '0.5rem',
              }}
            >
              Export Format
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.75rem' }}>
              {[
                { id: 'excel', label: 'Excel Data (.xlsx)', icon: FileSpreadsheet },
                { id: 'pdf', label: 'PDF Cards Sheet', icon: FileText },
                { id: 'zip', label: 'ZIP Photos Only', icon: ImageIcon },
                { id: 'pdf_zip', label: 'ZIP (PDF per photo)', icon: FileText },
              ].map((opt) => {
                const Icon = opt.icon;
                const active = format === opt.id;
                return (
                  <button
                    key={opt.id}
                    onClick={() => setFormat(opt.id)}
                    style={{
                      padding: '1rem 0.85rem',
                      borderRadius: '6px',
                      background: active ? '#eff6ff' : '#f8fafc',
                      border: active ? '2px solid #2563eb' : '1px solid #cbd5e1',
                      color: active ? '#1d4ed8' : '#334155',
                      display: 'flex',
                      alignItems: 'center',
                      gap: '0.65rem',
                      fontSize: '0.85rem',
                      fontWeight: 600,
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <Icon size={20} color={active ? '#2563eb' : '#64748b'} />
                    <span>{opt.label}</span>
                  </button>
                );
              })}
            </div>
          </div>

          <div>
            <label
              style={{
                display: 'block',
                fontSize: '0.85rem',
                fontWeight: 600,
                color: '#475569',
                marginBottom: '0.5rem',
              }}
            >
              Select Photo Field Column
            </label>
            <CustomSelect
              value={photoColumn}
              onChange={(val) => setPhotoColumn(val)}
              options={[
                { value: 'PHOTO', label: 'PHOTO (Main Photo)' },
                { value: 'FATHER_PHOTO', label: 'FATHER_PHOTO' },
              ]}
            />
          </div>
        </div>

        <div
          style={{
            padding: '14px 24px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '8px 16px',
              background: '#fff',
              border: '1px solid #cbd5e1',
              borderRadius: '4px',
              color: '#475569',
              fontWeight: 600,
              cursor: 'pointer',
              fontSize: '12px',
            }}
          >
            Cancel
          </button>
          <button
            onClick={() => {
              alert(`Generating ${format} export...`);
              onClose();
            }}
            style={{
              padding: '8px 20px',
              background: '#059669',
              border: 'none',
              borderRadius: '4px',
              color: '#fff',
              fontWeight: 700,
              cursor: 'pointer',
              fontSize: '12px',
              display: 'flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Download size={15} />
            <span>Generate & Download</span>
          </button>
        </div>
      </div>
    </div>
  );
}
