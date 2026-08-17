import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Pen,
  Users,
  Trash2,
  ToggleRight,
  Search,
  RefreshCw,
  Loader2,
  ShieldCheck,
  Building,
  Layers,
  X,
} from 'lucide-react';
import { managerApi, clientApi } from '../../services/api';
import { SkeletonTableRows } from '../common/Skeleton';
import CustomSelect from '../common/CustomSelect';
import { formatDT } from '../../utils/formatters';
import { STATUS_TABS } from '../../utils/constants';

const TYPE_TABS = ['All', 'Prime Manager', 'Super Manager', 'Guest Manager'];

export default function ClientAccountsView({ addToast, onOpenActionDrawer, onNavigate, onOpenDeleteModal }) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [allOrganisations, setAllOrganisations] = useState([]);
  const [selectedOrgId, setSelectedOrgId] = useState('all');
  const [meta, setMeta] = useState({
    max_super_managers: 4,
    super_manager_count: 0,
    available_super_manager_slots: 4,
    organisation_name: '',
  });

  const [search, setSearch] = useState('');
  const [statusTab, setStatusTab] = useState('All');
  const [typeTab, setTypeTab] = useState('All');
  const [selected, setSelected] = useState(null);

  useEffect(() => {
    (async () => {
      try {
        const data = await clientApi.getAllForAssignment?.();
        const list = data?.clients || data?.results || (Array.isArray(data) ? data : []);
        setAllOrganisations(list);
        if (list.length > 0 && selectedOrgId === 'all') {
          setSelectedOrgId(String(list[0].id));
        }
      } catch (_) {}
    })();
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const params = selectedOrgId && selectedOrgId !== 'all' ? { organisation_id: selectedOrgId } : {};
      const data = await managerApi.list(params);
      if (data && data.success) {
        setAccounts(data.managers || []);
        setMeta({
          max_super_managers: data.max_super_managers ?? 4,
          super_manager_count: data.super_manager_count ?? 0,
          available_super_manager_slots: data.available_super_manager_slots ?? 4,
          organisation_name: data.organisation_name ?? '',
        });
      } else {
        setAccounts([]);
      }
    } catch (err) {
      console.error('Manager API fetch failed:', err);
      setAccounts([]);
    } finally {
      setLoading(false);
    }
  }, [selectedOrgId]);

  useEffect(() => {
    load();
    window.__reloadClientAccounts = load;
    return () => {
      if (window.__reloadClientAccounts === load) delete window.__reloadClientAccounts;
    };
  }, [load]);

  /* Dispatch footer data count & selection */
  useEffect(() => {
    let selectedText = '';
    if (selected) {
      const match = accounts.find((c) => String(c.id) === String(selected));
      if (match) {
        selectedText = `Selected: ${match.name || match.username || `Account #${selected}`}`;
      }
    }
    window.dispatchEvent(
      new CustomEvent('cardflow:data-count', {
        detail: {
          text: `Total Managers: ${accounts.length}`,
          selectedText,
          count: accounts.length,
        },
      })
    );
  }, [accounts.length, selected]);

  const selAccount = accounts.find((c) => String(c.id) === String(selected));

  const filteredAccounts = accounts.filter((acc) => {
    // Filter by status
    if (statusTab !== 'All') {
      const accStatus = (acc.status || (acc.is_active ? 'active' : 'inactive')).toLowerCase();
      if (accStatus !== statusTab.toLowerCase()) return false;
    }
    // Filter by type
    if (typeTab === 'Prime Manager') {
      if (acc.manager_type !== 'prime_manager' && !acc.is_default && acc.client_type === 'manager') return false;
    } else if (typeTab === 'Super Manager') {
      if (acc.manager_type !== 'super_manager' && (acc.is_default || acc.manager_type === 'prime_manager')) return false;
    } else if (typeTab === 'Guest Manager') {
      if (acc.manager_type !== 'guest_manager') return false;
    }
    // Search query
    if (search) {
      const q = search.toLowerCase();
      const matchName = (acc.name || '').toLowerCase().includes(q);
      const matchUser = (acc.username || '').toLowerCase().includes(q);
      const matchEmail = (acc.email || '').toLowerCase().includes(q);
      if (!matchName && !matchUser && !matchEmail) return false;
    }
    return true;
  });

  const handleToggleStatus = async () => {
    if (!selAccount) {
      addToast?.('Select a manager account first.', 'warning');
      return;
    }
    try {
      const currentActive = selAccount.is_active !== false && selAccount.status !== 'inactive';
      await managerApi.update(selAccount.id, { is_active: !currentActive });
      addToast?.('Manager status updated successfully.', 'success');
      load();
    } catch (err) {
      const msg = err.response?.data?.message || 'Failed to toggle status.';
      addToast?.(msg, 'error');
    }
  };

  const handleDelete = () => {
    if (!selAccount) {
      addToast?.('Select a manager account to delete.', 'warning');
      return;
    }
    if (selAccount.manager_type === 'prime_manager' || selAccount.is_default) {
      addToast?.('Prime Manager (Organisation Owner) cannot be deleted.', 'error');
      return;
    }

    onOpenDeleteModal?.({
      title: 'Delete Manager Account',
      itemDescription: `Super Manager account "${selAccount.name}"`,
      onConfirm: async () => {
        try {
          await managerApi.delete(selAccount.id);
          addToast?.('Manager account deleted.', 'success');
          setSelected(null);
          load();
        } catch (err) {
          const msg = err.response?.data?.message || 'Could not delete manager account.';
          addToast?.(msg, 'error');
        }
      },
    });
  };

  return (
    <div
      className="view-container"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}
    >
      {/* ── ACTION BAR ── */}
      <div
        className="action-bar"
        id="client-accounts-action-bar"
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
          {/* Status Tabs */}
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
            {STATUS_TABS.map((tab) => (
              <button
                key={tab}
                onClick={() => {
                  setStatusTab(tab);
                  setPage(1);
                }}
                className={`status-tab${statusTab === tab ? ' active' : ''}`}
                style={{
                  padding: '0 10px',
                  height: '22px',
                  fontSize: '11px',
                  lineHeight: '22px',
                  borderRadius: '3px',
                  border: 'none',
                  cursor: 'pointer',
                  background: statusTab === tab ? '#2563eb' : 'transparent',
                  color: statusTab === tab ? '#ffffff' : '#cbd5e1',
                  fontWeight: statusTab === tab ? 700 : 600,
                  fontFamily: 'var(--font-family)',
                  transition: 'all 0.15s',
                  boxShadow: statusTab === tab ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                  display: 'inline-flex',
                  alignItems: 'center',
                }}
              >
                {tab}
              </button>
            ))}
          </div>

          <div
            className="action-divider"
            style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }}
          />

          {/* Organisation Scope Selector */}
          {allOrganisations.length > 0 && (
            <>
              <CustomSelect
                value={selectedOrgId}
                onChange={(val) => setSelectedOrgId(val)}
                options={allOrganisations.map((org) => ({
                  value: String(org.id),
                  label: org.name || org.school_name || `Org #${org.id}`,
                }))}
                height="28px"
                style={{ width: '220px' }}
              />
              <div
                className="action-divider"
                style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }}
              />
            </>
          )}

          {/* Type Filter */}
          <CustomSelect
            value={typeTab}
            onChange={(val) => setTypeTab(val)}
            options={TYPE_TABS.map((t) => ({ value: t, label: t }))}
            height="28px"
            style={{ width: '170px' }}
          />

          <div
            className="action-divider"
            style={{ width: '1px', height: '16px', background: 'rgba(255,255,255,0.15)', margin: '0 4px' }}
          />

          {/* Search Box */}
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
              type="text"
              value={search}
              onChange={(e) => {
                setSearch(e.target.value);
                setPage(1);
              }}
              placeholder="Search Manager accounts..."
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
        <div className="action-bar-right" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
          {/* Super Manager limit badge */}
          <div
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: '6px',
              padding: '3px 10px',
              borderRadius: '20px',
              fontSize: '11px',
              fontWeight: 700,
              background: meta.available_super_manager_slots <= 0 ? 'rgba(239, 68, 68, 0.15)' : 'rgba(59, 130, 246, 0.15)',
              border: meta.available_super_manager_slots <= 0 ? '1px solid rgba(239, 68, 68, 0.4)' : '1px solid rgba(59, 130, 246, 0.4)',
              color: meta.available_super_manager_slots <= 0 ? '#fca5a5' : '#93c5fd',
            }}
          >
            <Users size={12} />
            <span>Super Managers: {meta.super_manager_count} / {meta.max_super_managers} max</span>
          </div>

          <div className="actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <button
                className="btn"
                onClick={() => onOpenActionDrawer?.('add-manager')}
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
                <Plus size={13} /> Add Manager
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={() => selAccount && onOpenActionDrawer?.('edit-manager', selAccount)}
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
              <button
                className="btn"
                disabled={!selected}
                onClick={handleDelete}
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
            </div>
          </div>
        </div>
      </div>

      {/* ── Table View ── */}
      <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <table className="data-table" style={{ width: '100%', fontSize: '11px', flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th style={{ width: 'auto' }}>MANAGER NAME</th>
              <th style={{ width: '130px' }}>USERNAME</th>
              <th style={{ width: '130px' }}>ROLE / TYPE</th>
              <th style={{ width: '180px' }}>ORGANISATION</th>
              <th style={{ width: '130px', textAlign: 'center' }}>DELEGATED TABLES</th>
              <th style={{ width: '120px', textAlign: 'center' }}>ASSISTANTS (MAX 100)</th>
              <th style={{ width: '80px', textAlign: 'center' }}>STATUS</th>
              <th style={{ width: '120px', textAlign: 'center' }}>CREATED AT</th>
            </tr>
          </thead>
          <tbody id="manager-table-body">
            {loading ? (
              <SkeletonTableRows count={10} cols={9} dark={false} />
            ) : (
              filteredAccounts.map((acc, idx) => {
                const isSel = String(selected) === String(acc.id);
                const isPrimary = acc.manager_type === 'prime_manager' || (acc.client_type !== 'manager' && acc.is_default);
                const isGuest = acc.manager_type === 'guest_manager';
                const orgName = acc.organisation_name || acc.organisation?.name || acc.school_name || meta.organisation_name || 'Global Organisation';
                const assistantCount = acc.assistants_count ?? acc.assistant_count ?? 0;
                const sharedTablesCount = acc.shared_tables_count ?? 0;

                const roleLabel = isPrimary
                  ? 'Prime Manager'
                  : isGuest
                  ? 'Guest Manager'
                  : 'Super Manager';

                const badgeBg = isPrimary ? '#dbeafe' : isGuest ? '#fef3c7' : '#f3e8ff';
                const badgeColor = isPrimary ? '#1d4ed8' : isGuest ? '#b45309' : '#6b21a8';

                return (
                  <tr
                    key={acc.id}
                    onClick={() => setSelected(isSel ? null : acc.id)}
                    className={isSel ? 'selected' : ''}
                    style={{ cursor: 'pointer' }}
                  >
                    <td style={{ width: '45px', textAlign: 'center' }}>
                      <input type="radio" checked={isSel} onChange={() => setSelected(acc.id)} />
                    </td>
                    <td style={{ width: 'auto', fontWeight: 600, color: '#0f172a' }}>
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                        <Users size={13} style={{ color: isPrimary ? '#2563eb' : isGuest ? '#d97706' : '#7c3aed' }} />
                        <span>{acc.name}</span>
                      </div>
                    </td>
                    <td
                      style={{
                        width: '130px',
                        color: '#475569',
                        fontSize: '11px',
                        fontWeight: 500,
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {acc.username || acc.user?.username || acc.user_code || '—'}
                    </td>
                    <td style={{ width: '130px' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: 700,
                          background: badgeBg,
                          color: badgeColor,
                        }}
                      >
                        {roleLabel}
                      </span>
                    </td>
                    <td
                      style={{
                        width: '180px',
                        color: '#475569',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
                        <Building size={12} />
                        <span>{orgName}</span>
                      </div>
                    </td>
                    <td style={{ width: '130px', textAlign: 'center' }}>
                      <span
                        style={{
                          padding: '2px 8px',
                          borderRadius: '4px',
                          fontSize: '10px',
                          fontWeight: 700,
                          background: isPrimary ? '#f1f5f9' : sharedTablesCount > 0 ? '#ecfdf5' : '#f8fafc',
                          color: isPrimary ? '#64748b' : sharedTablesCount > 0 ? '#059669' : '#94a3b8',
                          border: '1px solid rgba(0,0,0,0.06)',
                        }}
                      >
                        {isPrimary ? 'All Tables (Owner)' : `${sharedTablesCount} Table(s)`}
                      </span>
                    </td>
                    <td style={{ width: '120px', textAlign: 'center' }}>
                      <span style={{ fontWeight: 700, color: assistantCount >= 100 ? '#dc2626' : '#059669' }}>
                        {assistantCount} / 100
                      </span>
                    </td>
                    <td style={{ width: '80px', textAlign: 'center' }}>
                      <span className={`badge ${acc.status === 'inactive' || acc.is_active === false ? 'badge-danger' : 'badge-success'}`}>
                        {acc.status || (acc.is_active ? 'active' : 'inactive')}
                      </span>
                    </td>
                    <td style={{ width: '120px', textAlign: 'center', color: '#64748b', fontSize: '11px' }}>
                      {formatDT(acc.created_at)}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Empty state — sibling to table so flex:1 fills remaining height */}
        {!loading && filteredAccounts.length === 0 && (
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
              <Users size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Manager Accounts Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No manager accounts match "${search}"` : 'There are no manager accounts registered yet.'}
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
                <Plus size={14} /> Add Manager Account
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export {
  ClientAccountsView as OrganisationAccountsView,
  ClientAccountsView as ManagerAccountsView,
};
