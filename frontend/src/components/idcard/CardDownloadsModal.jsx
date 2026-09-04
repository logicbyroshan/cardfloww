import React, { useState } from 'react';
import {
  X,
  Download,
  FileSpreadsheet,
  FileText,
  Archive,
  Printer,
  Image as ImageIcon,
  CheckCircle2,
  Loader2,
  Sparkles,
} from 'lucide-react';
import CustomSelect from '../common/CustomSelect';
import Button from '../common/Button';
import { exportApi } from '../../services/api';

export default function CardDownloadsModal({
  isOpen,
  onClose,
  table,
  status = 'approved',
  tableFields = [],
  addToast,
}) {
  const [format, setFormat] = useState('excel');
  const [targetStatus, setTargetStatus] = useState(status || 'approved');
  const [photoColumn, setPhotoColumn] = useState('PHOTO');
  const [downloading, setDownloading] = useState(false);

  if (!isOpen) return null;

  const tableId = table?.id;

  const photoOptions = (tableFields || [])
    .filter((f) => {
      const type = (f.type || '').toLowerCase();
      const name = (f.name || '').toLowerCase();
      return (
        type.includes('photo') ||
        type.includes('image') ||
        type.includes('sign') ||
        name.includes('photo') ||
        name.includes('pic') ||
        name.includes('sign')
      );
    })
    .map((f) => ({ value: f.name, label: `${f.name} (${f.type || 'image'})` }));

  const defaultPhotoOptions =
    photoOptions.length > 0
      ? photoOptions
      : [
          { value: 'PHOTO', label: 'PHOTO (Main Photo)' },
          { value: 'FATHER_PHOTO', label: 'FATHER_PHOTO' },
          { value: 'MOTHER_PHOTO', label: 'MOTHER_PHOTO' },
          { value: 'SIGN', label: 'SIGN (Signature)' },
        ];

  const handleDownload = () => {
    if (!tableId) {
      addToast?.('Please select a table to export cards.', 'error');
      return;
    }

    setDownloading(true);
    let downloadUrl = '';

    try {
      if (format === 'excel') {
        downloadUrl = exportApi.getDownloadXlsxUrl(tableId, targetStatus);
      } else if (format === 'pdf') {
        downloadUrl = exportApi.getDownloadPdfUrl(tableId, targetStatus);
      } else if (format === 'docx') {
        downloadUrl = exportApi.getDownloadDocxUrl(tableId, targetStatus);
      } else if (format === 'zip') {
        downloadUrl = exportApi.getDownloadImagesUrl(tableId, targetStatus, {
          photo_field: photoColumn,
        });
      } else if (format === 'all') {
        downloadUrl = exportApi.getDownloadAllCardsUrl(tableId, targetStatus);
      }

      if (downloadUrl) {
        window.open(downloadUrl, '_blank');
        addToast?.(`Downloading ${format.toUpperCase()} export file…`, 'success');
        setTimeout(() => {
          setDownloading(false);
          onClose();
        }, 600);
      } else {
        setDownloading(false);
      }
    } catch (err) {
      console.error('Export download error:', err);
      addToast?.('Failed to trigger export download.', 'error');
      setDownloading(false);
    }
  };

  return (
    <div className="center-modal-overlay">
      <div
        className="center-modal-panel modal-md"
        style={{
          width: 'var(--modal-width-md, 540px)',
          height: 'auto',
          maxHeight: '90vh',
          padding: '0',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: '8px',
          overflow: 'hidden',
          boxShadow: '0 20px 50px rgba(0, 0, 0, 0.35)',
        }}
      >
        {/* Header */}
        <div
          style={{
            background: '#1e293b',
            color: '#fff',
            height: '48px',
            minHeight: '48px',
            padding: '0 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          }}
        >
          <span style={{ fontWeight: 700, fontSize: '14px', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Download size={17} style={{ color: '#10b981' }} /> Download & Export Engine
          </span>
          <button
            onClick={onClose}
            style={{ background: 'transparent', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px' }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Modal Body */}
        <div
          style={{
            flex: 1,
            padding: '22px 24px',
            display: 'flex',
            flexDirection: 'column',
            gap: '16px',
            overflowY: 'auto',
            background: '#ffffff',
          }}
        >
          {/* Table Details Banner */}
          <div
            style={{
              padding: '10px 14px',
              background: '#f8fafc',
              border: '1px solid #e2e8f0',
              borderRadius: '8px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '12px',
            }}
          >
            <div>
              Table: <strong style={{ color: '#0f172a' }}>{table?.name || 'ID Cards Table'}</strong>
            </div>
            <div style={{ color: '#64748b' }}>
              Target List: <strong style={{ color: '#2563eb' }}>{targetStatus.toUpperCase()}</strong>
            </div>
          </div>

          {/* Format Selector Grid */}
          <div>
            <label
              style={{
                display: 'block',
                fontSize: '11px',
                fontWeight: 700,
                color: '#64748b',
                textTransform: 'uppercase',
                marginBottom: '8px',
                letterSpacing: '0.04em',
              }}
            >
              Select Export Format
            </label>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '10px' }}>
              {[
                { id: 'excel', label: 'Excel (.xlsx)', desc: 'Full Spreadsheet Data', icon: FileSpreadsheet, color: '#10b981' },
                { id: 'pdf', label: 'PDF Sheet', desc: 'Print-Ready Cards Grid', icon: FileText, color: '#ef4444' },
                { id: 'docx', label: 'Word (.docx)', desc: 'Formatted Print Pages', icon: Printer, color: '#3b82f6' },
                { id: 'zip', label: 'ZIP Photos', desc: 'High-Res Photo Archive', icon: ImageIcon, color: '#8b5cf6' },
                { id: 'all', label: 'Complete ZIP', desc: 'Data + All Assets', icon: Archive, color: '#f59e0b' },
              ].map((opt) => {
                const Icon = opt.icon;
                const active = format === opt.id;
                return (
                  <button
                    key={opt.id}
                    type="button"
                    onClick={() => setFormat(opt.id)}
                    style={{
                      padding: '12px 10px',
                      borderRadius: '8px',
                      background: active ? `${opt.color}12` : '#f8fafc',
                      border: active ? `2px solid ${opt.color}` : '1px solid #e2e8f0',
                      color: active ? opt.color : '#334155',
                      display: 'flex',
                      flexDirection: 'column',
                      alignItems: 'center',
                      gap: '4px',
                      textAlign: 'center',
                      cursor: 'pointer',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <Icon size={22} color={opt.color} />
                    <span style={{ fontSize: '12px', fontWeight: 700 }}>{opt.label}</span>
                    <span style={{ fontSize: '10px', color: '#64748b' }}>{opt.desc}</span>
                  </button>
                );
              })}
            </div>
          </div>

          {/* Status Filter Row */}
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
            <div>
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
                Filter by Card Status
              </label>
              <CustomSelect
                value={targetStatus}
                onChange={(val) => setTargetStatus(val)}
                options={[
                  { value: 'approved', label: 'Approved Cards Only' },
                  { value: 'pending', label: 'Pending Cards Only' },
                  { value: 'verified', label: 'Verified Cards Only' },
                  { value: 'printed', label: 'Printed / Downloaded Cards' },
                  { value: 'all', label: 'All Statuses Combined' },
                ]}
              />
            </div>

            {format === 'zip' && (
              <div>
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
                  Select Photo Field Column
                </label>
                <CustomSelect
                  value={photoColumn}
                  onChange={(val) => setPhotoColumn(val)}
                  options={defaultPhotoOptions}
                />
              </div>
            )}
          </div>
        </div>

        {/* Footer */}
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
          <Button
            variant="secondary"
            size="md"
            onClick={onClose}
            disabled={downloading}
          >
            Cancel
          </Button>
          <Button
            variant="success"
            size="md"
            onClick={handleDownload}
            disabled={downloading}
            loading={downloading}
            icon={<Download size={15} />}
          >
            Generate & Download
          </Button>
        </div>
      </div>
    </div>
  );
}
