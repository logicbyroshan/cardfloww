import React, { useState, useEffect, useCallback, useRef } from 'react';
import * as XLSX from 'xlsx';
import { createPortal } from 'react-dom';
import {
  Plus,
  Pen,
  Trash2,
  ToggleRight,
  Download,
  FileSpreadsheet,
  SlidersHorizontal,
  Settings,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RefreshCw,
  Loader2,
  Save,
  X,
  CheckCircle2,
  Users,
  Upload,
  FileText,
  Settings2,
  ListPlus,
  GripVertical,
  Edit3,
  PlusCircle,
  List,
  Info,
  Check,
  Tag,
  School,
  BookOpen,
  Briefcase,
  Sparkles,
  FolderKanban,
  ShieldCheck,
} from 'lucide-react';

import WatermarkLogo from '../common/WatermarkLogo';
import CreateXlsxModal from '../common/CreateXlsxModal';
import { schemaApi, clientApi } from '../../services/api';

const STATUS_TABS = ['All', 'Active', 'Inactive'];
const PAGE_SIZE_OPTIONS = [25, 50, 100];

/* ── Table Type metadata ── */
const TABLE_TYPES = [
  {
    value: 'school_student',
    label: 'School Student',
    icon: School,
    color: '#2563eb',
    bg: '#eff6ff',
    border: '#bfdbfe',
  },
  {
    value: 'college_student',
    label: 'College Student',
    icon: BookOpen,
    color: '#7c3aed',
    bg: '#f5f3ff',
    border: '#ddd6fe',
  },
  { value: 'staff', label: 'Staff', icon: Briefcase, color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
  { value: 'custom', label: 'Custom', icon: Settings2, color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
];

function getTableTypeMeta(value) {
  return TABLE_TYPES.find((t) => t.value === value) || TABLE_TYPES[3];
}

/* ── Smart table-type inference (mirrors backend logic) ── */
function inferTableType(tableName = '', orgName = '', fields = []) {
  const name = (tableName || '').toLowerCase().trim();
  const org = (orgName || '').toLowerCase().trim();

  const staffRe = /\b(staff|teacher|teachers|employee|employees|emp|faculty|personnel|hr|driver|workers|management)\b/;
  const collegeRe =
    /\b(college|university|institute|polytechnic|degree|btech|mtech|bca|mca|mba|bsc|msc|ba|ma|bcom|mcom|semester|sem|branch|dept|department)\b/;
  const schoolRe = /\b(school|vidyalaya|academy|convent|class|std|standard|grade|section|sec)\b/;
  const studentRe = /\b(student|students|pupil|scholars|list|data|records|info|all)\b/;

  if (staffRe.test(name)) return 'staff';
  if (collegeRe.test(name)) return 'college_student';
  if (schoolRe.test(name)) return 'school_student';

  if (studentRe.test(name)) {
    if (collegeRe.test(org)) return 'college_student';
    return 'school_student';
  }

  // Check fields if table name is generic
  if (Array.isArray(fields) && fields.length > 0) {
    const fieldTypes = fields.map((f) => (f.type || '').toLowerCase());
    const fieldNames = fields.map((f) => (f.name || '').toLowerCase()).join(' ');

    if (
      fieldTypes.includes('class') ||
      fieldTypes.includes('section') ||
      /\b(class|section|roll|father|mother)\b/.test(fieldNames)
    ) {
      return 'school_student';
    }
    if (/\b(branch|semester|sem|course|enrolment|enrollment)\b/.test(fieldNames)) {
      return 'college_student';
    }
    if (/\b(designation|emp|employee|department|salary)\b/.test(fieldNames)) {
      return 'staff';
    }
  }

  return 'custom';
}

/* ── Field type options that match backend ── */
const FIELD_TYPES = [
  { value: 'text', label: 'Text' },
  { value: 'number', label: 'Number' },
  { value: 'email', label: 'Email' },
  { value: 'date', label: 'Date' },
  { value: 'photo', label: 'Photo' },
  { value: 'rel_photo', label: 'Relation Photo' },
  { value: 'signature', label: 'Signature' },
  { value: 'barcode', label: 'Barcode' },
  { value: 'qr_code', label: 'QR Code' },
  { value: 'class', label: 'Class' },
  { value: 'section', label: 'Section' },
  { value: 'select', label: 'Select / Dropdown' },
  { value: 'textarea', label: 'Textarea' },
];

/* ── Smart field-type inference (same as backend header map) ── */
function inferFieldType(name = '') {
  const n = name.toLowerCase().trim();
  if (/\b(photo|pic|picture|image)\b/.test(n)) return 'photo';
  if (/\b(rel(?:ation)?[\s_-]*(?:photo|pic|image|1|2|one|two))\b/.test(n)) return 'rel_photo';
  if (/\b(mother|father)[\s_-]*(photo|pic|image)\b/.test(n)) return 'rel_photo';
  if (/\bsignature?\b/.test(n)) return 'signature';
  if (/\bbarcode\b/.test(n)) return 'barcode';
  if (/\bqr[\s_-]?code?\b/.test(n)) return 'qr_code';
  if (/\b(class|std|standard|grade)\b/.test(n)) return 'class';
  if (/\b(section|sec|div|division)\b/.test(n)) return 'section';
  if (/\b(email|e-mail|mail)\b/.test(n)) return 'email';
  if (/\b(no|number|no\.)\b/.test(n)) return 'number';
  if (/\b(date|dob|born)\b/.test(n)) return 'date';
  return 'text';
}

const DEFAULT_SCHEMA_FIELDS = [
  { id: 'f-1', name: 'PHOTO', type: 'photo', mandatory: true, show_path: true },
  { id: 'f-2', name: 'NAME', type: 'text', mandatory: true, show_path: false },
  { id: 'f-3', name: 'SERIAL NO', type: 'number', mandatory: true, show_path: false },
];

export default function TableSettingsView({ addToast, onNavigate }) {
  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusTab, setStatusTab] = useState('All');
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);

  const [showAddEditDrawer, setShowAddEditDrawer] = useState(false);
  const [showExcelDrawer, setShowExcelDrawer] = useState(false);
  const [editingTable, setEditingTable] = useState(null);
  const [groupId, setGroupId] = useState(null);
  const [clientOrg, setClientOrg] = useState('');

  /* Fetch group_id from the current client so we can call createTable(groupId, …) */
  const loadGroupId = useCallback(async () => {
    try {
      const data = await clientApi.getActive?.({ page_size: 1 });
      const clients = data?.results || data?.clients || (Array.isArray(data) ? data : []);
      if (clients.length > 0) {
        const client = clients[0];
        setGroupId(client.group_id || client.default_group_id || null);
        setClientOrg(client.name || client.client_name || '');
      }
    } catch {
      /* ignore — tables still work via fallback */
    }
  }, []);

  const getStoredTables = useCallback(() => {
    try {
      const stored = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
      const dummyNames = ['Class 1st to 5th', 'Class 6th to 10th', 'Class 11th & 12th', 'Staff & Teachers'];
      const cleaned = stored.filter((t) => t && !dummyNames.includes(t.name));
      if (cleaned.length !== stored.length) {
        localStorage.setItem('cf_custom_tables', JSON.stringify(cleaned));
      }
      return cleaned;
    } catch {
      return [];
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    let activeOrg = clientOrg;

    if (!activeOrg) {
      try {
        const clientsData = await clientApi.getActive?.({ page_size: 10 });
        const clients = clientsData?.results || clientsData?.clients || (Array.isArray(clientsData) ? clientsData : []);
        if (clients.length > 0) {
          activeOrg = clients[0].name || clients[0].client_name || '';
          setClientOrg(activeOrg);
          if (clients[0].group_id || clients[0].id) {
            setGroupId(clients[0].group_id || clients[0].id);
          }
        }
      } catch {
        /* fallback */
      }
    }

    const local = getStoredTables();
    try {
      let list = [];
      if (groupId) {
        const data = await schemaApi.getGroupTables(groupId);
        list = data?.tables || data?.results || (Array.isArray(data) ? data : []);
      } else {
        const data = await schemaApi.getSchemas?.();
        list = data?.tables || data?.results || (Array.isArray(data) ? data : []);
      }

      const merged = [...local];
      (list || []).forEach((item) => {
        if (!merged.some((t) => String(t.id) === String(item.id) || t.name === item.name)) {
          merged.push({
            ...item,
            client_name: item.client_name || item.client?.name || activeOrg,
            fields: item.fields || DEFAULT_SCHEMA_FIELDS,
          });
        }
      });

      const enriched = merged.map((t) => {
        const rawName = t.client_name || t.client?.name || '';
        const validName =
          rawName && !['Default Organisation', 'Organisation', '—'].includes(rawName.trim())
            ? rawName.trim()
            : activeOrg || 'Primary Organisation';
        return {
          ...t,
          client_name: validName,
        };
      });

      setTables(enriched);
    } catch {
      const enrichedLocal = local.map((t) => {
        const rawName = t.client_name || t.client?.name || '';
        const validName =
          rawName && !['Default Organisation', 'Organisation', '—'].includes(rawName.trim())
            ? rawName.trim()
            : activeOrg || 'Primary Organisation';
        return {
          ...t,
          client_name: validName,
        };
      });
      setTables(enrichedLocal);
    } finally {
      setLoading(false);
    }
  }, [groupId, clientOrg, getStoredTables]);

  useEffect(() => {
    loadGroupId();
  }, [loadGroupId]);
  useEffect(() => {
    load();
  }, [load]);

  const filtered = tables.filter((t) => {
    if (!t) return false;
    const q = (search || '').toLowerCase();
    const matchSearch =
      !q || (t.name || '').toLowerCase().includes(q) || (t.client_name || '').toLowerCase().includes(q);
    const isActive = t.is_active !== false;
    const matchStatus = statusTab === 'All' || (statusTab === 'Active' ? isActive : !isActive);
    return matchSearch && matchStatus;
  });

  const paged = filtered;
  const selTable = tables.find((t) => t.id === selected);

  const handleToggleStatus = async () => {
    if (!selected) return;
    try {
      try {
        await schemaApi.toggleTableStatus(selected);
      } catch (apiErr) {
        console.warn('Backend API toggle status notice:', apiErr);
      }
      const local = getStoredTables();
      const updated = local.map((t) => {
        if (String(t.id) === String(selected)) {
          const nextActive = t.is_active === false ? true : false;
          return {
            ...t,
            is_active: nextActive,
            status: nextActive ? 'active' : 'inactive',
            updated_at: new Date().toISOString(),
          };
        }
        return t;
      });
      localStorage.setItem('cf_custom_tables', JSON.stringify(updated));
      addToast?.(`Status toggled for ${selTable?.name}`, 'success');
      load();
    } catch {
      addToast?.('Error updating table status', 'error');
    }
  };

  const handleDeleteTable = async () => {
    if (!selected) return;
    if (!window.confirm(`Delete table "${selTable?.name}"? This cannot be undone.`)) return;
    try {
      try {
        await schemaApi.deleteTable(selected);
      } catch (apiErr) {
        console.warn('Backend API delete table notice:', apiErr);
      }
      const local = getStoredTables();
      const updated = local.filter((t) => String(t.id) !== String(selected));
      localStorage.setItem('cf_custom_tables', JSON.stringify(updated));
      addToast?.(`Table "${selTable?.name}" deleted`, 'success');
      setSelected(null);
      load();
    } catch (err) {
      addToast?.(err?.response?.data?.message || 'Error deleting table', 'error');
    }
  };

  const handleDownloadBlankTemplate = () => {
    addToast?.('Downloading Blank Excel Template (.xlsx)…', 'info');
  };

  const formatDate = (d) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleString('en-IN', {
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return d;
    }
  };

  return (
    <div
      className="view-container"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}
    >
      {/* ── ACTION BAR ── */}
      <div
        className="action-bar"
        id="gs-action-bar"
        style={{
          background: '#1e1e2e',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          height: '50px',
          padding: '0 16px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxSizing: 'border-box',
        }}
      >
        {/* Left */}
        <div className="action-bar-left" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            className="status-tabs"
            style={{
              display: 'flex',
              alignItems: 'center',
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.18)',
              borderRadius: '5px',
              padding: '2px',
              gap: '2px',
              height: '28px',
              boxSizing: 'border-box',
            }}
          >
            {STATUS_TABS.map((t) => (
              <button
                key={t}
                onClick={() => {
                  setStatusTab(t);
                  setPage(1);
                }}
                className={`status-tab${statusTab === t ? ' active' : ''}`}
                style={{
                  padding: '0 10px',
                  height: '22px',
                  fontSize: '11px',
                  lineHeight: '22px',
                  borderRadius: '3px',
                  border: 'none',
                  cursor: 'pointer',
                  background: statusTab === t ? '#2563eb' : 'transparent',
                  color: statusTab === t ? '#ffffff' : '#cbd5e1',
                  fontWeight: statusTab === t ? 700 : 600,
                  fontFamily: 'var(--font-family)',
                  transition: 'all 0.15s',
                  boxShadow: statusTab === t ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
              >
                {t}
              </button>
            ))}
          </div>

          <div
            className="action-divider"
            style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }}
          />

          <div
            className="notif-search-box"
            style={{
              width: '200px',
              height: '28px',
              background: 'rgba(255, 255, 255, 0.08)',
              border: '1px solid rgba(255, 255, 255, 0.18)',
              borderRadius: '5px',
              padding: '0 8px',
              display: 'flex',
              alignItems: 'center',
              boxSizing: 'border-box',
            }}
          >
            <Search size={12} style={{ color: '#94a3b8', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search tables..."
              style={{
                background: 'transparent',
                border: 'none',
                color: '#ffffff',
                outline: 'none',
                fontSize: '12px',
                width: '100%',
              }}
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                style={{
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  color: '#94a3b8',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0 2px',
                }}
                title="Clear search"
              >
                <X size={12} />
              </button>
            )}
          </div>
        </div>

        {/* Right */}
        <div className="action-bar-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                className="btn"
                onClick={() => {
                  setEditingTable(null);
                  setShowAddEditDrawer(true);
                }}
                style={{
                  background: '#2563eb',
                  color: '#ffffff',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  border: '1px solid #2563eb',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <Plus size={13} /> Add
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={() => {
                  setEditingTable(selTable);
                  setShowAddEditDrawer(true);
                }}
                style={{
                  background: selected ? '#2563eb' : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected ? '1px solid #2563eb' : '1px solid rgba(255, 255, 255, 0.15)',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: selected ? 'pointer' : 'not-allowed',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <Pen size={13} /> Edit
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={handleDeleteTable}
                style={{
                  background: selected ? '#ef4444' : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected ? '1px solid #ef4444' : '1px solid rgba(255, 255, 255, 0.15)',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: selected ? 'pointer' : 'not-allowed',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <Trash2 size={13} /> Delete
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={handleToggleStatus}
                style={{
                  background: selected ? '#f59e0b' : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected ? '1px solid #f59e0b' : '1px solid rgba(255, 255, 255, 0.15)',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: selected ? 'pointer' : 'not-allowed',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <ToggleRight size={13} /> Active
              </button>
            </div>

            <div
              className="btn-separator"
              style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }}
            />

            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                className="btn"
                onClick={() => setShowExcelDrawer(true)}
                title="Create Table with XLSX"
                style={{
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: '#ffffff',
                  border: '1px solid rgba(255, 255, 255, 0.18)',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <FileSpreadsheet size={13} /> <span>Create with XLSX</span>
              </button>
              <button
                className="btn"
                onClick={handleDownloadBlankTemplate}
                title="Download XLSX Template"
                style={{
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: '#ffffff',
                  border: '1px solid rgba(255, 255, 255, 0.18)',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <Download size={13} /> <span>Download XLSX Template</span>
              </button>
            </div>

            <div
              className="btn-separator"
              style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }}
            />

            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                className="btn"
                onClick={() => (onNavigate ? onNavigate('cards') : (window.location.href = '/panel/idcard-group/'))}
                title="Tables"
                style={{
                  background: 'rgba(255, 255, 255, 0.08)',
                  color: '#ffffff',
                  border: '1px solid rgba(255, 255, 255, 0.18)',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <ShieldCheck size={13} /> <span>Tables</span>
              </button>
              <button
                className="btn"
                title="Table Setting"
                style={{
                  background: '#2563eb',
                  color: '#ffffff',
                  border: '1px solid #2563eb',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 600,
                  borderRadius: '4px',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  boxSizing: 'border-box',
                }}
              >
                <Settings size={13} /> <span>Table Setting</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── TABLE CONTAINER ── */}
      <div
        id="gs-table-container"
        style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}
      >
        <div
          className="table-wrapper"
          style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', position: 'relative' }}
        >
          <WatermarkLogo />
          {paged.length === 0 && !loading ? (
            <div
              style={{
                flex: 1,
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                padding: '40px 20px',
                textAlign: 'center',
              }}
            >
              <div
                style={{
                  width: '64px',
                  height: '64px',
                  borderRadius: '50%',
                  background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                  color: '#2563eb',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  boxShadow: '0 4px 14px rgba(37,99,235,0.12)',
                  border: '1px solid #bfdbfe',
                  marginBottom: '12px',
                }}
              >
                <SlidersHorizontal size={30} />
              </div>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Table Settings Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No tables match "${search}"` : 'No table settings configured yet.'}
              </p>
              {!search && (
                <button
                  onClick={() => {
                    setEditingTable(null);
                    setShowAddEditDrawer(true);
                  }}
                  className="btn btn-primary btn-sm"
                  style={{
                    marginTop: '14px',
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    fontSize: '11px',
                    padding: '7px 16px',
                    borderRadius: '5px',
                  }}
                >
                  <Plus size={14} /> Add First Table Setting
                </button>
              )}
            </div>
          ) : (
            <table className="data-table">
              <thead>
                <tr>
                  <th style={{ width: '42px', textAlign: 'center' }}>S. NO.</th>
                  <th style={{ width: '200px', textAlign: 'left' }}>TABLE NAME</th>
                  <th style={{ width: '130px', textAlign: 'center' }}>TABLE TYPE</th>
                  <th style={{ width: '190px', textAlign: 'left' }}>ORGANISATION</th>
                  <th style={{ width: '140px', textAlign: 'center' }}>SCHEMA FIELDS</th>
                  <th style={{ width: '80px', textAlign: 'center' }}>STATUS</th>
                  <th style={{ width: '115px', textAlign: 'center' }}>CREATED AT</th>
                  <th style={{ width: '115px', textAlign: 'center' }}>UPDATED AT</th>
                </tr>
              </thead>
              <tbody>
                {loading
                  ? Array.from({ length: 12 }).map((_, i) => (
                      <tr key={i} className="skeleton-row">
                        <td style={{ textAlign: 'center' }}>
                          <div
                            className="skeleton"
                            style={{ width: '16px', height: '16px', borderRadius: '3px', margin: '0 auto' }}
                          />
                        </td>
                        <td>
                          <div className="skeleton" style={{ height: '13px', width: `${60 + (i % 4) * 8}%` }} />
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <div
                            className="skeleton"
                            style={{ height: '20px', width: '90px', margin: '0 auto', borderRadius: '10px' }}
                          />
                        </td>
                        <td>
                          <div className="skeleton" style={{ height: '13px', width: `${55 + (i % 3) * 10}%` }} />
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <div className="skeleton" style={{ height: '13px', width: '60%', margin: '0 auto' }} />
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <div className="skeleton skeleton-cell-badge" style={{ margin: '0 auto' }} />
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <div className="skeleton skeleton-cell-date" style={{ margin: '0 auto' }} />
                        </td>
                        <td style={{ textAlign: 'center' }}>
                          <div className="skeleton skeleton-cell-date" style={{ margin: '0 auto', width: '75%' }} />
                        </td>
                      </tr>
                    ))
                  : filtered.map((t, idx) => {
                      const name = t.name || `Table #${t.id || idx}`;
                      const rawClient = t.client_name || t.client?.name || '';
                      const clientName =
                        rawClient &&
                        !['Default Organisation', 'Organisation', 'Primary Organisation', '—'].includes(
                          rawClient.trim()
                        )
                          ? rawClient.trim()
                          : clientOrg || 'Mathura Das School of Execellence';
                      const isActive = t.is_active !== false;
                      const isSel = t.id === selected;
                      const fieldList =
                        Array.isArray(t.fields) && t.fields.length > 0 ? t.fields : DEFAULT_SCHEMA_FIELDS;
                      const requiredCount = fieldList.filter((f) => f.mandatory || f.is_required).length;
                      const typeMeta = getTableTypeMeta(t.table_type || 'custom');
                      const TypeIcon = typeMeta.icon;

                      return (
                        <tr
                          key={t.id || idx}
                          onClick={() => setSelected((prev) => (prev === t.id ? null : t.id))}
                          className={`table-row${isSel ? ' selected' : ''}`}
                          style={{ cursor: 'pointer' }}
                        >
                          <td
                            className="text-center"
                            style={{ width: '42px', textAlign: 'center', fontSize: '11px', color: '#64748b' }}
                          >
                            {idx + 1}
                          </td>
                          <td style={{ fontWeight: 600, color: isSel ? '#1d4ed8' : '#0f172a' }}>{name}</td>
                          <td className="text-center" style={{ width: '130px', textAlign: 'center' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                fontSize: '10px',
                                fontWeight: 600,
                                padding: '2px 8px',
                                borderRadius: '12px',
                                background: typeMeta.bg,
                                color: typeMeta.color,
                                border: `1px solid ${typeMeta.border}`,
                              }}
                            >
                              <TypeIcon size={11} /> {typeMeta.label}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', color: '#475569' }}>{clientName}</td>
                          <td className="text-center" style={{ width: '140px', textAlign: 'center' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '4px',
                                fontSize: '10px',
                                fontWeight: 600,
                                padding: '2px 8px',
                                borderRadius: '4px',
                                background: '#f1f5f9',
                                color: '#334155',
                                border: '1px solid #cbd5e1',
                              }}
                            >
                              <List size={10} style={{ color: '#2563eb' }} />
                              <span>
                                {fieldList.length} Fields ({requiredCount} Required)
                              </span>
                            </span>
                          </td>
                          <td className="text-center" style={{ width: '80px', textAlign: 'center' }}>
                            <span className={`badge ${isActive ? 'badge-success' : 'badge-neutral'}`}>
                              {isActive ? 'Active' : 'Inactive'}
                            </span>
                          </td>
                          <td
                            className="text-center"
                            style={{ width: '115px', fontSize: '11px', color: '#6b7280', textAlign: 'center' }}
                          >
                            {formatDate(t.created_at)}
                          </td>
                          <td
                            className="text-center"
                            style={{ width: '115px', fontSize: '11px', color: '#6b7280', textAlign: 'center' }}
                          >
                            {formatDate(t.updated_at)}
                          </td>
                        </tr>
                      );
                    })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── BACKDROP ── */}
      {(showAddEditDrawer || showExcelDrawer) && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            left: 0,
            right: 0,
            bottom: 0,
            background: 'rgba(15, 23, 42, 0.45)',
            backdropFilter: 'blur(4px)',
            WebkitBackdropFilter: 'blur(4px)',
            zIndex: 999,
            animation: 'fadeIn 0.15s ease-out',
          }}
        />
      )}

      {/* ── CREATE / EDIT DRAWER ── */}
      {showAddEditDrawer && (
        <TableDrawerForm
          editingTable={editingTable}
          groupId={groupId}
          orgName={clientOrg}
          onClose={() => setShowAddEditDrawer(false)}
          onSave={() => {
            setShowAddEditDrawer(false);
            load();
          }}
          addToast={addToast}
        />
      )}

      {/* ── CREATE WITH XLSX MODAL ── */}
      {showExcelDrawer && (
        <CreateXlsxModal
          groupId={groupId}
          onClose={() => setShowExcelDrawer(false)}
          onSuccess={() => {
            setShowExcelDrawer(false);
            load();
          }}
          addToast={addToast}
        />
      )}
    </div>
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   TABLE DRAWER FORM — Create New Table / Edit Table
   ═══════════════════════════════════════════════════════════════════════════ */
function TableDrawerForm({ editingTable, groupId, orgName, onClose, onSave, addToast }) {
  const isEditing = Boolean(editingTable);

  const [tableName, setTableName] = useState(editingTable?.name || '');
  const [tableType, setTableType] = useState(editingTable?.table_type || 'custom');
  const [typeAuto, setTypeAuto] = useState(false); // was this auto-detected?
  const [fields, setFields] = useState(
    (editingTable?.fields || []).map((f, i) => ({ ...f, id: f.id || `f_${i}`, type: (f.type || 'text').toLowerCase() }))
  );
  const [saving, setSaving] = useState(false);

  /* New-field form state */
  const [newName, setNewName] = useState('');
  const [newType, setNewType] = useState('text');
  const [typeAutoField, setTypeAutoField] = useState(false);

  /* Drag-and-drop state */
  const dragIdx = useRef(null);
  const [dragOver, setDragOver] = useState(null);

  /* ── Auto-detect table type as user types name or adds fields ── */
  useEffect(() => {
    if (isEditing) return; // don't auto-override in edit mode
    if (!tableName.trim() && fields.length === 0) {
      setTypeAuto(false);
      return;
    }
    const detected = inferTableType(tableName, orgName, fields);
    if (detected !== 'custom') {
      setTableType(detected);
      setTypeAuto(true);
    } else {
      setTypeAuto(false);
    }
  }, [tableName, orgName, fields, isEditing]);

  /* ── Auto-detect field type as user types field name ── */
  const handleNewNameChange = (val) => {
    setNewName(val);
    const detected = inferFieldType(val);
    setNewType(detected);
    setTypeAutoField(val.trim().length > 2);
  };

  /* ── Add field ── */
  const handleAddField = (e) => {
    e.preventDefault();
    if (!newName.trim()) return;
    const field = {
      id: `f_${Date.now()}`,
      name: newName.trim().toUpperCase(),
      type: newType,
      mandatory: false,
      show_path: ['photo', 'rel_photo', 'signature'].includes(newType),
    };
    setFields((prev) => [...prev, field]);
    setNewName('');
    setNewType('text');
    setTypeAutoField(false);
    addToast?.(`Field "${field.name}" added`, 'success');
  };

  /* ── Field mutations ── */
  const setFieldProp = (id, key, val) => setFields((prev) => prev.map((f) => (f.id === id ? { ...f, [key]: val } : f)));

  const handleFieldNameChange = (id, val) => {
    setFieldProp(id, 'name', val);
    // Also auto-detect type for existing fields
    const detected = inferFieldType(val);
    setFieldProp(id, 'type', detected);
  };

  const handleDeleteField = (id) => setFields((prev) => prev.filter((f) => f.id !== id));

  /* ── Drag & Drop Reorder ── */
  const onDragStart = (e, idx) => {
    dragIdx.current = idx;
    e.dataTransfer.effectAllowed = 'move';
  };
  const onDragOver = (e, idx) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOver(idx);
  };
  const onDrop = (e, idx) => {
    e.preventDefault();
    setDragOver(null);
    if (dragIdx.current === null || dragIdx.current === idx) return;
    const copy = [...fields];
    const [moved] = copy.splice(dragIdx.current, 1);
    copy.splice(idx, 0, moved);
    dragIdx.current = null;
    setFields(copy);
  };
  const onDragEnd = () => {
    dragIdx.current = null;
    setDragOver(null);
  };

  /* ── Arrow reorder (fallback) ── */
  const handleMoveUp = (idx) => {
    if (idx <= 0) return;
    const copy = [...fields];
    [copy[idx - 1], copy[idx]] = [copy[idx], copy[idx - 1]];
    setFields(copy);
  };
  const handleMoveDown = (idx) => {
    if (idx >= fields.length - 1) return;
    const copy = [...fields];
    [copy[idx], copy[idx + 1]] = [copy[idx + 1], copy[idx]];
    setFields(copy);
  };

  /* ── Submit ── */
  const handleSubmit = async () => {
    if (!tableName.trim()) {
      addToast?.('Table Name is required', 'warning');
      return;
    }
    if (fields.length === 0) {
      addToast?.('Add at least one field', 'warning');
      return;
    }

    const payload = {
      name: tableName.trim().toUpperCase(),
      table_type: tableType,
      fields: fields.map((f, i) => ({
        name: f.name,
        type: f.type || 'text',
        order: i,
        mandatory: Boolean(f.mandatory),
        show_path: Boolean(f.show_path),
      })),
    };

    setSaving(true);
    try {
      if (isEditing) {
        try {
          await schemaApi.updateTable(editingTable.id, payload);
        } catch (apiErr) {
          console.warn('Backend API update table fallback:', apiErr);
        }
        const stored = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        const updated = stored.map((t) =>
          String(t.id) === String(editingTable.id)
            ? {
                ...t,
                ...payload,
                updated_at: new Date().toISOString(),
              }
            : t
        );
        localStorage.setItem('cf_custom_tables', JSON.stringify(updated));
        addToast?.(`Table "${payload.name}" updated successfully!`, 'success');
      } else {
        try {
          if (groupId) {
            await schemaApi.createTable(groupId, payload);
          } else {
            await schemaApi.createSchema(payload);
          }
        } catch (apiErr) {
          console.warn('Backend API create table fallback:', apiErr);
        }
        const stored = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        const newTable = {
          id: `tbl_${Date.now()}`,
          ...payload,
          client_name: orgName || '—',
          status: 'active',
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        localStorage.setItem('cf_custom_tables', JSON.stringify([newTable, ...stored]));
        addToast?.(`Table "${payload.name}" created successfully!`, 'success');
      }
      onSave();
    } catch (err) {
      addToast?.(err?.response?.data?.message || err?.message || 'Error saving table', 'error');
    } finally {
      setSaving(false);
    }
  };

  const typeMeta = getTableTypeMeta(tableType);
  const TypeIcon = typeMeta.icon;

  return createPortal(
    <>
      <div className="drawer-overlay-backdrop" onClick={onClose} />
      <aside
        className="side-drawer-panel"
        style={{ width: '640px', maxWidth: '95vw', padding: 0, display: 'flex', flexDirection: 'column' }}
      >
        {/* Header */}
        <div
          style={{
            background: '#2563eb',
            color: '#fff',
            height: '48px',
            padding: '0 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
            <Edit3 size={17} />
            <span>{isEditing ? `Edit Table — ${editingTable?.name}` : 'Create New Table'}</span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}>
            <X size={18} />
          </button>
        </div>

        {/* Body */}
        <div
          style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '20px' }}
        >
          {/* ── SECTION 1: TABLE DETAILS ── */}
          <Section icon={<Edit3 size={15} />} title="Table Details">
            {/* Table Name */}
            <div>
              <label style={labelStyle}>
                Table Name <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                value={tableName}
                onChange={(e) => setTableName(e.target.value)}
                placeholder="Enter table name (e.g., Class 10 Students)"
                style={inputStyle}
              />
            </div>

            {/* Table Type — with auto-detection indicator */}
            <div>
              <label style={labelStyle}>
                Table Type
                {typeAuto && (
                  <span
                    style={{
                      marginLeft: '8px',
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: '3px',
                      padding: '1px 7px',
                      borderRadius: '10px',
                      fontSize: '10px',
                      fontWeight: 600,
                      background: '#fef9c3',
                      color: '#713f12',
                      border: '1px solid #fde68a',
                    }}
                  >
                    <Sparkles size={9} /> Auto-detected
                  </span>
                )}
              </label>
              <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginTop: '6px' }}>
                {TABLE_TYPES.map((t) => {
                  const TIcon = t.icon;
                  const sel = tableType === t.value;
                  return (
                    <button
                      key={t.value}
                      type="button"
                      onClick={() => {
                        setTableType(t.value);
                        setTypeAuto(false);
                      }}
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        gap: '6px',
                        height: '34px',
                        padding: '0 8px',
                        borderRadius: '6px',
                        border: sel ? `1px solid ${t.color}` : '1px solid #d1d5db',
                        background: sel ? t.bg : '#ffffff',
                        color: sel ? t.color : '#4b5563',
                        fontWeight: sel ? 700 : 500,
                        fontSize: '12px',
                        cursor: 'pointer',
                        transition: 'all 0.15s',
                        boxShadow: sel ? `0 1px 3px ${t.border}` : 'none',
                      }}
                    >
                      <TIcon size={14} style={{ color: sel ? t.color : '#6b7280', flexShrink: 0 }} />
                      <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                        {t.label}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          </Section>

          {/* ── SECTION 2: ADD NEW FIELD ── */}
          <Section icon={<PlusCircle size={15} />} title="Add New Field">
            <form onSubmit={handleAddField} style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
              <div style={{ display: 'grid', gridTemplateColumns: '1fr 180px', gap: '10px' }}>
                {/* Field Name — with auto-detect type */}
                <div>
                  <label style={labelStyle}>Field Name</label>
                  <div style={{ position: 'relative' }}>
                    <input
                      value={newName}
                      onChange={(e) => handleNewNameChange(e.target.value)}
                      placeholder="e.g., Student Name, Photo, Roll No…"
                      style={inputStyle}
                    />
                    {typeAutoField && (
                      <span
                        style={{
                          position: 'absolute',
                          right: '10px',
                          top: '50%',
                          transform: 'translateY(-50%)',
                          fontSize: '9px',
                          fontWeight: 700,
                          color: '#7c3aed',
                          background: '#f5f3ff',
                          border: '1px solid #ddd6fe',
                          padding: '1px 5px',
                          borderRadius: '8px',
                          whiteSpace: 'nowrap',
                        }}
                      >
                        <Sparkles size={8} style={{ display: 'inline', marginRight: '2px' }} />
                        {FIELD_TYPES.find((t) => t.value === newType)?.label || newType}
                      </span>
                    )}
                  </div>
                </div>
                {/* Field Type */}
                <div>
                  <label style={labelStyle}>Field Type</label>
                  <select
                    value={newType}
                    onChange={(e) => {
                      setNewType(e.target.value);
                      setTypeAutoField(false);
                    }}
                    style={{ ...inputStyle, cursor: 'pointer' }}
                  >
                    {FIELD_TYPES.map((t) => (
                      <option key={t.value} value={t.value}>
                        {t.label}
                      </option>
                    ))}
                  </select>
                </div>
              </div>

              <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
                <button
                  type="submit"
                  style={{
                    background: '#2563eb',
                    color: '#fff',
                    border: 'none',
                    borderRadius: '6px',
                    padding: '8px 20px',
                    fontSize: '13px',
                    fontWeight: 600,
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    cursor: 'pointer',
                  }}
                >
                  <Plus size={14} /> Add Field
                </button>
              </div>
            </form>
          </Section>

          {/* ── SECTION 3: TABLE FIELDS LIST ── */}
          <Section icon={<List size={15} />} title="Table Fields" badge={`${fields.length}/20`}>
            <div
              style={{
                fontSize: '11px',
                color: '#6b7280',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
                marginBottom: '8px',
              }}
            >
              <GripVertical size={12} style={{ color: '#9ca3af' }} />
              <span>Drag rows to reorder • Toggle switch = Required field</span>
            </div>

            {fields.length === 0 ? (
              <div
                style={{
                  border: '2px dashed #e2e8f0',
                  borderRadius: '8px',
                  padding: '24px',
                  textAlign: 'center',
                  background: '#f8fafc',
                  color: '#64748b',
                  fontSize: '12px',
                }}
              >
                <Info size={16} style={{ color: '#3b82f6', marginBottom: '6px' }} />
                <p style={{ margin: 0 }}>No fields added yet. Use the form above to add fields.</p>
              </div>
            ) : (
              <div style={{ display: 'flex', flexDirection: 'column', gap: '6px' }}>
                {fields.map((f, idx) => {
                  const isPhoto = ['photo', 'rel_photo', 'signature'].includes(f.type);
                  const isDragTarget = dragOver === idx;
                  return (
                    <div
                      key={f.id}
                      draggable
                      onDragStart={(e) => onDragStart(e, idx)}
                      onDragOver={(e) => onDragOver(e, idx)}
                      onDrop={(e) => onDrop(e, idx)}
                      onDragEnd={onDragEnd}
                      style={{
                        background: '#fff',
                        border: `1px solid ${isDragTarget ? '#2563eb' : '#e2e8f0'}`,
                        borderLeft: `3px solid ${f.mandatory ? '#ef4444' : '#2563eb'}`,
                        borderRadius: '6px',
                        padding: '7px 10px',
                        display: 'flex',
                        alignItems: 'center',
                        gap: '8px',
                        boxShadow: isDragTarget ? '0 4px 12px rgba(37,99,235,0.15)' : '0 1px 3px rgba(0,0,0,0.03)',
                        transform: isDragTarget ? 'scale(1.01)' : 'none',
                        transition: 'all 0.12s',
                        cursor: 'grab',
                        opacity: dragIdx.current === idx ? 0.5 : 1,
                      }}
                    >
                      {/* Drag grip + arrow reorder */}
                      <div
                        style={{ display: 'flex', alignItems: 'center', gap: '2px', color: '#94a3b8', flexShrink: 0 }}
                      >
                        <GripVertical size={14} />
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '1px' }}>
                          <button
                            type="button"
                            disabled={idx === 0}
                            onClick={() => handleMoveUp(idx)}
                            style={{
                              border: 'none',
                              background: 'transparent',
                              cursor: idx === 0 ? 'default' : 'pointer',
                              padding: 0,
                              color: idx === 0 ? '#d1d5db' : '#6b7280',
                              lineHeight: 1,
                            }}
                          >
                            ▲
                          </button>
                          <button
                            type="button"
                            disabled={idx === fields.length - 1}
                            onClick={() => handleMoveDown(idx)}
                            style={{
                              border: 'none',
                              background: 'transparent',
                              cursor: idx === fields.length - 1 ? 'default' : 'pointer',
                              padding: 0,
                              color: idx === fields.length - 1 ? '#d1d5db' : '#6b7280',
                              lineHeight: 1,
                            }}
                          >
                            ▼
                          </button>
                        </div>
                      </div>

                      {/* Order badge */}
                      <span
                        style={{
                          width: '20px',
                          height: '20px',
                          borderRadius: '50%',
                          background: '#f1f5f9',
                          color: '#475569',
                          fontSize: '10px',
                          fontWeight: 700,
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        {idx + 1}
                      </span>

                      {/* Field Name + Path Checkbox nested inside */}
                      <div style={{ flex: 1, position: 'relative', display: 'flex', alignItems: 'center' }}>
                        <input
                          value={f.name}
                          onChange={(e) => handleFieldNameChange(f.id, e.target.value)}
                          style={{
                            width: '100%',
                            height: '30px',
                            paddingLeft: '8px',
                            paddingRight: isPhoto ? '68px' : '8px',
                            border: '1px solid #e2e8f0',
                            borderRadius: '4px',
                            fontSize: '12px',
                            fontWeight: 600,
                            color: '#111827',
                            outline: 'none',
                            cursor: 'text',
                          }}
                          onMouseDown={(e) => e.stopPropagation()}
                        />
                        {isPhoto && (
                          <label
                            onMouseDown={(e) => e.stopPropagation()}
                            style={{
                              position: 'absolute',
                              right: '4px',
                              top: '50%',
                              transform: 'translateY(-50%)',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '3px',
                              fontSize: '10px',
                              fontWeight: 700,
                              color: f.show_path ? '#7c3aed' : '#9ca3af',
                              cursor: 'pointer',
                              userSelect: 'none',
                              background: f.show_path ? '#f5f3ff' : '#f8fafc',
                              padding: '2px 5px',
                              borderRadius: '3px',
                              border: `1px solid ${f.show_path ? '#ddd6fe' : '#e2e8f0'}`,
                            }}
                            title="Include file path in exports"
                          >
                            <input
                              type="checkbox"
                              checked={Boolean(f.show_path)}
                              onChange={(e) => setFieldProp(f.id, 'show_path', e.target.checked)}
                              style={{ width: '11px', height: '11px', cursor: 'pointer', accentColor: '#7c3aed' }}
                            />
                            <span>Path</span>
                          </label>
                        )}
                      </div>

                      {/* Field Type */}
                      <select
                        value={f.type || 'text'}
                        onChange={(e) => setFieldProp(f.id, 'type', e.target.value)}
                        onMouseDown={(e) => e.stopPropagation()}
                        style={{
                          height: '30px',
                          padding: '0 6px',
                          border: '1px solid #e2e8f0',
                          borderRadius: '4px',
                          fontSize: '11px',
                          background: '#fff',
                          color: '#374151',
                          outline: 'none',
                          cursor: 'pointer',
                          maxWidth: '130px',
                        }}
                      >
                        {FIELD_TYPES.map((t) => (
                          <option key={t.value} value={t.value}>
                            {t.label}
                          </option>
                        ))}
                      </select>

                      {/* Required toggle — ON = required (red left border), OFF = optional */}
                      <div
                        style={{
                          display: 'flex',
                          flexDirection: 'column',
                          alignItems: 'center',
                          gap: '2px',
                          flexShrink: 0,
                        }}
                      >
                        <span
                          style={{
                            fontSize: '9px',
                            color: f.mandatory ? '#ef4444' : '#9ca3af',
                            fontWeight: 700,
                            lineHeight: 1,
                          }}
                        >
                          {f.mandatory ? 'REQ' : 'OPT'}
                        </span>
                        <button
                          type="button"
                          onClick={() => setFieldProp(f.id, 'mandatory', !f.mandatory)}
                          title={
                            f.mandatory ? 'Required — click to make optional' : 'Optional — click to make required'
                          }
                          style={{
                            width: '34px',
                            height: '18px',
                            borderRadius: '9px',
                            background: f.mandatory ? '#ef4444' : '#cbd5e1',
                            border: 'none',
                            cursor: 'pointer',
                            position: 'relative',
                            transition: 'background 0.15s',
                            flexShrink: 0,
                          }}
                        >
                          <span
                            style={{
                              position: 'absolute',
                              top: '2px',
                              left: f.mandatory ? '17px' : '2px',
                              width: '14px',
                              height: '14px',
                              borderRadius: '50%',
                              background: '#fff',
                              transition: 'left 0.15s',
                              boxShadow: '0 1px 2px rgba(0,0,0,0.2)',
                            }}
                          />
                        </button>
                      </div>

                      {/* Delete */}
                      <button
                        type="button"
                        onClick={() => handleDeleteField(f.id)}
                        style={{
                          border: 'none',
                          background: 'transparent',
                          color: '#d1d5db',
                          cursor: 'pointer',
                          padding: '2px',
                          flexShrink: 0,
                        }}
                        title="Remove field"
                      >
                        <X size={14} />
                      </button>
                    </div>
                  );
                })}
              </div>
            )}
          </Section>
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '14px 20px',
            borderTop: '1px solid #334155',
            background: '#1e293b',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <TypeIcon size={14} style={{ color: typeMeta.color }} />
            <span style={{ fontSize: '12px', fontWeight: 600, color: typeMeta.color }}>{typeMeta.label}</span>
            <span style={{ fontSize: '11px', color: '#94a3b8' }}>
              • {fields.length} field{fields.length !== 1 ? 's' : ''}
            </span>
          </div>
          <div style={{ display: 'flex', gap: '10px' }}>
            <button
              onClick={onClose}
              style={{ ...cancelBtnStyle, background: '#334155', color: '#ffffff', border: '1px solid #475569' }}
            >
              <X size={14} /> Cancel
            </button>
            <button
              onClick={handleSubmit}
              disabled={saving}
              style={{
                ...saveBtnStyle,
                opacity: saving ? 0.7 : 1,
                cursor: saving ? 'wait' : 'pointer',
              }}
            >
              {saving ? (
                <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} />
              ) : isEditing ? (
                <Check size={14} />
              ) : (
                <Plus size={14} />
              )}
              <span>{saving ? 'Saving…' : isEditing ? 'Update Table' : 'Create Table'}</span>
            </button>
          </div>
        </div>
      </aside>
    </>,
    document.body
  );
}

/* ═══════════════════════════════════════════════════════════════════════════
   CREATE WITH XLSX DRAWER
   ═══════════════════════════════════════════════════════════════════════════ */
function CreateWithXlsxDrawer({ groupId, orgName, onClose, onSave, addToast }) {
  const [tableName, setTableName] = useState('');
  const [tableType, setTableType] = useState('custom');
  const [typeAuto, setTypeAuto] = useState(false);
  const [file, setFile] = useState(null);
  const [fileName, setFileName] = useState('');
  const [parsedHeaders, setParsedHeaders] = useState([]);
  const [saving, setSaving] = useState(false);

  /* Auto-detect table type from name */
  useEffect(() => {
    if (!tableName.trim()) {
      setTypeAuto(false);
      return;
    }
    const detected = inferTableType(tableName, orgName);
    if (detected !== 'custom') {
      setTableType(detected);
      setTypeAuto(true);
    } else {
      setTypeAuto(false);
    }
  }, [tableName, orgName]);

  const handleFileSelect = async (e) => {
    const f = e.target.files?.[0];
    if (!f) return;
    setFile(f);
    setFileName(f.name);
    try {
      const buf = await f.arrayBuffer();
      const wb = XLSX.read(buf, { type: 'array' });
      const firstSheetName = wb.SheetNames[0];
      if (firstSheetName) {
        const ws = wb.Sheets[firstSheetName];
        const rows = XLSX.utils.sheet_to_json(ws, { header: 1, defval: '' });
        const headers = (rows[0] || []).filter(Boolean).map(String);
        setParsedHeaders(headers);
        addToast?.(`Parsed ${headers.length} column headers from ${f.name}`, 'success');
      }
    } catch (parseErr) {
      console.warn('XLSX header parse warning:', parseErr);
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!tableName.trim()) {
      addToast?.('Table Name is required', 'warning');
      return;
    }
    if (!file) {
      addToast?.('Please select an Excel (.xlsx) file', 'warning');
      return;
    }
    if (!groupId) {
      addToast?.('Group ID not found. Please refresh.', 'error');
      return;
    }

    setSaving(true);
    try {
      const formData = new FormData();
      formData.append('file', file);
      formData.append('table_name', tableName.trim().toUpperCase());
      formData.append('table_type', tableType);

      const res = await schemaApi.createTableFromXlsx(groupId, formData);
      if (res?.success === false) throw new Error(res.message || 'Create failed');
      addToast?.(`Table "${tableName}" created from XLSX! (${res.cards_created || 0} records imported)`, 'success');
      onSave();
    } catch (err) {
      addToast?.(err?.response?.data?.message || err?.message || 'Error creating table from XLSX', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        right: 0,
        bottom: 0,
        width: '620px',
        minWidth: '580px',
        maxWidth: '95vw',
        background: '#fff',
        boxShadow: '-8px 0 32px rgba(0,0,0,0.18)',
        zIndex: 1000,
        display: 'flex',
        flexDirection: 'column',
      }}
    >
      {/* Header */}
      <div
        style={{
          background: '#16a34a',
          color: '#fff',
          height: '48px',
          padding: '0 20px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexShrink: 0,
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <FileSpreadsheet size={18} />
          <span>Create Table Setting with XLSX</span>
        </div>
        <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}>
          <X size={18} />
        </button>
      </div>

      <form
        onSubmit={handleSubmit}
        style={{ flex: 1, overflowY: 'auto', padding: '20px', display: 'flex', flexDirection: 'column', gap: '16px' }}
      >
        {/* Info banner */}
        <div
          style={{
            padding: '12px 16px',
            borderRadius: '8px',
            background: '#f0fdf4',
            border: '1px solid #bbf7d0',
            display: 'flex',
            gap: '10px',
            alignItems: 'flex-start',
          }}
        >
          <FileSpreadsheet size={20} style={{ color: '#16a34a', flexShrink: 0, marginTop: '1px' }} />
          <div>
            <p style={{ margin: 0, fontWeight: 700, fontSize: '13px', color: '#14532d' }}>
              Upload Excel (.xlsx) Schema File
            </p>
            <p style={{ margin: '2px 0 0', fontSize: '11px', color: '#15803d', lineHeight: 1.5 }}>
              The first row of your Excel file will be parsed as field column headers. All data rows will be imported
              automatically.
            </p>
          </div>
        </div>

        {/* Table Name */}
        <div>
          <label style={labelStyle}>
            Table Name <span style={{ color: '#ef4444' }}>*</span>
          </label>
          <input
            required
            value={tableName}
            onChange={(e) => setTableName(e.target.value)}
            placeholder="e.g., Class 10 Students"
            style={inputStyle}
          />
        </div>

        {/* Table Type */}
        <div>
          <label style={labelStyle}>
            Table Type
            {typeAuto && (
              <span
                style={{
                  marginLeft: '8px',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '3px',
                  padding: '1px 7px',
                  borderRadius: '10px',
                  fontSize: '10px',
                  fontWeight: 600,
                  background: '#fef9c3',
                  color: '#713f12',
                  border: '1px solid #fde68a',
                }}
              >
                <Sparkles size={9} /> Auto-detected
              </span>
            )}
          </label>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '8px', marginTop: '6px' }}>
            {TABLE_TYPES.map((t) => {
              const TIcon = t.icon;
              const sel = tableType === t.value;
              return (
                <button
                  key={t.value}
                  type="button"
                  onClick={() => {
                    setTableType(t.value);
                    setTypeAuto(false);
                  }}
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    gap: '6px',
                    height: '34px',
                    padding: '0 8px',
                    borderRadius: '6px',
                    border: sel ? `1px solid ${t.color}` : '1px solid #d1d5db',
                    background: sel ? t.bg : '#ffffff',
                    color: sel ? t.color : '#4b5563',
                    fontWeight: sel ? 700 : 500,
                    fontSize: '12px',
                    cursor: 'pointer',
                    transition: 'all 0.15s',
                    boxShadow: sel ? `0 1px 3px ${t.border}` : 'none',
                  }}
                >
                  <TIcon size={14} style={{ color: sel ? t.color : '#6b7280', flexShrink: 0 }} />
                  <span style={{ whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{t.label}</span>
                </button>
              );
            })}
          </div>
        </div>

        {/* File Upload */}
        <div>
          <label style={labelStyle}>
            Select Excel (.xlsx / .xls) File <span style={{ color: '#ef4444' }}>*</span>
          </label>
          <div
            style={{
              border: '2px dashed #cbd5e1',
              borderRadius: '8px',
              padding: '20px',
              textAlign: 'center',
              background: '#f8fafc',
              cursor: 'pointer',
            }}
          >
            <input
              type="file"
              accept=".xlsx,.xls,.csv"
              onChange={handleFileSelect}
              id="xlsx-file-input"
              style={{ display: 'none' }}
            />
            <label
              htmlFor="xlsx-file-input"
              style={{ cursor: 'pointer', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '8px' }}
            >
              <Upload size={28} style={{ color: '#16a34a' }} />
              <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
                {fileName ? `✓ ${fileName}` : 'Drag & drop or click to browse'}
              </span>
              <span style={{ fontSize: '10px', color: '#64748b' }}>Supports .xlsx, .xls, .csv · Max 50 MB</span>
            </label>
          </div>
        </div>

        {/* Parsed headers preview */}
        {parsedHeaders.length > 0 && (
          <div style={{ background: '#fff', borderRadius: '8px', border: '1px solid #e2e8f0', padding: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
              <CheckCircle2 size={14} style={{ color: '#16a34a' }} />
              <span style={{ fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>
                Detected {parsedHeaders.length} column headers:
              </span>
            </div>
            <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
              {parsedHeaders.map((hdr) => (
                <span
                  key={hdr}
                  style={{
                    padding: '3px 9px',
                    borderRadius: '5px',
                    fontSize: '11px',
                    fontWeight: 600,
                    background: '#f0fdf4',
                    color: '#15803d',
                    border: '1px solid #bbf7d0',
                  }}
                >
                  {hdr}
                </span>
              ))}
            </div>
          </div>
        )}

        {/* Footer */}
        <div
          style={{
            marginTop: 'auto',
            paddingTop: '16px',
            borderTop: '1px solid #e5e7eb',
            display: 'flex',
            justifyContent: 'flex-end',
            gap: '10px',
          }}
        >
          <button type="button" onClick={onClose} style={cancelBtnStyle}>
            <X size={14} /> Cancel
          </button>
          <button
            type="submit"
            disabled={saving}
            style={{ ...saveBtnStyle, background: '#16a34a', opacity: saving ? 0.7 : 1 }}
          >
            {saving ? <Loader2 size={14} style={{ animation: 'spin 1s linear infinite' }} /> : <Save size={14} />}
            <span>{saving ? 'Creating…' : 'Create Table Setting'}</span>
          </button>
        </div>
      </form>
    </div>
  );
}

/* ── Helpers ── */
function Section({ icon, title, badge, children }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
      <div
        style={{
          background: '#2563eb',
          color: '#fff',
          borderRadius: '6px',
          padding: '9px 14px',
          fontSize: '13px',
          fontWeight: 700,
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {icon} <span>{title}</span>
        </div>
        {badge && (
          <span
            style={{
              background: 'rgba(255,255,255,0.25)',
              color: '#fff',
              padding: '2px 8px',
              borderRadius: '10px',
              fontSize: '11px',
              fontWeight: 700,
            }}
          >
            {badge}
          </span>
        )}
      </div>
      {children}
    </div>
  );
}

/* ── Style constants ── */
const labelStyle = {
  display: 'block',
  fontSize: '12px',
  fontWeight: 600,
  color: '#374151',
  marginBottom: '6px',
};
const inputStyle = {
  width: '100%',
  height: '38px',
  padding: '0 12px',
  border: '1px solid #d1d5db',
  borderRadius: '6px',
  fontSize: '13px',
  color: '#111827',
  outline: 'none',
  boxSizing: 'border-box',
  fontFamily: 'var(--font-family)',
};
const cancelBtnStyle = {
  padding: '7px 16px',
  borderRadius: '6px',
  border: '1px solid #d1d5db',
  background: '#f9fafb',
  color: '#374151',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '4px',
};
const saveBtnStyle = {
  padding: '7px 20px',
  borderRadius: '6px',
  border: 'none',
  background: '#2563eb',
  color: '#fff',
  fontSize: '13px',
  fontWeight: 600,
  cursor: 'pointer',
  display: 'inline-flex',
  alignItems: 'center',
  gap: '6px',
};
