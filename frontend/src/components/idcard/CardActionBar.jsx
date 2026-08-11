import React from 'react';
import { Download, Upload, Trash2, CheckCircle2, RefreshCw, Eraser, Plus } from 'lucide-react';

export default function CardActionBar({ selectedCount = 0, onAddCard, onUploadPhotos, onExportModal, onClearPending }) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        marginBottom: '1.25rem',
        flexWrap: 'wrap',
        gap: '1rem',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <button
          onClick={onAddCard}
          style={{
            padding: '0.6rem 1.1rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--accent-primary)',
            border: 'none',
            color: '#fff',
            fontWeight: 600,
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            cursor: 'pointer',
          }}
        >
          <Plus size={16} />
          <span>Add New Card</span>
        </button>

        <button
          onClick={onUploadPhotos}
          style={{
            padding: '0.6rem 1.1rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-primary)',
            fontWeight: 600,
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            cursor: 'pointer',
          }}
        >
          <Upload size={16} />
          <span>Upload ZIP Photos</span>
        </button>
      </div>

      <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        {selectedCount > 0 && (
          <span style={{ fontSize: '0.85rem', color: 'var(--accent-amber)', fontWeight: 600 }}>
            {selectedCount} card(s) selected
          </span>
        )}

        <button
          onClick={onClearPending}
          style={{
            padding: '0.6rem 1rem',
            borderRadius: 'var(--radius-md)',
            background: 'var(--bg-elevated)',
            border: '1px solid var(--border-color)',
            color: 'var(--text-secondary)',
            fontWeight: 500,
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            cursor: 'pointer',
          }}
          title="Clear missing photo paths"
        >
          <Eraser size={15} />
          <span>Scan Paths</span>
        </button>

        <button
          onClick={onExportModal}
          style={{
            padding: '0.6rem 1.1rem',
            borderRadius: 'var(--radius-md)',
            background: 'rgba(16, 185, 129, 0.15)',
            border: '1px solid rgba(16, 185, 129, 0.3)',
            color: '#34d399',
            fontWeight: 600,
            fontSize: '0.85rem',
            display: 'flex',
            alignItems: 'center',
            gap: '0.4rem',
            cursor: 'pointer',
          }}
        >
          <Download size={16} />
          <span>Export / Download</span>
        </button>
      </div>
    </div>
  );
}
