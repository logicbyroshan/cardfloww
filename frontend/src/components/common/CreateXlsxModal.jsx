/**
 * CreateXlsxModal.jsx -> Create Table with Data
 *
 * 3-Step Wizard Modal for creating a new table from XLSX, XLS, CSV, or DOCX files.
 * Features:
 * - Supports .xlsx, .xls, .csv, and .docx Word documents containing tables.
 * - Automatic detection of embedded cell photos inside Excel & Word files.
 * - Schema preview & customizable column types.
 * - Optional ZIP photo attachments.
 */

import React, { useState, useRef } from 'react';
import * as XLSX from 'xlsx';
import {
  FileSpreadsheet,
  FileText,
  X,
  Upload,
  ArrowRight,
  ArrowLeft,
  FolderArchive,
  TableProperties,
  CheckCircle2,
  Loader2,
  Sparkles,
  Camera,
  Image as ImageIcon,
} from 'lucide-react';
import { apiClient } from '../../services/api';
import CustomSelect from './CustomSelect';
import Button from './Button';

export default function CreateXlsxModal({ groupId = 1, onClose, onSuccess, addToast }) {
  const [step, setStep] = useState(1); // 1 | 2 | 3
  const [file, setFile] = useState(null);
  const [tableName, setTableName] = useState('');
  const [zipFiles, setZipFiles] = useState([]);
  const [fields, setFields] = useState([]); // [{ name: 'NAME', type: 'text', mandatory: false }]
  const [dataRowCount, setDataRowCount] = useState(0);
  const [embeddedPhotosCount, setEmbeddedPhotosCount] = useState(0);
  const [isProcessing, setIsProcessing] = useState(false);
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [progress, setProgress] = useState(0);

  const fileInputRef = useRef(null);
  const zipInputRef = useRef(null);

  // Handle file selection in Step 1
  const handleFileSelect = async (selectedFile) => {
    if (!selectedFile) return;
    setFile(selectedFile);
    setIsAnalyzing(true);

    // Auto derive table name if empty
    if (!tableName) {
      const derived = selectedFile.name
        .replace(/\.[^/.]+$/, '')
        .replace(/[_.-]/g, ' ')
        .toUpperCase();
      setTableName(derived);
    }

    try {
      // 1. Try server-side preview first for rich docx/xlsx embedded photo detection
      const fd = new FormData();
      fd.append('file', selectedFile);
      const res = await apiClient.post('/api/imports/preview/', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      if (res.data && res.data.success) {
        const pData = res.data;
        setDataRowCount(pData.total_rows || 0);
        setEmbeddedPhotosCount(pData.total_embedded_images || 0);

        if (pData.detected_schema && pData.detected_schema.length > 0) {
          setFields(pData.detected_schema.map(f => ({
            name: f.name,
            type: f.type || 'text',
            mandatory: false,
          })));
          setIsAnalyzing(false);
          return;
        }
      }
    } catch (apiErr) {
      console.warn('Server-side preview fallback to client-side parsing:', apiErr);
    }

    // 2. Client-side fallback for Excel / CSV
    try {
      const reader = new FileReader();
      reader.onload = (e) => {
        const buf = e.target.result;
        let headers = [];
        let rowsCount = 0;

        try {
          const wb = XLSX.read(buf, { type: 'array' });
          const firstSheetName = wb.SheetNames[0];
          if (firstSheetName) {
            const ws = wb.Sheets[firstSheetName];
            const jsonRows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
            if (jsonRows.length > 0) {
              headers = (jsonRows[0] || []).map((h) => String(h || '').trim()).filter(Boolean);
              rowsCount = jsonRows.slice(1).filter((r) => Array.isArray(r) && r.some((c) => String(c || '').trim() !== '')).length;
            }
          }
        } catch {
          if (selectedFile.name.toLowerCase().endsWith('.csv')) {
            const text = new TextDecoder('utf-8').decode(buf);
            const lines = text.split(/\r?\n/).filter((l) => l.trim());
            if (lines.length > 0) {
              headers = lines[0]
                .split(/[,;\t]/)
                .map((h) => h.replace(/^["']|["']$/g, '').trim())
                .filter(Boolean);
              rowsCount = Math.max(0, lines.length - 1);
            }
          }
        }

        if (headers.length > 0) {
          const parsedFields = headers.map((name) => {
            const lower = name.toLowerCase();
            let type = 'text';
            if (lower.includes('father') && (lower.includes('photo') || lower.includes('pic'))) {
              type = 'father_photo';
            } else if (lower.includes('mother') && (lower.includes('photo') || lower.includes('pic'))) {
              type = 'mother_photo';
            } else if (lower.includes('photo') || lower.includes('pic') || lower.includes('image')) {
              type = 'photo';
            } else if (lower.includes('sign')) {
              type = 'sign';
            } else if (lower.includes('dob') || lower.includes('birth') || lower.includes('date')) {
              type = 'date';
            } else if (lower.includes('roll') || lower.includes('mobile') || lower.includes('phone') || lower.includes('adm')) {
              type = 'number';
            }
            return { name: name.toUpperCase(), type, mandatory: false };
          });
          setFields(parsedFields);
          setDataRowCount(rowsCount);
        }
        setIsAnalyzing(false);
      };
      reader.readAsArrayBuffer(selectedFile);
    } catch {
      setIsAnalyzing(false);
    }
  };

  const handleFieldTypeChange = (idx, newType) => {
    setFields((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], type: newType };
      return copy;
    });
  };

  const handleFieldNameChange = (idx, newName) => {
    setFields((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], name: newName.toUpperCase() };
      return copy;
    });
  };

  const handleMandatoryToggle = (idx) => {
    setFields((prev) => {
      const copy = [...prev];
      copy[idx] = { ...copy[idx], mandatory: !copy[idx].mandatory };
      return copy;
    });
  };

  const handleSubmit = async () => {
    if (!file) return;
    setIsProcessing(true);
    setProgress(25);

    try {
      const fd = new FormData();
      fd.append('file', file);
      if (tableName) fd.append('table_name', tableName);
      if (fields.length > 0) fd.append('fields', JSON.stringify(fields));

      if (zipFiles && zipFiles.length > 0) {
        for (let i = 0; i < zipFiles.length; i++) {
          fd.append('zip_files', zipFiles[i]);
        }
      }

      setProgress(60);

      const res = await apiClient.post(`/api/group/${groupId}/table/create-with-data/`, fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });

      setProgress(100);
      const msg = res.data?.message || `Table "${tableName || file.name}" created successfully!`;
      addToast?.(msg, 'success');
      onSuccess?.();
      onClose();
    } catch (err) {
      console.error('Table creation with data failed:', err);
      const msg = err?.response?.data?.message || err?.message || 'Failed to create table with data.';
      addToast?.(msg, 'error');
    } finally {
      setIsProcessing(false);
    }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel modal-lg" style={{ width: 'var(--modal-width-lg, 640px)', height: 'auto', maxHeight: '90vh' }}>
        {/* Header */}
        <div
          style={{
            background: '#1e293b',
            color: '#fff',
            height: '48px',
            minHeight: '48px',
            padding: '0 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TableProperties size={18} />
            <h3 style={{ fontSize: '14px', fontWeight: 700, margin: 0 }}>Create Table with Data</h3>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#fff' }}>
            <X size={18} />
          </button>
        </div>

        {/* 3-Step Indicator */}
        <div style={{ padding: '14px 24px 0', background: '#ffffff', borderBottom: '1px solid #e2e8f0' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', paddingBottom: '12px' }}>
            <div
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                background: step >= 1 ? '#10b981' : '#e2e8f0',
                color: '#fff',
                fontSize: '11px',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              1
            </div>
            <span style={{ fontSize: '12px', fontWeight: step === 1 ? 700 : 500, color: step === 1 ? '#0f172a' : '#64748b' }}>
              File & Name
            </span>
            <div style={{ flex: 1, height: '2px', background: step >= 2 ? '#10b981' : '#e2e8f0' }} />
            <div
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                background: step >= 2 ? '#10b981' : '#e2e8f0',
                color: '#fff',
                fontSize: '11px',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              2
            </div>
            <span style={{ fontSize: '12px', fontWeight: step === 2 ? 700 : 500, color: step === 2 ? '#0f172a' : '#64748b' }}>
              Schema & Types
            </span>
            <div style={{ flex: 1, height: '2px', background: step >= 3 ? '#10b981' : '#e2e8f0' }} />
            <div
              style={{
                width: '24px',
                height: '24px',
                borderRadius: '50%',
                background: step >= 3 ? '#10b981' : '#e2e8f0',
                color: '#fff',
                fontSize: '11px',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
              }}
            >
              3
            </div>
            <span style={{ fontSize: '12px', fontWeight: step === 3 ? 700 : 500, color: step === 3 ? '#0f172a' : '#64748b' }}>
              Photos & Import
            </span>
          </div>
        </div>

        {/* Body Area */}
        <div style={{ flex: 1, padding: '20px 24px', display: 'flex', flexDirection: 'column', gap: '16px', overflowY: 'auto' }}>
          {/* ── STEP 1: File & Name ── */}
          {step === 1 && (
            <>
              {!file ? (
                <div
                  onClick={() => fileInputRef.current?.click()}
                  style={{
                    border: '2px dashed #10b981',
                    borderRadius: '8px',
                    padding: '32px 16px',
                    textAlign: 'center',
                    cursor: 'pointer',
                    background: '#f0fdf4',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <FileSpreadsheet size={40} style={{ color: '#10b981', margin: '0 auto 10px' }} />
                  <div style={{ fontSize: '13.5px', fontWeight: 700, color: '#065f46' }}>
                    Select Excel (.xlsx, .xls, .csv) or Word (.docx) File
                  </div>
                  <div style={{ fontSize: '11.5px', color: '#047857', marginTop: '6px' }}>
                    Auto-detects data columns and extracts photos embedded directly inside worksheet or Word document tables
                  </div>
                  <input
                    ref={fileInputRef}
                    type="file"
                    accept=".xlsx,.xls,.csv,.docx"
                    style={{ display: 'none' }}
                    onChange={(e) => handleFileSelect(e.target.files[0])}
                  />
                </div>
              ) : (
                <div
                  style={{
                    background: '#ecfdf5',
                    padding: '12px 16px',
                    borderRadius: '6px',
                    border: '1px solid #a7f3d0',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'space-between',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                    {file.name.toLowerCase().endsWith('.docx') ? (
                      <FileText size={22} style={{ color: '#2563eb' }} />
                    ) : (
                      <FileSpreadsheet size={22} style={{ color: '#10b981' }} />
                    )}
                    <div>
                      <div style={{ fontSize: '12.5px', fontWeight: 700, color: '#065f46' }}>{file.name}</div>
                      <div style={{ fontSize: '11px', color: '#047857' }}>
                        {(file.size / 1024).toFixed(1)} KB • {dataRowCount} data rows detected
                      </div>
                    </div>
                  </div>
                  <button
                    onClick={() => {
                      setFile(null);
                      setFields([]);
                      setDataRowCount(0);
                      setEmbeddedPhotosCount(0);
                    }}
                    style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#ef4444', padding: '4px' }}
                  >
                    <X size={18} />
                  </button>
                </div>
              )}

              {/* Embedded Photos Detected Badge */}
              {embeddedPhotosCount > 0 && (
                <div
                  style={{
                    padding: '10px 14px',
                    background: '#eff6ff',
                    border: '1px solid #bfdbfe',
                    borderRadius: '6px',
                    display: 'flex',
                    alignItems: 'center',
                    gap: '10px',
                  }}
                >
                  <Camera size={20} style={{ color: '#2563eb', flexShrink: 0 }} />
                  <div style={{ fontSize: '12px', color: '#1e40af' }}>
                    <strong>{embeddedPhotosCount} Embedded Photos Detected!</strong>
                    <div style={{ fontSize: '11px', color: '#3b82f6', marginTop: '2px' }}>
                      These photos will be automatically extracted and assigned to student records without needing a ZIP file.
                    </div>
                  </div>
                </div>
              )}

              {/* Table Name Input */}
              <div>
                <label
                  style={{
                    display: 'block',
                    fontSize: '11px',
                    fontWeight: 700,
                    color: '#475569',
                    textTransform: 'uppercase',
                    marginBottom: '6px',
                    letterSpacing: '0.04em',
                  }}
                >
                  Table Name
                </label>
                <input
                  type="text"
                  value={tableName}
                  onChange={(e) => setTableName(e.target.value)}
                  placeholder="e.g., ADARSH VIDYALAYA 2026-27"
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    border: '1px solid #cbd5e1',
                    borderRadius: '4px',
                    fontSize: '12px',
                    fontWeight: 600,
                    outline: 'none',
                    background: '#f8fafc',
                  }}
                />
              </div>
            </>
          )}

          {/* ── STEP 2: Schema & Column Types ── */}
          {step === 2 && (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <span style={{ fontSize: '12px', fontWeight: 700, color: '#334155' }}>
                  Detected Columns ({fields.length})
                </span>
                <span style={{ fontSize: '11px', color: '#64748b' }}>
                  {dataRowCount} student rows will be imported
                </span>
              </div>

              <div
                style={{
                  border: '1px solid #e2e8f0',
                  borderRadius: '6px',
                  overflow: 'hidden',
                  maxHeight: '260px',
                  overflowY: 'auto',
                }}
              >
                <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                  <thead
                    style={{
                      background: '#f8fafc',
                      borderBottom: '1px solid #e2e8f0',
                      position: 'sticky',
                      top: 0,
                      zIndex: 5,
                    }}
                  >
                    <tr>
                      <th style={{ padding: '8px 10px', textAlign: 'left', width: '45%' }}>Field Name</th>
                      <th style={{ padding: '8px 10px', textAlign: 'left', width: '35%' }}>Data Type</th>
                      <th style={{ padding: '8px 10px', textAlign: 'center', width: '20%' }}>Mandatory</th>
                    </tr>
                  </thead>
                  <tbody>
                    {fields.map((f, idx) => (
                      <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                        <td style={{ padding: '6px 10px' }}>
                          <input
                            type="text"
                            value={f.name}
                            onChange={(e) => handleFieldNameChange(idx, e.target.value)}
                            style={{
                              width: '100%',
                              padding: '5px 8px',
                              border: '1px solid #cbd5e1',
                              borderRadius: '4px',
                              fontSize: '11.5px',
                              fontWeight: 600,
                              background: '#fff',
                            }}
                          />
                        </td>
                        <td style={{ padding: '6px 10px' }}>
                          <CustomSelect
                            value={f.type}
                            onChange={(val) => handleFieldTypeChange(idx, val)}
                            options={[
                              { value: 'text', label: 'Text' },
                              { value: 'number', label: 'Number' },
                              { value: 'date', label: 'Date' },
                              { value: 'photo', label: 'Photo (Main)' },
                              { value: 'father_photo', label: 'Father Photo' },
                              { value: 'mother_photo', label: 'Mother Photo' },
                              { value: 'sign', label: 'Signature' },
                            ]}
                          />
                        </td>
                        <td style={{ padding: '6px 10px', textAlign: 'center' }}>
                          <input
                            type="checkbox"
                            checked={f.mandatory || false}
                            onChange={() => handleMandatoryToggle(idx)}
                            style={{ cursor: 'pointer' }}
                          />
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </>
          )}

          {/* ── STEP 3: Photos ZIP & Submission ── */}
          {step === 3 && (
            <>
              <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
                <label
                  style={{
                    display: 'block',
                    fontSize: '11px',
                    fontWeight: 700,
                    color: '#64748b',
                    textTransform: 'uppercase',
                    marginBottom: '6px',
                    letterSpacing: '0.04em',
                  }}
                >
                  Upload Photos ZIP (Optional)
                </label>
                <p style={{ fontSize: '11px', color: '#64748b', margin: '0 0 10px' }}>
                  {embeddedPhotosCount > 0
                    ? `Note: ${embeddedPhotosCount} photos are already embedded in the document. You can optionally attach an additional ZIP archive.`
                    : 'Attach photo ZIP archive(s) to match images by filename against student roll numbers or names.'}
                </p>

                <div
                  onClick={() => zipInputRef.current?.click()}
                  style={{
                    border: '1px dashed #10b981',
                    borderRadius: '6px',
                    padding: '16px',
                    textAlign: 'center',
                    cursor: 'pointer',
                    background: '#f0fdf4',
                  }}
                >
                  <FolderArchive size={24} style={{ color: '#10b981', margin: '0 auto 6px' }} />
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#065f46' }}>
                    {zipFiles && zipFiles.length > 0
                      ? `${zipFiles.length} ZIP file(s) attached`
                      : 'Click to select ZIP photo archive(s)'}
                  </div>
                  <input
                    ref={zipInputRef}
                    type="file"
                    accept=".zip"
                    multiple
                    style={{ display: 'none' }}
                    onChange={(e) => setZipFiles(e.target.files)}
                  />
                </div>
              </div>

              {isProcessing && (
                <div style={{ background: '#f0fdf4', padding: '12px', borderRadius: '6px', border: '1px solid #bbf7d0' }}>
                  <div style={{ fontSize: '12px', fontWeight: 600, color: '#166534', marginBottom: '6px' }}>
                    Creating table, extracting embedded photos & importing records...
                  </div>
                  <div style={{ height: '6px', background: '#dcfce7', borderRadius: '3px', overflow: 'hidden' }}>
                    <div
                      style={{
                        height: '100%',
                        width: `${progress}%`,
                        background: '#10b981',
                        transition: 'width 0.3s ease',
                      }}
                    />
                  </div>
                </div>
              )}
            </>
          )}
        </div>

        {/* Footer Actions */}
        <div
          style={{
            padding: '12px 20px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            gap: '10px',
            justifyContent: 'space-between',
            alignItems: 'center',
          }}
        >
          {step > 1 ? (
            <button
              onClick={() => setStep(step - 1)}
              disabled={isProcessing}
              style={{
                padding: '8px 16px',
                background: '#fff',
                border: '1px solid #cbd5e1',
                borderRadius: '4px',
                color: '#475569',
                fontWeight: 600,
                cursor: 'pointer',
                fontSize: '12px',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <ArrowLeft size={14} /> Back
            </button>
          ) : (
            <Button
              variant="secondary"
              size="md"
              onClick={onClose}
            >
              Cancel
            </Button>
          )}

          <div style={{ display: 'flex', gap: '8px' }}>
            {step < 3 ? (
              <Button
                variant="primary"
                size="md"
                onClick={() => setStep(step + 1)}
                disabled={!file || isAnalyzing}
                loading={isAnalyzing}
                icon={<ArrowRight size={14} />}
                iconPosition="end"
              >
                {isAnalyzing ? 'Analyzing Document...' : 'Next'}
              </Button>
            ) : (
              <Button
                variant="success"
                size="md"
                onClick={handleSubmit}
                disabled={isProcessing}
                loading={isProcessing}
                icon={<Upload size={14} />}
              >
                {isProcessing ? 'Creating Table...' : 'Create Table & Import'}
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
