import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Pen,
  Eye,
  EyeOff,
  Users,
  UsersRound,
  Trash2,
  ToggleRight,
  Building,
  Settings,
  CreditCard,
  Search,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RefreshCw,
  Loader2,
  Info,
  Save,
  Mail,
  Phone,
  Shield,
  CheckCircle2,
  User,
} from 'lucide-react';

import WatermarkLogo from '../common/WatermarkLogo';
import { SkeletonTableRows } from '../common/Skeleton';
import CustomSelect from '../common/CustomSelect';
import { clientApi, managerApi, staffApi } from '../../services/api';
import { formatDT } from '../../utils/formatters';
import { STATUS_TABS, DEFAULT_PAGE_SIZE_OPTIONS as PAGE_SIZE_OPTIONS } from '../../utils/constants';

export default function ClientDirectoryView({ addToast, onOpenActionDrawer, onNavigate, onOpenDeleteModal }) {
  const [clients, setClients] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [statusTab, setStatusTab] = useState('All');
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal] = useState(0);

  /* Dispatch footer data count & selection */
  useEffect(() => {
    let selectedText = '';
    if (selected) {
      const match = clients.find((c) => String(c.id) === String(selected));
      if (match) {
        const orgName = match.name || match.school_name || match.username || `Org #${match.id}`;
        selectedText = `Selected: ${orgName}`;
      }
    }
    window.dispatchEvent(
      new CustomEvent('cardflow:data-count', {
        detail: {
          text: `Total Organisations: ${clients.length}`,
          selectedText,
          count: clients.length,
        },
      })
    );
  }, [clients, selected]);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await clientApi.getActive({
        page,
        search,
        status: statusTab !== 'All' ? statusTab.toLowerCase() : '',
        page_size: pageSize,
      });
      const list = Array.isArray(data?.clients)
        ? data.clients
        : Array.isArray(data?.results)
          ? data.results
          : Array.isArray(data)
            ? data
            : [];
      setClients(list);
      setTotal(data?.total || data?.count || list.length);
    } catch (err) {
      console.error('Load client directory error:', err);
      setClients([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusTab, pageSize]);

  useEffect(() => {
    load();
    window.__reloadClientDirectory = load;
    return () => {
      if (window.__reloadClientDirectory === load) delete window.__reloadClientDirectory;
    };
  }, [load]);

  const selClient = clients.find((c) => c.id === selected);

  const handleToggleStatus = async () => {
    if (!selected) return;

    try {
      await clientApi.toggleStatus(selected);
      addToast?.(`Status toggled for ${selClient?.name || 'organisation'}`, 'success');
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Failed to toggle status';
      addToast?.(msg, 'error');
    } finally {
      load();
      window.__reloadDashboard?.();
    }
  };

  const handleDeleteClient = () => {
    if (!selected) return;
    if (onOpenDeleteModal) {
      onOpenDeleteModal({
        title: `Delete Organisation "${selClient?.name || ''}"`,
        itemDescription: `organisation "${selClient?.name || ''}"`,
        onConfirm: async () => {
          try {
            await clientApi.deleteClient(selected);
            addToast?.(`Organisation "${selClient?.name || ''}" deleted`, 'success');
          } catch (err) {
            const msg = err?.response?.data?.message || err?.message || 'Failed to delete organisation';
            addToast?.(msg, 'error');
          } finally {
            setSelected(null);
            load();
            window.__reloadDashboard?.();
          }
        },
      });
    }
  };

  const [showManagersDrawer, setShowManagersDrawer] = useState(false);
  const [showAssistantsDrawer, setShowAssistantsDrawer] = useState(false);
  const [editingManager, setEditingManager] = useState(null); // null | 'new' | managerObj
  const [editingAssistant, setEditingAssistant] = useState(null); // null | 'new' | assistantObj
  const [orgManagers, setOrgManagers] = useState([]);
  const [orgAssistants, setOrgAssistants] = useState([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const getManagerCount = useCallback((org) => {
    if (!org) return 1;
    return org.managers_count ?? org.manager_count ?? 1;
  }, []);

  const getAssistantCount = useCallback((org) => {
    if (!org) return 0;
    return org.assistants_count ?? org.assistant_count ?? 0;
  }, []);

  const loadOrgManagers = useCallback(async (org) => {
    if (!org?.id) return;
    setDrawerLoading(true);
    try {
      const data = await managerApi.list({ organisation_id: org.id });
      setOrgManagers(data?.managers || []);
    } catch {
      setOrgManagers([]);
    } finally {
      setDrawerLoading(false);
    }
  }, []);

  const loadOrgAssistants = useCallback(async (org) => {
    if (!org?.id) return;
    setDrawerLoading(true);
    try {
      const data = await staffApi.list({ client_id: org.id, role: 'assistant' });
      setOrgAssistants(data?.staff || data?.results || (Array.isArray(data) ? data : []));
    } catch {
      setOrgAssistants([]);
    } finally {
      setDrawerLoading(false);
    }
  }, []);

  const handleOpenManagersDrawer = (client) => {
    setSelected(client.id);
    loadOrgManagers(client);
    setShowManagersDrawer(true);
  };

  const handleOpenAssistantsDrawer = (client) => {
    setSelected(client.id);
    loadOrgAssistants(client);
    setShowAssistantsDrawer(true);
  };

  const handleSaveManagerInline = async (mgrData) => {
    try {
      if (mgrData.id && !String(mgrData.id).startsWith('mgr_')) {
        await managerApi.update(mgrData.id, mgrData);
      } else {
        await managerApi.create({
          ...mgrData,
          organisation_id: selClient?.id,
        });
      }
      addToast?.(`Manager ${mgrData.name || ''} saved successfully!`, 'success');
      setEditingManager(null);
      if (selClient) loadOrgManagers(selClient);
    } catch (err) {
      console.error('Save manager error:', err);
      addToast?.(err?.response?.data?.message || 'Failed to save manager', 'error');
    }
  };

  const handleSaveAssistantInline = async (astData) => {
    try {
      if (astData.id) {
        await staffApi.update(astData.id, astData);
      } else {
        await staffApi.create({
          ...astData,
          client: selClient?.id,
          role: 'assistant',
        });
      }
      addToast?.(`Assistant ${astData.name || ''} saved successfully!`, 'success');
      setEditingAssistant(null);
      if (selClient) loadOrgAssistants(selClient);
    } catch (err) {
      console.error('Save assistant error:', err);
      addToast?.(err?.response?.data?.message || 'Failed to save assistant', 'error');
    }
  };

  return (
    <div
      className="view-container"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', position: 'relative' }}
    >
      {/* ── ACTION BAR ── */}
      <div
        className="action-bar"
        id="client-action-bar"
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
            style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)' }}
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
              placeholder="Search All..."
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
                onClick={() => onOpenActionDrawer?.('add-client')}
                style={{
                  background: '#2563eb',
                  color: '#ffffff',
                  height: '28px',
                  padding: '0 10px',
                  fontSize: '11px',
                  fontWeight: 700,
                  borderRadius: '4px',
                  border: 'none',
                  cursor: 'pointer',
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                }}
              >
                <Plus size={13} /> Add
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={() => selClient && onOpenActionDrawer?.('edit-client', selClient)}
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
                onClick={handleDeleteClient}
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
                disabled={!selected}
                onClick={() => selClient && onNavigate?.('cards', { clientId: selClient.id, clientName: selClient.name || selClient.school_name, org: selClient })}
                title="View Tables"
                style={{
                  background: selected ? '#3b82f6' : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected ? '1px solid #3b82f6' : '1px solid rgba(255, 255, 255, 0.15)',
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
                <CreditCard size={13} /> <span>Tables</span>
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={() => {
                  setShowManagersDrawer(!showManagersDrawer);
                  setShowAssistantsDrawer(false);
                }}
                title="Manage Managers"
                style={{
                  background: selected ? (showManagersDrawer ? '#2563eb' : '#3b82f6') : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected
                    ? showManagersDrawer
                      ? '1px solid #2563eb'
                      : '1px solid #3b82f6'
                    : '1px solid rgba(255, 255, 255, 0.15)',
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
                <Users size={13} /> <span>Managers</span>
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={() => {
                  setShowAssistantsDrawer(!showAssistantsDrawer);
                  setShowManagersDrawer(false);
                }}
                title="Manage Assistants"
                style={{
                  background: selected ? (showAssistantsDrawer ? '#2563eb' : '#3b82f6') : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected
                    ? showAssistantsDrawer
                      ? '1px solid #2563eb'
                      : '1px solid #3b82f6'
                    : '1px solid rgba(255, 255, 255, 0.15)',
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
                <UsersRound size={13} /> <span>Assistants</span>
              </button>
            </div>
          </div>
        </div>
      </div>

      {/* ── TABLE CONTAINER ── */}
      <div
        className="table-wrapper"
        style={{
          flex: 1,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          position: 'relative',
        }}
      >
        <WatermarkLogo />
        <table className="data-table" id="clientsTable" style={{ flexShrink: 0, fontSize: '13px' }}>
          <thead>
            <tr style={{ fontSize: '12px' }}>
              <th style={{ width: '45px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>S. No.</th>
              <th style={{ width: 'auto', textAlign: 'left', fontSize: '12px', padding: '9px 12px' }}>Name</th>
              <th style={{ width: '180px', textAlign: 'left', fontSize: '12px', padding: '9px 12px' }}>Email</th>
              <th style={{ width: '130px', textAlign: 'left', fontSize: '12px', padding: '9px 12px' }}>Username</th>
              <th style={{ width: '110px', textAlign: 'center', fontSize: '12px', padding: '9px 12px' }}>Mobile</th>
              <th style={{ width: '80px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>Status</th>
              <th style={{ width: '80px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>Managers</th>
              <th style={{ width: '80px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>Assistants</th>
              <th style={{ width: '75px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>Tables</th>
              <th style={{ width: '120px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>Created At</th>
              <th style={{ width: '120px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }}>Updated At</th>
              <th style={{ width: '45px', textAlign: 'center', fontSize: '12px', padding: '9px 8px' }} title="Log">
                Log
              </th>
            </tr>
          </thead>
          <tbody id="client-table-body">
            {loading ? (
              <SkeletonTableRows count={12} cols={12} dark={false} />
            ) : (
              clients.map((c, idx) => {
                const statusStr = String(
                  c.status || (c.is_active !== undefined ? (c.is_active ? 'active' : 'inactive') : 'active')
                ).toLowerCase();
                const isActive = statusStr === 'active' || statusStr === 'true' || c.is_active === true;
                const isSel = c.id === selected;
                return (
                  <tr
                    key={c.id}
                    className={isSel ? 'selected' : ''}
                    onClick={() => setSelected(isSel ? null : c.id)}
                    onDoubleClick={() => onNavigate?.('cards', { clientId: c.id, clientName: c.name || c.school_name, org: c })}
                    data-client-id={c.id}
                    style={{ fontSize: '13px', cursor: 'pointer' }}
                    title="Single-click to select | Double-click to open Tables"
                  >
                    <td
                      className="text-center"
                      style={{
                        width: '45px',
                        textAlign: 'center',
                        fontWeight: 600,
                        color: '#475569',
                        fontSize: '12px',
                        padding: '9px 8px',
                      }}
                    >
                      {(page - 1) * pageSize + idx + 1}
                    </td>
                    <td style={{ width: 'auto', textAlign: 'left', padding: '9px 12px' }}>
                      <div className="client-name-cell">
                        <span style={{ fontWeight: 600, color: '#0f172a', fontSize: '13px' }}>
                          {c.name || c.school_name || '—'}
                        </span>
                      </div>
                    </td>
                    <td
                      style={{
                        width: '180px',
                        color: '#334155',
                        fontSize: '12px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        textAlign: 'left',
                        padding: '9px 12px',
                      }}
                    >
                      {c.email || c.user?.email || '—'}
                    </td>
                    <td
                      style={{
                        width: '130px',
                        color: '#334155',
                        fontSize: '12px',
                        fontWeight: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                        textAlign: 'left',
                        padding: '9px 12px',
                      }}
                    >
                      {c.username ||
                        c.user?.username ||
                        c.user_code ||
                        (c.email ? c.email.split('@')[0] : '') ||
                        (c.name ? c.name.toLowerCase().replace(/[^a-z0-9]/g, '') : '—')}
                    </td>
                    <td
                      className="text-center"
                      style={{
                        width: '110px',
                        color: '#334155',
                        fontSize: '12px',
                        textAlign: 'center',
                        padding: '9px 12px',
                      }}
                    >
                      {c.phone || c.user?.phone || '—'}
                    </td>
                    <td className="text-center" style={{ width: '80px', textAlign: 'center', padding: '9px 8px' }}>
                      <span
                        className={`badge ${isActive ? 'badge-success' : 'badge-neutral'}`}
                        style={{ fontSize: '11px', padding: '3px 8px' }}
                      >
                        {isActive ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="text-center" style={{ width: '80px', textAlign: 'center', padding: '9px 8px' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          background: '#f3e8ff',
                          color: '#6b21a8',
                          fontSize: '12px',
                          fontWeight: 600,
                          border: '1px solid #d8b4fe',
                        }}
                      >
                        <Users size={12} /> {getManagerCount(c)}
                      </span>
                    </td>
                    <td className="text-center" style={{ width: '80px', textAlign: 'center', padding: '9px 8px' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          background: '#dcfce7',
                          color: '#15803d',
                          fontSize: '12px',
                          fontWeight: 600,
                          border: '1px solid #86efac',
                        }}
                      >
                        <UsersRound size={12} /> {getAssistantCount(c)}
                      </span>
                    </td>
                    <td className="text-center" style={{ width: '75px', textAlign: 'center', padding: '9px 8px' }}>
                      <span
                        style={{
                          display: 'inline-flex',
                          alignItems: 'center',
                          gap: '4px',
                          padding: '3px 8px',
                          borderRadius: '4px',
                          background: '#dbeafe',
                          color: '#1e40af',
                          fontSize: '12px',
                          fontWeight: 600,
                          border: '1px solid #93c5fd',
                        }}
                      >
                        <CreditCard size={12} /> {c.table_count || c.tables_count || 0}
                      </span>
                    </td>
                    <td
                      className="text-center"
                      style={{
                        width: '120px',
                        fontSize: '12px',
                        color: '#475569',
                        textAlign: 'center',
                        padding: '9px 8px',
                      }}
                    >
                      {formatDT(c.created_at)}
                    </td>
                    <td
                      className="text-center"
                      style={{
                        width: '120px',
                        fontSize: '12px',
                        color: '#475569',
                        textAlign: 'center',
                        padding: '9px 8px',
                      }}
                    >
                      {formatDT(c.updated_at)}
                    </td>
                    <td className="text-center" style={{ width: '45px', textAlign: 'center', padding: '9px 8px' }}>
                      <button
                        className="client-history-trigger"
                        onClick={(e) => {
                          e.stopPropagation();
                          addToast?.(`Log: ${c.name || idx + 1}`, 'info');
                        }}
                        title="View log"
                        style={{
                          width: '24px',
                          height: '24px',
                          border: 'none',
                          borderRadius: '4px',
                          background: 'rgba(37,99,235,0.1)',
                          color: '#2563eb',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <Info size={13} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Empty state — sibling to table so flex:1 fills remaining height */}
        {!loading && clients.length === 0 && (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '40px 20px',
              textAlign: 'center',
              minHeight: '240px',
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
              <Building size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Organisations Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search
                  ? `No organisations match "${search}"`
                  : 'There are no organisations registered in the system yet.'}
              </p>
            </div>
            {!search && (
              <button
                onClick={() => onOpenActionDrawer?.('add-client')}
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
                <Plus size={14} /> Add First Organisation
              </button>
            )}
          </div>
        )}
      </div>

      {/* ── BACKDROP OVERLAY WITH BLUR (No onClick -> closed by close buttons only) ── */}
      {(showManagersDrawer || showAssistantsDrawer) && (
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

      {/* ── MANAGERS SLIDE-OVER DRAWER ── */}
      {showManagersDrawer && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            width: '620px',
            minWidth: '600px',
            maxWidth: '95vw',
            background: '#ffffff',
            boxShadow: '-8px 0 25px rgba(0,0,0,0.15)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Drawer Header */}
          <div
            style={{
              background: 'linear-gradient(135deg, #1e3a8a 0%, #2563eb 100%)',
              color: '#fff',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
                <Users size={18} />
                <span>Managers for "{selClient?.name || 'Organisation'}"</span>
              </div>
              <p style={{ margin: '3px 0 0 0', fontSize: '11px', color: '#bfdbfe' }}>
                Primary owner & extra manager accounts with assigned table access
              </p>
            </div>
            <button
              onClick={() => {
                setShowManagersDrawer(false);
                setEditingManager(null);
              }}
              style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}
            >
              <X size={18} />
            </button>
          </div>

          {editingManager ? (
            <ManagerInlineForm
              manager={editingManager === 'new' ? null : editingManager}
              orgName={selClient?.name || 'Organisation'}
              onSave={handleSaveManagerInline}
              onCancel={() => setEditingManager(null)}
            />
          ) : (
            <>
              {/* Action Row */}
              <div
                style={{
                  padding: '12px 20px',
                  background: '#f8fafc',
                  borderBottom: '1px solid #e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
                  Total Managers: {orgManagers.length}
                </span>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => setEditingManager('new')}
                  style={{ fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                >
                  <Plus size={12} /> Add Manager Account
                </button>
              </div>

              {/* Manager Cards List */}
              <div
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  padding: '16px 20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                  background: '#f8fafc',
                }}
              >
                {orgManagers.map((m, idx) => {
                  const isPrimary = m.is_default || m.client_type === 'primary';
                  const isActive = m.status !== 'inactive' && m.is_active !== false;

                  return (
                    <div
                      key={m.id || idx}
                      style={{
                        position: 'relative',
                        border: '1px solid #e2e8f0',
                        borderRadius: '10px',
                        background: '#ffffff',
                        boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                        overflow: 'hidden',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {/* Accent Line Header */}
                      <div
                        style={{
                          height: '4px',
                          background: isPrimary
                            ? 'linear-gradient(90deg, #1d4ed8 0%, #3b82f6 100%)'
                            : 'linear-gradient(90deg, #7c3aed 0%, #a855f7 100%)',
                        }}
                      />

                      <div style={{ padding: '16px 18px' }}>
                        {/* Top Header Row */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            marginBottom: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                            <div
                              style={{
                                width: '38px',
                                height: '38px',
                                borderRadius: '8px',
                                background: isPrimary
                                  ? 'linear-gradient(135deg, #1d4ed8 0%, #3b82f6 100%)'
                                  : 'linear-gradient(135deg, #6b21a8 0%, #9333ea 100%)',
                                color: '#ffffff',
                                display: 'flex',
                                alignItems: 'center',
                                justifyContent: 'center',
                                boxShadow: isPrimary
                                  ? '0 3px 8px rgba(37,99,235,0.25)'
                                  : '0 3px 8px rgba(147,51,234,0.25)',
                              }}
                            >
                              <User size={18} />
                            </div>
                            <div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                                <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                                  {m.name}
                                </h4>
                              </div>
                              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginTop: '3px' }}>
                                <span
                                  style={{
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    padding: '2px 8px',
                                    borderRadius: '4px',
                                    background: isPrimary ? '#dbeafe' : '#f3e8ff',
                                    color: isPrimary ? '#1d4ed8' : '#6b21a8',
                                    border: isPrimary ? '1px solid #bfdbfe' : '1px solid #e9d5ff',
                                  }}
                                >
                                  {isPrimary ? 'Client (Primary Owner)' : 'Manager'}
                                </span>
                              </div>
                            </div>
                          </div>

                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '5px',
                                fontSize: '11px',
                                fontWeight: 600,
                                padding: '3px 9px',
                                borderRadius: '12px',
                                background: isActive ? '#f0fdf4' : '#fff1f2',
                                color: isActive ? '#15803d' : '#be123c',
                                border: isActive ? '1px solid #bbf7d0' : '1px solid #fecdd3',
                              }}
                            >
                              <span
                                style={{
                                  width: '6px',
                                  height: '6px',
                                  borderRadius: '50%',
                                  background: isActive ? '#22c55e' : '#e11d48',
                                }}
                              />
                              {isActive ? 'Active' : 'Inactive'}
                            </span>
                          </div>
                        </div>

                        {/* Contact Info Box */}
                        <div
                          style={{
                            display: 'grid',
                            gridTemplateColumns: '1fr 1fr',
                            gap: '10px',
                            padding: '10px 12px',
                            borderRadius: '8px',
                            background: '#f8fafc',
                            border: '1px solid #f1f5f9',
                            fontSize: '11px',
                            color: '#475569',
                            marginBottom: '12px',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
                            <Mail size={13} style={{ color: '#64748b', flexShrink: 0 }} />
                            <span
                              style={{
                                fontWeight: 600,
                                color: '#334155',
                                whiteSpace: 'nowrap',
                                overflow: 'hidden',
                                textOverflow: 'ellipsis',
                              }}
                            >
                              {m.username || m.email || '—'}
                            </span>
                          </div>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <Phone size={13} style={{ color: '#64748b', flexShrink: 0 }} />
                            <span style={{ fontWeight: 600, color: '#334155' }}>{m.phone || '—'}</span>
                          </div>
                        </div>

                        {/* Assigned Tables */}
                        <div style={{ marginBottom: '14px' }}>
                          <div
                            style={{
                              fontSize: '11px',
                              fontWeight: 700,
                              color: '#334155',
                              marginBottom: '6px',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '5px',
                            }}
                          >
                            <CreditCard size={12} style={{ color: '#2563eb' }} />
                            <span>Assigned Tables ({(m.assigned_tables || ['All Tables']).length}):</span>
                          </div>
                          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '5px' }}>
                            {(m.assigned_tables || ['All Tables']).map((tbl, tIdx) => (
                              <span
                                key={tIdx}
                                style={{
                                  fontSize: '10px',
                                  fontWeight: 600,
                                  padding: '3px 9px',
                                  borderRadius: '5px',
                                  background: '#eff6ff',
                                  color: '#1e40af',
                                  border: '1px solid #bfdbfe',
                                }}
                              >
                                {tbl}
                              </span>
                            ))}
                          </div>
                        </div>

                        {/* Card Actions Footer */}
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'flex-end',
                            gap: '8px',
                            paddingTop: '10px',
                            borderTop: '1px solid #f1f5f9',
                          }}
                        >
                          <button
                            className="btn btn-xs btn-neutral"
                            onClick={() => setEditingManager(m)}
                            style={{
                              fontSize: '11px',
                              padding: '5px 12px',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px',
                            }}
                          >
                            <Pen size={12} /> Edit Manager
                          </button>
                          <button
                            className="btn btn-xs btn-warning"
                            onClick={() => addToast?.(`Status toggled for ${m.name}`, 'success')}
                            style={{
                              fontSize: '11px',
                              padding: '5px 12px',
                              display: 'inline-flex',
                              alignItems: 'center',
                              gap: '5px',
                            }}
                          >
                            <ToggleRight size={12} /> Toggle Status
                          </button>
                        </div>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      )}

      {/* ── ASSISTANTS SLIDE-OVER DRAWER ── */}
      {showAssistantsDrawer && (
        <div
          style={{
            position: 'fixed',
            top: 0,
            right: 0,
            bottom: 0,
            width: '620px',
            minWidth: '600px',
            maxWidth: '95vw',
            background: '#ffffff',
            boxShadow: '-8px 0 25px rgba(0,0,0,0.15)',
            zIndex: 1000,
            display: 'flex',
            flexDirection: 'column',
          }}
        >
          {/* Drawer Header */}
          <div
            style={{
              background: 'linear-gradient(135deg, #15803d 0%, #16a34a 100%)',
              color: '#fff',
              padding: '16px 20px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              flexShrink: 0,
            }}
          >
            <div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
                <UsersRound size={18} />
                <span>Assistants for "{selClient?.name || 'Organisation'}"</span>
              </div>
              <p style={{ margin: '3px 0 0 0', fontSize: '11px', color: '#dcfce7' }}>
                Assigned assistant accounts & permission settings
              </p>
            </div>
            <button
              onClick={() => {
                setShowAssistantsDrawer(false);
                setEditingAssistant(null);
              }}
              style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}
            >
              <X size={18} />
            </button>
          </div>

          {editingAssistant ? (
            <AssistantInlineForm
              assistant={editingAssistant === 'new' ? null : editingAssistant}
              orgName={selClient?.name || 'Organisation'}
              onSave={handleSaveAssistantInline}
              onCancel={() => setEditingAssistant(null)}
            />
          ) : (
            <>
              {/* Action Row */}
              <div
                style={{
                  padding: '12px 20px',
                  background: '#f8fafc',
                  borderBottom: '1px solid #e2e8f0',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                }}
              >
                <span style={{ fontSize: '12px', fontWeight: 600, color: '#475569' }}>
                  Total Assistants: {orgAssistants.length}
                </span>
                <button
                  className="btn btn-sm btn-primary"
                  onClick={() => setEditingAssistant('new')}
                  style={{ fontSize: '11px', display: 'inline-flex', alignItems: 'center', gap: '5px' }}
                >
                  <Plus size={12} /> Add Assistant Account
                </button>
              </div>

              {/* Assistant Cards List */}
              <div
                style={{
                  flex: 1,
                  overflowY: 'auto',
                  padding: '16px 20px',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '14px',
                  background: '#f8fafc',
                }}
              >
                {orgAssistants.length === 0 ? (
                  <div style={{ textAlign: 'center', padding: '40px 20px', color: '#64748b' }}>
                    <UsersRound size={36} style={{ opacity: 0.3, marginBottom: '10px' }} />
                    <h4 style={{ margin: 0, fontSize: '14px', color: '#334155' }}>No Assistants Found</h4>
                    <p style={{ fontSize: '12px', margin: '4px 0 14px 0' }}>
                      There are no assistants created for this organisation yet.
                    </p>
                    <button className="btn btn-sm btn-primary" onClick={() => setEditingAssistant('new')}>
                      <Plus size={12} /> Add Assistant Account
                    </button>
                  </div>
                ) : (
                  orgAssistants.map((a, idx) => {
                    const isActive = a.status !== 'inactive' && a.is_active !== false;
                    return (
                      <div
                        key={a.id || idx}
                        style={{
                          position: 'relative',
                          border: '1px solid #e2e8f0',
                          borderRadius: '10px',
                          background: '#ffffff',
                          boxShadow: '0 2px 8px rgba(0,0,0,0.04)',
                          overflow: 'hidden',
                          transition: 'all 0.15s ease',
                        }}
                      >
                        {/* Accent Line Header */}
                        <div
                          style={{ height: '4px', background: 'linear-gradient(90deg, #15803d 0%, #22c55e 100%)' }}
                        />

                        <div style={{ padding: '16px 18px' }}>
                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'space-between',
                              marginBottom: '12px',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
                              <div
                                style={{
                                  width: '38px',
                                  height: '38px',
                                  borderRadius: '8px',
                                  background: 'linear-gradient(135deg, #15803d 0%, #22c55e 100%)',
                                  color: '#ffffff',
                                  display: 'flex',
                                  alignItems: 'center',
                                  justifyContent: 'center',
                                  boxShadow: '0 3px 8px rgba(22,128,61,0.25)',
                                }}
                              >
                                <UsersRound size={18} />
                              </div>
                              <div>
                                <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
                                  {a.name}
                                </h4>
                                <span
                                  style={{
                                    fontSize: '10px',
                                    fontWeight: 700,
                                    padding: '2px 8px',
                                    borderRadius: '4px',
                                    background: '#dcfce7',
                                    color: '#15803d',
                                    border: '1px solid #bbf7d0',
                                    marginTop: '3px',
                                    display: 'inline-block',
                                  }}
                                >
                                  Assistant Account
                                </span>
                              </div>
                            </div>

                            <span
                              style={{
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '5px',
                                fontSize: '11px',
                                fontWeight: 600,
                                padding: '3px 9px',
                                borderRadius: '12px',
                                background: isActive ? '#f0fdf4' : '#fff1f2',
                                color: isActive ? '#15803d' : '#be123c',
                                border: isActive ? '1px solid #bbf7d0' : '1px solid #fecdd3',
                              }}
                            >
                              <span
                                style={{
                                  width: '6px',
                                  height: '6px',
                                  borderRadius: '50%',
                                  background: isActive ? '#22c55e' : '#e11d48',
                                }}
                              />
                              {isActive ? 'Active' : 'Inactive'}
                            </span>
                          </div>

                          <div
                            style={{
                              display: 'grid',
                              gridTemplateColumns: '1fr 1fr',
                              gap: '10px',
                              padding: '10px 12px',
                              borderRadius: '8px',
                              background: '#f8fafc',
                              border: '1px solid #f1f5f9',
                              fontSize: '11px',
                              color: '#475569',
                              marginBottom: '14px',
                            }}
                          >
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px', overflow: 'hidden' }}>
                              <Mail size={13} style={{ color: '#64748b', flexShrink: 0 }} />
                              <span
                                style={{
                                  fontWeight: 600,
                                  color: '#334155',
                                  whiteSpace: 'nowrap',
                                  overflow: 'hidden',
                                  textOverflow: 'ellipsis',
                                }}
                              >
                                {a.username || a.email || '—'}
                              </span>
                            </div>
                            <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                              <Phone size={13} style={{ color: '#64748b', flexShrink: 0 }} />
                              <span style={{ fontWeight: 600, color: '#334155' }}>{a.phone || '—'}</span>
                            </div>
                          </div>

                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              justifyContent: 'flex-end',
                              gap: '8px',
                              paddingTop: '10px',
                              borderTop: '1px solid #f1f5f9',
                            }}
                          >
                            <button
                              className="btn btn-xs btn-neutral"
                              onClick={() => setEditingAssistant(a)}
                              style={{
                                fontSize: '11px',
                                padding: '5px 12px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '5px',
                              }}
                            >
                              <Pen size={12} /> Edit Assistant
                            </button>
                            <button
                              className="btn btn-xs btn-warning"
                              onClick={() => addToast?.(`Status toggled for ${a.name}`, 'success')}
                              style={{
                                fontSize: '11px',
                                padding: '5px 12px',
                                display: 'inline-flex',
                                alignItems: 'center',
                                gap: '5px',
                              }}
                            >
                              <ToggleRight size={12} /> Toggle Status
                            </button>
                          </div>
                        </div>
                      </div>
                    );
                  })
                )}
              </div>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/* ── INLINE EDIT/ADD FORM FOR MANAGERS ── */
function ManagerInlineForm({ manager, orgName, onSave, onCancel }) {
  const [name, setName] = useState(manager?.name || '');
  const [username, setUsername] = useState(manager?.username || '');
  const [email, setEmail] = useState(manager?.email || '');
  const [phone, setPhone] = useState(manager?.phone || '');
  const [status, setStatus] = useState(manager?.status || 'active');
  const [passwordOption, setPasswordOption] = useState('custom');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [assignedTables, setAssignedTables] = useState(manager?.assigned_tables || ['All Tables']);

  const isEditing = Boolean(manager && manager.id);
  const isPrimary = Boolean(manager && (manager.is_default || manager.client_type === 'primary'));

  const availableTables = [
    'All Tables',
    'Class 10A',
    'Class 10B',
    'Class 11A',
    'Class 12A',
    'Class 12B',
    'Staff & Teachers',
  ];

  const toggleTable = (tbl) => {
    if (tbl === 'All Tables') {
      setAssignedTables(['All Tables']);
      return;
    }
    let updated = assignedTables.filter((t) => t !== 'All Tables');
    if (updated.includes(tbl)) {
      updated = updated.filter((t) => t !== tbl);
    } else {
      updated.push(tbl);
    }
    if (updated.length === 0) updated = ['All Tables'];
    setAssignedTables(updated);
  };

  const handleEmailChange = (val) => {
    setEmail(val);
    if (!username && val.includes('@')) {
      setUsername(val.split('@')[0]);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    const finalUsername =
      username.trim() ||
      (email.trim()
        ? email.trim().split('@')[0]
        : name
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]/g, ''));
    onSave({
      ...(manager || {}),
      name: name.trim(),
      username: finalUsername,
      email: email.trim(),
      phone: phone.trim(),
      status,
      password_option: passwordOption,
      password: passwordOption === 'custom' ? password : phone.trim() || '12345678',
      assigned_tables: assignedTables,
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        background: '#f8fafc',
        flex: 1,
        overflowY: 'auto',
      }}
    >
      {/* Form Header Banner */}
      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          background: isPrimary
            ? 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)'
            : 'linear-gradient(135deg, #faf5ff 0%, #f3e8ff 100%)',
          border: isPrimary ? '1px solid #bfdbfe' : '1px solid #e9d5ff',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              background: isPrimary ? '#2563eb' : '#9333ea',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <User size={18} />
          </div>
          <div>
            <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#0f172a' }}>
              {isEditing
                ? isPrimary
                  ? `Edit Primary Owner for "${orgName}"`
                  : `Edit Manager Account`
                : `Add Manager for "${orgName}"`}
            </h4>
            <p style={{ margin: '2px 0 0 0', fontSize: '11px', color: '#64748b' }}>
              {isPrimary
                ? 'Update primary owner account credentials & permissions'
                : 'Set manager details, login credentials and assigned table groups below'}
            </p>
          </div>
        </div>
        <span
          style={{
            fontSize: '10px',
            fontWeight: 700,
            padding: '3px 10px',
            borderRadius: '12px',
            background: isPrimary ? '#2563eb' : '#9333ea',
            color: '#ffffff',
          }}
        >
          {isPrimary ? 'Primary Owner' : 'Manager'}
        </span>
      </div>

      <div
        style={{
          background: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Manager Name *
            </label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Full Name"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Username
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="username_code (derived from email if empty)"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Email Address
            </label>
            <input
              type="email"
              value={email}
              onChange={(e) => handleEmailChange(e.target.value)}
              placeholder="manager@domain.com"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Mobile Phone
            </label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91 9876543210"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Account Status
            </label>
            <CustomSelect
              value={status}
              onChange={(val) => setStatus(val)}
              options={[
                { value: 'active', label: 'Active' },
                { value: 'inactive', label: 'Inactive' },
              ]}
              height="34px"
            />
          </div>

          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Password Option
            </label>
            <CustomSelect
              value={passwordOption}
              onChange={(val) => setPasswordOption(val)}
              options={[
                { value: 'custom', label: 'Custom Password' },
                { value: 'auto', label: 'Use Phone Number / Auto Generate' },
              ]}
              height="34px"
            />
          </div>
        </div>

        {passwordOption === 'custom' && (
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Password *
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter account password"
                style={{
                  width: '100%',
                  height: '34px',
                  padding: '0 36px 0 12px',
                  border: '1px solid #cbd5e1',
                  borderRadius: '5px',
                  fontSize: '12px',
                  outline: 'none',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  border: 'none',
                  background: 'none',
                  color: '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Assigned Tables */}
      <div
        style={{
          background: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
          padding: '16px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginBottom: '8px' }}>
          <CreditCard size={14} style={{ color: '#2563eb' }} />
          <label style={{ fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>Assign Tables:</label>
        </div>
        <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
          {availableTables.map((tbl) => {
            const isSel = assignedTables.includes(tbl);
            return (
              <button
                key={tbl}
                type="button"
                onClick={() => toggleTable(tbl)}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '5px 12px',
                  borderRadius: '6px',
                  fontSize: '11px',
                  fontWeight: 600,
                  border: isSel ? '1px solid #2563eb' : '1px solid #cbd5e1',
                  background: isSel ? '#eff6ff' : '#ffffff',
                  color: isSel ? '#1d4ed8' : '#475569',
                  cursor: 'pointer',
                  transition: 'all 0.12s',
                }}
              >
                {isSel && <CheckCircle2 size={12} style={{ color: '#2563eb' }} />}
                <span>{tbl}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Form Buttons */}
      <div
        style={{
          marginTop: 'auto',
          paddingTop: '16px',
          borderTop: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: '10px',
        }}
      >
        <button
          type="button"
          onClick={onCancel}
          className="btn btn-md btn-neutral"
          style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
        >
          <X size={14} /> Cancel
        </button>
        <button
          type="submit"
          className="btn btn-md btn-primary"
          style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <Save size={14} /> <span>{isEditing ? 'Save Changes' : 'Create Manager Account'}</span>
        </button>
      </div>
    </form>
  );
}

/* ── INLINE EDIT/ADD FORM FOR ASSISTANTS ── */
function AssistantInlineForm({ assistant, orgName, onSave, onCancel }) {
  const [name, setName] = useState(assistant?.name || '');
  const [username, setUsername] = useState(assistant?.username || '');
  const [email, setEmail] = useState(assistant?.email || '');
  const [phone, setPhone] = useState(assistant?.phone || '');
  const [status, setStatus] = useState(assistant?.status || (assistant?.is_active === false ? 'inactive' : 'active'));
  const [passwordOption, setPasswordOption] = useState('custom');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  const isEditing = Boolean(assistant && assistant.id);

  const handleEmailChange = (val) => {
    setEmail(val);
    if (!username && val.includes('@')) {
      setUsername(val.split('@')[0]);
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    if (!name.trim()) return;
    const finalUsername =
      username.trim() ||
      (email.trim()
        ? email.trim().split('@')[0]
        : name
            .trim()
            .toLowerCase()
            .replace(/[^a-z0-9]/g, ''));
    onSave({
      ...(assistant || {}),
      name: name.trim(),
      username: finalUsername,
      email: email.trim(),
      phone: phone.trim(),
      status,
      password_option: passwordOption,
      password: passwordOption === 'custom' ? password : phone.trim() || '12345678',
      is_active: status === 'active',
    });
  };

  return (
    <form
      onSubmit={handleSubmit}
      style={{
        padding: '20px 24px',
        display: 'flex',
        flexDirection: 'column',
        gap: '16px',
        background: '#f8fafc',
        flex: 1,
        overflowY: 'auto',
      }}
    >
      {/* Form Header Banner */}
      <div
        style={{
          padding: '14px 16px',
          borderRadius: '8px',
          background: 'linear-gradient(135deg, #f0fdf4 0%, #dcfce7 100%)',
          border: '1px solid #bbf7d0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          <div
            style={{
              width: '34px',
              height: '34px',
              borderRadius: '8px',
              background: '#16a34a',
              color: '#fff',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <UsersRound size={18} />
          </div>
          <div>
            <h4 style={{ margin: 0, fontSize: '14px', fontWeight: 700, color: '#14532d' }}>
              {isEditing ? `Edit Assistant Account` : `Add New Assistant for "${orgName}"`}
            </h4>
            <p style={{ margin: '2px 0 0 0', fontSize: '11px', color: '#15803d' }}>
              Assistant credentials, password settings & permissions for organisation data entry
            </p>
          </div>
        </div>
        <span
          style={{
            fontSize: '10px',
            fontWeight: 700,
            padding: '3px 10px',
            borderRadius: '12px',
            background: '#16a34a',
            color: '#ffffff',
          }}
        >
          Assistant
        </span>
      </div>

      <div
        style={{
          background: '#ffffff',
          borderRadius: '8px',
          border: '1px solid #e2e8f0',
          padding: '18px',
          display: 'flex',
          flexDirection: 'column',
          gap: '14px',
          boxShadow: '0 1px 3px rgba(0,0,0,0.03)',
        }}
      >
        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Assistant Name *
            </label>
            <input
              required
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="Full Name"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Username
            </label>
            <input
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="assistant_code (derived from email if empty)"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Email Address *
            </label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => handleEmailChange(e.target.value)}
              placeholder="assistant@domain.com"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Mobile Phone
            </label>
            <input
              value={phone}
              onChange={(e) => setPhone(e.target.value)}
              placeholder="+91 9876543210"
              style={{
                width: '100%',
                height: '34px',
                padding: '0 12px',
                border: '1px solid #cbd5e1',
                borderRadius: '5px',
                fontSize: '12px',
                outline: 'none',
              }}
            />
          </div>
        </div>

        <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '14px' }}>
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Account Status
            </label>
            <CustomSelect
              value={status}
              onChange={(val) => setStatus(val)}
              options={[
                { value: 'active', label: 'Active' },
                { value: 'inactive', label: 'Inactive' },
              ]}
              height="34px"
            />
          </div>

          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Password Option
            </label>
            <CustomSelect
              value={passwordOption}
              onChange={(val) => setPasswordOption(val)}
              options={[
                { value: 'custom', label: 'Custom Password' },
                { value: 'auto', label: 'Use Phone Number / Auto Generate' },
              ]}
              height="34px"
            />
          </div>
        </div>

        {passwordOption === 'custom' && (
          <div>
            <label
              style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#374151', marginBottom: '5px' }}
            >
              Password *
            </label>
            <div style={{ position: 'relative' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                required
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Enter account password"
                style={{
                  width: '100%',
                  height: '34px',
                  padding: '0 36px 0 12px',
                  border: '1px solid #cbd5e1',
                  borderRadius: '5px',
                  fontSize: '12px',
                  outline: 'none',
                }}
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                style={{
                  position: 'absolute',
                  right: '10px',
                  top: '50%',
                  transform: 'translateY(-50%)',
                  border: 'none',
                  background: 'none',
                  color: '#6b7280',
                  cursor: 'pointer',
                  display: 'flex',
                  alignItems: 'center',
                }}
              >
                {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
              </button>
            </div>
          </div>
        )}
      </div>

      {/* Form Buttons */}
      <div
        style={{
          marginTop: 'auto',
          paddingTop: '16px',
          borderTop: '1px solid #e2e8f0',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'flex-end',
          gap: '10px',
        }}
      >
        <button
          type="button"
          onClick={onCancel}
          className="btn btn-md btn-neutral"
          style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '4px' }}
        >
          <X size={14} /> Cancel
        </button>
        <button
          type="submit"
          className="btn btn-md btn-primary"
          style={{ fontSize: '12px', display: 'inline-flex', alignItems: 'center', gap: '6px' }}
        >
          <Save size={14} /> <span>{isEditing ? 'Save Changes' : 'Create Assistant Account'}</span>
        </button>
      </div>
    </form>
  );
}

export { ClientDirectoryView as OrganisationDirectoryView };
