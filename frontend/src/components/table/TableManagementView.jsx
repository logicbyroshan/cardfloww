import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Clock,
  CheckCircle,
  Download,
  Layers,
  Settings,
  Upload,
  Trash2,
  ArrowUp,
  X,
  Loader2,
  FileSpreadsheet,
  Plus,
  ToggleRight,
  School,
  BookOpen,
  Briefcase,
  Settings2,
  FolderKanban,
  Pencil,
  Save,
  Building,
  Share2,
} from 'lucide-react';
import WatermarkLogo from '../common/WatermarkLogo';
import CreateXlsxModal from '../common/CreateXlsxModal';
import Button from '../common/Button';
import Input from '../common/Input';
import Modal from '../common/Modal';
import { TableDrawerForm } from '../settings/TableSettingsView';
import { cardApi, schemaApi, clientApi } from '../../services/api';



const STATUS_TABS = ['All', 'Active', 'Inactive'];

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

function inferTableType(tableName = '', orgName = '') {
  const name = (tableName || '').toLowerCase().trim();
  const org = (orgName || '').toLowerCase().trim();
  const staffRe = /\b(staff|teacher|teachers|employee|employees|emp|faculty|personnel|hr|driver|workers|management)\b/;
  const collegeRe =
    /\b(college|university|institute|polytechnic|degree|btech|mtech|bca|mca|mba|bsc|msc|ba|ma|bcom|mcom|semester|sem|branch|dept|department)\b/;
  const schoolRe = /\b(school|vidyalaya|academy|convent|class|std|standard|grade|section|sec)\b/;

  if (staffRe.test(name)) return 'staff';
  if (collegeRe.test(name)) return 'college_student';
  if (schoolRe.test(name)) return 'school_student';
  if (collegeRe.test(org)) return 'college_student';
  return 'school_student';
}

function getTableCounts(t) {

  if (!t) return { pending: 0, verified: 0, approved: 0, download: 0, pool: 0, rpCnt: 0, reqCnt: 0, confCnt: 0 };
  const pending = t.pending_count ?? t.pending ?? 0;
  const verified = t.verified_count ?? t.verified ?? 0;
  const approved = t.approved_count ?? t.approved ?? 0;
  const download = t.download_count ?? t.downloaded ?? t.download ?? t.printed ?? 0;
  const pool = t.pool_count ?? t.deleted ?? t.pool ?? 0;

  const rpCnt = t.reprint_count ?? t.reprint ?? 0;
  const reqCnt = t.reprint_request_count ?? t.reprint_request ?? t.request ?? t.requested ?? 0;
  const confCnt = t.reprint_confirmed_count ?? t.reprint_confirmed ?? t.confirmed ?? 0;

  return { pending, verified, approved, download, pool, rpCnt, reqCnt, confCnt };
}

function getDisplayOrgName(table, fallbackOrg) {
  if (!table) return '';
  const orgName = table.organisation_name || table.client_name || table.school_name || '';
  const ignoreList = ['—', 'Primary Org', 'Default Organisation', 'Default Organization', 'null', 'undefined'];
  if (orgName && !ignoreList.includes(String(orgName).trim())) {
    return String(orgName).trim();
  }
  if (fallbackOrg && !ignoreList.includes(String(fallbackOrg).trim())) {
    return String(fallbackOrg).trim();
  }
  return '';
}

export default function CardTableView({
  addToast,
  onNavigate,
  currentUser,
  userRole = 'super_admin',
  selectedClientId = null,
  selectedClientOrg = null,
  onClearSelectedClient = null,
  onOrgResolved = null,
}) {
  const role = String(currentUser?.role || userRole || '').toLowerCase();
  const isAssistant = role === 'assistant';
  const isAdminOrOperator = ['prime_admin', 'super_admin', 'pro_user', 'operator'].includes(role);
  const isPrimeManager = ['prime_manager', 'client', 'guest_prime_manager'].includes(role);
  const canCreateTable = isAdminOrOperator || isPrimeManager;
  const canShareTable = isAdminOrOperator || isPrimeManager;

  const [tables, setTables] = useState([]);
  const [loading, setLoading] = useState(true);
  const [filterOrgId, setFilterOrgId] = useState(selectedClientId ? String(selectedClientId) : null);
  const [allOrganisations, setAllOrganisations] = useState([]);
  const [showCreateXlsxModal, setShowCreateXlsxModal] = useState(false);
  const [shareModalTable, setShareModalTable] = useState(null);

  /* Table selection in main view (Default to NULL so buttons are only active when selected!) */
  const [selectedTableId, setSelectedTableId] = useState(null);

  /* Table Setting Drawers & Modals */
  const [showAddEditDrawer, setShowAddEditDrawer] = useState(false);
  const [editingTable, setEditingTable] = useState(null);
  const [settingModalTable, setSettingModalTable] = useState(null);
  const [groupId, setGroupId] = useState(1);


  /* Modal states for bulk actions */
  const [activeModal, setActiveModal] = useState(null);
  const [deleteCodeInput, setDeleteCodeInput] = useState('');

  /* Sync with selectedClientId prop */
  useEffect(() => {
    if (selectedClientId) {
      setFilterOrgId(String(selectedClientId));
    }
  }, [selectedClientId]);

  /* Load all organisations (Admin only) */
  useEffect(() => {
    (async () => {
      try {
        const data = await clientApi.getAllForAssignment?.();
        const clients = data?.clients || data?.results || (Array.isArray(data) ? data : []);
        setAllOrganisations(clients);
        if (clients.length > 0) {
          setGroupId((prev) => (!prev || prev === 1 ? (clients[0].group_id || clients[0].id || 1) : prev));
        }
      } catch {
        /* fallback */
      }
    })();
  }, []);

  /* Redirect if no organisation is scoped */
  useEffect(() => {
    if (!selectedClientId && (!filterOrgId || filterOrgId === 'all')) {
      onNavigate?.('organisations');
    }
  }, [selectedClientId, filterOrgId, onNavigate]);

  /* Load tables list strictly scoped to organisation */
  const loadTables = useCallback(async () => {
    const orgId = selectedClientId || (filterOrgId && filterOrgId !== 'all' ? filterOrgId : null);
    if (!orgId) {
      setTables([]);
      setLoading(false);
      return;
    }
    setLoading(true);
    try {
      const data = await schemaApi.getSchemas({ client_id: orgId });
      const list = data?.tables || data?.results || (Array.isArray(data) ? data : []);
      setTables(list);
    } catch (err) {
      console.error('Load tables error:', err);
      setTables([]);
    } finally {
      setLoading(false);
    }
  }, [selectedClientId, filterOrgId]);

  useEffect(() => {
    loadTables();
  }, [loadTables]);

  const activeScopedOrg = useMemo(() => {
    const orgId = selectedClientId || (filterOrgId && filterOrgId !== 'all' ? filterOrgId : null);
    if (!orgId) return null;
    return allOrganisations.find((o) => String(o.id) === String(orgId)) || selectedClientOrg || null;
  }, [selectedClientId, filterOrgId, allOrganisations, selectedClientOrg]);

  useEffect(() => {
    if (activeScopedOrg && onOrgResolved) {
      onOrgResolved(activeScopedOrg);
    }
  }, [activeScopedOrg, onOrgResolved]);

  const selectedTable = useMemo(
    () => tables.find((t) => String(t.id) === String(selectedTableId)),
    [tables, selectedTableId]
  );

  /* Dispatch footer data count & selection */
  useEffect(() => {
    let selectedText = '';
    if (selectedTable) {
      selectedText = `Selected: ${selectedTable.name || `Table #${selectedTable.id}`}`;
    }
    window.dispatchEvent(
      new CustomEvent('cardflow:data-count', {
        detail: {
          text: `Total Tables: ${tables.length}`,
          selectedText,
          count: tables.length,
        },
      })
    );
  }, [tables.length, selectedTable]);

  /* Toggle Row Selection */
  const handleSelectRow = (tableId) => {
    setSelectedTableId((prev) => (String(prev) === String(tableId) ? null : tableId));
  };

  /* Toggle Table Status */
  const handleToggleStatus = async (tableToToggle) => {
    const target = tableToToggle || selectedTable;
    if (!target) return;
    try {
      await schemaApi.toggleTableStatus(target.id);
      addToast?.(`Status updated for "${target.name}"`, 'success');
      loadTables();
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Error updating table status';
      addToast?.(msg, 'error');
    }
  };

  /* Delete Table */
  const handleDeleteTable = async (tableToDelete) => {
    const target = tableToDelete || selectedTable;
    if (!target) return;
    if (!window.confirm(`Delete table "${target.name}"? This action cannot be undone.`)) return;

    try {
      await schemaApi.deleteTable(target.id);
      addToast?.(`Table "${target.name}" deleted`, 'success');
      if (selectedTableId === target.id) setSelectedTableId(null);
      loadTables();
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Error deleting table';
      addToast?.(msg, 'error');
    }
  };

  /* Download Blank Template */
  const handleDownloadBlankTemplate = () => {
    addToast?.('Downloading Blank Excel Template (.xlsx)…', 'info');
  };

  const filteredTables = useMemo(() => {
    return tables.filter(Boolean);
  }, [tables]);

  /* Open IDCardActionsView */
  const openIDCardActions = (table, status = 'pending') => {
    if (onNavigate) {
      const orgId = table?.organisation_id || table?.client_id || (activeScopedOrg ? activeScopedOrg.id : null);
      const orgName = table?.organisation_name || table?.client_name || (activeScopedOrg ? (activeScopedOrg.name || activeScopedOrg.school_name) : null);
      onNavigate('idcard-actions', {
        tableId: table.id,
        status,
        orgId,
        orgName,
        tableName: table.name,
      });
    }
  };

  /* Confirm Delete All */
  const confirmDeleteAll = async () => {
    if (!deleteCodeInput) {
      addToast?.('Please enter confirmation code', 'warning');
      return;
    }
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
    <div
      className="view-container"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}
    >
      {/* ── ACTION BAR / TOPBAR ── */}
      <div
        className="action-bar"
        id="idcard-group-action-bar"
        style={{
          background: '#1e1e2e',
          borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
          height: '44px',
          padding: '6px 6px',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          boxSizing: 'border-box',
        }}
      >
        {/* Left Side: Status Filters | 4 Table Action Buttons | 2 XLSX Buttons */}
        <div className="action-bar-left" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          {/* Section 1: Table Action Buttons (Hidden for Assistant) */}
          {!isAssistant && (
            <>
              <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                {/* 1. Add Button */}
                {canCreateTable && (
                  <Button
                    size="sm"
                    variant="primary"
                    onClick={() => {
                      setEditingTable(null);
                      setShowAddEditDrawer(true);
                    }}
                    icon={<Plus size={13} />}
                    title="Add New Table"
                  >
                    Add
                  </Button>
                )}

                {/* 2. Edit Button */}
                <Button
                  size="sm"
                  variant={selectedTable ? 'primary' : 'neutral'}
                  disabled={!selectedTable}
                  onClick={() => {
                    setEditingTable(selectedTable);
                    setShowAddEditDrawer(true);
                  }}
                  title={!selectedTable ? 'Select a table row to edit' : `Edit ${selectedTable.name}`}
                  icon={<Pencil size={13} />}
                >
                  Edit
                </Button>

                {/* 3. Delete Button */}
                <Button
                  size="sm"
                  variant={selectedTable ? 'danger' : 'neutral'}
                  disabled={!selectedTable}
                  onClick={() => handleDeleteTable(selectedTable)}
                  title={!selectedTable ? 'Select a table row to delete' : `Delete ${selectedTable.name}`}
                  icon={<Trash2 size={13} />}
                >
                  Delete
                </Button>

                {/* 4. Active/Inactive Toggle Button */}
                <Button
                  size="sm"
                  variant={selectedTable ? 'success' : 'neutral'}
                  disabled={!selectedTable}
                  onClick={() => handleToggleStatus(selectedTable)}
                  title={
                    !selectedTable
                      ? 'Select a table row to toggle status'
                      : selectedTable.is_active !== false
                        ? 'Deactivate Table'
                        : 'Activate Table'
                  }
                  icon={<ToggleRight size={13} />}
                >
                  {selectedTable && selectedTable.is_active === false ? 'Activate' : 'Active'}
                </Button>

                {/* 5. Share / Table Delegation Button */}
                {canShareTable && (
                  <Button
                    size="sm"
                    variant={selectedTable ? 'primary' : 'neutral'}
                    disabled={!selectedTable}
                    onClick={() => selectedTable && setShareModalTable(selectedTable)}
                    title={!selectedTable ? 'Select a table row to delegate' : `Delegate ${selectedTable.name} to Super Managers`}
                    icon={<Share2 size={13} />}
                  >
                    Share
                  </Button>
                )}
              </div>
            </>
          )}

          {/* | Divider */}
          <span style={{ width: '1px', height: '16px', background: 'rgba(255, 255, 255, 0.2)', margin: '0 4px' }} />

          {/* Section 3: XLSX Buttons */}
          <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
            <Button
              size="sm"
              variant="neutral"
              onClick={handleDownloadBlankTemplate}
              title="Download Blank XLSX Template"
              icon={<Download size={13} />}
            >
              Download Template
            </Button>

            {canCreateTable && (
              <Button
                size="sm"
                variant="success"
                onClick={() => setShowCreateXlsxModal(true)}
                title="Create table directly from an XLSX file"
                icon={<FileSpreadsheet size={13} />}
              >
                Create with Data
              </Button>
            )}
          </div>
        </div>

        {/* Right Side: Bulk Actions for Selected Table */}
        <div className="action-bar-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Button
                size="sm"
                variant={selectedTable ? 'warning' : 'neutral'}
                disabled={!selectedTable}
                onClick={() => setActiveModal('reupload')}
                title={!selectedTable ? 'Select a table row first' : `Reupload Images for ${selectedTable.name}`}
                icon={<Upload size={12} />}
              >
                Reupload Image
              </Button>

              <Button
                size="sm"
                variant={selectedTable ? 'primary' : 'neutral'}
                disabled={!selectedTable}
                onClick={() => setActiveModal('download-all')}
                title={!selectedTable ? 'Select a table row first' : `Download All ID Cards for ${selectedTable.name}`}
                icon={<Download size={12} />}
              >
                Download All ID Card
              </Button>

              <Button
                size="sm"
                variant={selectedTable ? 'danger' : 'neutral'}
                disabled={!selectedTable}
                onClick={() => {
                  setDeleteCodeInput('');
                  setActiveModal('delete-all');
                }}
                title={!selectedTable ? 'Select a table row first' : `Delete All ID Cards for ${selectedTable.name}`}
                icon={<Trash2 size={12} />}
              >
                Delete All ID Cards
              </Button>

              <Button
                size="sm"
                variant={selectedTable ? 'success' : 'neutral'}
                disabled={!selectedTable}
                onClick={() => setActiveModal('upgrade')}
                title={!selectedTable ? 'Select a table row first' : `Upgrade All Class for ${selectedTable.name}`}
                icon={<ArrowUp size={12} />}
              >
                Upgrade All Class
              </Button>
            </div>
          </div>
        </div>
      </div>

      {/* ── MAIN TABLE GROUP DATA TABLE ── */}
      <div
        id="gs-table-container"
        style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, overflow: 'hidden' }}
      >
        <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', position: 'relative' }}>
          <WatermarkLogo />
          {loading ? (
            <div style={{ padding: '60px', textAlign: 'center', color: '#64748b' }}>
              <Loader2
                size={28}
                style={{ animation: 'spin 1s linear infinite', margin: '0 auto 12px', display: 'block' }}
              />
              <span>Loading Tables data…</span>
            </div>
          ) : filteredTables.length === 0 ? (
            <div
              style={{
                padding: '60px 20px',
                textAlign: 'center',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
              }}
            >
              <FolderKanban size={40} style={{ color: '#cbd5e1', marginBottom: '12px' }} />
              <h4 style={{ margin: '0 0 6px', color: '#334155', fontSize: '15px', fontWeight: 600 }}>
                No Tables Found
              </h4>
              <p style={{ margin: 0, color: '#64748b', fontSize: '13px' }}>
                Click <strong>Add</strong> or <strong>Create with XLSX</strong> to create your first table.
              </p>
            </div>
          ) : (
            <table className="data-table" style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
              <thead
                style={{
                  position: 'sticky',
                  top: 0,
                  zIndex: 10,
                  background: '#2d3748',
                  borderTop: '1px solid rgba(255, 255, 255, 0.25)',
                  borderBottom: '1px solid #1a202c',
                }}
              >
                <tr>
                  <th
                    rowSpan="2"
                    style={{
                      width: '50px',
                      textAlign: 'center',
                      padding: '10px 8px',
                      color: '#ffffff',
                      fontWeight: 700,
                      fontSize: '11px',
                      letterSpacing: '0.05em',
                      background: '#2d3748',
                      borderRight: '1px solid #4a5568',
                    }}
                  >
                    S. NO.
                  </th>
                  <th
                    rowSpan="2"
                    style={{
                      width: '220px',
                      textAlign: 'left',
                      padding: '10px 12px',
                      color: '#ffffff',
                      fontWeight: 700,
                      fontSize: '11px',
                      letterSpacing: '0.05em',
                      background: '#2d3748',
                      borderRight: '1px solid #4a5568',
                    }}
                  >
                    NAME
                  </th>
                  <th
                    colSpan={isAssistant ? "3" : "5"}
                    style={{
                      textAlign: 'center',
                      padding: '10px 12px',
                      color: '#ffffff',
                      fontWeight: 700,
                      fontSize: '11px',
                      letterSpacing: '0.05em',
                      background: '#2d3748',
                      borderRight: '1px solid #4a5568',
                    }}
                  >
                    ID CARD LISTS
                  </th>
                  {!isAssistant && (
                    <th
                      colSpan="3"
                      style={{
                        textAlign: 'center',
                        padding: '10px 12px',
                        color: '#ffffff',
                        fontWeight: 700,
                        fontSize: '11px',
                        letterSpacing: '0.05em',
                        background: '#2d3748',
                        borderRight: '1px solid #4a5568',
                      }}
                    >
                      REPRINT CARD LISTS
                    </th>
                  )}
                  <th
                    rowSpan="2"
                    style={{
                      width: '90px',
                      textAlign: 'center',
                      padding: '10px 8px',
                      color: '#ffffff',
                      fontWeight: 700,
                      fontSize: '11px',
                      letterSpacing: '0.05em',
                      background: '#2d3748',
                      borderRight: isAdminOrOperator ? '1px solid #4a5568' : 'none',
                    }}
                  >
                    STATUS
                  </th>
                  {isAdminOrOperator && (
                    <th
                      rowSpan="2"
                      style={{
                        width: '95px',
                        textAlign: 'center',
                        padding: '10px 8px',
                        color: '#ffffff',
                        fontWeight: 700,
                        fontSize: '11px',
                        letterSpacing: '0.05em',
                        background: '#2d3748',
                        borderRight: 'none',
                      }}
                    >
                      SETTINGS
                    </th>
                  )}
                </tr>
              </thead>
              <tbody>
                {filteredTables.map((t, idx) => {
                  const isSel = String(t.id) === String(selectedTableId);
                  const counts = getTableCounts(t);
                  const isActive = t.is_active !== false;

                  const displayOrg = getDisplayOrgName(t, activeScopedOrg?.name || '');

                  return (
                    <tr
                      key={t.id}
                      onClick={() => handleSelectRow(t.id)}
                      style={{
                        background: isSel ? 'rgba(37, 99, 235, 0.08)' : 'transparent',
                        borderBottom: '1px solid #f1f5f9',
                        cursor: 'pointer',
                        transition: 'background 0.15s',
                      }}
                      className={isSel ? 'selected' : ''}
                    >
                      {/* S. NO. Column */}
                      <td style={{ padding: '8px', textAlign: 'center', fontWeight: 600, color: '#64748b' }}>
                        {idx + 1}
                      </td>

                      {/* NAME Column */}
                      <td style={{ padding: '8px 12px', textAlign: 'left' }}>
                        <span style={{ color: '#0f172a', fontWeight: 700, fontSize: '13px' }}>{t.name}</span>
                      </td>

                      {/* ID CARD LISTS Badges */}
                      <td colSpan={isAssistant ? "3" : "5"} style={{ padding: '8px' }}>
                        <div style={{ display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'nowrap' }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              openIDCardActions(t, 'pending');
                            }}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '6px',
                              padding: '3px 8px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 700,
                              background: '#ffffff',
                              color: '#c2410c',
                              border: '1.5px solid #f97316',
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                              boxShadow: '0 1px 2px rgba(249,115,22,0.06)',
                            }}
                            title="View Pending List"
                          >
                            <span>Pending</span>
                            <span style={{ fontSize: '12px', fontWeight: 800, color: '#c2410c' }}>{counts.pending}</span>
                          </button>

                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              openIDCardActions(t, 'verified');
                            }}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '6px',
                              padding: '3px 8px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 700,
                              background: '#ffffff',
                              color: '#047857',
                              border: '1.5px solid #10b981',
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                              boxShadow: '0 1px 2px rgba(16,185,129,0.06)',
                            }}
                            title="View Verified List"
                          >
                            <span>Verified</span>
                            <span style={{ fontSize: '12px', fontWeight: 800, color: '#047857' }}>{counts.verified}</span>
                          </button>

                          {!isAssistant && (
                            <>
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openIDCardActions(t, 'approved');
                                }}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '6px',
                                  padding: '3px 8px',
                                  borderRadius: '6px',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                  background: '#ffffff',
                                  color: '#1d4ed8',
                                  border: '1.5px solid #2563eb',
                                  cursor: 'pointer',
                                  whiteSpace: 'nowrap',
                                  boxShadow: '0 1px 2px rgba(37,99,235,0.06)',
                                }}
                                title="View Approved List"
                              >
                                <span>Approved</span>
                                <span style={{ fontSize: '12px', fontWeight: 800, color: '#1d4ed8' }}>{counts.approved}</span>
                              </button>

                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  openIDCardActions(t, 'printed');
                                }}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  gap: '6px',
                                  padding: '3px 8px',
                                  borderRadius: '6px',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                  background: '#ffffff',
                                  color: '#334155',
                                  border: '1.5px solid #64748b',
                                  cursor: 'pointer',
                                  whiteSpace: 'nowrap',
                                  boxShadow: '0 1px 2px rgba(100,116,139,0.06)',
                                }}
                                title="View Printed List"
                              >
                                <span>Printed</span>
                                <span style={{ fontSize: '12px', fontWeight: 800, color: '#334155' }}>{counts.download}</span>
                              </button>
                            </>
                          )}

                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              openIDCardActions(t, 'deleted');
                            }}
                            style={{
                              display: 'inline-flex',
                              alignItems: 'center',
                              justifyContent: 'center',
                              gap: '6px',
                              padding: '3px 8px',
                              borderRadius: '6px',
                              fontSize: '11px',
                              fontWeight: 700,
                              background: '#ffffff',
                              color: '#b91c1c',
                              border: '1.5px solid #ef4444',
                              cursor: 'pointer',
                              whiteSpace: 'nowrap',
                              boxShadow: '0 1px 2px rgba(239,68,68,0.06)',
                            }}
                            title="View Deleted List"
                          >
                            <span>Deleted</span>
                            <span style={{ fontSize: '12px', fontWeight: 800, color: '#b91c1c' }}>{counts.pool}</span>
                          </button>
                        </div>
                      </td>

                      {/* REPRINT CARD LISTS (Hidden for Assistant) */}
                      {!isAssistant && (
                        <td colSpan="3" style={{ padding: '8px' }}>
                          <div style={{ display: 'flex', gap: '4px', justifyContent: 'center', flexWrap: 'nowrap' }}>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openIDCardActions(t, 'reprint');
                              }}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: 700,
                                background: '#ffffff',
                                color: '#b45309',
                                border: '1.5px solid #d97706',
                                cursor: 'pointer',
                                whiteSpace: 'nowrap',
                                boxShadow: '0 1px 2px rgba(217,119,6,0.06)',
                              }}
                              title="View Reprinting List"
                            >
                              <span>Reprinting</span>
                              <span style={{ fontSize: '12px', fontWeight: 800, color: '#b45309' }}>{counts.rpCnt}</span>
                            </button>

                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openIDCardActions(t, 'request');
                              }}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: 700,
                                background: '#ffffff',
                                color: '#6d28d9',
                                border: '1.5px solid #8b5cf6',
                                cursor: 'pointer',
                                whiteSpace: 'nowrap',
                                boxShadow: '0 1px 2px rgba(139,92,246,0.06)',
                              }}
                              title="View Requested List"
                            >
                              <span>Requested</span>
                              <span style={{ fontSize: '12px', fontWeight: 800, color: '#6d28d9' }}>{counts.reqCnt}</span>
                            </button>

                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                openIDCardActions(t, 'confirm');
                              }}
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                gap: '6px',
                                padding: '3px 8px',
                                borderRadius: '6px',
                                fontSize: '11px',
                                fontWeight: 700,
                                background: '#ffffff',
                                color: '#047857',
                                border: '1.5px solid #059669',
                                cursor: 'pointer',
                                whiteSpace: 'nowrap',
                                boxShadow: '0 1px 2px rgba(5,150,105,0.06)',
                              }}
                              title="View Confirmed List"
                            >
                              <span>Confirmed</span>
                              <span style={{ fontSize: '12px', fontWeight: 800, color: '#047857' }}>{counts.confCnt}</span>
                            </button>
                          </div>
                        </td>
                      )}

                      {/* STATUS Column */}
                      <td style={{ padding: '8px', textAlign: 'center' }}>
                        <button
                          onClick={(e) => {
                            e.stopPropagation();
                            handleToggleStatus(t);
                          }}
                          style={{
                            padding: '3px 8px',
                            borderRadius: '4px',
                            fontSize: '11px',
                            fontWeight: 700,
                            background: isActive ? '#d1fae5' : '#fee2e2',
                            color: isActive ? '#047857' : '#dc2626',
                            border: isActive ? '1px solid #a7f3d0' : '1px solid #fca5a5',
                            cursor: 'pointer',
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '4px',
                          }}
                          title="Click to toggle Active/Inactive status"
                        >
                          <ToggleRight size={12} /> {isActive ? 'Active' : 'Inactive'}
                        </button>
                      </td>

                      {/* SETTINGS Column (Visible for Super Admin, Pro User, Admin, Operator — Hidden for Org roles) */}
                      {isAdminOrOperator && (
                        <td style={{ padding: '8px', textAlign: 'center' }}>
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setSettingModalTable(t);
                            }}
                            style={{
                              padding: '3px 8px',
                              borderRadius: '4px',
                              fontSize: '11px',
                              fontWeight: 700,
                              background: '#eff6ff',
                              color: '#2563eb',
                              border: '1px solid #bfdbfe',
                              cursor: 'pointer',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '4px',
                              transition: 'all 0.15s',
                            }}
                            onMouseEnter={(e) => {
                              e.currentTarget.style.background = '#2563eb';
                              e.currentTarget.style.color = '#ffffff';
                            }}
                            onMouseLeave={(e) => {
                              e.currentTarget.style.background = '#eff6ff';
                              e.currentTarget.style.color = '#2563eb';
                            }}
                            title={`Configure Table Schema & Settings for ${t.name}`}
                          >
                            <Settings size={12} /> <span>Settings</span>
                          </button>
                        </td>
                      )}
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
          orgName={activeScopedOrg?.name || selectedTable?.client_name || selectedClientOrg?.name || ''}
          onClose={() => setShowAddEditDrawer(false)}
          onSave={() => {
            setShowAddEditDrawer(false);
            loadTables();
          }}
          addToast={addToast}
        />
      )}

      {/* Dedicated Table Setting Details Center Modal (No redundant buttons/stats!) */}
      {settingModalTable && (
        <TableSettingSchemaModal
          table={settingModalTable}
          orgName={activeScopedOrg?.name || selectedTable?.client_name || selectedClientOrg?.name || ''}
          onClose={() => setSettingModalTable(null)}
        />
      )}

      {/* Delete All Confirmation Modal */}
      {activeModal === 'delete-all' && selectedTable && (
        <Modal
          isOpen={true}
          onClose={() => setActiveModal(null)}
          title="Delete All ID Cards"
          icon={<Trash2 size={16} style={{ color: '#ef4444' }} />}
          size="sm"
          footer={
            <>
              <Button size="sm" variant="secondary" onClick={() => setActiveModal(null)}>
                Cancel
              </Button>
              <Button size="sm" variant="danger" onClick={confirmDeleteAll}>
                Confirm Delete All
              </Button>
            </>
          }
        >
          <p style={{ fontSize: '12px', color: '#475569', margin: '0 0 14px', lineHeight: 1.5 }}>
            Are you sure you want to permanently delete all cards in <strong>"{selectedTable.name}"</strong>? Enter
            the confirmation code below:
          </p>
          <Input
            size="md"
            value={deleteCodeInput}
            onChange={(e) => setDeleteCodeInput(e.target.value)}
            placeholder="Enter 10-digit delete code"
            style={{ width: '100%' }}
          />
        </Modal>
      )}

      {/* ── Table Delegation / Sharing Modal ── */}
      {shareModalTable && (
        <TableShareModal
          table={shareModalTable}
          onClose={() => setShareModalTable(null)}
          addToast={addToast}
        />
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
        day: '2-digit',
        month: '2-digit',
        year: 'numeric',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch {
      return String(d);
    }
  };

  return (
    <div className="center-modal-overlay">
      <div
        className="center-modal-panel"
        style={{
          width: '560px',
          height: 'auto',
          maxHeight: '85vh',
          padding: 0,
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          borderRadius: '10px',
        }}
      >
        {/* Modal Header */}
        <div
          style={{
            padding: '16px 20px',
            background: '#1e293b',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div>
            <h3
              style={{
                margin: 0,
                fontSize: '15px',
                fontWeight: 700,
                display: 'flex',
                alignItems: 'center',
                gap: '8px',
                color: '#ffffff',
              }}
            >
              <Settings size={18} style={{ color: '#38bdf8' }} /> Table Setting Details
            </h3>
            <span style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px', display: 'block' }}>{table.name}</span>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#94a3b8', cursor: 'pointer', padding: '4px' }}
          >
            <X size={20} />
          </button>
        </div>

        {/* Modal Body */}
        <div
          style={{ flex: 1, padding: '20px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '16px' }}
        >
          {/* Metadata Card */}
          <div
            style={{
              background: '#f8fafc',
              padding: '14px',
              borderRadius: '8px',
              border: '1px solid #e2e8f0',
              display: 'flex',
              flexDirection: 'column',
              gap: '10px',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                Table Metadata
              </span>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <span
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '4px',
                    padding: '3px 8px',
                    borderRadius: '4px',
                    background: typeMeta.bg,
                    color: typeMeta.color,
                    border: `1px solid ${typeMeta.border}`,
                    fontSize: '11px',
                    fontWeight: 600,
                  }}
                >
                  <TypeIcon size={12} /> {typeMeta.label}
                </span>
                <span
                  style={{
                    padding: '3px 8px',
                    borderRadius: '4px',
                    background: table.is_active !== false ? '#d1fae5' : '#fee2e2',
                    color: table.is_active !== false ? '#047857' : '#dc2626',
                    fontSize: '11px',
                    fontWeight: 700,
                  }}
                >
                  {table.is_active !== false ? 'Active' : 'Inactive'}
                </span>
              </div>
            </div>

            <div
              style={{
                fontSize: '12px',
                color: '#334155',
                display: 'grid',
                gridTemplateColumns: '1fr 1fr',
                gap: '8px',
                paddingTop: '8px',
                borderTop: '1px solid #e2e8f0',
              }}
            >
              <div>
                <strong style={{ color: '#64748b' }}>Organisation:</strong>{' '}
                {getDisplayOrgName(table.client_name, orgName) || 'Standard'}
              </div>
              <div>
                <strong style={{ color: '#64748b' }}>Created By:</strong> {table.created_by || table.user || 'Admin'}
              </div>
              <div>
                <strong style={{ color: '#64748b' }}>Created At:</strong> {formatDate(table.created_at)}
              </div>
              <div>
                <strong style={{ color: '#64748b' }}>Last Updated:</strong>{' '}
                {formatDate(table.updated_at || table.created_at)}
              </div>
            </div>
          </div>

          {/* Fields Schema List */}
          <div>
            <div
              style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}
            >
              <span style={{ fontSize: '11px', fontWeight: 700, color: '#64748b', textTransform: 'uppercase' }}>
                Table Fields Schema ({fields.length} Fields)
              </span>
            </div>

            <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', overflow: 'hidden' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}>
                  <tr>
                    <th style={{ padding: '8px', textAlign: 'center', width: '40px', color: '#475569' }}>#</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', color: '#475569' }}>Field Name</th>
                    <th style={{ padding: '8px 12px', textAlign: 'left', width: '130px', color: '#475569' }}>
                      Data Type
                    </th>
                    <th style={{ padding: '8px', textAlign: 'center', width: '80px', color: '#475569' }}>Mandatory</th>
                  </tr>
                </thead>
                <tbody>
                  {fields.map((f, idx) => (
                    <tr key={idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                      <td
                        style={{
                          padding: '7px 8px',
                          textAlign: 'center',
                          color: '#94a3b8',
                          fontSize: '11px',
                          fontWeight: 600,
                        }}
                      >
                        {idx + 1}
                      </td>
                      <td style={{ padding: '7px 12px', fontWeight: 600, color: '#1e293b' }}>{f.name}</td>
                      <td
                        style={{
                          padding: '7px 12px',
                          color: '#2563eb',
                          textTransform: 'uppercase',
                          fontSize: '11px',
                          fontWeight: 700,
                        }}
                      >
                        {f.type || 'text'}
                      </td>
                      <td style={{ padding: '7px 8px', textAlign: 'center' }}>
                        {f.mandatory ? (
                          <span
                            style={{
                              padding: '2px 6px',
                              borderRadius: '3px',
                              background: '#dcfce7',
                              color: '#15803d',
                              fontSize: '10px',
                              fontWeight: 700,
                            }}
                          >
                            Required
                          </span>
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
        <div
          style={{
            padding: '12px 20px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            justifyContent: 'flex-end',
          }}
        >
          <button
            onClick={onClose}
            style={{
              padding: '7px 18px',
              background: '#2563eb',
              border: 'none',
              borderRadius: '4px',
              color: '#ffffff',
              fontWeight: 700,
              cursor: 'pointer',
              fontSize: '12px',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>
  );
}

/* ─── Table Delegation / Sharing Modal (Prime Manager assigns table access to Super Managers) ─── */
function TableShareModal({ table, onClose, addToast, onSuccess }) {
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [superManagers, setSuperManagers] = useState([]);
  const [selectedManagerIds, setSelectedManagerIds] = useState([]);

  useEffect(() => {
    (async () => {
      setLoading(true);
      try {
        const res = await schemaApi.getSharedManagers(table.id);
        if (res && res.success) {
          const list = res.super_managers || [];
          setSuperManagers(list);
          setSelectedManagerIds(list.filter((m) => m.is_shared).map((m) => m.manager_id));
        }
      } catch {
        addToast?.('Failed to load Super Managers for this table.', 'error');
      } finally {
        setLoading(false);
      }
    })();
  }, [table.id, addToast]);


  const toggleManager = (id) => {
    setSelectedManagerIds((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id]
    );
  };

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await schemaApi.shareManagers(table.id, {
        manager_ids: selectedManagerIds,
        can_edit_cards: true,
        can_approve_print: false,
      });
      addToast?.(res?.message || 'Table delegation updated successfully!', 'success');
      onSuccess?.();
      onClose();
    } catch (err) {
      const msg = err.response?.data?.message || 'Failed to update table delegation.';
      addToast?.(msg, 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        background: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 99999999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
      }}
    >
      <div
        style={{
          width: '480px',
          maxWidth: '95vw',
          background: '#ffffff',
          borderRadius: '8px',
          boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.2)',
          overflow: 'hidden',
          display: 'flex',
          flexDirection: 'column',
          maxHeight: '90vh',
        }}
      >
        <div
          style={{
            background: '#7c3aed',
            color: '#fff',
            padding: '14px 18px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '14px' }}>
            <Share2 size={16} />
            <span>Delegate Table: {table.name}</span>
          </div>
          <button
            onClick={onClose}
            style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}
          >
            <X size={18} />
          </button>
        </div>

        <div style={{ padding: '16px 20px', flex: 1, overflowY: 'auto' }}>
          <p style={{ fontSize: '12px', color: '#64748b', margin: '0 0 12px 0', lineHeight: 1.5 }}>
            Select Super Managers who are permitted to manage this table. Super Managers can only view and edit cards for tables delegated to them.
          </p>

          {loading ? (
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '30px 0' }}>
              <Loader2 size={24} className="animate-spin" style={{ color: '#7c3aed' }} />
            </div>
          ) : superManagers.length === 0 ? (
            <div
              style={{
                padding: '20px',
                textAlign: 'center',
                background: '#f8fafc',
                borderRadius: '6px',
                border: '1px dashed #cbd5e1',
                fontSize: '12px',
                color: '#64748b',
              }}
            >
              No Super Managers found for this Organisation. You can create Super Managers from the <strong>Manager Accounts</strong> section.
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {superManagers.map((sm) => {
                const isChecked = selectedManagerIds.includes(sm.manager_id);
                return (
                  <label
                    key={sm.manager_id}
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      gap: '12px',
                      padding: '10px 14px',
                      borderRadius: '6px',
                      border: isChecked ? '1px solid #7c3aed' : '1px solid #e2e8f0',
                      background: isChecked ? '#f5f3ff' : '#ffffff',
                      cursor: 'pointer',
                      transition: 'all 0.15s',
                    }}
                  >
                    <input
                      type="checkbox"
                      checked={isChecked}
                      onChange={() => toggleManager(sm.manager_id)}
                      style={{ accentColor: '#7c3aed', width: '16px', height: '16px' }}
                    />
                    <div style={{ flex: 1 }}>
                      <div style={{ fontWeight: 600, fontSize: '13px', color: '#0f172a' }}>{sm.name}</div>
                      <div style={{ fontSize: '11px', color: '#64748b' }}>
                        @{sm.username} {sm.email ? `• ${sm.email}` : ''}
                      </div>
                    </div>
                    {isChecked && (
                      <span
                        style={{
                          fontSize: '10px',
                          fontWeight: 700,
                          padding: '2px 8px',
                          borderRadius: '4px',
                          background: '#ede9fe',
                          color: '#6d28d9',
                        }}
                      >
                        Delegated
                      </span>
                    )}
                  </label>
                );
              })}
            </div>
          )}
        </div>

        <div
          style={{
            padding: '12px 18px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            gap: '8px',
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '7px 14px',
              background: '#ffffff',
              border: '1px solid #cbd5e1',
              borderRadius: '4px',
              color: '#64748b',
              fontWeight: 600,
              fontSize: '12px',
              cursor: 'pointer',
            }}
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={saving || loading || superManagers.length === 0}
            onClick={handleSave}
            style={{
              padding: '7px 16px',
              background: '#7c3aed',
              border: 'none',
              borderRadius: '4px',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '12px',
              cursor: saving || superManagers.length === 0 ? 'not-allowed' : 'pointer',
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
            }}
          >
            {saving ? <Loader2 size={13} className="animate-spin" /> : <Save size={13} />}
            <span>{saving ? 'Saving...' : 'Save Delegation'}</span>
          </button>
        </div>
      </div>
    </div>
  );
}

function bulkBtnStyle(type, disabled) {

  const activeColors = {
    reupload: { bg: '#f97316', color: '#ffffff', border: '#f97316' },
    downloadAll: { bg: '#2563eb', color: '#ffffff', border: '#2563eb' },
    deleteAll: { bg: '#ef4444', color: '#ffffff', border: '#ef4444' },
    upgradeClass: { bg: '#10b981', color: '#ffffff', border: '#10b981' },
  };
  const cfg = activeColors[type] || activeColors.reupload;
  return {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '5px',
    height: '28px',
    padding: '0 10px',
    borderRadius: '4px',
    fontSize: '11px',
    fontWeight: 600,
    background: disabled ? 'rgba(255, 255, 255, 0.08)' : cfg.bg,
    color: disabled ? 'rgba(255, 255, 255, 0.45)' : cfg.color,
    border: disabled ? '1px solid rgba(255, 255, 255, 0.15)' : `1px solid ${cfg.border}`,
    cursor: disabled ? 'not-allowed' : 'pointer',
    whiteSpace: 'nowrap',
    boxSizing: 'border-box',
    opacity: disabled ? 0.6 : 1,
    fontFamily: 'var(--font-family)',
    transition: 'all 0.15s',
  };
}
