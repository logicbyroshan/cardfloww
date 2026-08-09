import React, { useState, useEffect, useCallback, useMemo } from "react";
import {
  Clock, CheckCircle, ThumbsUp, Download, Layers, Settings,
  Upload, Trash2, ArrowUp, RefreshCw, X, Loader2,
  SlidersHorizontal, FileSpreadsheet, Plus, ToggleRight, School,
  BookOpen, Briefcase, Settings2, FolderKanban, CheckCircle2, Pencil, Save
} from "lucide-react";
import WatermarkLogo from "../common/WatermarkLogo";
import CreateXlsxModal from "../common/CreateXlsxModal";
import CustomSelect from "../common/CustomSelect";
import { cardApi, schemaApi, clientApi } from "../../services/api";

const STATUS_TABS = ["All", "Active", "Inactive"];

/* ── Table Type metadata ── */
const TABLE_TYPES = [
  { value: 'school_student',  label: 'School Student',  icon: School,   color: '#2563eb', bg: '#eff6ff', border: '#bfdbfe' },
  { value: 'college_student', label: 'College Student', icon: BookOpen, color: '#7c3aed', bg: '#f5f3ff', border: '#ddd6fe' },
  { value: 'staff',           label: 'Staff',           icon: Briefcase,color: '#059669', bg: '#ecfdf5', border: '#a7f3d0' },
  { value: 'custom',          label: 'Custom',          icon: Settings2, color: '#d97706', bg: '#fffbeb', border: '#fde68a' },
];

function getTableTypeMeta(value) {
  return TABLE_TYPES.find(t => t.value === value) || TABLE_TYPES[3];
}

function inferTableType(tableName = '', orgName = '') {
  const name = (tableName || '').toLowerCase().trim();
  const org  = (orgName || '').toLowerCase().trim();
  const staffRe   = /\b(staff|teacher|teachers|employee|employees|emp|faculty|personnel|hr|driver|workers|management)\b/;
  const collegeRe = /\b(college|university|institute|polytechnic|degree|btech|mtech|bca|mca|mba|bsc|msc|ba|ma|bcom|mcom|semester|sem|branch|dept|department)\b/;
  const schoolRe  = /\b(school|vidyalaya|academy|convent|class|std|standard|grade|section|sec)\b/;

  if (staffRe.test(name)) return 'staff';
  if (collegeRe.test(name)) return 'college_student';
  if (schoolRe.test(name)) return 'school_student';
  if (collegeRe.test(org)) return 'college_student';
  return 'school_student';
}

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

const FIELD_TYPES = [
  { value: 'text',       label: 'Text' },
  { value: 'number',     label: 'Number' },
  { value: 'email',      label: 'Email' },
  { value: 'date',       label: 'Date' },
  { value: 'photo',      label: 'Photo' },
  { value: 'rel_photo',  label: 'Relation Photo' },
  { value: 'signature',  label: 'Signature' },
  { value: 'barcode',    label: 'Barcode' },
  { value: 'qr_code',    label: 'QR Code' },
  { value: 'class',      label: 'Class' },
  { value: 'section',    label: 'Section' },
  { value: 'select',     label: 'Select / Dropdown' },
  { value: 'textarea',   label: 'Textarea' },
];

function getTableCounts(t) {
  if (!t) return { pending: 0, verified: 0, approved: 0, download: 0, pool: 0, rpCnt: 0, reqCnt: 0, confCnt: 0 };
  let pending = t.pending_count ?? t.pending ?? 0;
  let verified = t.verified_count ?? t.verified ?? 0;
  let approved = t.approved_count ?? t.approved ?? 0;
  let download = t.download_count ?? t.downloaded ?? t.download ?? t.printed ?? 0;
  let pool = t.pool_count ?? t.deleted ?? t.pool ?? 0;

  let rpCnt = t.reprint_count ?? t.reprint ?? 0;
  let reqCnt = t.reprint_request_count ?? t.reprint_request ?? t.request ?? t.requested ?? 0;
  let confCnt = t.reprint_confirmed_count ?? t.reprint_confirmed ?? t.confirmed ?? 0;

  try {
    const listByTableId = JSON.parse(localStorage.getItem(`cf_custom_cards_${t.id}`) || '[]');
    const listByTableName = JSON.parse(localStorage.getItem(`cf_custom_cards_${t.name}`) || '[]');
    const allCustomCards = JSON.parse(localStorage.getItem('cf_custom_cards') || '[]');
    const filteredGlobalCards = allCustomCards.filter(c => String(c.table_id || c.table) === String(t.id) || String(c.table_name) === String(t.name));

    const allCards = [...listByTableId, ...listByTableName, ...filteredGlobalCards];

    if (allCards.length > 0) {
      pending += allCards.filter(c => !c.status || c.status === 'pending').length;
      verified += allCards.filter(c => c.status === 'verified').length;
      approved += allCards.filter(c => c.status === 'approved').length;
      download += allCards.filter(c => c.status === 'download' || c.status === 'printed').length;
      pool += allCards.filter(c => c.status === 'pool' || c.status === 'deleted').length;
    }
  } catch { /* ignore */ }

  return { pending, verified, approved, download, pool, rpCnt, reqCnt, confCnt };
}

function getDisplayOrgName(clientName, activeOrg) {
  const ignoreList = ['—', 'Primary Org', 'Default Organisation', 'Default Organization', 'null', 'undefined'];
  if (clientName && !ignoreList.includes(String(clientName).trim())) {
    return String(clientName).trim();
  }
  if (activeOrg && !ignoreList.includes(String(activeOrg).trim())) {
    return String(activeOrg).trim();
  }
  return '';
}

export default function CardTableView({ addToast, onNavigate }) {
  const [tables, setTables]               = useState([]);
  const [loading, setLoading]             = useState(true);
  const [statusTab, setStatusTab]         = useState("All");
  const [clientOrg, setClientOrg]         = useState("");
  const [showCreateXlsxModal, setShowCreateXlsxModal] = useState(false);

  /* Table selection in main view (Default to NULL so buttons are only active when selected!) */
  const [selectedTableId, setSelectedTableId] = useState(null);

  /* Table Setting Drawers & Modals */
  const [showAddEditDrawer, setShowAddEditDrawer] = useState(false);
  const [editingTable, setEditingTable]           = useState(null);
  const [settingModalTable, setSettingModalTable] = useState(null);
  const [groupId, setGroupId]                     = useState(1);

  /* Modal states for bulk actions */
  const [activeModal, setActiveModal]     = useState(null);
  const [deleteCodeInput, setDeleteCodeInput] = useState("");

  /* Fetch client org name */
  useEffect(() => {
    (async () => {
      try {
        const data = await clientApi.getActive?.({ page_size: 1 });
        const clients = data?.results || data?.clients || (Array.isArray(data) ? data : []);
        if (clients.length > 0) {
          setClientOrg(clients[0].name || clients[0].client_name || '');
          if (clients[0].group_id || clients[0].id) {
            setGroupId(clients[0].group_id || clients[0].id);
          }
        }
      } catch { /* fallback */ }
    })();
  }, []);

  /* Load tables list */
  const loadTables = useCallback(async () => {
    setLoading(true);
    let local = [];
    try {
      local = JSON.parse(localStorage.getItem("cf_custom_tables") || "[]");
      const dummyNames = ['Class 1st to 5th', 'Class 6th to 10th', 'Class 11th & 12th', 'Staff & Teachers'];
      local = local.filter(t => t && !dummyNames.includes(t.name));
    } catch { local = []; }

    try {
      const data = await schemaApi.getSchemas();
      const list = data?.tables || data?.results || (Array.isArray(data) ? data : []);
      const merged = [...local];
      (list || []).forEach(item => {
        if (!merged.some(t => String(t.id) === String(item.id) || t.name === item.name)) {
          merged.push(item);
        }
      });
      setTables(merged);
    } catch {
      setTables(local);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { loadTables(); }, [loadTables]);

  const selectedTable = useMemo(() => tables.find(t => String(t.id) === String(selectedTableId)), [tables, selectedTableId]);

  /* Toggle Row Selection */
  const handleSelectRow = (tableId) => {
    setSelectedTableId(prev => (String(prev) === String(tableId) ? null : tableId));
  };

  /* Toggle Table Status */
  const handleToggleStatus = async (tableToToggle) => {
    const target = tableToToggle || selectedTable;
    if (!target) return;
    try {
      try {
        await schemaApi.toggleTableStatus(target.id);
      } catch { /* fallback local */ }

      const local = JSON.parse(localStorage.getItem("cf_custom_tables") || "[]");
      const updated = local.map(t => {
        if (String(t.id) === String(target.id)) {
          const nextActive = t.is_active === false;
          return { ...t, is_active: nextActive, status: nextActive ? 'active' : 'inactive' };
        }
        return t;
      });
      localStorage.setItem("cf_custom_tables", JSON.stringify(updated));

      setTables(prev => prev.map(t => {
        if (String(t.id) === String(target.id)) {
          const nextActive = t.is_active === false;
          return { ...t, is_active: nextActive, status: nextActive ? 'active' : 'inactive' };
        }
        return t;
      }));

      addToast?.(`Status updated for "${target.name}"`, 'success');
    } catch {
      addToast?.('Error updating table status', 'error');
    }
  };

  /* Delete Table */
  const handleDeleteTable = async (tableToDelete) => {
    const target = tableToDelete || selectedTable;
    if (!target) return;
    if (!window.confirm(`Delete table "${target.name}"? This action cannot be undone.`)) return;

    try {
      try {
        await schemaApi.deleteTable(target.id);
      } catch { /* fallback local */ }

      const local = JSON.parse(localStorage.getItem("cf_custom_tables") || "[]");
      const updated = local.filter(t => String(t.id) !== String(target.id));
      localStorage.setItem("cf_custom_tables", JSON.stringify(updated));

      addToast?.(`Table "${target.name}" deleted`, 'success');
      if (selectedTableId === target.id) setSelectedTableId(null);
      loadTables();
    } catch {
      addToast?.('Error deleting table', 'error');
    }
  };

  /* Download Blank Template */
  const handleDownloadBlankTemplate = () => {
    addToast?.('Downloading Blank Excel Template (.xlsx)…', 'info');
  };

  const filteredTables = useMemo(() => {
    return tables.filter(t => {
      if (!t) return false;
      const isActive = t.is_active !== false;
      if (statusTab === 'Active') return isActive;
      if (statusTab === 'Inactive') return !isActive;
      return true;
    });
  }, [tables, statusTab]);

  /* Open IDCardActionsView */
  const openIDCardActions = (table, status = 'pending') => {
    if (onNavigate) {
      onNavigate('idcard-actions', { tableId: table.id, status });
    }
  };

  /* Confirm Delete All */
  const confirmDeleteAll = async () => {
    if (!deleteCodeInput) { addToast?.('Please enter confirmation code', 'warning'); return; }
    if (!selectedTable) return;
    try {
      await cardApi.deleteAllCards(selectedTable.id, { code: deleteCodeInput });
      addToast?.(`All cards in "${selectedTable.name}" deleted successfully`, 'success');
      setActiveModal(null);
      loadTables();
    } catch (err) {
      addToast?.(err?.response?.data?.message || 'Error deleting cards. Check code.', 'error');
    }
  };

  return (
    <div className="view-container" style={{ display: "flex", flexDirection: "column", height: "100%", overflow: "hidden" }}>
      
      {/* ── ACTION BAR / TOPBAR ── */}
      <div className="action-bar" id="idcard-group-action-bar" style={{ background: '#1e1e2e', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', height: '50px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxSizing: 'border-box' }}>
        
        {/* Left Side: Status Filters | 4 Table Action Buttons | 2 XLSX Buttons */}
        <div className="action-bar-left" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          
          {/* Section 1: Status Filter Tabs */}
          <div className="status-tabs" style={{ display: 'flex', alignItems: 'center', background: 'rgba(255, 255, 255, 0.08)', border: '1px solid rgba(255, 255, 255, 0.18)', borderRadius: '5px', padding: '2px', gap: '2px', height: '28px', boxSizing: 'border-box' }}>
            {STATUS_TABS.map((t) => (
              <button
                key={t}
                onClick={() => setStatusTab(t)}
                className={`status-tab${statusTab === t ? ' active' : ''}`}
                style={{
                  padding: '0 10px', height: '22px', fontSize: '11px', lineHeight: '22px', borderRadius: '3px',
                  border: 'none', cursor: 'pointer', background: statusTab === t ? '#2563eb' : 'transparent',
                  color: statusTab === t ? '#ffffff' : '#cbd5e1', fontWeight: statusTab === t ? 700 : 600,
                  fontFamily: 'var(--font-family)', transition: 'all 0.15s',
                  boxShadow: statusTab === t ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                  display: 'inline-flex', alignItems: 'center'
                }}
              >
                {t}
              </button>
            ))}
          </div>

          {/* | Divider */}
          <span style={{ width: '1px', height: '16px', background: 'rgba(255, 255, 255, 0.2)', margin: '0 4px' }} />

          {/* Section 2: 4 Table Buttons (Add always enabled; Edit, Delete, Active require row selection!) */}
          <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            
            {/* 1. Add Button (Always Enabled) */}
            <button
              className="btn"
              onClick={() => { setEditingTable(null); setShowAddEditDrawer(true); }}
              title="Add New Table Setting"
              style={{ background: '#2563eb', color: '#ffffff', border: '1px solid #2563eb', height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '5px', boxSizing: 'border-box' }}
            >
              <Plus size={13} /> <span>Add</span>
            </button>

            {/* 2. Edit Button (Requires Table Selection) */}
            <button
              className="btn"
              disabled={!selectedTable}
              onClick={() => { setEditingTable(selectedTable); setShowAddEditDrawer(true); }}
              title={!selectedTable ? "Select a table row to edit" : `Edit ${selectedTable.name}`}
              style={{
                background: selectedTable ? '#2563eb' : 'rgba(255, 255, 255, 0.08)',
                color: selectedTable ? '#ffffff' : 'rgba(255, 255, 255, 0.4)',
                border: selectedTable ? '1px solid #2563eb' : '1px solid rgba(255, 255, 255, 0.15)',
                height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px',
                cursor: selectedTable ? 'pointer' : 'not-allowed', display: 'inline-flex', alignItems: 'center', gap: '5px', boxSizing: 'border-box',
                opacity: selectedTable ? 1 : 0.6
              }}
            >
              <Pencil size={13} /> <span>Edit</span>
            </button>

            {/* 3. Delete Button (Requires Table Selection) */}
            <button
              className="btn"
              disabled={!selectedTable}
              onClick={() => handleDeleteTable(selectedTable)}
              title={!selectedTable ? "Select a table row to delete" : `Delete ${selectedTable.name}`}
              style={{
                background: selectedTable ? '#ef4444' : 'rgba(255, 255, 255, 0.08)',
                color: selectedTable ? '#ffffff' : 'rgba(255, 255, 255, 0.4)',
                border: selectedTable ? '1px solid #ef4444' : '1px solid rgba(255, 255, 255, 0.15)',
                height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px',
                cursor: selectedTable ? 'pointer' : 'not-allowed', display: 'inline-flex', alignItems: 'center', gap: '5px', boxSizing: 'border-box',
                opacity: selectedTable ? 1 : 0.6
              }}
            >
              <Trash2 size={13} /> <span>Delete</span>
            </button>

            {/* 4. Active Button (Requires Table Selection) */}
            <button
              className="btn"
              disabled={!selectedTable}
              onClick={() => handleToggleStatus(selectedTable)}
              title={!selectedTable ? "Select a table row to toggle status" : `Toggle status for ${selectedTable.name}`}
              style={{
                background: selectedTable ? '#f59e0b' : 'rgba(255, 255, 255, 0.08)',
                color: selectedTable ? '#ffffff' : 'rgba(255, 255, 255, 0.4)',
                border: selectedTable ? '1px solid #f59e0b' : '1px solid rgba(255, 255, 255, 0.15)',
                height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px',
                cursor: selectedTable ? 'pointer' : 'not-allowed', display: 'inline-flex', alignItems: 'center', gap: '5px', boxSizing: 'border-box',
                opacity: selectedTable ? 1 : 0.6
              }}
            >
              <ToggleRight size={13} /> <span>Active</span>
            </button>
          </div>

          {/* | Divider */}
          <span style={{ width: '1px', height: '16px', background: 'rgba(255, 255, 255, 0.2)', margin: '0 4px' }} />

          {/* Section 3: 2 XLSX Buttons Together (Download Template & Create with XLSX) */}
          <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <button
              className="btn"
              onClick={handleDownloadBlankTemplate}
              title="Download Blank XLSX Template"
              style={{ background: 'rgba(255, 255, 255, 0.08)', color: '#ffffff', border: '1px solid rgba(255, 255, 255, 0.18)', height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '5px', boxSizing: 'border-box' }}
            >
              <Download size={13} /> <span>Download Template</span>
            </button>

            <button
              className="btn"
              onClick={() => setShowCreateXlsxModal(true)}
              title="Create table directly from an XLSX file"
              style={{ background: '#10b981', color: '#ffffff', border: '1px solid #10b981', height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px', cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '5px', boxSizing: 'border-box' }}
            >
              <FileSpreadsheet size={13} /> <span>Create with XLSX</span>
            </button>
          </div>
        </div>

        {/* Right Side: Bulk Actions for Selected Table */}
        <div className="action-bar-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                type="button"
                onClick={() => setActiveModal('reupload')}
                style={bulkBtnStyle('reupload', !selectedTable)}
                disabled={!selectedTable}
                title={!selectedTable ? "Select a table row first" : `Reupload Images for ${selectedTable.name}`}
              >
                <Upload size={12} /> Reupload Image
              </button>

              <button
                type="button"
                onClick={() => setActiveModal('download-all')}
                style={bulkBtnStyle('downloadAll', !selectedTable)}
                disabled={!selectedTable}
                title={!selectedTable ? "Select a table row first" : `Download All ID Cards for ${selectedTable.name}`}
              >
                <Download size={12} /> Download All ID Card
              </button>

              <button
                type="button"
                onClick={() => { setDeleteCodeInput(''); setActiveModal('delete-all'); }}
                style={bulkBtnStyle('deleteAll', !selectedTable)}
                disabled={!selectedTable}
                title={!selectedTable ? "Select a table row first" : `Delete All ID Cards for ${selectedTable.name}`}
              >
                <Trash2 size={12} /> Delete All ID Cards
              </button>

              <button
                type="button"
                onClick={() => setActiveModal('upgrade')}
                style={bulkBtnStyle('upgradeClass', !selectedTable)}
                disabled={!selectedTable}
                title={!selectedTable ? "Select a table row first" : `Upgrade All Class for ${selectedTable.name}`}
              >
                <ArrowUp size={12} /> Upgrade All Class
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── MAIN TABLE GROUP DATA TABLE ── */}
      <div id="gs-table-container" style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}>
        <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
          <WatermarkLogo />
          {loading ? (
            <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
              <Loader2 size={28} style={{ animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }} />
              <span>Loading Table Group data…</span>
            </div>
          ) : filteredTables.length === 0 ? (
            <div style={{ padding: '60px 20px', textAlign: 'center', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
              <FolderKanban size={40} style={{ color: '#cbd5e1', marginBottom: '12px' }} />
              <h4 style={{ margin: '0 0 6px', color: '#334155', fontSize: '15px', fontWeight: 600 }}>No Table Settings Found</h4>
              <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>Click <strong>Add</strong> or <strong>Create with XLSX</strong> to create your first table setting.</p>
            </div>
          ) : (
            <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead style={{ position: 'sticky', top: 0, zIndex: 10, background: '#2d3748', borderTop: '1px solid rgba(255, 255, 255, 0.25)', borderBottom: '1px solid #1a202c' }}>
                <tr>
                  <th rowSpan="2" style={{ width: '50px', textAlign: 'center', padding: '10px 8px', color: '#ffffff', fontWeight: 700, fontSize: '11px', letterSpacing: '0.05em', background: '#2d3748', borderRight: '1px solid #4a5568' }}>S. NO.</th>
                  <th rowSpan="2" style={{ width: '220px', textAlign: 'left', padding: '10px 12px', color: '#ffffff', fontWeight: 700, fontSize: '11px', letterSpacing: '0.05em', background: '#2d3748', borderRight: '1px solid #4a5568' }}>NAME</th>
                  <th colSpan="5" style={{ textAlign: 'center', padding: '10px 12px', color: '#ffffff', fontWeight: 700, fontSize: '11px', letterSpacing: '0.05em', background: '#2d3748', borderRight: '1px solid #4a5568' }}>ID CARD LISTS</th>
                  <th colSpan="3" style={{ textAlign: 'center', padding: '10px 12px', color: '#ffffff', fontWeight: 700, fontSize: '11px', letterSpacing: '0.05em', background: '#2d3748', borderRight: '1px solid #4a5568' }}>REPRINT CARD LISTS</th>
                  <th rowSpan="2" style={{ width: '90px', textAlign: 'center', padding: '10px 8px', color: '#ffffff', fontWeight: 700, fontSize: '11px', letterSpacing: '0.05em', background: '#2d3748', borderRight: '1px solid #4a5568' }}>STATUS</th>
                  <th rowSpan="2" style={{ width: '90px', textAlign: 'center', padding: '10px 8px', color: '#ffffff', fontWeight: 700, fontSize: '11px', letterSpacing: '0.05em', background: '#2d3748', borderRight: 'none' }}>ACTION</th>
                </tr>
              </thead>
              <tbody>
                {filteredTables.map((t, idx) => {
                  const isSel = String(t.id) === String(selectedTableId);
                  const counts = getTableCounts(t);
                  const isActive = t.is_active !== false;

                  const displayOrg = getDisplayOrgName(t.client_name, clientOrg);

                  return (
                    <tr
                      key={t.id}
                      onClick={() => handleSelectRow(t.id)}
                      style={{
                        background: isSel ? 'rgba(37, 99, 235, 0.08)' : 'transparent',
                        borderBottom: '1px solid #f1f5f9',
                        cursor: 'pointer',
                        transition: 'background 0.15s'
                      }}
                      className={isSel ? 'selected' : ''}
                    >
                      {/* S. NO. Column */}
                      <td style={{ padding: '8px', textAlign: 'center', fontWeight: 600, color: '#64748b' }}>
                        {idx + 1}
                      </td>

                      {/* NAME Column (Clean formatting without underline or dash lines!) */}
                      <td style={{ padding: '8px 12px', textAlign: 'left' }}>
                        <span style={{ color: '#0f172a', fontWeight: 700, fontSize: '13px' }}>
                          {t.name}
                        </span>
                        {Boolean(displayOrg) && (
                          <div style={{ fontSize: '11px', color: '#64748b', marginTop: '2px' }}>
                            {displayOrg}
                          </div>
                        )}
                      </td>

                      {/* ID CARD LISTS (5 Badges) */}
                      <td colSpan="5" style={{ padding: '8px' }}>
                        <div style={{ display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'nowrap' }}>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'pending'); }} style={statusBtnStyle('pending').btn} title="View Pending List">
                            <span>Pending List</span><span style={statusBtnStyle('pending').badge}>{counts.pending}</span>
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'verified'); }} style={statusBtnStyle('verified').btn} title="View Verified List">
                            <span>Verified List</span><span style={statusBtnStyle('verified').badge}>{counts.verified}</span>
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'approved'); }} style={statusBtnStyle('approved').btn} title="View Approved List">
                            <span>Approved List</span><span style={statusBtnStyle('approved').badge}>{counts.approved}</span>
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'printed'); }} style={statusBtnStyle('printed').btn} title="View Printed List">
                            <span>Printed List</span><span style={statusBtnStyle('printed').badge}>{counts.download}</span>
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'deleted'); }} style={statusBtnStyle('deleted').btn} title="View Deleted List">
                            <span>Deleted List</span><span style={statusBtnStyle('deleted').badge}>{counts.pool}</span>
                          </button>
                        </div>
                      </td>

                      {/* REPRINT CARD LISTS (3 Badges) */}
                      <td colSpan="3" style={{ padding: '8px' }}>
                        <div style={{ display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'nowrap' }}>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'reprint'); }} style={reprintBtnStyle('reprint').btn} title="View Reprinting List">
                            <span>Reprinting List</span><span style={reprintBtnStyle('reprint').badge}>{counts.rpCnt}</span>
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'request'); }} style={reprintBtnStyle('request').btn} title="View Requested List">
                            <span>Requested List</span><span style={reprintBtnStyle('request').badge}>{counts.reqCnt}</span>
                          </button>
                          <button onClick={(e) => { e.stopPropagation(); openIDCardActions(t, 'confirm'); }} style={reprintBtnStyle('confirm').btn} title="View Confirmed List">
                            <span>Confirmed List</span><span style={reprintBtnStyle('confirm').badge}>{counts.confCnt}</span>
                          </button>
                        </div>
                      </td>

                      {/* STATUS Column */}
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); handleToggleStatus(t); }}
                          style={{
                            padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 700,
                            background: isActive ? '#d1fae5' : '#fee2e2',
                            color: isActive ? '#047857' : '#dc2626',
                            border: isActive ? '1px solid #a7f3d0' : '1px solid #fca5a5',
                            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px'
                          }}
                          title="Click to toggle Active/Inactive status"
                        >
                          <ToggleRight size={12} /> {isActive ? 'Active' : 'Inactive'}
                        </button>
                      </td>

                      {/* ACTION Column (Setting Button opens dedicated Table Setting Schema Modal!) */}
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <button
                          onClick={(e) => { e.stopPropagation(); setSettingModalTable(t); }}
                          style={{
                            padding: '4px 10px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
                            background: '#f1f5f9', color: '#1e293b', border: '1px solid #cbd5e1',
                            cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px'
                          }}
                          title={`View table schema for ${t.name}`}
                        >
                          <Settings size={12} style={{ color: '#2563eb' }} /> Setting
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          )}
        </div>
      </div>

      {/* ── MODALS & DRAWERS ── */}

      {/* 3-Step Create Table from XLSX Modal */}
      {showCreateXlsxModal && (
        <CreateXlsxModal
          groupId={groupId}
          onClose={() => setShowCreateXlsxModal(false)}
          onSuccess={() => loadTables()}
          addToast={addToast}
        />
      )}

      {/* Add / Edit Table Drawer */}
      {showAddEditDrawer && (
        <TableDrawerForm
          editingTable={editingTable}
          groupId={groupId}
          orgName={clientOrg}
          onClose={() => setShowAddEditDrawer(false)}
          onSave={() => { setShowAddEditDrawer(false); loadTables(); }}
          addToast={addToast}
        />
      )}

      {/* Dedicated Table Setting Details Center Modal (No redundant buttons/stats!) */}
      {settingModalTable && (
        <TableSettingSchemaModal
          table={settingModalTable}
          orgName={clientOrg}
          onClose={() => setSettingModalTable(null)}
        />
      )}

      {/* Delete All Confirmation Modal */}
      {activeModal === 'delete-all' && selectedTable && (
        <div className="center-modal-overlay">
          <div className="center-modal-panel" style={{ width: '420px', height: 'auto', padding: '20px' }}>
            <h3 style={{ margin: '0 0 8px', color: '#dc2626', fontSize: '16px', fontWeight: 700 }}>
              Delete All ID Cards
            </h3>
            <p style={{ fontSize: '12px', color: '#475569', margin: '0 0 14px' }}>
              Are you sure you want to permanently delete all cards in <strong>"{selectedTable.name}"</strong>? Enter the confirmation code below:
            </p>
            <input
              value={deleteCodeInput}
              onChange={e => setDeleteCodeInput(e.target.value)}
              placeholder="Enter 10-digit delete code"
              style={{ width: '100%', height: '36px', border: '1px solid #cbd5e1', borderRadius: '6px', padding: '0 10px', fontSize: '13px', marginBottom: '14px' }}
            />
            <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '8px' }}>
              <button onClick={() => setActiveModal(null)} className="btn btn-neutral btn-sm">Cancel</button>
              <button onClick={confirmDeleteAll} className="btn btn-danger btn-sm">Confirm Delete All</button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}

/* ─── Dedicated Table Setting Schema Center Modal (No repeated buttons or stats!) ─── */
function TableSettingSchemaModal({ table, orgName, onClose }) {
  if (!table) return null;

  const fields = table.fields || [
    { name: 'PHOTO', type: 'photo', mandatory: true },
    { name: 'NAME', type: 'text', mandatory: true },
    { name: 'SERIAL NO', type: 'number', mandatory: true },
    { name: 'CLASS', type: 'text', mandatory: false },
    { name: 'SECTION', type: 'text', mandatory: false },
  ];
  const typeMeta = getTableTypeMeta(table.table_type || inferTableType(table.name, orgName));
  const TypeIcon = typeMeta.icon;

  const formatDate = (d) => {
    if (!d) return '—';
    try {
      return new Date(d).toLocaleString('en-IN', {
        day: '2-digit', month: '2-digit', year: 'numeric',
        hour: '2-digit', minute: '2-digit'
      });
    } catch { return String(d); }
  };

  return (
    <div className="center-modal-overlay">
      <div className="center-modal-panel" style={{ width: '560px', height: 'auto', maxHeight: '85vh', padding: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column', borderRadius: '10px' }}>
        
        {/* Modal Header */}
        <div style={{ padding: '16px 20px', background: '#1e293b', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <div>
            <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, display: 'flex', alignItems: 'center', gap: '8px', color: '#ffffff' }}>
              <Settings size={18} style={{ color: '#38bdf8' }} /> Table Setting Details
            </h3>
            <span style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', display: 'block' }}>
              {table.name}
            </span>
          </div>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px' }}>
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div style={{ flex: 1, padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          
          {/* Metadata Card */}
          <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '8px', border: '1px solid #e2e8f0', display: 'flex', flexDirection: 'column', gap: '10px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Table Metadata</span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', background: typeMeta.bg, color: typeMeta.color, border: `1px solid ${typeMeta.border}`, fontSize: '11px', fontWeight: 600 }}>
                  <TypeIcon size={12} /> {typeMeta.label}
                </span>
                <span style={{ padding: '3px 8px', borderRadius: '4px', background: table.is_active !== false ? '#d1fae5' : '#fee2e2', color: table.is_active !== false ? '#047857' : '#dc2626', fontSize: '11px', fontWeight: 700 }}>
                  {table.is_active !== false ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>

            <div style={{ fontSize: '12px', color: '#334155', display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '8px', paddingTop: '8px', borderTop: '1px solid #e2e8f0' }}>
              <div><strong style={{ color: '#64748b' }}>Organisation:</strong> {getDisplayOrgName(table.client_name, orgName) || 'Standard'}</div>
              <div><strong style={{ color: '#64748b' }}>Created By:</strong> {table.created_by || table.user || 'Admin'}</div>
              <div><strong style={{ color: '#64748b' }}>Created At:</strong> {formatDate(table.created_at)}</div>
              <div><strong style={{ color: '#64748b' }}>Last Updated:</strong> {formatDate(table.updated_at || table.created_at)}</div>
            </div>
          </div>

          {/* Fields Schema List */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>Table Fields Schema ({fields.length} Fields)</span>
            </div>

            <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                  <tr>
                    <th style={{ padding: '8px', textAlign: 'center', width: '40px', color: '#475569' }}>#</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569' }}>Field Name</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', width: '130px', color: '#475569' }}>Data Type</th>
                    <th style={{ padding: '8px', textAlign: 'center', width: '80px', color: '#475569' }}>Mandatory</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((f, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '7px 8px', textAlign: 'center', color: '#94a3b8', fontSize: '11px', fontWeight: 600 }}>{idx + 1}</td>
                      <td style={{ padding: '7px 12px', fontWeight: 600, color: '#1e293b' }}>{f.name}</td>
                      <td style={{ padding: '7px 12px', color: '#2563eb', textTransform: 'uppercase', fontSize: '11px', fontWeight: 700 }}>{f.type || 'text'}</td>
                      <td style={{ padding: '7px 8px', textAlign: 'center' }}>
                        {f.mandatory ? (
                          <span style={{ padding: '2px 6px', borderRadius: '3px', background: '#dcfce7', color: '#15803d', fontSize: '10px', fontWeight: 700 }}>Required</span>
                        ) : (
                          <span style={{ color: '#94a3b8', fontSize: '11px' }}>Optional</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div style={{ padding: '12px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '7px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#ffffff', fontWeight: 700, cursor: 'pointer', fontSize: '12px' }}>
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Add / Edit Table Drawer Form Component ─── */
function TableDrawerForm({ editingTable, groupId, orgName, onClose, onSave, addToast }) {
  const isEditing = Boolean(editingTable);
  const [tableName, setTableName]   = useState(editingTable?.name || '');
  const [tableType, setTableType]   = useState(editingTable?.table_type || 'custom');
  const [fields, setFields]         = useState(
    (editingTable?.fields || [
      { id: 'f_1', name: 'PHOTO', type: 'photo', mandatory: true, show_path: true },
      { id: 'f_2', name: 'NAME', type: 'text', mandatory: true, show_path: false },
      { id: 'f_3', name: 'SERIAL NO', type: 'number', mandatory: true, show_path: false },
    ]).map((f, i) => ({ ...f, id: f.id || `f_${i}`, type: (f.type || 'text').toLowerCase() }))
  );
  const [saving, setSaving]         = useState(false);

  const [newName, setNewName]       = useState('');
  const [newType, setNewType]       = useState('text');

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
    setFields(prev => [...prev, field]);
    setNewName('');
    setNewType('text');
    addToast?.(`Field "${field.name}" added`, 'success');
  };

  const handleDeleteField = (id) => setFields(prev => prev.filter(f => f.id !== id));

  const handleSubmit = async () => {
    if (!tableName.trim()) { addToast?.('Table Name is required', 'warning'); return; }
    if (fields.length === 0) { addToast?.('Add at least one field', 'warning'); return; }

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
        } catch { /* fallback local */ }

        const stored = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        const updated = stored.map(t => String(t.id) === String(editingTable.id) ? {
          ...t, ...payload, updated_at: new Date().toISOString()
        } : t);
        localStorage.setItem('cf_custom_tables', JSON.stringify(updated));
        addToast?.(`Table "${payload.name}" updated successfully!`, 'success');
      } else {
        try {
          if (groupId) {
            await schemaApi.createTable(groupId, payload);
          } else {
            await schemaApi.createSchema(payload);
          }
        } catch { /* fallback local */ }

        const stored = JSON.parse(localStorage.getItem('cf_custom_tables') || '[]');
        const newTable = {
          id: `tbl_${Date.now()}`,
          ...payload,
          client_name: orgName || 'Primary Org',
          status: 'active',
          is_active: true,
          created_at: new Date().toISOString(),
          updated_at: new Date().toISOString(),
        };
        localStorage.setItem('cf_custom_tables', JSON.stringify([newTable, ...stored]));
        addToast?.(`Table "${payload.name}" created successfully!`, 'success');
      }
      onSave();
    } catch {
      addToast?.('Error saving table setting', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div style={{ position: 'fixed', inset: 0, zIndex: 9999999, display: 'flex', justifyContent: 'flex-end', background: 'rgba(15, 23, 42, 0.45)' }}>
      <div style={{ width: '520px', height: '100%', background: '#ffffff', boxShadow: '-10px 0 25px rgba(0,0,0,0.15)', display: 'flex', flexDirection: 'column' }}>
        {/* Header */}
        <div style={{ padding: '16px 20px', background: '#1e293b', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
          <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#ffffff', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <SlidersHorizontal size={18} style={{ color: '#38bdf8' }} /> {isEditing ? `Edit Table: ${editingTable.name}` : 'Add New Table Setting'}
          </h3>
          <button onClick={onClose} style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer' }}><X size={20} /></button>
        </div>

        {/* Body */}
        <div style={{ flex: 1, padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>Table Name *</label>
            <input
              type="text"
              value={tableName}
              onChange={e => setTableName(e.target.value)}
              placeholder="e.g. CLASS 10TH DATA"
              style={{ width: '100%', height: '36px', border: '1px solid #cbd5e1', borderRadius: '4px', padding: '0 10px', fontSize: '13px', boxSizing: 'border-box' }}
            />
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '6px' }}>Table Type</label>
            <CustomSelect
              value={tableType}
              onChange={setTableType}
              options={TABLE_TYPES.map(t => ({ value: t.value, label: t.label }))}
            />
          </div>

          {/* Add Field */}
          <div style={{ background: '#f8fafc', padding: '14px', borderRadius: '6px', border: '1px solid #e2e8f0' }}>
            <label style={{ display: 'block', fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase', marginBottom: '8px' }}>Add Schema Field</label>
            <div style={{ display: 'flex', gap: '8px' }}>
              <input
                type="text"
                value={newName}
                onChange={e => {
                  setNewName(e.target.value);
                  setNewType(inferFieldType(e.target.value));
                }}
                placeholder="Field name (e.g. FATHER NAME)"
                style={{ flex: 1, height: '34px', border: '1px solid #cbd5e1', borderRadius: '4px', padding: '0 10px', fontSize: '12px' }}
              />
              <div style={{ width: '140px' }}>
                <CustomSelect
                  value={newType}
                  onChange={setNewType}
                  options={FIELD_TYPES}
                />
              </div>
              <button onClick={handleAddField} style={{ padding: '0 12px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px' }}>
                Add
              </button>
            </div>
          </div>

          {/* Fields List */}
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 700, color: '#334155', marginBottom: '8px' }}>Defined Fields ({fields.length})</label>
            <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                  <tr>
                    <th style={{ padding: '8px', textAlign: 'left' }}>Field Name</th>
                    <th style={{ padding: '8px', textAlign: 'left', width: '120px' }}>Type</th>
                    <th style={{ padding: '8px', textAlign: 'center', width: '60px' }}>Req.</th>
                    <th style={{ padding: '8px', textAlign: 'center', width: '40px' }}>Action</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((f, idx) => (
                    <tr key={f.id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td style={{ padding: '6px 8px', fontWeight: 600, color: '#1e293b' }}>{f.name}</td>
                      <td style={{ padding: '4px 8px' }}>
                        <CustomSelect
                          value={f.type || 'text'}
                          onChange={val => {
                            const copy = [...fields];
                            copy[idx].type = val;
                            setFields(copy);
                          }}
                          options={FIELD_TYPES}
                        />
                      </td>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={Boolean(f.mandatory)}
                          onChange={e => {
                            const copy = [...fields];
                            copy[idx].mandatory = e.target.checked;
                            setFields(copy);
                          }}
                          style={{ cursor: 'pointer' }}
                        />
                      </td>
                      <td style={{ padding: '6px 8px', textAlign: 'center' }}>
                        <button onClick={() => handleDeleteField(f.id)} style={{ background: 'none', border: 'none', color: '#ef4444', cursor: 'pointer' }}><Trash2 size={14} /></button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </div>

        {/* Footer */}
        <div style={{ padding: '14px 20px', background: '#f8fafc', borderTop: '1px solid #e2e8f0', display: 'flex', gap: '8px', justifyContent: 'flex-end' }}>
          <button onClick={onClose} style={{ padding: '8px 16px', background: '#fff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#475569', fontWeight: 600, cursor: 'pointer', fontSize: '12px' }} disabled={saving}>Cancel</button>
          <button onClick={handleSubmit} disabled={saving} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#fff', fontWeight: 700, cursor: 'pointer', fontSize: '12px', display: 'flex', alignItems: 'center', gap: '6px' }}>
            <Save size={14} /> {saving ? 'Saving...' : 'Save Table Setting'}
          </button>
        </div>
      </div>
    </div>
  );
}

function statusBtnStyle(type) {
  const activeColors = {
    pending:  { bg: '#f97316', color: '#ffffff', border: '#f97316', badgeBg: '#ea580c' },
    verified: { bg: '#10b981', color: '#ffffff', border: '#10b981', badgeBg: '#059669' },
    approved: { bg: '#3b82f6', color: '#ffffff', border: '#3b82f6', badgeBg: '#2563eb' },
    printed:  { bg: '#64748b', color: '#ffffff', border: '#64748b', badgeBg: '#475569' },
    request:  { bg: '#8b5cf6', color: '#ffffff', border: '#8b5cf6', badgeBg: '#7c3aed' },
    deleted:  { bg: '#ef4444', color: '#ffffff', border: '#ef4444', badgeBg: '#dc2626' },
  };
  const cfg = activeColors[type] || activeColors.pending;
  return {
    btn: {
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '5px',
      padding: '3px 7px', borderRadius: '5px', fontSize: '11px', fontWeight: 600,
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
      cursor: 'pointer', transition: 'all 0.15s', whiteSpace: 'nowrap'
    },
    badge: {
      background: cfg.badgeBg, color: '#ffffff', minWidth: '20px', height: '16px',
      borderRadius: '8px', fontSize: '10px', fontWeight: 700, display: 'inline-flex',
      alignItems: 'center', justifyContent: 'center', padding: '0 4px', marginLeft: '2px'
    }
  };
}

function reprintBtnStyle(type) {
  const activeColors = {
    reprint: { bg: '#06b6d4', color: '#ffffff', border: '#06b6d4', badgeBg: '#0891b2' },
    request: { bg: '#a855f7', color: '#ffffff', border: '#a855f7', badgeBg: '#9333ea' },
    confirm: { bg: '#10b981', color: '#ffffff', border: '#10b981', badgeBg: '#059669' },
  };
  const cfg = activeColors[type] || activeColors.reprint;
  return {
    btn: {
      display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '5px',
      padding: '3px 7px', borderRadius: '5px', fontSize: '11px', fontWeight: 600,
      background: cfg.bg, color: cfg.color, border: `1px solid ${cfg.border}`,
      cursor: 'pointer', transition: 'all 0.15s', whiteSpace: 'nowrap'
    },
    badge: {
      background: cfg.badgeBg, color: '#ffffff', minWidth: '20px', height: '16px',
      borderRadius: '8px', fontSize: '10px', fontWeight: 700, display: 'inline-flex',
      alignItems: 'center', justifyContent: 'center', padding: '0 4px', marginLeft: '2px'
    }
  };
}

function bulkBtnStyle(type, disabled) {
  const activeColors = {
    reupload:     { bg: '#f97316', color: '#ffffff', border: '#f97316' },
    downloadAll:  { bg: '#2563eb', color: '#ffffff', border: '#2563eb' },
    deleteAll:    { bg: '#ef4444', color: '#ffffff', border: '#ef4444' },
    upgradeClass: { bg: '#10b981', color: '#ffffff', border: '#10b981' },
  };
  const cfg = activeColors[type] || activeColors.reupload;
  return {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center', gap: '5px',
    height: '28px', padding: '0 10px', borderRadius: '4px', fontSize: '11px', fontWeight: 600,
    background: disabled ? 'rgba(255, 255, 255, 0.08)' : cfg.bg,
    color: disabled ? 'rgba(255, 255, 255, 0.45)' : cfg.color,
    border: disabled ? '1px solid rgba(255, 255, 255, 0.15)' : `1px solid ${cfg.border}`,
    cursor: disabled ? 'not-allowed' : 'pointer',
    whiteSpace: 'nowrap',
    boxSizing: 'border-box',
    opacity: disabled ? 0.6 : 1,
    fontFamily: 'var(--font-family)', transition: 'all 0.15s'
  };
}
