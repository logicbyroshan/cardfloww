import React, { useState, useEffect, useRef } from 'react';
import { Upload, RotateCcw, RotateCw, Trash2, Image as ImageIcon, Check, FileText } from 'lucide-react';
import { cardApi } from '../../services/api';

const getImgSrc = (path) => {
  if (!path) return '';
  const s = String(path).trim();
  if (s.startsWith('http://') || s.startsWith('https://') || s.startsWith('data:')) {
    return s;
  }
  if (s.startsWith('/')) return s;
  return `/${s}`;
};

export default function ImageUploadSlot({ cardId, fieldName, currentPath, onUpdate }) {
  const [loading, setLoading] = useState(false);
  const [imagePath, setImagePath] = useState(currentPath || '');
  const [imgError, setImgError] = useState(false);
  const fileInputRef = useRef(null);

  useEffect(() => {
    setImagePath(currentPath || '');
    setImgError(false);
  }, [currentPath]);

  const updatePath = (newPath) => {
    setImagePath(newPath);
    setImgError(false);
    if (onUpdate) onUpdate(fieldName, newPath);
  };

  const handleFileSelect = (e) => {
    const file = e.target.files?.[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (event) => {
      const dataUrl = event.target?.result;
      if (dataUrl) {
        updatePath(dataUrl);
      }
    };
    reader.readAsDataURL(file);
    e.target.value = '';
  };

  const handleRemove = () => {
    updatePath('');
  };

  const handleUndo = async () => {
    if (!cardId) return;
    setLoading(true);
    try {
      const res = await cardApi.undoImage(cardId, fieldName);
      if (res?.success && res?.restored_path) {
        updatePath(res.restored_path);
      }
    } catch (err) {
      console.error('Error undoing image:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleRedo = async () => {
    if (!cardId) return;
    setLoading(true);
    try {
      const res = await cardApi.redoImage(cardId, fieldName);
      if (res?.success && res?.restored_path) {
        updatePath(res.restored_path);
      }
    } catch (err) {
      console.error('Error redoing image:', err);
    } finally {
      setLoading(false);
    }
  };

  const isSig = (fieldName || '').toLowerCase().includes('sign');
  const isQr = (fieldName || '').toLowerCase().includes('qr');
  const isBar = (fieldName || '').toLowerCase().includes('bar');

  // Uniform thumbnail preview dimensions matching photo cards
  const thumbW = isSig ? '95px' : isQr || isBar ? '75px' : '75px';
  const thumbH = isSig ? '70px' : isQr || isBar ? '75px' : '85px';

  const hasPath = Boolean(imagePath && imagePath.trim() !== '');
  const isDataUrl = hasPath && imagePath.startsWith('data:');
  const isLoaded = hasPath && (!imgError || isDataUrl);
  const isPathOnly = hasPath && imgError && !isDataUrl;

  const imgSrc = getImgSrc(imagePath);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        justifyContent: 'space-between',
        height: '100%',
        border: '1px solid #cbd5e1',
        borderRadius: '8px',
        background: '#ffffff',
        width: '100%',
        boxSizing: 'border-box',
        boxShadow: '0 2px 6px rgba(0, 0, 0, 0.05)',
        overflow: 'hidden',
      }}
    >
      {/* Sleek Dark Banner Header */}
      <div
        style={{
          background: '#1e293b',
          color: '#ffffff',
          padding: '7px 12px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          borderBottom: '1px solid #334155',
        }}
      >
        <span
          style={{
            fontSize: '11px',
            fontWeight: 700,
            textTransform: 'uppercase',
            letterSpacing: '0.04em',
            color: '#ffffff',
          }}
        >
          {fieldName}
        </span>

        {/* Status Badge */}
        {isLoaded ? (
          <span
            style={{
              fontSize: '10px',
              fontWeight: 700,
              color: '#4ade80',
              background: 'rgba(74, 222, 128, 0.15)',
              border: '1px solid rgba(74, 222, 128, 0.3)',
              padding: '1px 7px',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
            }}
          >
            <Check size={10} /> Loaded
          </span>
        ) : isPathOnly ? (
          <span
            style={{
              fontSize: '10px',
              fontWeight: 700,
              color: '#fbbf24',
              background: 'rgba(251, 191, 36, 0.15)',
              border: '1px solid rgba(251, 191, 36, 0.3)',
              padding: '1px 7px',
              borderRadius: '10px',
              display: 'flex',
              alignItems: 'center',
              gap: '3px',
            }}
          >
            <FileText size={10} /> Path Set
          </span>
        ) : (
          <span
            style={{
              fontSize: '10px',
              fontWeight: 600,
              color: '#94a3b8',
              background: 'rgba(255, 255, 255, 0.1)',
              padding: '1px 7px',
              borderRadius: '10px',
            }}
          >
            Empty
          </span>
        )}
      </div>

      {/* Main Body: Thumbnail + Grouped Action Buttons */}
      <div
        style={{
          padding: '10px 12px',
          display: 'flex',
          alignItems: 'center',
          gap: '12px',
          background: '#f8fafc',
          flex: 1,
        }}
      >
        {/* Thumbnail Preview Box */}
        <div
          style={{
            width: thumbW,
            height: thumbH,
            minWidth: thumbW,
            background: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            overflow: 'hidden',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            flexShrink: 0,
            boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.04)',
            position: 'relative',
            margin: '0 auto',
          }}
        >
          {hasPath && !imgError ? (
            <img
              src={imgSrc}
              alt={fieldName}
              style={{ width: '100%', height: '100%', objectFit: isSig || isQr || isBar ? 'contain' : 'cover' }}
              onError={() => setImgError(true)}
            />
          ) : isPathOnly ? (
            <div style={{ textAlign: 'center', padding: '4px', color: '#d97706' }}>
              <FileText size={20} style={{ margin: '0 auto 2px' }} />
              <div style={{ fontSize: '9px', fontWeight: 700, lineHeight: 1 }}>PATH ONLY</div>
            </div>
          ) : (
            <ImageIcon size={22} style={{ color: '#cbd5e1' }} />
          )}
        </div>

        {/* Grouped Action Buttons */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '6px', justifyContent: 'center' }}>
          {/* Primary Action Pair: Upload + Remove */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*,.heic,.heif"
              style={{ display: 'none' }}
              onChange={handleFileSelect}
            />
            <button
              type="button"
              onClick={() => fileInputRef.current?.click()}
              className="img-slot-btn img-slot-upload-btn"
              title="Upload photo from device"
            >
              <Upload size={12} />
              <span>Upload</span>
            </button>

            {hasPath && (
              <button
                type="button"
                onClick={handleRemove}
                className="img-slot-btn img-slot-remove-btn"
                title="Remove photo"
              >
                <Trash2 size={12} />
                <span>Remove</span>
              </button>
            )}
          </div>

          {/* History Action Pair: Undo + Redo together */}
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <button
              type="button"
              onClick={handleUndo}
              disabled={loading || !cardId}
              className="img-slot-btn"
              title="Undo image version"
            >
              <RotateCcw size={11} />
              <span>Undo</span>
            </button>

            <button
              type="button"
              onClick={handleRedo}
              disabled={loading || !cardId}
              className="img-slot-btn"
              title="Redo image version"
            >
              <RotateCw size={11} />
              <span>Redo</span>
            </button>
          </div>
        </div>
      </div>

      {/* Path Input Footer */}
      <div style={{ padding: '6px 12px 10px 12px', background: '#f8fafc', borderTop: '1px solid #e2e8f0' }}>
        <input
          type="text"
          className="img-slot-path-input"
          value={imagePath}
          placeholder="Enter image filename or path (e.g., photo.jpg)..."
          onChange={(e) => updatePath(e.target.value)}
          spellCheck={false}
          autoComplete="off"
        />
      </div>
    </div>
  );
}
