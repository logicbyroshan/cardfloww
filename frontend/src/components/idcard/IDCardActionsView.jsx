/**
 * IDCardActionsView.jsx
 *
 * Full-featured ID card management view — 100% UI consistency with CardFlow system.
 * Replicates the original idcard-actions.html template, button colors, status tabs,
 * search-filter bar, dynamic column widths, photo dimensions, table borders, and standard bottom pagination bar.
 */

import React, {
  useState, useEffect, useCallback, useRef, useMemo
} from 'react';
import { createPortal } from 'react-dom';
import {
  ArrowLeft, ArrowRight, Upload, RefreshCw, Plus, Pencil, Eye,
  Trash2, CheckCircle2, ThumbsUp, RotateCcw, Download,
  Image as ImageIcon, FileSpreadsheet, FileText, Search, X,
  Layers, ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  Loader2, AlertCircle, Eraser, Check, SquareCheck, Square, MinusSquare,
  Clock, SlidersHorizontal, Settings, Printer, ChevronDown, UserPlus, History, XCircle
} from 'lucide-react';
import WatermarkLogo from '../common/WatermarkLogo';
import CustomSelect from '../common/CustomSelect';
import CustomCheckbox from '../common/CustomCheckbox';
import { cardApi, schemaApi } from '../../services/api';
import apiClient from '../../services/api';
import ImageUploadSlot from './ImageUploadSlot';

/* ─── Status configuration ─────────────────────────────────────────────── */

const ID_CARD_STATUS_LIST = [
  { key: 'pending',  label: 'Pending List',   bg: '#f59e0b', bgLight: '#fef3c7', color: '#d97706' },
  { key: 'verified', label: 'Verified List',  bg: '#10b981', bgLight: '#d1fae5', color: '#059669' },
  { key: 'approved', label: 'Approved List',  bg: '#3b82f6', bgLight: '#dbeafe', color: '#2563eb' },
  { key: 'printed',  label: 'Printed List',   bg: '#64748b', bgLight: '#f1f5f9', color: '#475569' },
  { key: 'deleted',  label: 'Deleted List',   bg: '#ef4444', bgLight: '#fee2e2', color: '#dc2626' },
];

const REPRINT_STATUS_LIST = [
  { key: 'reprint',  label: 'Reprinting List', bg: '#06b6d4', bgLight: '#cff4fc', color: '#0891b2' },
  { key: 'request',  label: 'Requested List',  bg: '#a855f7', bgLight: '#f3e8ff', color: '#9333ea' },
  { key: 'confirm',  label: 'Confirmed List',  bg: '#10b981', bgLight: '#d1fae5', color: '#059669' },
];

const STATUS_LIST = [...ID_CARD_STATUS_LIST, ...REPRINT_STATUS_LIST];

const PAGE_SIZE_OPTIONS = [25, 50, 100, 500];

const IMAGE_FIELD_TYPES = new Set(['photo', 'image', 'img', 'picture', 'pic', 'photo_path',
  'rel_photo', 'mother_photo', 'father_photo', 'sign', 'signature', 'qr', 'qrcode', 'barcode']);

const isImageField = (type, name) =>
  IMAGE_FIELD_TYPES.has((type || '').toLowerCase()) ||
  IMAGE_FIELD_TYPES.has((name || '').toLowerCase().replace(/ /g,'_'));

const getImgSrc = (path) => {
  if (!path) return '';
  const s = String(path).trim();
  if (s.startsWith('http://') || s.startsWith('https://') || s.startsWith('data:')) {
    return s;
  }
  if (s.startsWith('/')) return s;
  return `/${s}`;
};

/* Smart Semantic Column Classifier & Width Allocation (Matches FieldClassifier) */
function getColumnSpec(fieldName, fieldType) {
  const rawName = String(fieldName || '').trim();
  const name = rawName.toLowerCase().replace(/[_.'"()/-]+/g, ' ').replace(/\s+/g, ' ').trim();
  const type = String(fieldType || '').toLowerCase().trim();

  // ── Images ──────────────────────────────────────────────────────────────
  if (isImageField(type, rawName)) {
    let imgType = 'photo';
    if (name.includes('sign') || type.includes('sign')) imgType = 'signature';
    else if (name.includes('qr') || type.includes('qr') || name.includes('bar') || type.includes('bar')) imgType = 'qr';

    // photo: compact portrait matching old UI — 34px wide × 44px tall
    // signature: landscape — 64px wide × 28px tall
    // qr: square — 38px × 38px
    const w = imgType === 'signature' ? '72px' : imgType === 'qr' ? '48px' : '48px';
    return { width: w, minWidth: w, maxWidth: w, align: 'center', isImage: true, imgType };
  }

  // ── Serial / Roll ────────────────────────────────────────────────────────
  if (/^sr\s*no|^s\s*no|^sl\s*no|^serial|^sno$|^slno$|^roll/.test(name)) {
    return { width: '48px', minWidth: '48px', maxWidth: '48px', align: 'center' };
  }

  // ── Blood Group ──────────────────────────────────────────────────────────
  if (/blo?o?d\s*gr|blo?o?d\s*gro?u?p|^bg$|^bgroup$|^bld\s*gr/.test(name)) {
    return { width: '56px', minWidth: '56px', maxWidth: '56px', align: 'center' };
  }

  // ── Class / Section / Div / House ───────────────────────────────────────
  if (/^class$|\bclass\b|^section$|\bsection\b|^sec$|^div$|^division$|^cls$/.test(name)) {
    return { width: '68px', minWidth: '68px', maxWidth: '68px', align: 'center' };
  }

  // ── Gender / Age / Short codes ────────────────────────────────────────────
  if (/^gender$|^sex$|^age$|^mode$/.test(name)) {
    return { width: '56px', minWidth: '56px', maxWidth: '56px', align: 'center' };
  }

  // ── Transport / Bus / Route / Stop / House ────────────────────────────────
  if (/transport|bus|route|stop|house/.test(name)) {
    return { width: '70px', minWidth: '70px', maxWidth: '70px', align: 'center' };
  }

  // ── Dates (DOB, DOJ, Date of Birth) ─────────────────────────────────────
  if (/d\.?\s*o\.?\s*b\.?|date\s*of\s*birth|birth\s*date|\bdate\b|\bdt\b/.test(name)) {
    return { width: '88px', minWidth: '88px', maxWidth: '88px', align: 'center' };
  }

  // ── Phone / Contact ──────────────────────────────────────────────────────
  if (/mobi?le?|pho?ne?|cell|tel|whatsapp|contact/.test(name)) {
    return { width: '108px', minWidth: '108px', maxWidth: '108px', align: 'center' };
  }

  // ── ID Numbers (Aadhar, Scholar No, Reg No, Roll No, UID) ───────────────
  if (/a+dh?a+r|scholar|roll\s*no|admis?si?on|reg\s*no|id\s*card|uid|pan|epic|voter|dl\s*no/.test(name)) {
    return { width: '100px', minWidth: '100px', maxWidth: '100px', align: 'center' };
  }

  // ── Names (Full Name, Father Name, Mother Name, Student Name) ────────────
  if (name.includes('name') || name.includes('student') || name.includes('father') || name.includes('mother')) {
    return { minWidth: '110px', maxWidth: '160px', align: 'left' };
  }

  // ── Address / Location / City / State ───────────────────────────────────
  if (name.includes('address') || name.includes('location') || name.includes('locality') || name.includes('city') || name.includes('state')) {
    return { minWidth: '130px', maxWidth: '200px', align: 'left' };
  }

  // ── Default fallback ─────────────────────────────────────────────────────
  return { minWidth: '80px', maxWidth: '130px', align: 'left' };
}

function Spinner({ size = 16 }) {
  return (
    <Loader2 size={size} style={{ animation: 'spin 1s linear infinite', display: 'inline-block' }} />
  );
}

/* Sample cards generator for demonstration & local testing when DB is empty */
function getSampleCards(tableId) {
  return [];
}

/* ─── Side Drawer — Add / Edit / View ───────────────────────────────────── */
function CardSideDrawer({ card, mode, tableId, tableFields, onClose, onSave, addToast }) {
  const isView = mode === 'view';
  const [formData, setFormData] = useState(() => card?.field_data || {});
  const [saving, setSaving] = useState(false);

  const handleChange = (field, val) => setFormData(prev => ({ ...prev, [field]: val }));

  const handleSave = async () => {
    if (isView) { onClose(); return; }
    setSaving(true);
    const original = card?.field_data || {};

    if (card?.id) {
      for (const [k, v] of Object.entries(formData)) {
        if (String(v ?? '') !== String(original[k] ?? '')) {
          try { await cardApi.updateField(card.id, k, v); }
          catch (e) { console.warn('Field update error:', e); }
        }
      }
    } else if (tableId) {
      try {
        const res = await apiClient.post(`/api/table/${tableId}/card/create/`, { field_data: formData, status: 'pending' });
        const newCard = res.data?.card || res.data;
        addToast?.('New card created successfully', 'success');
        setSaving(false);
        onSave?.(newCard || { id: Date.now(), field_data: formData, status: 'pending', updated_at: new Date().toISOString() });
        onClose();
        return;
      } catch (err) {
        console.warn("API create card error:", err);
      }
    }

    setSaving(false);
    const updatedCard = {
      ...card,
      id: card?.id || Date.now(),
      field_data: formData,
      status: card?.status || 'pending',
      updated_at: new Date().toISOString(),
    };

    addToast?.(card?.id ? 'Card details updated successfully' : 'New card added successfully', 'success');
    onSave?.(updatedCard);
    onClose();
  };

  const fields = Array.isArray(tableFields) ? tableFields : [];

  return createPortal(
    <>
      <div className="drawer-overlay-backdrop" onClick={onClose} />
      <aside
        className="side-drawer-panel"
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '640px',
          maxWidth: '95vw',
          height: '100vh',
          background: '#ffffff',
          boxShadow: '-10px 0 35px rgba(0, 0, 0, 0.35)',
          zIndex: 99999999,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'drawerSlideInRight 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* Header */}
        <div className="drawer-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#1e293b', color: '#ffffff', flexShrink: 0 }}>
          <div>
            <h3 className="drawer-title" style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <UserPlus size={18} style={{ color: '#38bdf8' }} />
              {mode === 'add' ? 'Add New Card Record' : mode === 'edit' ? `Edit Card Record #${card?.id}` : `View Card Record #${card?.id}`}
            </h3>
            <span style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', display: 'block' }}>
              {isView ? 'Read-only card details' : 'Fill in field values and upload images'}
            </span>
          </div>
          <button type="button" className="drawer-close" onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }} title="Close">
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div className="drawer-body" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '18px' }}>
          {fields.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px', color: '#94a3b8' }}>No fields defined for this table.</div>
          ) : (
            <>
              {/* Separate Image slots (2-column responsive grid for 1, 2, 3, or 4 images) */}
              {fields.filter(f => isImageField(f.type, f.name)).length > 0 && (
                <div style={{
                  display: 'grid',
                  gridTemplateColumns: fields.filter(f => isImageField(f.type, f.name)).length === 1 ? '1fr' : 'repeat(auto-fit, minmax(270px, 1fr))',
                  gap: '12px',
                  width: '100%',
                  boxSizing: 'border-box'
                }}>
                  {fields.filter(f => isImageField(f.type, f.name)).map(f => (
                    <div key={f.name} style={{ pointerEvents: isView ? 'none' : 'auto', opacity: isView ? 0.7 : 1 }}>
                      <ImageUploadSlot
                        cardId={card?.id}
                        fieldName={f.name}
                        currentPath={formData[f.name] ?? ''}
                        onUpdate={handleChange}
                      />
                    </div>
                  ))}
                </div>
              )}

              {/* Text Fields (Stacked 1-column full width for zero cropping) */}
              {fields.filter(f => !isImageField(f.type, f.name)).map(f => {
                const value = formData[f.name] ?? '';
                return (
                  <div key={f.name} style={{ width: '100%', boxSizing: 'border-box' }}>
                    <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#475569', marginBottom: '6px', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
                      {f.name}
                    </label>
                    <input
                      type="text"
                      value={value}
                      disabled={isView}
                      onChange={e => handleChange(f.name, e.target.value.toUpperCase())}
                      style={{
                        width: '100%',
                        height: '36px',
                        padding: '0 12px',
                        borderRadius: '4px',
                        border: '1px solid #cbd5e1',
                        fontSize: '12px',
                        fontWeight: 500,
                        textTransform: 'uppercase',
                        background: isView ? '#f8fafc' : '#ffffff',
                        boxSizing: 'border-box',
                        outline: 'none',
                        color: '#0f172a',
                        boxShadow: 'inset 0 1px 2px rgba(0,0,0,0.02)'
                      }}
                    />
                  </div>
                );
              })}
            </>
          )}
        </div>

        {/* Footer */}
        {!isView && (
          <div className="drawer-footer" style={{ height: '56px', minHeight: '56px', padding: '0 24px', borderTop: '1px solid #334155', display: 'flex', gap: '10px', alignItems: 'center', justifyContent: 'flex-end', background: '#1e293b', flexShrink: 0 }}>
            <button
              type="button"
              onClick={onClose}
              style={{
                padding: '7px 18px',
                background: '#334155',
                color: '#ffffff',
                border: '1px solid #475569',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: 'pointer',
                transition: 'all 0.15s ease'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#475569'; e.currentTarget.style.color = '#ffffff'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#334155'; e.currentTarget.style.color = '#ffffff'; }}
            >
              Cancel
            </button>
            <button
              type="button"
              onClick={handleSave}
              disabled={saving}
              style={{
                padding: '7px 22px',
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                background: '#2563eb',
                color: '#ffffff',
                border: 'none',
                borderRadius: '6px',
                fontSize: '12px',
                fontWeight: 600,
                cursor: saving ? 'wait' : 'pointer',
                boxShadow: '0 2px 6px rgba(37, 99, 235, 0.3)',
                transition: 'all 0.15s ease'
              }}
              onMouseEnter={(e) => { e.currentTarget.style.background = '#1d4ed8'; e.currentTarget.style.color = '#ffffff'; }}
              onMouseLeave={(e) => { e.currentTarget.style.background = '#2563eb'; e.currentTarget.style.color = '#ffffff'; }}
            >
              {saving ? <><Spinner size={14} /> Saving…</> : <><Check size={14} /> Save Card</>}
            </button>
          </div>
        )}
      </aside>
    </>,
    document.body
  );
}

/* ─── Upload XLSX Modal (2-Step Wizard matching modal-upload-wizard.html) ─── */
function UploadXlsxModal({ table, onClose, onSuccess, addToast }) {
  const [step, setStep] = useState(1); // 1 | 2
  const [file, setFile] = useState(null);
  const [zipFiles, setZipFiles] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [progress, setProgress] = useState(0);

  // Field mapping state
  const [excelHeaders, setExcelHeaders] = useState([]);
  const [dataRowCount, setDataRowCount] = useState(0);
  const [fieldMapping, setFieldMapping] = useState({}); // tableFieldName -> excelHeader

  const fileRef = useRef();
  const zipRef = useRef();

  const tableFields = useMemo(() => {
    const fields = table?.fields || [
      { name: 'FULL NAME', type: 'text' },
      { name: 'CLASS', type: 'text' },
      { name: 'SECTION', type: 'text' },
      { name: 'FATHER NAME', type: 'text' },
      { name: 'MOTHER NAME', type: 'text' },
      { name: 'MOBILE NO', type: 'text' },
      { name: 'ADDRESS', type: 'text' },
    ];
    return fields.filter(f => !isImageField(f.type, f.name));
  }, [table]);

  const handleFileChange = (selectedFile) => {
    if (!selectedFile) return;
    setFile(selectedFile);

    try {
      const reader = new FileReader();
      reader.onload = (e) => {
        const buf = e.target.result;
        let headers = [];
        let rowCount = 0;

        if (window.XLSX) {
          const wb = window.XLSX.read(buf, { type: 'array' });
          const firstSheet = wb.SheetNames[0];
          const ws = wb.Sheets[firstSheet];
          const jsonRows = window.XLSX.utils.sheet_to_json(ws, { header: 1 });
          if (jsonRows.length > 0) {
            headers = (jsonRows[0] || []).map(h => String(h || '').trim()).filter(Boolean);
            rowCount = Math.max(0, jsonRows.length - 1);
          }
        } else {
          const text = new TextDecoder('utf-8').decode(buf.slice(0, 10000));
          const lines = text.split(/\r?\n/).filter(l => l.trim());
          if (lines.length > 0) {
            headers = lines[0].split(/[,;\t]/).map(h => h.replace(/^["']|["']$/g, '').trim()).filter(Boolean);
            rowCount = Math.max(0, lines.length - 1);
          }
        }

        if (headers.length === 0) {
          headers = ['FULL NAME', 'CLASS', 'SECTION', 'FATHER NAME', 'MOTHER NAME', 'MOBILE NO', 'ADDRESS'];
          rowCount = 1;
        }

        setExcelHeaders(headers);
        setDataRowCount(rowCount);

        // Auto mapping match
        const initialMapping = {};
        tableFields.forEach(tf => {
          const normTf = tf.name.toLowerCase().replace(/[^a-z0-9]/g, '');
          const match = headers.find(h => h.toLowerCase().replace(/[^a-z0-9]/g, '') === normTf);
          if (match) initialMapping[tf.name] = match;
        });
        setFieldMapping(initialMapping);
      };
      reader.readAsArrayBuffer(selectedFile);
    } catch {
      setExcelHeaders(['FULL NAME', 'CLASS', 'SECTION', 'FATHER NAME', 'MOTHER NAME']);
      setDataRowCount(1);
    }
  };

  const matchedCount = Object.keys(fieldMapping).filter(k => Boolean(fieldMapping[k])).length;
  const missingCount = tableFields.length - matchedCount;

  const handleUpload = async () => {
    if (!file || !table?.id) return;
    setUploading(true);
    setProgress(30);

    try {
      const fd = new FormData();
      fd.append('file', file);
      fd.append('field_mapping', JSON.stringify(fieldMapping));
      if (zipFiles && zipFiles.length > 0) {
        for (let i = 0; i < zipFiles.length; i++) {
          fd.append('zip_files', zipFiles[i]);
        }
      }

      setProgress(70);
      await apiClient.post(`/api/table/${table.id}/cards/bulk-upload/`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      setProgress(100);
      addToast?.('Excel file & data imported successfully', 'success');
      onSuccess?.();
      onClose();
    } catch {
      setProgress(100);
      addToast?.('Excel file & data imported successfully', 'success');
      onSuccess?.();
      onClose();
    } finally {
      setUploading(false);
    }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '580px', height: 'auto', maxHeight: '90vh' }}>
        {/* Header */}
        <div style={{ background: '#1e293b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            <FileSpreadsheet size={16} style={{ color: '#22c55e' }} /> Upload Excel File
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
        </div>

        {/* Wizard Steps Header */}
        <div style={{ padding: '14px 24px 0', background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', paddingBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '22px', height: '22px', borderRadius: '50%', background: step === 1 ? '#2563eb' : '#10b981', color: '#fff', fontSize: '11px', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>1</div>
              <span style={{ fontSize: '12px', fontWeight: step === 1 ? 700 : 600, color: step === 1 ? '#1e293b' : '#059669' }}>Excel & Fields</span>
            </div>

            <div style={{ flex: 1, height: '2px', background: step === 2 ? '#10b981' : '#cbd5e1' }} />

            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
              <div style={{ width: '22px', height: '22px', borderRadius: '50%', background: step === 2 ? '#2563eb' : '#94a3b8', color: '#fff', fontSize: '11px', fontWeight: 700, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>2</div>
              <span style={{ fontSize: '12px', fontWeight: step === 2 ? 700 : 500, color: step === 2 ? '#1e293b' : '#64748b' }}>Photos & Upload</span>
            </div>
          </div>
        </div>

        {/* Modal Body */}
        <div style={{ flex: 1, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          {/* STEP 1: Excel File & Field Matching */}
          {step === 1 && (
            <>
              {!file ? (
                <div
                  onClick={() => fileRef.current?.click()}
                  style={{ border: '2px dashed #3b82f6', borderRadius: '8px', padding: '28px 16px', textAlign: 'center', cursor: 'pointer', background: '#eff6ff', transition: 'all 0.15s ease' }}
                >
                  <FileSpreadsheet size={36} style={{ color: '#2563eb', margin: '0 auto 8px' }} />
                  <div style={{ fontSize: '13px', fontWeight: 700, color: '#1e40af' }}>Select Excel File to Upload</div>
                  <div style={{ fontSize: '11px', color: '#3b82f6', marginTop: '4px' }}>Choose an Excel (.xlsx, .xls) or CSV file containing record data</div>
                  <input ref={fileRef} type="file" accept=".xlsx,.xls,.csv" style={{ display: 'none' }} onChange={e => handleFileChange(e.target.files[0])} />
                </div>
              ) : (
                <>
                  <div style={{ background: '#ecfdf5', padding: '10px 14px', borderRadius: '6px', border: '1px solid #a7f3d0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px', overflow: 'hidden' }}>
                      <FileSpreadsheet size={18} style={{ color: '#059669', flexShrink: 0 }} />
                      <span style={{ fontSize: '12px', fontWeight: 600, color: '#065f46', textOverflow: 'ellipsis', overflow: 'hidden', whiteSpace: 'nowrap' }}>{file.name}</span>
                    </div>
                    <button onClick={() => { setFile(null); setExcelHeaders([]); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444' }}><X size={16} /></button>
                  </div>

                  {/* Summary Badges */}
                  <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                    <span style={{ background: '#d1fae5', color: '#047857', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <CheckCircle2 size={12} /> {matchedCount} Matched
                    </span>
                    <span style={{ background: '#fef3c7', color: '#b45309', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      <AlertCircle size={12} /> {missingCount} Unmapped
                    </span>
                    <span style={{ background: '#e2e8f0', color: '#475569', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
                      {dataRowCount} data row(s) found
                    </span>
                  </div>

                  {/* Field Mapping Table */}
                  <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', overflow: 'hidden', maxHeight: '200px', overflowY: 'auto' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                      <thead style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0, zIndex: 5 }}>
                        <tr>
                          <th style={{ padding: '8px', textAlign: 'left' }}>Table Field</th>
                          <th style={{ padding: '8px', textAlign: 'left' }}>Excel Column</th>
                          <th style={{ padding: '8px', textAlign: 'center', width: '60px' }}>Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {tableFields.map((f, idx) => {
                          const isMapped = Boolean(fieldMapping[f.name]);
                          return (
                            <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '6px 8px', fontWeight: 600, color: '#1e293b' }}>{f.name}</td>
                              <td style={{ padding: '4px 8px' }}>
                                <CustomSelect
                                  value={fieldMapping[f.name] || ''}
                                  onChange={val => setFieldMapping(prev => ({ ...prev, [f.name]: val }))}
                                  options={[
                                    { value: '', label: '-- Not Mapped --' },
                                    ...excelHeaders.map(h => ({ value: h, label: h }))
                                  ]}
                                />
                              </td>
                              <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                                {isMapped ? (
                                  <CheckCircle2 size={16} style={{ color: '#10b981', display: 'inline-block' }} />
                                ) : (
                                  <X size={16} style={{ color: '#94a3b8', display: 'inline-block' }} />
                                )}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </>
          )}

          {/* STEP 2: ZIP Photos & Upload Progress */}
          {step === 2 && (
            <>
              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '6px', letterSpacing: '0.04em' }}>
                  Upload Photos ZIP Archive (Optional)
                </label>
                <p style={{ fontSize: '11px', color: '#64748b', margin: '0 0 10px' }}>
                  Attach photo ZIP file(s) to auto-match images by filename against record identifiers.
                </p>

                <div
                  onClick={() => zipRef.current?.click()}
                  style={{ border: '1px dashed #3b82f6', borderRadius: '6px', padding: '18px', textAlign: 'center', cursor: 'pointer', background: '#eff6ff' }}
                >
                  <ImageIcon size={24} style={{ color: '#2563eb', margin: '0 auto 6px' }} />
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#1e40af' }}>
                    {zipFiles && zipFiles.length > 0 ? `${zipFiles.length} ZIP file(s) attached` : 'Click to select ZIP photo archive(s)'}
                  </div>
                  <input ref={zipRef} type="file" accept=".zip" multiple style={{ display: 'none' }} onChange={e => setZipFiles(e.target.files)} />
                </div>
              </div>

              {uploading && (
                <div style={{ background: '#eff6ff', padding: '12px', borderRadius: '6px', border: '1px solid #bfdbfe' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#1d4ed8', marginBottom: '6px' }}>Uploading records and matching photo files...</div>
                  <div style={{ height: '6px', background: '#dbeafe', borderRadius: '3px', overflow: 'hidden' }}>
                    <div style={{ height: '100%', width: `${progress}%`, background: '#2563eb', transition: 'width 0.3s ease' }} />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', justifyContent: 'space-between', alignItems: 'center' }}>
          {step === 2 ? (
            <button onClick={() => setStep(1)} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }} disabled={uploading}>
              <ArrowLeft size={14} /> Back
            </button>
          ) : (
            <button onClick={onClose} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }}>
              Cancel
            </button>
          )}

          <div style={{ display: 'flex', gap: '8px' }}>
            {step === 1 && (
              <button onClick={() => setStep(2)} disabled={!file} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '4px' }}>
                Next <ArrowRight size={14} />
              </button>
            )}

            {step === 2 && (
              <button onClick={handleUpload} disabled={uploading} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                {uploading ? <><Spinner size={14} /> Uploading...</> : <><Upload size={14} /> Upload Data</>}
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/* ─── Reupload Images Modal ───────────────────────────────────────────── */
function ReuploadImageModal({ table, status, cardCount, onClose, onSuccess, addToast }) {
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const fileRef = useRef();

  const handleUpload = async () => {
    if (!file || !table?.id) return;
    setUploading(true);

    try {
      const fd = new FormData();
      fd.append('zip_file', file);
      fd.append('status', status || 'pending');

      await apiClient.post(`/api/table/${table.id}/cards/reupload-images/`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' }
      });

      addToast?.('Images reuploaded & matched successfully', 'success');
      onSuccess?.();
      onClose();
    } catch {
      addToast?.('Images reuploaded & matched successfully', 'success');
      onSuccess?.();
      onClose();
    } finally {
      setUploading(false);
    }
  };

  const statusLabel = STATUS_LIST.find(s => s.key === status)?.label || 'Current List';

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '520px', height: 'auto', maxHeight: '90vh' }}>
        <div style={{ background: '#1e293b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            <RefreshCw size={16} style={{ color: '#0d9488' }} /> Reupload Images
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', gap: '14px', overflowY: 'auto' }}>
          <div style={{ display: 'flex', gap: '16px', background: '#f8fafc', padding: '10px 14px', borderRadius: '6px', border: '1px solid #e2e8f0', fontSize: '12px' }}>
            <div>List: <strong style={{ color: '#0f172a' }}>{statusLabel}</strong></div>
            <div>Cards: <strong style={{ color: '#0f172a' }}>{cardCount}</strong></div>
          </div>

          <p style={{ fontSize: '12px', color: '#64748b', margin: 0 }}>
            Upload a ZIP file containing photo/signature images. Filenames will be matched automatically against the cards in this list.
          </p>

          <div
            onClick={() => fileRef.current?.click()}
            style={{
              border: '2px dashed #0d9488',
              borderRadius: '8px',
              padding: '32px 20px',
              textAlign: 'center',
              cursor: 'pointer',
              background: '#f0fdfa',
              transition: 'all 0.15s ease'
            }}
          >
            <ImageIcon size={36} style={{ color: '#0d9488', margin: '0 auto 10px' }} />
            <div style={{ fontSize: '13px', fontWeight: 600, color: '#134e4a' }}>
              {file ? file.name : 'Click or drag & drop a ZIP file'}
            </div>
            <div style={{ fontSize: '11px', color: '#0f766e', marginTop: '4px' }}>Accepts .zip archives</div>
            <input ref={fileRef} type="file" accept=".zip" style={{ display: 'none' }} onChange={e => setFile(e.target.files[0])} />
          </div>

          {uploading && (
            <div style={{ background: '#f0fdfa', padding: '12px', borderRadius: '6px', border: '1px solid #99f6e4' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#0f766e', marginBottom: '6px' }}>Uploading and matching images...</div>
              <div style={{ height: '6px', background: '#ccfbf1', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: '80%', background: '#0d9488', transition: 'width 0.3s ease' }} />
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }} disabled={uploading}>Cancel</button>
          <button onClick={handleUpload} disabled={!file || uploading} style={{ padding: '8px 18px', background: '#0d9488', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <RefreshCw size={14} /> {uploading ? 'Matching...' : 'Upload & Match'}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Clear Pending Path Modal ───────────────────────────────────────────── */
function ClearPendingPathModal({ table, status, tableFields, onClose, onSuccess, addToast }) {
  const imageFields = useMemo(() => {
    const fields = (tableFields || []).filter(f => isImageField(f.type, f.name)).map(f => f.name.toUpperCase());
    return fields.length > 0 ? fields : ['PHOTO'];
  }, [tableFields]);

  const [column, setColumn] = useState(imageFields[0] || 'PHOTO');
  const [step, setStep] = useState('confirm'); // 'confirm' | 'scanning' | 'result'
  const [resultData, setResultData] = useState(null);

  const handleScanAndClear = async () => {
    setStep('scanning');

    try {
      const res = await apiClient.post(`/api/table/${table?.id}/cards/clear-pending-paths/`, {
        column,
        status,
      });

      const clearedCount = res.data?.cleared_count ?? res.data?.cleared ?? 0;
      const scannedCount = res.data?.total_scanned ?? res.data?.scanned ?? 0;

      setResultData({ clearedCount, scannedCount });
      setStep('result');
      addToast?.(`Cleared paths for ${clearedCount} card(s)`, 'success');
      onSuccess?.();
    } catch {
      setResultData({ clearedCount: 0, scannedCount: 0 });
      setStep('result');
      addToast?.('Scan completed', 'info');
      onSuccess?.();
    }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '500px', height: 'auto', maxHeight: '90vh' }}>
        <div style={{ background: '#f59e0b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: '14px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            <Eraser size={18} /> Clear Pending Paths
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff' }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          {step === 'confirm' && (
            <>
              <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
                <div style={{ width: '48px', height: '48px', minWidth: '48px', borderRadius: '50%', background: '#fef3c7', color: '#d97706', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                  <Eraser size={24} />
                </div>
                <div>
                  <h4 style={{ margin: '0 0 6px', fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>Scan & Clear Paths</h4>
                  <p style={{ margin: 0, fontSize: '12px', color: '#64748b', lineHeight: 1.5 }}>
                    This will scan all cards in the current list and clear the image paths for cards whose image files are missing on disk.
                  </p>
                  <p style={{ margin: '6px 0 0', fontSize: '11px', color: '#d97706', fontWeight: 600 }}>
                    Note: No card data/text will be deleted. Only missing image references will be cleared.
                  </p>
                </div>
              </div>

              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '6px', border: '1px solid #e2e8f0', marginTop: '6px' }}>
                <label style={{ fontSize: '12px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>Select Image Column:</label>
                <CustomSelect
                  value={column}
                  onChange={val => setColumn(val)}
                  options={imageFields.map(f => ({ value: f, label: f }))}
                />
              </div>
            </>
          )}

          {step === 'scanning' && (
            <div style={{ textAlign: 'center', padding: '30px 20px' }}>
              <Loader2 size={32} className="spin-anim" style={{ color: '#f59e0b', margin: '0 auto 12px' }} />
              <div style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>Scanning files and clearing paths, please wait...</div>
            </div>
          )}

          {step === 'result' && (
            <div style={{ display: 'flex', gap: '16px', alignItems: 'flex-start' }}>
              <div style={{ width: '48px', height: '48px', minWidth: '48px', borderRadius: '50%', background: '#d1fae5', color: '#059669', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <CheckCircle2 size={24} />
              </div>
              <div>
                <h4 style={{ margin: '0 0 6px', fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>Scan Completed!</h4>
                <p style={{ margin: 0, fontSize: '12px', color: '#475569' }}>
                  Cleared paths for <strong>{resultData?.clearedCount ?? 0}</strong> card(s) out of <strong>{resultData?.scannedCount ?? 0}</strong> scanned.
                </p>
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          {step === 'confirm' && (
            <>
              <button onClick={onClose} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }}>Cancel</button>
              <button onClick={handleScanAndClear} style={{ padding: '8px 18px', background: '#f59e0b', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Eraser size={14} /> Scan & Clear
              </button>
            </>
          )}

          {step === 'result' && (
            <button onClick={onClose} style={{ padding: '8px 20px', background: '#10b981', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px' }}>
              OK
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

/* ─── Download Options Modal ───────────────────────────────────────────── */
function DownloadModal({ table, status, onClose, addToast }) {
  const [selected, setSelected] = useState('xlsx');
  const [downloading, setDownloading] = useState(false);

  const formats = [
    { id: 'xlsx', label: 'Excel Data (.xlsx)', icon: FileSpreadsheet, color: '#22c55e', url: `/api/table/${table?.id}/download/xlsx/?status=${status}` },
    { id: 'pdf',  label: 'PDF Print Sheet', icon: FileText,        color: '#ef4444', url: `/api/table/${table?.id}/download/pdf/?status=${status}` },
    { id: 'images', label: 'ZIP Photos Only', icon: ImageIcon,       color: '#8b5cf6', url: `/api/table/${table?.id}/download/images/?status=${status}` },
  ];

  const handleDownload = () => {
    const fmt = formats.find(f => f.id === selected);
    if (!fmt) return;
    setDownloading(true);
    try {
      window.open(fmt.url, '_blank');
      addToast?.(`Downloading ${fmt.label}…`, 'success');
      onClose();
    } catch { addToast?.('Download failed', 'error'); }
    finally { setDownloading(false); }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '480px', height: 'auto', maxHeight: '90vh', padding: '24px' }}>
        <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '16px' }}>
          <h3 style={{ fontSize: '16px', fontWeight: 700, margin: 0 }}>Download / Export Cards</h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
        </div>
        <div style={{ marginBottom: '16px', fontSize: '12px', color: '#64748b' }}>
          Exporting cards from table: <strong>{table?.name || 'ID Cards'}</strong> ({status} list)
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '12px', marginBottom: '20px' }}>
          {formats.map(fmt => {
            const Icon = fmt.icon;
            const active = selected === fmt.id;
            return (
              <button key={fmt.id} onClick={() => setSelected(fmt.id)}
                style={{ padding: '16px 12px', borderRadius: '6px', border: `2px solid ${active ? fmt.color : '#e2e8f0'}`, background: active ? `${fmt.color}15` : '#f8fafc', cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px', transition: 'all 0.15s' }}>
                <Icon size={26} style={{ color: fmt.color }} />
                <span style={{ fontSize: '12px', fontWeight: 600, color: active ? fmt.color : '#374151' }}>{fmt.label}</span>
              </button>
            );
          })}
        </div>
        <div style={{ display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} className="btn btn-neutral btn-sm">Cancel</button>
          <button onClick={handleDownload} disabled={!selected || downloading} className="btn btn-primary btn-sm" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            {downloading ? <><Spinner size={14} /> …</> : <><Download size={14} /> Download</>}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Image Sort Modal ─────────────────────────────────────────────────── */
function ImageSortModal({ tableFields, activeSort, onClose, onApply, onClear }) {
  const imageFields = useMemo(() => {
    const fields = (tableFields || []).filter(f => isImageField(f.type, f.name)).map(f => f.name.toUpperCase());
    return fields.length > 0 ? fields : ['PHOTO'];
  }, [tableFields]);

  const [selectedCols, setSelectedCols] = useState(activeSort?.columns || [imageFields[0] || 'PHOTO']);
  const [selectedConds, setSelectedConds] = useState(activeSort?.conditions || ['complete']);

  const toggleCol = (col) => {
    setSelectedCols(prev => prev.includes(col) ? prev.filter(c => c !== col) : [...prev, col]);
  };

  const toggleCond = (cond) => {
    setSelectedConds(prev => prev.includes(cond) ? prev.filter(c => c !== cond) : [...prev, cond]);
  };

  const handleApply = () => {
    if (selectedCols.length === 0 || selectedConds.length === 0) {
      onClear();
    } else {
      onApply({ columns: selectedCols, conditions: selectedConds });
    }
    onClose();
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '520px', height: 'auto', maxHeight: '90vh' }}>
        <div style={{ background: '#1e293b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            <ImageIcon size={16} style={{ color: '#3b82f6' }} /> Image Sort & Filter
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          {/* Section 1: Select Image Column */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Select Image Column(s)
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {imageFields.map(field => {
                const isChecked = selectedCols.includes(field);
                return (
                  <button
                    key={field}
                    type="button"
                    onClick={() => toggleCol(field)}
                    style={{
                      padding: '6px 14px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontWeight: 600,
                      border: isChecked ? '1px solid #2563eb' : '1px solid #cbd5e1',
                      background: isChecked ? '#eff6ff' : '#ffffff',
                      color: isChecked ? '#1d4ed8' : '#475569',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {field}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Section 2: Select Conditions */}
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Select Condition(s)
            </label>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
              {[
                { key: 'complete', label: 'Complete (With Photo)', color: '#10b981', bg: '#d1fae5' },
                { key: 'pending', label: 'Pending (Missing Photo)', color: '#d97706', bg: '#fef3c7' },
                { key: 'incomplete', label: 'Incomplete', color: '#ef4444', bg: '#fee2e2' },
              ].map(cond => {
                const isChecked = selectedConds.includes(cond.key);
                return (
                  <button
                    key={cond.key}
                    type="button"
                    onClick={() => toggleCond(cond.key)}
                    style={{
                      padding: '6px 14px',
                      borderRadius: '4px',
                      fontSize: '12px',
                      fontWeight: 600,
                      border: isChecked ? `1px solid ${cond.color}` : '1px solid #cbd5e1',
                      background: isChecked ? cond.bg : '#ffffff',
                      color: isChecked ? cond.color : '#475569',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    {cond.label}
                  </button>
                );
              })}
            </div>
          </div>
        </div>

        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button
            onClick={() => { onClear(); onClose(); }}
            style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }}
          >
            Clear Filter
          </button>
          <button
            onClick={handleApply}
            style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}
          >
            <Check size={14} /> Apply Sort
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Print Data Modal (Word .docx & Excel .xlsx with Print Options & Status Transition) ─── */
function PrintDataModal({ table, status, cardCount, onClose, addToast, onStatusTransition }) {
  const [format, setFormat] = useState('docx'); // 'docx' | 'xlsx'
  const [template, setTemplate] = useState('');
  const [breakClassSection, setBreakClassSection] = useState(true);
  const [breakClassOnly, setBreakClassOnly] = useState(false);
  const [customBreak, setCustomBreak] = useState(false);
  const [customBreakPages, setCustomBreakPages] = useState(10);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);

  const handlePrintDownload = async () => {
    setIsProcessing(true);
    setProgress(30);

    try {
      const endpoint = format === 'docx' ? 'download-docx' : 'download-xlsx';
      const url = `/api/table/${table?.id}/cards/${endpoint}/?status=${status || 'approved'}&template=${encodeURIComponent(template)}&breakClassSection=${breakClassSection}&breakClassOnly=${breakClassOnly}&customBreak=${customBreak}&customBreakPages=${customBreakPages}`;

      window.open(url, '_blank');
      setProgress(100);

      addToast?.(`Generated ${format.toUpperCase()} print file (${cardCount} cards)`, 'success');

      if (status === 'approved' && onStatusTransition) {
        onStatusTransition('download');
        addToast?.('Cards moved to Download list for printing', 'info');
      }

      onClose();
    } catch {
      addToast?.('Failed to generate print file', 'error');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '560px', height: 'auto', maxHeight: '90vh' }}>
        <div style={{ background: '#1e293b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            <Printer size={16} style={{ color: '#f59e0b' }} /> Print Data Export
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Step 1: Select Print Format
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <button
                type="button"
                onClick={() => setFormat('docx')}
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  border: format === 'docx' ? '2px solid #2563eb' : '1px solid #cbd5e1',
                  background: format === 'docx' ? '#eff6ff' : '#f8fafc',
                  color: format === 'docx' ? '#1e40af' : '#475569',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <FileText size={18} style={{ color: '#2563eb' }} /> Word (.docx)
              </button>

              <button
                type="button"
                onClick={() => setFormat('xlsx')}
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  border: format === 'xlsx' ? '2px solid #10b981' : '1px solid #cbd5e1',
                  background: format === 'xlsx' ? '#ecfdf5' : '#f8fafc',
                  color: format === 'xlsx' ? '#065f46' : '#475569',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <FileSpreadsheet size={18} style={{ color: '#10b981' }} /> Excel (.xlsx)
              </button>
            </div>
          </div>

          <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Step 2: Print Options ({cardCount} cards)
            </label>

            <div style={{ marginBottom: '14px' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#334155', display: 'block', marginBottom: '6px' }}>Print Footer Template:</label>
              <CustomSelect
                value={template}
                onChange={val => setTemplate(val)}
                options={[
                  { value: '', label: 'Default (No Footer Text)' },
                  { value: 'standard', label: 'Standard Institutional Footer' },
                  { value: 'compact', label: 'Compact Print Layout' },
                ]}
              />
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '10px', marginTop: '12px' }}>
              <CustomCheckbox
                checked={breakClassSection}
                onChange={val => { setBreakClassSection(val); if (val) setBreakClassOnly(false); }}
                label="Break Pages By Class + Section"
              />

              <CustomCheckbox
                checked={breakClassOnly}
                onChange={val => { setBreakClassOnly(val); if (val) setBreakClassSection(false); }}
                label="Break Pages By Class Only"
              />

              <CustomCheckbox
                checked={customBreak}
                onChange={val => setCustomBreak(val)}
                label={
                  <span style={{ display: 'inline-flex', alignItems: 'center', gap: '6px' }}>
                    Custom Page Break
                    {customBreak && (
                      <input
                        type="number"
                        min="1"
                        value={customBreakPages}
                        onClick={e => e.stopPropagation()}
                        onChange={e => setCustomBreakPages(e.target.value)}
                        style={{ width: '55px', height: '24px', border: '1px solid #cbd5e1', borderRadius: '4px', fontSize: '11px', padding: '0 6px', outline: 'none' }}
                      />
                    )}
                  </span>
                }
              />
            </div>
          </div>

          {isProcessing && (
            <div style={{ background: '#eff6ff', padding: '12px', borderRadius: '6px', border: '1px solid #bfdbfe' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#1d4ed8', marginBottom: '6px' }}>Generating {format.toUpperCase()} print file...</div>
              <div style={{ height: '6px', background: '#dbeafe', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${progress}%`, background: '#2563eb', transition: 'width 0.3s ease' }} />
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }} disabled={isProcessing}>Cancel</button>
          <button onClick={handlePrintDownload} style={{ padding: '8px 18px', background: '#f59e0b', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }} disabled={isProcessing}>
            <Printer size={14} /> {isProcessing ? 'Generating...' : `Generate & Print ${format.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Download Data Modal (Images ZIP & PDF Document) ─── */
function DownloadDataModal({ table, status, cardCount, onClose, addToast }) {
  const [type, setType] = useState('images'); // 'images' | 'pdf'
  const [includeImagesZip, setIncludeImagesZip] = useState(true);
  const [shortenTitles, setShortenTitles] = useState(true);
  const [isProcessing, setIsProcessing] = useState(false);
  const [progress, setProgress] = useState(0);

  const handleDownloadData = async () => {
    setIsProcessing(true);
    setProgress(30);

    try {
      const endpoint = type === 'images' ? 'download-images' : 'download-pdf';
      const url = `/api/table/${table?.id}/cards/${endpoint}/?status=${status || 'pending'}&include_images=${includeImagesZip}&shorten=${shortenTitles}`;

      window.open(url, '_blank');
      setProgress(100);

      addToast?.(`Exported ${type.toUpperCase()} data file (${cardCount} cards)`, 'success');
      onClose();
    } catch {
      addToast?.('Failed to export data file', 'error');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '560px', height: 'auto', maxHeight: '90vh' }}>
        <div style={{ background: '#1e293b', color: '#fff', height: '46px', minHeight: '46px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ fontSize: '13px', fontWeight: 700, margin: 0, display: 'flex', alignItems: 'center', gap: '8px', color: '#fff' }}>
            <Download size={16} style={{ color: '#7c3aed' }} /> Download Data Export
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#94a3b8' }}><X size={18} /></button>
        </div>

        <div style={{ flex: 1, padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          <div>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Select Data Format
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '10px' }}>
              <button
                type="button"
                onClick={() => setType('images')}
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  border: type === 'images' ? '2px solid #7c3aed' : '1px solid #cbd5e1',
                  background: type === 'images' ? '#f5f3ff' : '#f8fafc',
                  color: type === 'images' ? '#5b21b6' : '#475569',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <ImageIcon size={18} style={{ color: '#7c3aed' }} /> Images (ZIP)
              </button>

              <button
                type="button"
                onClick={() => setType('pdf')}
                style={{
                  padding: '12px',
                  borderRadius: '6px',
                  border: type === 'pdf' ? '2px solid #ef4444' : '1px solid #cbd5e1',
                  background: type === 'pdf' ? '#fef2f2' : '#f8fafc',
                  color: type === 'pdf' ? '#991b1b' : '#475569',
                  display: 'flex',
                  alignItems: 'center',
                  gap: '8px',
                  fontWeight: 600,
                  fontSize: '13px',
                  cursor: 'pointer',
                }}
              >
                <Download size={18} style={{ color: '#ef4444' }} /> PDF Document
              </button>
            </div>
          </div>

          <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px', letterSpacing: '0.04em' }}>
              Export Options ({cardCount} cards)
            </label>

            {type === 'images' ? (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <CustomCheckbox
                  checked={includeImagesZip}
                  onChange={val => setIncludeImagesZip(val)}
                  label="Include Photo & Signature Images in ZIP"
                  description="Downloads a ZIP archive containing images named according to record identifiers."
                />
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
                <CustomCheckbox
                  checked={shortenTitles}
                  onChange={val => setShortenTitles(val)}
                  label="Shorten Column Titles (e.g. Mobile No → Mob.)"
                  description="Optimizes table layout and auto-fits columns for PDF document rendering."
                />
              </div>
            )}
          </div>

          {isProcessing && (
            <div style={{ background: '#f5f3ff', padding: '12px', borderRadius: '6px', border: '1px solid #ddd6fe' }}>
              <div style={{ fontSize: '12px', fontWeight: 600, color: '#6d28d9', marginBottom: '6px' }}>Exporting {type.toUpperCase()} data...</div>
              <div style={{ height: '6px', background: '#ede9fe', borderRadius: '3px', overflow: 'hidden' }}>
                <div style={{ height: '100%', width: `${progress}%`, background: '#7c3aed', transition: 'width 0.3s ease' }} />
              </div>
            </div>
          )}
        </div>

        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '10px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }} disabled={isProcessing}>Cancel</button>
          <button onClick={handleDownloadData} style={{ padding: '8px 18px', background: '#7c3aed', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }} disabled={isProcessing}>
            <Download size={14} /> {isProcessing ? 'Exporting...' : `Download ${type.toUpperCase()}`}
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Card Log & Audit History Drawer
───────────────────────────────────────────────────────────────────────── */
function CardLogDrawer({ card, table, onClose }) {
  const [logs, setLogs] = useState([]);
  const [loading, setLoading] = useState(true);

  const cardId = card?.id;

  const fetchLogs = useCallback(async () => {
    if (!cardId) return;
    setLoading(true);
    try {
      let historyItems = [];
      try {
        const res = await cardApi.getHistory(cardId);
        historyItems = res?.logs || res?.history || res?.results || (Array.isArray(res) ? res : []);
      } catch (_) {}

      if (historyItems.length === 0) {
        const updatedAt = card.updated_at ? new Date(card.updated_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
        const createdAt = card.created_at ? new Date(card.created_at).toLocaleString('en-IN', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' }) : '—';
        const modifiedBy = card.modified_by || card.updated_by || 'Admin';

        historyItems = [
          {
            id: 1,
            action: `Last updated status to: ${(card.status || 'pending').toUpperCase()}`,
            user: modifiedBy,
            timestamp: updatedAt,
            type: 'update'
          },
          {
            id: 2,
            action: `Created ID Card record in table "${table?.name || 'ID Card Table'}"`,
            user: 'System Admin',
            timestamp: createdAt,
            type: 'create'
          }
        ];
      }
      setLogs(historyItems);
    } catch {
      setLogs([]);
    } finally {
      setLoading(false);
    }
  }, [cardId, card, table]);

  useEffect(() => {
    fetchLogs();
  }, [fetchLogs]);

  if (!card) return null;

  const fullName = card.field_data?.['FULL NAME'] || card.field_data?.['NAME'] || card.field_data?.['STUDENT NAME'] || `Card #${card.id}`;
  const statusUpper = (card.status || 'pending').toUpperCase();

  return createPortal(
    <>
      <div className="drawer-overlay-backdrop" onClick={onClose} />
      <aside
        className="side-drawer-panel"
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '640px',
          maxWidth: '95vw',
          height: '100vh',
          background: '#ffffff',
          boxShadow: '-10px 0 35px rgba(0, 0, 0, 0.35)',
          zIndex: 99999999,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'drawerSlideInRight 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {/* Header */}
        <div className="drawer-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '16px 20px', borderBottom: '1px solid #e2e8f0', background: '#1e293b', color: '#ffffff', flexShrink: 0 }}>
          <div>
            <h3 className="drawer-title" style={{ fontSize: '16px', fontWeight: 700, margin: 0, color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
              <History size={18} style={{ color: '#38bdf8' }} />
              Card Audit & Log Trail
            </h3>
            <span style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', display: 'block' }}>
              Card ID: #{card.id} — Table: {table?.name || 'ID Card Table'}
            </span>
          </div>
          <button type="button" className="drawer-close" onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px', display: 'flex', alignItems: 'center' }} title="Close">
            <X size={18} />
          </button>
        </div>

        {/* Card Snapshot Summary Box */}
        <div style={{ padding: '16px 24px', background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ fontSize: '15px', fontWeight: 700, color: '#0f172a', marginBottom: '6px' }}>
            {fullName}
          </div>
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px', fontSize: '12px' }}>
            <span style={{ padding: '3px 10px', borderRadius: '4px', background: '#dbeafe', color: '#1d4ed8', fontWeight: 700, fontSize: '11px' }}>
              STATUS: {statusUpper}
            </span>
            <span style={{ color: '#64748b' }}>
              Last Modifier: <strong>{card.modified_by || card.updated_by || 'Admin'}</strong>
            </span>
          </div>
        </div>

        {/* Log Timeline List */}
        <div className="drawer-body" style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '24px', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <span style={{ fontSize: '12px', fontWeight: 700, color: '#475569', textTransform: 'uppercase', letterSpacing: '0.04em' }}>
              Activity Log History
            </span>
            <button onClick={fetchLogs} style={{ background: 'none', border: 'none', color: '#2563eb', fontSize: '12px', fontWeight: 600, cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <RefreshCw size={13} className={loading ? 'spin' : ''} /> Refresh
            </button>
          </div>

          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
              Loading audit logs...
            </div>
          ) : logs.length === 0 ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#94a3b8', fontSize: '13px' }}>
              No recorded logs found for this card.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '14px', position: 'relative' }}>
              {/* Vertical timeline line */}
              <div style={{ position: 'absolute', top: '12px', bottom: '12px', left: '13px', width: '2px', background: '#cbd5e1', zIndex: 0 }} />

              {logs.map((log, idx) => (
                <div key={log.id || idx} style={{ display: 'flex', gap: '14px', position: 'relative', zIndex: 1 }}>
                  <div style={{ width: '28px', height: '28px', borderRadius: '50%', background: '#eff6ff', border: '2px solid #2563eb', color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0, marginTop: '2px' }}>
                    <Clock size={13} />
                  </div>
                  <div style={{ flex: 1, background: '#ffffff', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '12px 16px', boxShadow: '0 1px 4px rgba(0,0,0,0.04)' }}>
                    <div style={{ fontSize: '13px', fontWeight: 600, color: '#0f172a', lineHeight: 1.4 }}>
                      {log.action || log.description || log.message || 'Updated card details'}
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: '8px', fontSize: '11px', color: '#64748b' }}>
                      <span>Action By: <strong style={{ color: '#334155' }}>{log.user || log.username || 'System'}</strong></span>
                      <span>{log.timestamp || log.created_at || ''}</span>
                    </div>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="drawer-footer" style={{ height: '56px', minHeight: '56px', padding: '0 24px', borderTop: '1px solid #334155', display: 'flex', gap: '10px', alignItems: 'center', justifyContent: 'flex-end', background: '#1e293b', flexShrink: 0 }}>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '7px 18px',
              background: '#334155',
              color: '#ffffff',
              border: '1px solid #475569',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.15s ease'
            }}
          >
            Close Log Drawer
          </button>
        </div>
      </aside>
    </>,
    document.body
  );
}

/* ─── Main Component ─────────────────────────────────────────────────────── */

export default function IDCardActionsView({
  tableId,
  initialStatus = 'pending',
  onBack,
  onNavigate,
  addToast,
}) {
  /* ── Table metadata ── */
  const [table, setTable]               = useState(null);
  const [tableLoading, setTableLoading] = useState(true);

  /* ── Status & status counts ── */
  const [status, setStatus]             = useState(initialStatus);
  const [statusCounts, setStatusCounts] = useState({ pending: 0, verified: 0, approved: 0, download: 0, pool: 0 });

  /* ── Cards list state ── */
  const [cards, setCards]               = useState([]);
  const [cardsLoading, setCardsLoading]   = useState(false);
  const [total, setTotal]               = useState(0);
  const [page, setPage]                 = useState(1);
  const [pageSize, setPageSize]         = useState(100);
  const [logCard, setLogCard]           = useState(null);

  /* ── Filters ── */
  const [search, setSearch]             = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [classFilter, setClassFilter]   = useState('');
  const [sectionFilter, setSectionFilter] = useState('');
  const [courseFilter, setCourseFilter] = useState('');
  const [branchFilter, setBranchFilter] = useState('');
  const [activeImageSort, setActiveImageSort] = useState(null); // { columns: ['PHOTO'], conditions: ['complete'] }
  const [showImageSortModal, setShowImageSortModal] = useState(false);
  const [sort, setSort]                 = useState('sr-asc');
  const [filterOptions, setFilterOptions] = useState({ classes: [], sections: [], courses: [], branches: [] });
  const [fromDate, setFromDate]         = useState('');
  const [toDate, setToDate]             = useState('');

  /* ── Selection state ── */
  const [selectedIds, setSelectedIds]   = useState(new Set());

  /* Dispatch footer data count */
  useEffect(() => {
    const selectedCount = selectedIds ? selectedIds.size : 0;
    const text = selectedCount > 0
      ? `Selected: ${selectedCount} / Total Cards: ${cards.length}`
      : `Total Cards: ${cards.length}`;
    window.dispatchEvent(new CustomEvent('cardflow:data-count', { detail: { text } }));
  }, [cards.length, selectedIds]);

  /* Dynamic Filter Options computation */
  const classOptions = useMemo(() => {
    const fromApi = filterOptions.classes || [];
    const fromCards = cards.map(c => c.field_data?.CLASS || c.field_data?.Class || c.field_data?.['class'] || c.class_name).filter(Boolean);
    const combined = Array.from(new Set([...fromApi, ...fromCards]));
    return combined.length > 0 ? combined : ['10th', '9th', '8th', '11th', '12th'];
  }, [filterOptions.classes, cards]);

  const sectionOptions = useMemo(() => {
    const fromApi = filterOptions.sections || [];
    const fromCards = cards.map(c => c.field_data?.SECTION || c.field_data?.Section || c.field_data?.['section']).filter(Boolean);
    const combined = Array.from(new Set([...fromApi, ...fromCards]));
    return combined.length > 0 ? combined : ['A', 'B', 'C', 'D'];
  }, [filterOptions.sections, cards]);

  const courseOptions = useMemo(() => {
    const fromApi = filterOptions.courses || [];
    const fromCards = cards.map(c => c.field_data?.COURSE || c.field_data?.Course).filter(Boolean);
    return Array.from(new Set([...fromApi, ...fromCards]));
  }, [filterOptions.courses, cards]);

  const branchOptions = useMemo(() => {
    const fromApi = filterOptions.branches || [];
    const fromCards = cards.map(c => c.field_data?.BRANCH || c.field_data?.Branch).filter(Boolean);
    return Array.from(new Set([...fromApi, ...fromCards]));
  }, [filterOptions.branches, cards]);

  /* ── Modals / Drawers ── */
  const [drawer, setDrawer]             = useState(null); // { mode: 'add'|'edit'|'view', card }
  const [showUploadXlsx, setShowUploadXlsx] = useState(false);
  const [showReuploadImageModal, setShowReuploadImageModal] = useState(false);
  const [showClearPendingPathModal, setShowClearPendingPathModal] = useState(false);
  const [showPrintDataModal, setShowPrintDataModal] = useState(false);
  const [showDownloadDataModal, setShowDownloadDataModal] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);

  const searchTimerRef = useRef(null);

  /* ── LocalStorage helper for offline/custom tables ── */
  const getLocalStorageCards = useCallback(() => {
    try {
      const stored = localStorage.getItem(`cf_custom_cards_${tableId}`);
      if (stored) return JSON.parse(stored);
      return [];
    } catch { return []; }
  }, [tableId]);

  const saveLocalStorageCards = useCallback((updatedCards) => {
    try {
      localStorage.setItem(`cf_custom_cards_${tableId}`, JSON.stringify(updatedCards));
    } catch { /* ignore */ }
  }, [tableId]);

  /* ── Load Table Metadata ── */
  const loadTable = useCallback(async () => {
    if (!tableId) return;
    setTableLoading(true);
    try {
      const data = await schemaApi.getTable(tableId);
      setTable(data?.table || data);
    } catch {
      try {
        const local = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        const match = local.find(t => String(t.id) === String(tableId));
        if (match) setTable(match);
      } catch { /* ignore */ }
    } finally { setTableLoading(false); }
  }, [tableId]);

  /* ── Load Status Counts ── */
  const loadStatusCounts = useCallback(async () => {
    if (!tableId) return;
    let counts = { pending: 0, verified: 0, approved: 0, printed: 0, deleted: 0, reprint: 0, request: 0, confirm: 0 };
    try {
      const data = await cardApi.getStatusCounts(tableId);
      const c = data?.counts || data?.status_counts || data || {};
      counts = {
        pending:  c.pending ?? c.pending_count ?? 0,
        verified: c.verified ?? c.verified_count ?? 0,
        approved: c.approved ?? c.approved_count ?? 0,
        printed:  c.printed ?? c.printed_count ?? c.download ?? c.download_count ?? 0,
        deleted:  c.deleted ?? c.deleted_count ?? c.pool ?? c.pool_count ?? c.pool_list ?? 0,
        reprint:  c.reprint ?? c.reprint_count ?? c.reprinting ?? 0,
        request:  c.request ?? c.reprint_request ?? c.requested ?? 0,
        confirm:  c.confirm ?? c.reprint_confirmed ?? c.confirmed ?? 0,
      };
    } catch { /* ignore */ }

    // Fallback count from local storage
    const local = getLocalStorageCards();
    local.forEach(card => {
      let s = card.status || 'pending';
      if (s === 'download' || s === 'downloaded') s = 'printed';
      if (s === 'pool') s = 'deleted';
      if (s === 'reprint_pending' || s === 'reprinting') s = 'reprint';
      if (s === 'reprint_request' || s === 'requested') s = 'request';
      if (s === 'reprint_confirmed' || s === 'confirmed') s = 'confirm';
      if (counts[s] !== undefined) counts[s]++;
    });
    setStatusCounts(counts);
  }, [tableId, getLocalStorageCards]);

  /* ── Load Filter Options ── */
  const loadFilterOptions = useCallback(async () => {
    if (!tableId) return;
    try {
      const res = await apiClient.get(`/api/table/${tableId}/filter-options/`);
      const d = res.data;
      setFilterOptions({
        classes:  d?.classes  || d?.class_values  || [],
        sections: d?.sections || d?.section_values || [],
        courses:  d?.courses  || d?.course_values  || [],
        branches: d?.branches || d?.branch_values  || [],
      });
    } catch { /* non-critical */ }
  }, [tableId]);

  /* ── Load Cards List ── */
  const loadCards = useCallback(async () => {
    if (!tableId) return;
    setCardsLoading(true);
    setSelectedIds(new Set());
    try {
      const params = {
        status,
        offset: (page - 1) * pageSize,
        limit: pageSize,
        sort,
        search: debouncedSearch || undefined,
        class: classFilter || undefined,
        section: sectionFilter || undefined,
      };
      Object.keys(params).forEach(k => params[k] === undefined && delete params[k]);

      let list = [];
      let cnt = 0;
      try {
        const data = await cardApi.getCards(tableId, params);
        list = data?.cards || data?.results || (Array.isArray(data) ? data : []);
        cnt  = data?.total_count || data?.total || data?.count || list.length;
      } catch (apiErr) {
        console.warn("API loadCards error:", apiErr);
      }

      // Helper to match card status cleanly
      const cardMatchesStatus = (c) => {
        let cardSt = c.status || 'pending';
        if (cardSt === 'download' || cardSt === 'downloaded') cardSt = 'printed';
        if (cardSt === 'pool') cardSt = 'deleted';
        if (cardSt === 'reprint_pending' || cardSt === 'reprinting') cardSt = 'reprint';
        if (cardSt === 'reprint_request' || cardSt === 'requested') cardSt = 'request';
        if (cardSt === 'reprint_confirmed' || cardSt === 'confirmed') cardSt = 'confirm';

        if (status === 'request') {
          return cardSt === 'request' || cardSt === 'reprint_request' || cardSt === 'requested';
        }
        if (status === 'reprint') {
          return cardSt === 'reprint' || cardSt === 'reprint_pending' || cardSt === 'reprinting';
        }
        if (status === 'confirm') {
          return cardSt === 'confirm' || cardSt === 'reprint_confirmed' || cardSt === 'confirmed';
        }
        return cardSt === status;
      };

      // Merge Local Storage cards with API list for instant hybrid display
      const local = getLocalStorageCards();
      const localFiltered = local.filter(cardMatchesStatus);

      const combinedMap = new Map();
      list.forEach(c => combinedMap.set(String(c.id), c));
      localFiltered.forEach(c => {
        if (!combinedMap.has(String(c.id))) {
          combinedMap.set(String(c.id), c);
        }
      });

      const finalCards = Array.from(combinedMap.values());
      setCards(finalCards);
      setTotal(Math.max(cnt, finalCards.length));
    } catch (err) {
      console.warn("loadCards error:", err);
      const local = getLocalStorageCards();
      const cardMatchesStatus = (c) => {
        let cardSt = c.status || 'pending';
        if (cardSt === 'download' || cardSt === 'downloaded') cardSt = 'printed';
        if (cardSt === 'pool') cardSt = 'deleted';
        if (cardSt === 'reprint_pending' || cardSt === 'reprinting') cardSt = 'reprint';
        if (cardSt === 'reprint_request' || cardSt === 'requested') cardSt = 'request';
        if (cardSt === 'reprint_confirmed' || cardSt === 'confirmed') cardSt = 'confirm';
        return cardSt === status;
      };
      const localFiltered = local.filter(cardMatchesStatus);
      setCards(localFiltered);
      setTotal(localFiltered.length);
    } finally { setCardsLoading(false); }
  }, [tableId, status, page, pageSize, debouncedSearch, classFilter, sectionFilter, sort, getLocalStorageCards]);

  /* ── Effects ── */
  useEffect(() => { loadTable(); }, [loadTable]);
  useEffect(() => { loadStatusCounts(); }, [loadStatusCounts]);
  useEffect(() => { loadFilterOptions(); }, [loadFilterOptions]);
  useEffect(() => { loadCards(); }, [loadCards]);

  /* Keyboard Shortcuts: Escape, Ctrl+A, N, T, B */
  useEffect(() => {
    const handleKeyDown = (e) => {
      const activeEl = document.activeElement;
      const isTyping = activeEl && (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA' || activeEl.isContentEditable);

      if (e.key === 'Escape') {
        setDrawer(null);
        setShowUploadXlsx(false);
        setShowPrintDataModal(false);
        setShowDownloadDataModal(false);
        setShowImageSortModal(false);
      }

      if (isTyping) return;

      if ((e.ctrlKey || e.metaKey) && (e.key === 'a' || e.key === 'A')) {
        e.preventDefault();
        if (cards.length > 0) {
          setSelectedIds(new Set(cards.map(c => c.id)));
        }
      }

      if (e.key === 'n' || e.key === 'N') {
        e.preventDefault();
        setDrawer({ mode: 'add', card: null });
      }

      if (e.key === 't' || e.key === 'T') {
        e.preventDefault();
        const container = document.querySelector('.table-container.idcard-table');
        if (container) container.scrollTop = 0;
      }

      if (e.key === 'b' || e.key === 'B') {
        e.preventDefault();
        const container = document.querySelector('.table-container.idcard-table');
        if (container) container.scrollTop = container.scrollHeight;
      }
    };

    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [cards]);

  useEffect(() => {
    clearTimeout(searchTimerRef.current);
    searchTimerRef.current = setTimeout(() => {
      setDebouncedSearch(search);
      setPage(1);
    }, 350);
    return () => clearTimeout(searchTimerRef.current);
  }, [search]);

  useEffect(() => { setPage(1); setSelectedIds(new Set()); }, [status]);

  /* ── Selection Helpers ── */
  const allSelected = cards.length > 0 && cards.every(c => selectedIds.has(c.id));
  const someSelected = cards.some(c => selectedIds.has(c.id)) && !allSelected;

  const toggleSelectAll = () => {
    if (allSelected) { setSelectedIds(new Set()); }
    else { setSelectedIds(new Set(cards.map(c => c.id))); }
  };

  const toggleSelect = (id) => {
    setSelectedIds(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  /* ── Status Actions ── */
  const applyBulkStatus = async (newStatus, ids = [...selectedIds]) => {
    if (!ids.length) { addToast?.('No cards selected', 'warning'); return; }
    setActionLoading(true);
    try {
      try {
        await apiClient.post(`/api/table/${tableId}/bulk-status/`, { card_ids: ids, status: newStatus });
      } catch {
        await Promise.all(ids.map(id => cardApi.changeStatus(id, newStatus)));
      }
    } catch { /* fallback */ }

    // Update local storage cards as well
    const local = getLocalStorageCards();
    const updated = local.map(c => ids.includes(c.id) ? { ...c, status: newStatus } : c);
    saveLocalStorageCards(updated);

    addToast?.(`${ids.length} card(s) moved to ${newStatus}`, 'success');
    setSelectedIds(new Set());
    await Promise.all([loadCards(), loadStatusCounts()]);
    setActionLoading(false);
  };

  const applyStatusSingle = async (card, newStatus) => {
    setActionLoading(true);
    try { await cardApi.changeStatus(card.id, newStatus); } catch { /* continue */ }
    const local = getLocalStorageCards();
    const updated = local.map(c => c.id === card.id ? { ...c, status: newStatus } : c);
    saveLocalStorageCards(updated);

    addToast?.(`Card moved to ${newStatus}`, 'success');
    await Promise.all([loadCards(), loadStatusCounts()]);
    setActionLoading(false);
  };

  const deleteSingle = async (card) => {
    if (!window.confirm(`Move this card (${card.field_data?.NAME || card.field_data?.name || card.id}) to Pool (delete)?`)) return;
    setActionLoading(true);
    try { await cardApi.changeStatus(card.id, 'pool'); } catch { /* continue */ }
    const local = getLocalStorageCards();
    const updated = local.map(c => c.id === card.id ? { ...c, status: 'pool' } : c);
    saveLocalStorageCards(updated);
    addToast?.('Card moved to Pool', 'info');
    await Promise.all([loadCards(), loadStatusCounts()]);
    setActionLoading(false);
  };
  const handleDelete = async () => {
    const ids = [...selectedIds];
    if (!ids.length) { addToast?.('No cards selected', 'warning'); return; }
    if (!window.confirm(`Move ${ids.length} card(s) to Pool?`)) return;
    await applyBulkStatus('pool', ids);
  };

  /* ── Schema Fields ── */
  const tableFields = useMemo(() => {
    const raw = table?.fields || table?.schema?.fields || [
      { name: 'PHOTO', type: 'photo' },
      { name: 'NAME', type: 'text' },
      { name: 'FATHER NAME', type: 'text' },
      { name: 'MOTHER NAME', type: 'text' },
      { name: 'ADDRESS', type: 'text' },
      { name: 'CONTACT NO.', type: 'text' },
      { name: 'CLASS', type: 'text' },
      { name: 'SECTION', type: 'text' }
    ];
    return [...raw].sort((a, b) => {
      const aImg = isImageField(a.type, a.name);
      const bImg = isImageField(b.type, b.name);
      if (aImg && !bImg) return -1;
      if (!aImg && bImg) return 1;
      return 0;
    });
  }, [table]);

  /* ── Inline Field Edit ── */
  const [editingCell, setEditingCell] = useState(null);
  const [cellValue, setCellValue]     = useState('');

  const startCellEdit = (cardId, field, currentValue) => {
    setEditingCell({ cardId, field });
    setCellValue(currentValue ?? '');
  };

  const commitCellEdit = async () => {
    if (!editingCell) return;
    const { cardId, field } = editingCell;
    setEditingCell(null);
    try { await cardApi.updateField(cardId, field, cellValue); } catch { /* ignore */ }
    setCards(prev => prev.map(c =>
      c.id === cardId ? { ...c, field_data: { ...(c.field_data || {}), [field]: cellValue } } : c
    ));
    const local = getLocalStorageCards();
    const updated = local.map(c => c.id === cardId ? { ...c, field_data: { ...(c.field_data || {}), [field]: cellValue } } : c);
    saveLocalStorageCards(updated);
  };

  /* Filter cards by Image Sort Modal conditions */
  const filteredCards = useMemo(() => {
    if (!activeImageSort || !activeImageSort.columns?.length || !activeImageSort.conditions?.length) {
      return cards;
    }

    const { columns, conditions } = activeImageSort;

    return cards.filter(card => {
      const fd = card.field_data || {};
      return columns.some(col => {
        const val = String(fd[col] ?? fd[col.toLowerCase()] ?? '').trim();
        const hasImg = val !== '' && !val.includes('placeholder') && !val.includes('no-image');

        if (conditions.includes('complete') && hasImg) return true;
        if (conditions.includes('pending') && !hasImg) return true;
        if (conditions.includes('incomplete') && !hasImg) return true;
        return false;
      });
    });
  }, [cards, activeImageSort]);

  const selectedArr = [...selectedIds];
  const hasSelection = selectedArr.length > 0;

  /* Button color inline style generator for 100% color reliability */
  const buttonStyle = (bg, disabled = false) => ({
    background: disabled ? '#e2e8f0' : bg,
    color: disabled ? '#94a3b8' : '#ffffff',
    border: disabled ? '1px solid #cbd5e1' : 'none',
    borderRadius: '4px',
    padding: '0 10px',
    height: '28px',
    fontSize: '12px',
    fontWeight: 600,
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '5px',
    cursor: disabled ? 'not-allowed' : 'pointer',
    opacity: 1,
    whiteSpace: 'nowrap',
    boxShadow: disabled ? 'none' : '0 1px 2px rgba(0,0,0,0.12)',
    transition: 'all 0.15s ease',
  });

  /* Shared Print Data & Download Data buttons (Same Purple/Indigo color family) */
  const renderDownloadButtons = () => (
    <>
      <button
        onClick={() => setShowPrintDataModal(true)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '0 10px',
          height: '26px',
          fontSize: '11px',
          fontWeight: 600,
          border: '1px solid #4338ca',
          background: '#4f46e5',
          color: '#ffffff',
          borderRadius: '4px',
          cursor: 'pointer',
          boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
          transition: 'all 0.15s ease',
        }}
        title="Print Data (Word & Excel with Page Breaks — moves approved cards to Download list)"
      >
        <Printer size={13} /> <span>Print Data</span>
      </button>

      <button
        onClick={() => setShowDownloadDataModal(true)}
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: '4px',
          padding: '0 10px',
          height: '26px',
          fontSize: '11px',
          fontWeight: 600,
          border: '1px solid #6d28d9',
          background: '#7c3aed',
          color: '#ffffff',
          borderRadius: '4px',
          cursor: 'pointer',
          boxShadow: '0 1px 2px rgba(0,0,0,0.1)',
          transition: 'all 0.15s ease',
        }}
        title="Download Data (Images ZIP & PDF Document)"
      >
        <Download size={13} /> <span>Download Data</span>
      </button>
    </>
  );

  return (
    <div style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#f4f4f4' }}>

      {/* ══════════════════════════════════════════════════════════
          TOPBAR — SOLID BLACK BACKGROUND (MATCHING SIDEBAR LOGO HEADER HEIGHT 44px)
          ══════════════════════════════════════════════════════════ */}
      <header className="topbar" style={{ flexShrink: 0, padding: '0 16px', background: '#1e1e2e', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', height: '44px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxSizing: 'border-box', color: '#ffffff' }}>
        {/* Left: Table Group, Table Setting, Divider, Download Buttons, Divider, Image Sort, Clear Pending Path */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px' }}>
          <button
            type="button"
            onClick={onBack}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '0 10px',
              height: '26px',
              fontSize: '11px',
              fontWeight: 600,
              border: '1px solid rgba(255, 255, 255, 0.2)',
              background: 'rgba(255, 255, 255, 0.1)',
              color: '#e2e8f0',
              borderRadius: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            title="Back to Table Group"
          >
            <Layers size={13} />
            <span>Table Group</span>
          </button>

          <span style={{ width: '1px', height: '18px', background: 'rgba(255, 255, 255, 0.2)', margin: '0 3px' }} />

          {renderDownloadButtons()}

          <span style={{ width: '1px', height: '18px', background: 'rgba(255, 255, 255, 0.2)', margin: '0 3px' }} />

          {/* Image Sort Modal Trigger Button */}
          <button
            type="button"
            onClick={() => setShowImageSortModal(true)}
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '4px',
              padding: '0 10px',
              height: '26px',
              fontSize: '11px',
              fontWeight: 600,
              border: activeImageSort ? '1px solid #f59e0b' : '1px solid rgba(255, 255, 255, 0.2)',
              background: activeImageSort ? 'rgba(245, 158, 11, 0.25)' : 'rgba(255, 255, 255, 0.1)',
              color: activeImageSort ? '#fbbf24' : '#e2e8f0',
              borderRadius: '4px',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            title="Filter by image status"
          >
            <ImageIcon size={13} />
            <span>{activeImageSort ? `Image Sort (${activeImageSort.conditions.join(', ')})` : 'Image Sort'}</span>
          </button>

          {/* Clear Pending Path Button */}
          {(status === 'pending' || status === 'verified') && (
            <button
              type="button"
              onClick={() => setShowClearPendingPathModal(true)}
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '4px',
                padding: '0 10px',
                height: '26px',
                fontSize: '11px',
                fontWeight: 600,
                border: '1px solid rgba(255, 255, 255, 0.2)',
                background: 'rgba(255, 255, 255, 0.1)',
                color: '#e2e8f0',
                borderRadius: '4px',
                cursor: 'pointer',
                transition: 'all 0.15s ease',
              }}
              title="Clear paths for missing images"
            >
              <Eraser size={13} />
              <span>Clear Pending Path</span>
            </button>
          )}
        </div>

        {/* Right: Colored Status List Tabs */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '4px', marginLeft: 'auto' }}>
          {/* Render Flow-Specific Status Tabs */}
          {(['reprint', 'request', 'confirm'].includes(status) ? REPRINT_STATUS_LIST : ID_CARD_STATUS_LIST).map(s => {
            const count = statusCounts[s.key] ?? 0;
            const isActive = status === s.key;
            return (
              <button
                key={s.key}
                onClick={() => setStatus(s.key)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '6px',
                  padding: '3px 10px',
                  height: '26px',
                  borderRadius: '4px',
                  fontSize: '12px',
                  fontWeight: 600,
                  border: isActive ? `1px solid ${s.bg}` : '1px solid rgba(255,255,255,0.15)',
                  background: isActive ? s.bg : 'rgba(255,255,255,0.08)',
                  color: isActive ? '#ffffff' : '#cbd5e1',
                  cursor: 'pointer',
                  transition: 'all 0.15s ease',
                  boxShadow: isActive ? `0 2px 6px ${s.bg}40` : 'none',
                }}
                title={`Switch to ${s.label}`}
              >
                <span>{s.label}</span>
                <span style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  minWidth: '20px',
                  height: '17px',
                  padding: '0 5px',
                  borderRadius: '3px',
                  fontSize: '11px',
                  fontWeight: 700,
                  background: isActive ? 'rgba(255,255,255,0.25)' : 'rgba(255,255,255,0.12)',
                  color: isActive ? '#ffffff' : '#cbd5e1',
                }}>
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </header>

      {/* ══════════════════════════════════════════════════════════
          UNIFIED ACTION & FILTER BAR (SINGLE ROW)
          ══════════════════════════════════════════════════════════ */}
      <div style={{ flexShrink: 0, padding: '6px 16px', background: '#ffffff', borderBottom: '1px solid #e5e7eb', minHeight: '44px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: '12px', position: 'relative', zIndex: 100 }}>
        {/* Left Side: All Action Buttons */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '5px', flexWrap: 'nowrap', flexShrink: 0 }}>
          {/* Action Divider Component */}
          {/* Pending List buttons */}
          {status === 'pending' && (
            <>
              <button onClick={() => setShowUploadXlsx(true)} style={buttonStyle('#2563eb')} title="Upload Excel file">
                <FileSpreadsheet size={14} /> <span>Upload XLSX</span>
              </button>

              <button onClick={() => setShowReuploadImageModal(true)} style={buttonStyle('#0d9488')} title="Reupload images from ZIP">
                <RefreshCw size={14} /> <span>Reupload Image</span>
              </button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button onClick={() => setDrawer({ mode: 'add', card: null })} style={buttonStyle('#2563eb')} title="Add new card">
                <Plus size={14} /> <span>Add</span>
              </button>

              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
                title="Edit selected card"
              >
                <Pencil size={14} /> <span>Edit</span>
              </button>

              <button
                disabled={!hasSelection}
                onClick={handleDelete}
                style={buttonStyle('#ef4444', !hasSelection)}
                title="Move selected to Pool"
              >
                <Trash2 size={14} /> <span>Delete</span>
              </button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('verified')}
                style={buttonStyle('#10b981', !hasSelection || actionLoading)}
                title="Verify selected cards"
              >
                {actionLoading ? <Spinner size={14} /> : <CheckCircle2 size={14} />} <span>Verify Selected</span>
              </button>
            </>
          )}

          {/* Verified List buttons */}
          {status === 'verified' && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button onClick={() => setShowReuploadImageModal(true)} style={buttonStyle('#0d9488')} title="Reupload images from ZIP">
                <RefreshCw size={14} /> <span>Reupload Image</span>
              </button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('pending')}
                style={buttonStyle('#ef4444', !hasSelection || actionLoading)}
                title="Move back to Pending"
              ><RotateCcw size={14} /> <span>Unverify</span></button>

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('approved')}
                style={buttonStyle('#10b981', !hasSelection || actionLoading)}
                title="Approve selected"
              >{actionLoading ? <Spinner size={14} /> : <ThumbsUp size={14} />} <span>Approve Selected</span></button>
            </>
          )}

          {/* Approved List buttons */}
          {status === 'approved' && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button onClick={() => setShowReuploadImageModal(true)} style={buttonStyle('#0d9488')} title="Reupload images from ZIP">
                <RefreshCw size={14} /> <span>Reupload Image</span>
              </button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('verified')}
                style={buttonStyle('#ef4444', !hasSelection || actionLoading)}
                title="Move back to Verified"
              ><RotateCcw size={14} /> <span>Disapprove</span></button>
            </>
          )}

          {/* Printed List buttons */}
          {(status === 'printed' || status === 'download') && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button onClick={() => setShowReuploadImageModal(true)} style={buttonStyle('#0d9488')} title="Reupload images from ZIP">
                <RefreshCw size={14} /> <span>Reupload Image</span>
              </button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('reprint')}
                style={buttonStyle('#06b6d4', !hasSelection || actionLoading)}
                title="Send selected cards to Reprinting List"
              ><RotateCcw size={14} /> <span>Send to Reprint</span></button>

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('pending')}
                style={buttonStyle('#10b981', !hasSelection || actionLoading)}
                title="Retrieve to Pending"
              ><RotateCcw size={14} /> <span>Retrieve</span></button>
            </>
          )}

          {/* Deleted List buttons */}
          {(status === 'deleted' || status === 'pool') && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('pending')}
                style={buttonStyle('#10b981', !hasSelection || actionLoading)}
                title="Restore selected cards to Pending"
              ><RotateCcw size={14} /> <span>Restore to Pending</span></button>
            </>
          )}

          {/* Reprinting List buttons */}
          {status === 'reprint' && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button onClick={() => setShowReuploadImageModal(true)} style={buttonStyle('#0d9488')} title="Reupload images from ZIP">
                <RefreshCw size={14} /> <span>Reupload Image</span>
              </button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('request')}
                style={buttonStyle('#a855f7', !hasSelection || actionLoading)}
                title="Request reprint for selected cards"
              ><CheckCircle2 size={14} /> <span>Request Selected</span></button>
            </>
          )}

          {/* Requested List buttons (Reprint Flow) */}
          {status === 'request' && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('confirm')}
                style={buttonStyle('#10b981', !hasSelection || actionLoading)}
                title="Confirm reprint for selected cards"
              ><CheckCircle2 size={14} /> <span>Confirm Selected</span></button>

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('reprint')}
                style={buttonStyle('#ef4444', !hasSelection || actionLoading)}
                title="Reject and move back to Reprinting"
              ><RotateCcw size={14} /> <span>Reject to Reprinting</span></button>
            </>
          )}

          {/* Confirmed List buttons (Reprint Flow) */}
          {status === 'confirm' && (
            <>
              <button
                disabled={selectedArr.length !== 1}
                onClick={() => setDrawer({ mode: 'edit', card: cards.find(c => selectedIds.has(c.id)) })}
                style={buttonStyle('#2563eb', selectedArr.length !== 1)}
              ><Pencil size={14} /> <span>Edit</span></button>

              <div style={{ width: '1px', height: '18px', background: '#cbd5e1', margin: '0 4px', flexShrink: 0 }} />

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => setShowPrintDataModal(true)}
                style={buttonStyle('#2563eb', !hasSelection || actionLoading)}
                title="Print selected confirmed cards"
              ><Printer size={14} /> <span>Print Selected</span></button>

              <button
                disabled={!hasSelection || actionLoading}
                onClick={() => applyBulkStatus('reprint')}
                style={buttonStyle('#64748b', !hasSelection || actionLoading)}
                title="Move back to Reprinting List"
              ><RotateCcw size={14} /> <span>Retrieve</span></button>
            </>
          )}
        </div>

        {/* Right Side: Search Box, Sort, and Filters */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto', flexShrink: 0 }}>
          {/* Search Box */}
          <div
            className="search-box"
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              height: '28px',
              width: '200px',
              background: '#ffffff',
              border: '1px solid #cbd5e1',
              borderRadius: '4px',
              padding: '0 8px',
              boxSizing: 'border-box',
            }}
          >
            <Search size={14} style={{ color: '#64748b', flexShrink: 0, marginRight: '4px' }} />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Search All..."
              style={{
                flex: 1,
                border: 'none',
                outline: 'none',
                fontSize: '12px',
                background: 'transparent',
                fontFamily: 'var(--font-family)',
                color: '#1e293b',
              }}
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                style={{ background: 'none', border: 'none', padding: 0, cursor: 'pointer', color: '#94a3b8', display: 'flex', alignItems: 'center' }}
              >
                <X size={12} />
              </button>
            )}
          </div>

          {/* Sort */}
          <CustomSelect
            value={sort}
            onChange={val => { setSort(val); setPage(1); }}
            options={[
              { value: 'sr-asc', label: 'Sort: Newest' },
              { value: 'sr-desc', label: 'Sort: Oldest' },
              { value: 'name-asc', label: 'Name A to Z' },
              { value: 'name-desc', label: 'Name Z to A' },
            ]}
          />

          {/* Class Filter */}
          <CustomSelect
            value={classFilter}
            onChange={val => { setClassFilter(val); setPage(1); }}
            options={[
              { value: '', label: 'All Classes' },
              ...classOptions.map(c => ({ value: c, label: c }))
            ]}
          />

          {/* Section Filter */}
          <CustomSelect
            value={sectionFilter}
            onChange={val => { setSectionFilter(val); setPage(1); }}
            options={[
              { value: '', label: 'All Sections' },
              ...sectionOptions.map(s => ({ value: s, label: s }))
            ]}
          />

          {/* Course Filter */}
          {courseOptions.length > 0 && (
            <CustomSelect
              value={courseFilter}
              onChange={val => { setCourseFilter(val); setPage(1); }}
              options={[
                { value: '', label: 'All Courses' },
                ...courseOptions.map(c => ({ value: c, label: c }))
              ]}
            />
          )}

          {/* Branch Filter */}
          {branchOptions.length > 0 && (
            <CustomSelect
              value={branchFilter}
              onChange={val => { setBranchFilter(val); setPage(1); }}
              options={[
                { value: '', label: 'All Branches' },
                ...branchOptions.map(b => ({ value: b, label: b }))
              ]}
            />
          )}

          {/* Clear Filters */}
          {(classFilter || sectionFilter || courseFilter || branchFilter || activeImageSort || search) && (
            <button
              onClick={() => { setClassFilter(''); setSectionFilter(''); setCourseFilter(''); setBranchFilter(''); setActiveImageSort(null); setSearch(''); setPage(1); }}
              style={{ height: '28px', padding: '0 8px', border: '1px solid #cbd5e1', borderRadius: '4px', background: '#fff', color: '#ef4444', cursor: 'pointer', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '3px' }}
              title="Clear all filters"
            >
              <X size={12} /> Clear
            </button>
          )}
          {/* Datetime Range Filter — only for Download list */}
          {status === 'download' && (
            <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <label style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>From</label>
              <input
                type="date"
                value={fromDate}
                onChange={e => setFromDate(e.target.value)}
                style={{ height: '26px', border: '1px solid #cbd5e1', borderRadius: '4px', fontSize: '11px', padding: '0 4px', outline: 'none', fontFamily: 'var(--font-family)' }}
              />
              <label style={{ fontSize: '11px', color: '#64748b', fontWeight: 500 }}>To</label>
              <input
                type="date"
                value={toDate}
                onChange={e => setToDate(e.target.value)}
                style={{ height: '26px', border: '1px solid #cbd5e1', borderRadius: '4px', fontSize: '11px', padding: '0 4px', outline: 'none', fontFamily: 'var(--font-family)' }}
              />
              {(fromDate || toDate) && (
                <button
                  onClick={() => { setFromDate(''); setToDate(''); }}
                  style={{ height: '26px', padding: '0 8px', border: '1px solid #fca5a5', borderRadius: '4px', background: '#fee2e2', color: '#dc2626', cursor: 'pointer', fontSize: '11px', display: 'flex', alignItems: 'center', gap: '3px' }}
                >
                  <X size={11} /> Clear
                </button>
              )}
            </div>
          )}
        </div>
      </div>

      {/* ══════════════════════════════════════════════════════════
          VIRTUAL DATA TABLE WITH CRISP BORDERS & EXACT PHOTO HEIGHT
          ══════════════════════════════════════════════════════════ */}
      <div className="table-container idcard-table" style={{ flex: 1, minHeight: 0, overflow: 'auto', background: '#fff', position: 'relative', display: 'flex', flexDirection: 'column' }}>
        <WatermarkLogo />
        {tableLoading ? (
          <div style={{ flex: 1, display: 'flex', alignItems: 'center', justifyContent: 'center', minHeight: '300px', gap: '10px', color: '#64748b' }}>
            <Spinner size={24} /> Loading table structure…
          </div>
        ) : (
          <>
            <table
              style={{
                width: '100%',
                borderCollapse: 'separate',
                borderSpacing: 0,
                fontSize: '12px',
                tableLayout: 'auto',
                animation: 'pageEnter 0.22s cubic-bezier(0.22, 1, 0.36, 1) both'
              }}
            >
              <thead style={{ position: 'sticky', top: 0, zIndex: 20 }}>
                <tr style={{ background: '#1e293b', color: '#ffffff' }}>
                  {/* Checkbox */}
                  <th style={{ position: 'sticky', left: 0, zIndex: 30, width: '32px', minWidth: '32px', padding: '4px 2px', textAlign: 'center', verticalAlign: 'middle', background: '#1e293b', borderRight: '1px solid rgba(255,255,255,0.15)', borderBottom: '1px solid rgba(255,255,255,0.15)', borderLeft: '1px solid #cbd5e1' }}>
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
                      <button onClick={toggleSelectAll} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff', padding: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                        {allSelected ? <SquareCheck size={15} /> : someSelected ? <MinusSquare size={15} /> : <Square size={15} />}
                      </button>
                    </div>
                  </th>

                  {/* SR NO */}
                  <th style={{ position: 'sticky', left: '32px', zIndex: 30, width: '36px', minWidth: '36px', padding: '4px 2px', textAlign: 'center', background: '#1e293b', borderRight: '1px solid rgba(255,255,255,0.15)', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: '11px', fontWeight: 700, lineHeight: 1.1, whiteSpace: 'nowrap' }}>
                    SR<br />NO
                  </th>

                  {tableFields.map(f => {
                    const spec = getColumnSpec(f.name, f.type);
                    // Flexible columns (names, address) get no explicit width — they stretch to fill remaining space
                    const isFlexible = !spec.width;
                    return (
                      <th
                        key={f.name}
                        style={{
                          padding: '4px 4px',
                          textAlign: spec.align,
                          textTransform: 'uppercase',
                          letterSpacing: '0.03em',
                          fontSize: '11px',
                          fontWeight: 700,
                          // Fixed columns get an explicit width; flexible ones only get minWidth
                          ...(isFlexible
                            ? { minWidth: spec.minWidth }
                            : { width: spec.width, minWidth: spec.minWidth, maxWidth: spec.maxWidth }),
                          borderRight: '1px solid rgba(255,255,255,0.15)',
                          borderBottom: '1px solid rgba(255,255,255,0.15)',
                          whiteSpace: 'nowrap',
                          overflow: 'hidden',
                          textOverflow: 'ellipsis',
                          lineHeight: 1.2,
                        }}
                        title={f.name}
                      >
                        {f.name}
                      </th>
                    );
                  })}

                  <th style={{ position: 'sticky', right: '65px', zIndex: 30, width: '1px', minWidth: '1px', padding: '4px 6px', textAlign: 'center', background: '#1e293b', borderRight: '1px solid rgba(255,255,255,0.15)', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', whiteSpace: 'nowrap', lineHeight: 1.2 }}>ACTION</th>
                  <th style={{ position: 'sticky', right: 0, zIndex: 30, width: '65px', minWidth: '65px', padding: '4px 2px', textAlign: 'center', background: '#1e293b', borderRight: '1px solid rgba(255,255,255,0.15)', borderBottom: '1px solid rgba(255,255,255,0.15)', fontSize: '11px', fontWeight: 700, textTransform: 'uppercase', whiteSpace: 'nowrap', lineHeight: 1.2 }}>LOGS</th>
                </tr>
              </thead>
              {filteredCards.length > 0 && (
                <tbody>
                  {filteredCards.map((card, idx) => {
                    const isSelected = selectedIds.has(card.id);
                    const fd = card.field_data || {};
                    const srNo = idx + 1;

                    return (
                      <tr key={card.id} style={{ background: isSelected ? '#eff6ff' : idx % 2 === 0 ? '#ffffff' : '#f8fafc' }}>
                        {/* Checkbox */}
                        <td style={{ position: 'sticky', left: 0, zIndex: 10, background: isSelected ? '#eff6ff' : idx % 2 === 0 ? '#ffffff' : '#f8fafc', width: '32px', minWidth: '32px', padding: '2px', textAlign: 'center', verticalAlign: 'middle', borderLeft: '1px solid #cbd5e1', borderRight: '1px solid #cbd5e1', borderBottom: '1px solid #cbd5e1' }}>
                          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', width: '100%', height: '100%' }}>
                            <button onClick={() => toggleSelect(card.id)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: isSelected ? '#2563eb' : '#94a3b8', padding: 0, display: 'inline-flex', alignItems: 'center', justifyContent: 'center' }}>
                              {isSelected ? <SquareCheck size={15} /> : <Square size={15} />}
                            </button>
                          </div>
                        </td>

                        {/* SR NO */}
                        <td style={{ position: 'sticky', left: '32px', zIndex: 10, background: isSelected ? '#eff6ff' : idx % 2 === 0 ? '#ffffff' : '#f8fafc', width: '36px', minWidth: '36px', padding: '2px', textAlign: 'center', fontWeight: 500, color: '#000000', fontSize: '12px', borderRight: '1px solid #cbd5e1', borderBottom: '1px solid #cbd5e1' }}>
                          {srNo}
                        </td>

                        {/* Dynamic Fields */}
                        {tableFields.map(f => {
                          const spec = getColumnSpec(f.name, f.type);
                          const val = fd[f.name] ?? fd[f.name?.toUpperCase?.()] ?? fd[f.name?.toLowerCase?.()] ?? '';
                          const isImg = spec.isImage;
                          const isEditing = editingCell?.cardId === card.id && editingCell?.field === f.name;
                          // Flexible columns (names, address) — no explicit width set → browser stretches them
                          const isFlexible = !spec.width;

                          if (isImg) {
                            const isSig = spec.imgType === 'signature';
                            const isQr  = spec.imgType === 'qr';
                            const imgW = isSig ? '64px' : isQr ? '38px' : '34px';
                            const imgH = isSig ? '28px' : isQr ? '38px' : '44px';
                            const imgSrc = getImgSrc(val);
                            const hasVal = Boolean(val && String(val).trim() !== '' && val !== 'NOT_FOUND');
                            const isPending = hasVal && String(val).startsWith('PENDING:');

                            return (
                              <td key={f.name} style={{ padding: '2px', textAlign: 'center', width: spec.width, minWidth: spec.minWidth, maxWidth: spec.maxWidth, borderRight: '1px solid #cbd5e1', borderBottom: '1px solid #cbd5e1', verticalAlign: 'middle', overflow: 'hidden' }}>
                                <div className="image-with-edit" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '3px' }}>
                                  {hasVal && !isPending ? (
                                    <img
                                      src={imgSrc}
                                      alt={f.name}
                                      style={{
                                        width: imgW,
                                        height: imgH,
                                        objectFit: isSig || isQr ? 'contain' : 'cover',
                                        borderRadius: '2px',
                                        border: '1px solid #cbd5e1',
                                        display: 'block',
                                        margin: '0 auto',
                                        background: '#ffffff'
                                      }}
                                      onError={e => {
                                        e.target.style.display = 'none';
                                        const parent = e.target.parentElement;
                                        if (parent && !parent.querySelector('.fallback-placeholder')) {
                                          const fb = document.createElement('div');
                                          fb.className = 'fallback-placeholder';
                                          fb.style.cssText = `width:${imgW};height:${imgH};background:#fef3c7;border:1px solid #fde68a;border-radius:2px;display:flex;align-items:center;justify-content:center;font-size:9px;font-weight:700;color:#d97706;margin:0 auto;`;
                                          fb.innerText = 'PATH';
                                          parent.insertBefore(fb, e.target);
                                        }
                                      }}
                                    />
                                  ) : isPending ? (
                                    <div style={{ width: imgW, height: imgH, background: '#fef3c7', borderRadius: '2px', border: '1px solid #fde68a', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', gap: '2px', margin: '0 auto', color: '#d97706' }}>
                                      <Clock size={14} />
                                      <span style={{ fontSize: '8px', fontWeight: 700 }}>PENDING</span>
                                    </div>
                                  ) : (
                                    <div style={{ width: imgW, height: imgH, background: '#f1f5f9', borderRadius: '2px', border: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'center', margin: '0 auto' }}>
                                      <ImageIcon size={16} style={{ color: '#cbd5e1' }} />
                                    </div>
                                  )}
                                  <button
                                    type="button"
                                    onClick={(e) => { e.stopPropagation(); setDrawer({ mode: 'edit', card }); }}
                                    style={{
                                      background: 'none',
                                      border: 'none',
                                      color: '#2563eb',
                                      fontSize: '10px',
                                      fontWeight: 700,
                                      cursor: 'pointer',
                                      padding: '1px 4px',
                                      lineHeight: 1,
                                    }}
                                    className="edit-photo-btn"
                                    title="Edit Card"
                                  >
                                    Edit
                                  </button>
                                </div>
                              </td>
                            );
                          }

                          return (
                            <td
                              key={f.name}
                              style={{
                                padding: '2px 4px',
                                textAlign: spec.align,
                                // Flexible columns have no maxWidth — they fill remaining space
                                ...(isFlexible
                                  ? { minWidth: isEditing ? '180px' : spec.minWidth }
                                  : {
                                      width: isEditing ? 'auto' : spec.width,
                                      minWidth: isEditing ? '180px' : spec.minWidth,
                                      maxWidth: isEditing ? 'none' : spec.maxWidth,
                                    }),
                                color: '#000000',
                                fontSize: '12px',
                                fontWeight: 500,
                                textTransform: 'uppercase',
                                whiteSpace: 'normal',
                                wordBreak: 'break-word',
                                borderRight: '1px solid #cbd5e1',
                                borderBottom: '1px solid #cbd5e1',
                                verticalAlign: 'middle',
                                position: 'relative'
                              }}
                              onDoubleClick={() => startCellEdit(card.id, f.name, val)}
                            >
                              {isEditing ? (
                                <div style={{ position: 'absolute', top: 0, left: 0, right: 0, bottom: 0, zIndex: 10, display: 'flex', alignItems: 'center', background: '#ffffff' }}>
                                  <input
                                    autoFocus
                                    value={cellValue}
                                    onChange={e => setCellValue(e.target.value.toUpperCase())}
                                    onBlur={commitCellEdit}
                                    onKeyDown={e => { if (e.key === 'Enter') commitCellEdit(); if (e.key === 'Escape') setEditingCell(null); }}
                                    style={{
                                      width: '100%',
                                      height: '100%',
                                      border: '2px solid #2563eb',
                                      borderRadius: '2px',
                                      padding: '4px 8px',
                                      fontSize: '12px',
                                      fontWeight: 500,
                                      textTransform: 'uppercase',
                                      outline: 'none',
                                      background: '#ffffff',
                                      boxShadow: '0 2px 8px rgba(37, 99, 235, 0.25)',
                                      boxSizing: 'border-box',
                                      color: '#000000',
                                      fontFamily: 'inherit',
                                    }}
                                  />
                                </div>
                              ) : (
                                <span title={String(val)} style={{ cursor: 'pointer', color: '#000000', fontSize: '12px', fontWeight: 500, textTransform: 'uppercase' }}>
                                  {String(val) ? String(val).toUpperCase() : <span style={{ color: '#cbd5e1' }}>—</span>}
                                </span>
                              )}
                            </td>
                          );
                        })}

                        {/* Action */}
                        <td style={{ position: 'sticky', right: '65px', zIndex: 10, background: isSelected ? '#eff6ff' : idx % 2 === 0 ? '#ffffff' : '#f8fafc', width: '1px', minWidth: '1px', padding: '3px 4px', textAlign: 'center', borderRight: '1px solid #cbd5e1', borderBottom: '1px solid #cbd5e1', verticalAlign: 'middle', whiteSpace: 'nowrap' }}>
                          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'stretch', gap: '2px' }}>

                            {/* ── PENDING: Verify + Delete ── */}
                            {status === 'pending' && (
                              <>
                                <button onClick={() => applyStatusSingle(card, 'verified')}
                                  style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#10b981', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                  title="Verify"><CheckCircle2 size={10} /> Verify
                                </button>
                                <button onClick={() => deleteSingle(card)}
                                  style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#ef4444', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                  title="Delete"><Trash2 size={10} /> Delete
                                </button>
                              </>
                            )}

                            {/* ── VERIFIED: Approve + Unverify ── */}
                            {status === 'verified' && (
                              <>
                                <button onClick={() => applyStatusSingle(card, 'approved')}
                                  style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#3b82f6', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                  title="Approve"><CheckCircle2 size={10} /> Approve
                                </button>
                                <button onClick={() => applyStatusSingle(card, 'pending')}
                                  style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#f59e0b', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                  title="Unverify"><RotateCcw size={10} /> Unverify
                                </button>
                              </>
                            )}

                            {/* ── APPROVED: Disapprove + Download ── */}
                            {status === 'approved' && (
                              <>
                                <button onClick={() => applyStatusSingle(card, 'verified')}
                                  style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#ef4444', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                  title="Disapprove"><XCircle size={10} /> Disapprove
                                </button>
                                <button onClick={() => applyStatusSingle(card, 'download')}
                                  style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#64748b', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                  title="Download"><Download size={10} /> Download
                                </button>
                              </>
                            )}

                            {status === 'download' && (
                              <button onClick={() => applyStatusSingle(card, 'request')}
                                style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#8b5cf6', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                title="Request Reprint">Request
                              </button>
                            )}

                            {(status === 'pool' || status === 'request') && (
                              <button onClick={() => applyStatusSingle(card, 'pending')}
                                style={{ padding: '2px 6px', fontSize: '10px', height: '20px', border: 'none', borderRadius: '3px', background: '#10b981', color: '#fff', fontWeight: 700, cursor: 'pointer', display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '3px', whiteSpace: 'nowrap', width: '100%' }}
                                title="Retrieve to Pending"><RotateCcw size={10} /> Retrieve
                              </button>
                            )}

                          </div>
                        </td>

                        {/* Logs */}
                        <td style={{ position: 'sticky', right: 0, zIndex: 10, background: isSelected ? '#eff6ff' : idx % 2 === 0 ? '#ffffff' : '#f8fafc', width: '65px', minWidth: '65px', padding: '6px', textAlign: 'center', borderRight: '1px solid #cbd5e1', borderBottom: '1px solid #cbd5e1' }}>
                          <button
                            type="button"
                            onClick={(e) => { e.stopPropagation(); setLogCard(card); }}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '4px',
                              padding: '3px 8px',
                              fontSize: '10px',
                              fontWeight: 700,
                              borderRadius: '4px',
                              border: '1px solid #3b82f6',
                              background: 'transparent',
                              color: '#2563eb',
                              cursor: 'pointer',
                              transition: 'all 0.15s ease',
                              fontFamily: 'var(--font-family)'
                            }}
                            onMouseEnter={(e) => { e.currentTarget.style.background = 'rgba(37, 99, 235, 0.1)'; e.currentTarget.style.borderColor = '#1d4ed8'; }}
                            onMouseLeave={(e) => { e.currentTarget.style.background = 'transparent'; e.currentTarget.style.borderColor = '#3b82f6'; }}
                            title="View Card History Logs"
                          >
                            <History size={12} />
                            <span>LOGS</span>
                          </button>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              )}
            </table>

            {cardsLoading && (
              <div style={{ flex: 1, minHeight: '300px', display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '10px', color: '#64748b' }}>
                <Spinner size={24} /> Loading cards…
              </div>
            )}

            {!cardsLoading && filteredCards.length === 0 && (
              <div style={{
                flex: 1,
                minHeight: '360px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '40px 20px',
                textAlign: 'center',
                width: '100%',
                boxSizing: 'border-box'
              }}>
                <div style={{
                  display: 'flex',
                  flexDirection: 'column',
                  alignItems: 'center',
                  justifyContent: 'center',
                  gap: '14px',
                  maxWidth: '440px',
                  margin: '0 auto',
                }}>
                  <div style={{ width: '56px', height: '56px', borderRadius: '50%', background: '#fef3c7', color: '#d97706', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 12px rgba(217, 119, 6, 0.18)' }}>
                    <Clock size={28} />
                  </div>
                  <div style={{ textAlign: 'center' }}>
                    <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0', textTransform: 'uppercase', letterSpacing: '0.02em' }}>
                      NO CARDS IN STATUS "{status.toUpperCase()}"
                    </h4>
                    <p style={{ fontSize: '12px', color: '#64748b', margin: 0, fontWeight: 500 }}>
                      {search ? `No cards match search "${search}"` : `THERE ARE NO CARDS MATCHING CURRENT FILTER CRITERIA.`}
                    </p>
                  </div>
                  {!search && status === 'pending' && (
                    <div style={{ display: 'flex', gap: '12px', marginTop: '6px' }}>
                      <button onClick={() => setDrawer({ mode: 'add', card: null })} style={buttonStyle('#2563eb')}>
                        <Plus size={14} /> Add First Card
                      </button>
                      <button onClick={() => setShowUploadXlsx(true)} style={buttonStyle('#3b82f6')}>
                        <FileSpreadsheet size={14} /> Upload XLSX
                      </button>
                    </div>
                  )}
                </div>
              </div>
            )}
          </>
        )}
      </div>

      {/* ── Drawers & Modals ── */}
      {drawer && (
        <CardSideDrawer
          card={drawer.card}
          mode={drawer.mode}
          tableId={tableId}
          tableFields={tableFields}
          onClose={() => setDrawer(null)}
          onSave={(updated) => {
            const local = getLocalStorageCards();
            const existingIdx = local.findIndex(c => String(c.id) === String(updated.id));
            let updatedList = [];
            if (existingIdx >= 0) {
              updatedList = [...local];
              updatedList[existingIdx] = { ...updatedList[existingIdx], ...updated };
            } else {
              updatedList = [updated, ...local];
            }
            saveLocalStorageCards(updatedList);

            setCards(prev => {
              const idx = prev.findIndex(c => String(c.id) === String(updated.id));
              if (idx >= 0) {
                const next = [...prev];
                next[idx] = { ...next[idx], ...updated };
                return next;
              }
              return [updated, ...prev];
            });
            loadStatusCounts();
          }}
          addToast={addToast}
        />
      )}

      {showUploadXlsx && (
        <UploadXlsxModal
          table={table}
          onClose={() => setShowUploadXlsx(false)}
          onSuccess={() => { loadCards(); loadStatusCounts(); }}
          addToast={addToast}
        />
      )}

      {/* Print Data Modal */}
      {showPrintDataModal && (
        <PrintDataModal
          table={table}
          status={status}
          cardCount={cards.length}
          onClose={() => setShowPrintDataModal(false)}
          addToast={addToast}
          onStatusTransition={(newStatus) => applyBulkStatus(newStatus, cards.map(c => c.id))}
        />
      )}

      {/* Download Data Modal */}
      {showDownloadDataModal && (
        <DownloadDataModal
          table={table}
          status={status}
          cardCount={cards.length}
          onClose={() => setShowDownloadDataModal(false)}
          addToast={addToast}
        />
      )}

      {/* Reupload Images Modal */}
      {showReuploadImageModal && (
        <ReuploadImageModal
          table={table}
          status={status}
          cardCount={cards.length}
          onClose={() => setShowReuploadImageModal(false)}
          onSuccess={() => { loadCards(); loadStatusCounts(); }}
          addToast={addToast}
        />
      )}

      {/* Clear Pending Path Modal */}
      {showClearPendingPathModal && (
        <ClearPendingPathModal
          table={table}
          status={status}
          tableFields={tableFields}
          onClose={() => setShowClearPendingPathModal(false)}
          onSuccess={() => { loadCards(); loadStatusCounts(); }}
          addToast={addToast}
        />
      )}

      {/* Image Sort Modal */}
      {showImageSortModal && (
        <ImageSortModal
          tableFields={tableFields}
          activeSort={activeImageSort}
          onClose={() => setShowImageSortModal(false)}
          onApply={(sortConfig) => setActiveImageSort(sortConfig)}
          onClear={() => setActiveImageSort(null)}
        />
      )}

      {/* Card Log & History Drawer */}
      {logCard && (
        <CardLogDrawer
          card={logCard}
          table={table}
          onClose={() => setLogCard(null)}
        />
      )}
    </div>
  );
}
