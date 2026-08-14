import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Pen,
  Users,
  Trash2,
  ToggleRight,
  Search,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RefreshCw,
  Loader2,
  AlertCircle,
  ShieldCheck,
  Building,
  X,
} from 'lucide-react';
import { clientApi } from '../../services/api';
import { SkeletonTableRows } from '../common/Skeleton';
import { formatDT } from '../../utils/formatters';
import { STATUS_TABS, DEFAULT_PAGE_SIZE_OPTIONS as PAGE_SIZE_OPTIONS } from '../../utils/constants';

const TYPE_TABS = ['All', 'Client (Primary)', 'Manager'];

export default function ClientAccountsView({ addToast, onOpenActionDrawer, onNavigate, onOpenDeleteModal }) {
  const [accounts, setAccounts] = useState([]);
  const [loading, setLoading] = useState(true);

  const [search, setSearch] = useState('');
  const [statusTab, setStatusTab] = useState('All');
  const [typeTab, setTypeTab] = useState('All');
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const getStoredManagers = useCallback(() => {
    try {
      const customMgrs = JSON.parse(localStorage.getItem('cf_custom_managers') || '[]');
      const customClients = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
      const autoPrimary = customClients.map((c) => ({
        id: `mgr_${c.id}`,
        name: c.name,
        username: c.email || c.name.toLowerCase().replace(/\s+/g, ''),
        email: c.email,
        phone: c.phone,
        client_type: 'primary',
        is_default: true,
        organisation: { id: c.id, name: c.name },
        school_name: c.name,
        status: c.status || 'active',
        is_active: c.is_active !== false,
        created_at: c.created_at || new Date().toISOString(),
      }));
      return [...customMgrs, ...autoPrimary];
    } catch {
      return [];
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    const localItems = getStoredManagers();
    try {
      const data = await clientApi.getActive({
        page,
        search,
        status: statusTab !== 'All' ? statusTab.toLowerCase() : '',
        page_size: pageSize,
      });
      const apiList = Array.isArray(data) ? data : data?.clients || data?.results || [];
      const combined = [...localItems];
      apiList.forEach((item) => {
        if (
          !combined.some(
            (c) =>
              String(c.id) === String(item.id) ||
              (c.email && item.email && c.email.toLowerCase() === item.email.toLowerCase())
          )
        ) {
          combined.push(item);
        }
      });
      setAccounts(combined);
      setTotal(combined.length);
    } catch (err) {
      console.warn('Load manager accounts warning, using stored managers:', err);
      setAccounts(localItems);
      setTotal(localItems.length);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusTab, pageSize, getStoredManagers]);

  useEffect(() => {
    load();
    window.__reloadClientAccounts = load;
    return () => {
      if (window.__reloadClientAccounts === load) delete window.__reloadClientAccounts;
    };
  }, [load]);

  const selAccount = accounts.find((c) => c.id === selected);

  const filteredAccounts = accounts.filter((acc) => {
    if (typeTab === 'Client (Primary)' && (acc.client_type === 'manager' || !acc.is_default)) return false;
    if (typeTab === 'Manager' && acc.client_type !== 'manager' && acc.is_default) return false;
    return true;
  });

  const handleToggleStatus = async () => {
    if (!selected) {
      addToast?.('Select a client account first.', 'warning');
      return;
    }
    try {
      await clientApi.toggleStatus(selected);
      addToast?.('Status updated successfully.', 'success');
      load();
    } catch {
      addToast?.('Failed to toggle status.', 'error');
    }
  };

  const handleDelete = () => {
    if (!selAccount) {
      addToast?.('Select a client account to delete.', 'warning');
      return;
    }
    onOpenDeleteModal?.({
      title: 'Delete Client Account',
      itemDescription: `client account "${selAccount.name}"`,
      onConfirm: async () => {
        try {
          await clientApi.deleteClient(selected);
          addToast?.('Client account deleted.', 'success');
          setSelected(null);
          load();
        } catch {
          addToast?.('Could not delete account.', 'error');
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

          {/* Type Filter */}
          <select
            value={typeTab}
            onChange={(e) => setTypeTab(e.target.value)}
            className="form-input"
            style={{
              height: '28px',
              fontSize: '12px',
              padding: '0 8px',
              background: 'rgba(255, 255, 255, 0.08)',
              borderRadius: '4px',
              border: '1px solid rgba(255, 255, 255, 0.18)',
              color: '#ffffff',
              outline: 'none',
            }}
          >
            {TYPE_TABS.map((t) => (
              <option key={t} value={t} style={{ background: '#1e1e2e', color: '#ffffff' }}>
                {t}
              </option>
            ))}
          </select>

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
        <div className="action-bar-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
                <Plus size={13} /> Add Manager Account
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
              <th style={{ width: 'auto' }}>ACCOUNT NAME</th>
              <th style={{ width: '130px' }}>USERNAME</th>
              <th style={{ width: '130px' }}>ACCOUNT TYPE</th>
              <th style={{ width: '180px' }}>ORGANISATION</th>
              <th style={{ width: '140px', textAlign: 'center' }}>ASSISTANTS (MAX 100)</th>
              <th style={{ width: '80px', textAlign: 'center' }}>STATUS</th>
              <th style={{ width: '120px', textAlign: 'center' }}>CREATED AT</th>
            </tr>
          </thead>
          <tbody id="manager-table-body">
            {loading ? (
              <SkeletonTableRows count={10} cols={9} dark={false} />
            ) : (
              filteredAccounts.map((acc, idx) => {
                const isSel = selected === acc.id;
                const isPrimary = acc.client_type !== 'manager' && acc.is_default;
                const orgName = acc.organisation?.name || acc.school_name || 'Global Organisation';
                const assistantCount = acc.assistant_count ?? acc.assistants?.length ?? 0;

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
                        <Users size={13} style={{ color: isPrimary ? '#2563eb' : '#7c3aed' }} />
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
                          background: isPrimary ? '#dbeafe' : '#f3e8ff',
                          color: isPrimary ? '#1d4ed8' : '#6b21a8',
                        }}
                      >
                        {isPrimary ? 'Client (Primary)' : 'Manager'}
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
                    <td style={{ width: '140px', textAlign: 'center' }}>
                      <span style={{ fontWeight: 700, color: assistantCount >= 100 ? '#dc2626' : '#059669' }}>
                        {assistantCount} / 100
                      </span>
                    </td>
                    <td style={{ width: '80px', textAlign: 'center' }}>
                      <span className={`badge ${acc.status === 'inactive' ? 'badge-danger' : 'badge-success'}`}>
                        {acc.status || 'active'}
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
