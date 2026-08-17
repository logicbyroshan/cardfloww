import React, { useState } from 'react';
import { createPortal } from 'react-dom';
import { X, Check, Sliders, Sparkles, ListPlus, ShieldCheck } from 'lucide-react';
import { FORMAT_PRESETS, getPresetsForFieldType } from '../../utils/formatPresets';

/**
 * FormatPresetConfigModal
 * Lets users pick from standard format presets (Roman, Ordinal, Numeric, Words, Alphabets, Courses, Branches)
 * or enter a custom list of options for any column.
 */
export default function FormatPresetConfigModal({
  field,
  onClose,
  onSave,
}) {
  const applicablePresets = getPresetsForFieldType(field?.type);
  const initialPreset = field?.format_preset || (applicablePresets[0]?.id || 'custom');
  const [selectedPreset, setSelectedPreset] = useState(initialPreset);

  const initialOptionsStr = Array.isArray(field?.options)
    ? field.options.join(', ')
    : typeof field?.options === 'string'
      ? field.options
      : (FORMAT_PRESETS[initialPreset]?.options || []).join(', ');

  const [customOptionsStr, setCustomOptionsStr] = useState(initialOptionsStr);

  const handlePresetSelect = (presetId) => {
    setSelectedPreset(presetId);
    if (presetId !== 'custom' && FORMAT_PRESETS[presetId]) {
      setCustomOptionsStr(FORMAT_PRESETS[presetId].options.join(', '));
    }
  };

  const currentOptionsList = customOptionsStr
    .split(/[\n,]+/)
    .map((s) => s.trim())
    .filter(Boolean);

  const handleApply = () => {
    onSave({
      format_preset: selectedPreset,
      options: currentOptionsList,
    });
    onClose();
  };

  return createPortal(
    <>
      <div
        className="drawer-overlay-backdrop"
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(15, 23, 42, 0.65)',
          backdropFilter: 'blur(3px)',
          zIndex: 999999999,
        }}
        onClick={onClose}
      />
      <div
        style={{
          position: 'fixed',
          top: '50%',
          left: '50%',
          transform: 'translate(-50%, -50%)',
          width: '540px',
          maxWidth: '92vw',
          maxHeight: '90vh',
          background: '#ffffff',
          borderRadius: '10px',
          boxShadow: '0 20px 45px rgba(0, 0, 0, 0.3)',
          zIndex: 1000000000,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          fontFamily: 'var(--font-family, system-ui, sans-serif)',
          animation: 'fadeIn 0.18s ease',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '14px 20px',
            background: '#1e293b',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #334155',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Sliders size={18} style={{ color: '#38bdf8' }} />
            <div>
              <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#ffffff' }}>
                Column Options &amp; Format: {field?.name || 'Field'}
              </h4>
              <span style={{ fontSize: '11px', color: '#94a3b8' }}>
                Type: {field?.type?.toUpperCase()} — Select preset or configure custom dropdown options
              </span>
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div style={{ padding: '18px 20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '14px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', marginBottom: '8px' }}>
              Choose Format Preset
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px' }}>
              {applicablePresets.map((p) => {
                const isSelected = selectedPreset === p.id;
                return (
                  <button
                    key={p.id}
                    type="button"
                    onClick={() => handlePresetSelect(p.id)}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      padding: '8px 12px',
                      borderRadius: '6px',
                      border: isSelected ? '2px solid #2563eb' : '1px solid #cbd5e1',
                      background: isSelected ? '#eff6ff' : '#f8fafc',
                      color: isSelected ? '#1d4ed8' : '#334155',
                      fontWeight: isSelected ? 700 : 500,
                      fontSize: '12px',
                      cursor: 'pointer',
                      textAlign: 'left',
                      transition: 'all 0.12s ease',
                    }}
                  >
                    <span>{p.label}</span>
                    {isSelected && <Check size={14} style={{ color: '#2563eb', flexShrink: 0 }} />}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Editable Options Textbox */}
          <div>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '6px' }}>
              <label style={{ fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase' }}>
                Dropdown Values (Comma-separated)
              </label>
              <span style={{ fontSize: '10px', color: '#64748b', fontWeight: 600 }}>
                {currentOptionsList.length} options defined
              </span>
            </div>
            <textarea
              rows={3}
              value={customOptionsStr}
              onChange={(e) => {
                setCustomOptionsStr(e.target.value);
                setSelectedPreset('custom');
              }}
              placeholder="e.g. 1st, 2nd, 3rd, 4th, 5th... or I, II, III..."
              style={{
                width: '100%',
                padding: '8px 10px',
                borderRadius: '6px',
                border: '1px solid #cbd5e1',
                fontSize: '12px',
                fontFamily: 'inherit',
                outline: 'none',
                boxSizing: 'border-box',
                resize: 'vertical',
                lineHeight: 1.4,
              }}
            />
          </div>

          {/* Live Preview Cloud */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', marginBottom: '6px' }}>
              Live Dropdown Preview ({currentOptionsList.length})
            </label>
            <div
              style={{
                display: 'flex',
                flexWrap: 'wrap',
                gap: '5px',
                padding: '10px',
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '6px',
                maxHeight: '120px',
                overflowY: 'auto',
              }}
            >
              {currentOptionsList.length === 0 ? (
                <span style={{ fontSize: '11px', color: '#94a3b8', fontStyle: 'italic' }}>
                  No options defined yet. Select a preset or type values above.
                </span>
              ) : (
                currentOptionsList.map((opt, i) => (
                  <span
                    key={i}
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      padding: '2px 8px',
                      borderRadius: '4px',
                      background: '#ffffff',
                      border: '1px solid #cbd5e1',
                      color: '#0f172a',
                      fontSize: '11px',
                      fontWeight: 600,
                    }}
                  >
                    {opt}
                  </span>
                ))
              )}
            </div>
          </div>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 20px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: '10px',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '7px 16px',
              borderRadius: '6px',
              border: '1px solid #cbd5e1',
              background: '#ffffff',
              color: '#475569',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            onClick={handleApply}
            style={{
              padding: '7px 18px',
              borderRadius: '6px',
              border: 'none',
              background: '#2563eb',
              color: '#ffffff',
              fontSize: '12px',
              fontWeight: 700,
              cursor: 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            <Check size={14} /> Apply Format
          </button>
        </div>
      </div>
    </>,
    document.body
  );
}
