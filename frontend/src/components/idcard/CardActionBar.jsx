import React from 'react';
import { Download, Upload, Trash2, CheckCircle2, RefreshCw, Eraser, Plus, Undo2, Redo2, History } from 'lucide-react';

export default function CardActionBar({
  selectedCount = 0,
  onAddCard,
  onUploadPhotos,
  onExportModal,
  onClearPending,
  onUndo,
  onRedo,
  canUndo = false,
  canRedo = false,
  undoTooltip = 'Undo (Ctrl+Z)',
  redoTooltip = 'Redo (Ctrl+Y)',
  onHistory,
}) {
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
        {onUndo && (
          <button
            disabled={!canUndo}
            onClick={onUndo}
            style={{
              padding: '0.6rem 0.9rem',
              borderRadius: 'var(--radius-md)',
              background: canUndo ? 'var(--bg-elevated)' : 'transparent',
              border: '1px solid var(--border-color)',
              color: canUndo ? 'var(--text-primary)' : 'var(--text-muted, #94a3b8)',
              fontWeight: 600,
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              cursor: canUndo ? 'pointer' : 'not-allowed',
              opacity: canUndo ? 1 : 0.5,
            }}
            title={undoTooltip}
          >
            <Undo2 size={16} />
            <span>Undo</span>
          </button>
        )}

        {onRedo && (
          <button
            disabled={!canRedo}
            onClick={onRedo}
            style={{
              padding: '0.6rem 0.9rem',
              borderRadius: 'var(--radius-md)',
              background: canRedo ? 'var(--bg-elevated)' : 'transparent',
              border: '1px solid var(--border-color)',
              color: canRedo ? 'var(--text-primary)' : 'var(--text-muted, #94a3b8)',
              fontWeight: 600,
              fontSize: '0.85rem',
              display: 'flex',
              alignItems: 'center',
              gap: '0.4rem',
              cursor: canRedo ? 'pointer' : 'not-allowed',
              opacity: canRedo ? 1 : 0.5,
            }}
            title={redoTooltip}
          >
            <Redo2 size={16} />
            <span>Redo</span>
          </button>
        )}

        {onHistory && (
          <button
            onClick={onHistory}
            style={{
              padding: '0.6rem 0.9rem',
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
            title="View Reversible History & Audit Trail"
          >
            <History size={16} />
            <span>History</span>
          </button>
        )}

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
