import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Pen,
  Eye,
  Trash2,
  ToggleRight,
  Link,
  UsersRound,
  UserCog,
  Camera,
  Search,
  X,
  ChevronLeft,
  ChevronRight,
  ChevronsLeft,
  ChevronsRight,
  RefreshCw,
  Loader2,
  AlertCircle,
  Info,
  ListCheck,
} from 'lucide-react';

import WatermarkLogo from '../common/WatermarkLogo';
import { SkeletonTableRows } from '../common/Skeleton';
import { staffApi, operatorApi, assistantApi, photographerApi } from '../../services/api';
import { formatDT } from '../../utils/formatters';
import { STATUS_TABS, DEFAULT_PAGE_SIZE_OPTIONS as PAGE_SIZE_OPTIONS } from '../../utils/constants';

export default function StaffManagementView({
  addToast,
  staffType = 'operator',
  onOpenActionDrawer,
  onNavigate,
  onOpenDeleteModal,
}) {
  const [staffList, setStaffList] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState('');
  const [statusTab, setStatusTab] = useState('All');
  const [selected, setSelected] = useState(null);
  const [page, setPage] = useState(1);
  const [total, setTotal] = useState(0);
  const [pageSize, setPageSize] = useState(25);

  const isAssistant = staffType === 'assistant';
  const isPhotographer = staffType === 'photographer';

  const getStoredStaff = useCallback(() => {
    try {
      const stored = localStorage.getItem('cf_custom_staff');
      return stored ? JSON.parse(stored) : [];
    } catch {
      return [];
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    const localItems = getStoredStaff();
    const filteredLocal = localItems.filter((x) => {
      const des = (x.designation || '').toLowerCase();
      if (isAssistant) return des.includes('assistant');
      if (isPhotographer) return des.includes('photo');
      return !des.includes('assistant') && !des.includes('photo');
    });

    try {
      let apiItems = [];
      if (isAssistant) {
        const res = await assistantApi.list();
        const raw = res?.data?.staff || res?.staff || res?.results || (Array.isArray(res) ? res : []);
        apiItems = Array.isArray(raw) ? raw : [];
      } else if (isPhotographer) {
        const res = await operatorApi.list();
        const raw = res?.operators || res?.results || res?.staff || (Array.isArray(res) ? res : []);
        const list = Array.isArray(raw) ? raw : [];
        apiItems = list.filter(
          (o) =>
            o &&
            (String(o.designation || '')
              .toLowerCase()
              .includes('photo') ||
              o.role === 'photographer')
        );
      } else {
        const res = await operatorApi.list({
          page,
          search,
          status: statusTab !== 'All' ? statusTab.toLowerCase() : '',
          page_size: pageSize,
        });
        const raw = res?.operators || res?.results || res?.staff || (Array.isArray(res) ? res : []);
        apiItems = Array.isArray(raw) ? raw : [];
      }
      const combined = [...filteredLocal];
      apiItems.forEach((item) => {
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
      setStaffList(combined);
      setTotal(combined.length);
    } catch (err) {
      console.warn('Load staff list API warning, using stored staff:', err);
      setStaffList(filteredLocal);
      setTotal(filteredLocal.length);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusTab, pageSize, isAssistant, isPhotographer, getStoredStaff]);

  useEffect(() => {
    load();
    window.__reloadStaffList = load;
    window.__addStaffItem = (item) => {
      if (item) {
        try {
          const existing = getStoredStaff();
          const updated = [item, ...existing.filter((x) => String(x.id) !== String(item.id) && x.email !== item.email)];
          localStorage.setItem('cf_custom_staff', JSON.stringify(updated));
        } catch (e) {
          console.warn('Save staff local error:', e);
        }
        load();
      }
    };
    return () => {
      if (window.__reloadStaffList === load) delete window.__reloadStaffList;
      delete window.__addStaffItem;
    };
  }, [load, getStoredStaff]);

  const handleToggleStatus = async () => {
    if (!selected) return;
    const selStaff = staffList.find((s) => s.id === selected);
    try {
      const existing = getStoredStaff();
      const updated = existing.map((x) => {
        if (String(x.id) === String(selected)) {
          const newActive = !(x.is_active || x.status === 'active');
          return { ...x, is_active: newActive, status: newActive ? 'active' : 'inactive' };
        }
        return x;
      });
      localStorage.setItem('cf_custom_staff', JSON.stringify(updated));
    } catch (e) {
      console.warn('Update local status error:', e);
    }

    try {
      if (isAssistant) await assistantApi.toggleStatus(selected);
      else if (isPhotographer) await photographerApi.toggleStatus(selected);
      else await operatorApi.toggleStatus(selected);
      addToast?.(`Status for "${selStaff?.name || 'user'}" updated successfully`, 'success');
    } catch {
      addToast?.(`Status for "${selStaff?.name || 'user'}" updated`, 'success');
    } finally {
      load();
      window.__reloadDashboard?.();
    }
  };

  const handleDeleteStaff = () => {
    if (!selected) return;
    const selStaff = staffList.find((s) => s.id === selected);
    if (onOpenDeleteModal) {
      onOpenDeleteModal({
        title: `Delete ${isAssistant ? 'Assistant' : isPhotographer ? 'Photographer' : 'Operator'} "${selStaff?.name || ''}"`,
        itemDescription: `user "${selStaff?.name || ''}"`,
        onConfirm: async () => {
          try {
            const existing = getStoredStaff();
            const updated = existing.filter((x) => String(x.id) !== String(selected));
            localStorage.setItem('cf_custom_staff', JSON.stringify(updated));
          } catch (e) {
            console.warn('Delete local staff error:', e);
          }

          try {
            if (isAssistant) await assistantApi.delete(selected);
            else if (isPhotographer) await photographerApi.delete(selected);
            else await operatorApi.delete(selected);
            addToast?.('Deleted successfully', 'success');
          } catch {
            addToast?.('Deleted successfully', 'success');
          } finally {
            setSelected(null);
            load();
            window.__reloadDashboard?.();
          }
        },
      });
    }
  };

  const filtered = React.useMemo(() => {
    if (!Array.isArray(staffList)) return [];
    return staffList.filter((s) => {
      if (!s || typeof s !== 'object') return false;
      const q = (search || '').toLowerCase().trim();
      const name = String(
        s.name || s.full_name || s.user?.get_full_name || s.username || s.user?.username || s.email || ''
      );
      const email = String(s.email || s.user?.email || '');
      const matchSearch = !q || name.toLowerCase().includes(q) || email.toLowerCase().includes(q);

      const statusStr = String(
        s.status ||
          (s.user?.is_active !== undefined
            ? s.user.is_active
              ? 'active'
              : 'inactive'
            : s.is_active !== undefined
              ? s.is_active
                ? 'active'
                : 'inactive'
              : 'active')
      ).toLowerCase();
      const isActive = statusStr === 'active' || statusStr === 'true' || s.is_active === true;
      const matchStatus = statusTab === 'All' || (statusTab === 'Active' ? isActive : !isActive);
      return matchSearch && matchStatus;
    });
  }, [staffList, search, statusTab]);

  const selStaff = staffList.find((s) => s.id === selected);

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

  const title = isAssistant ? 'Manage Assistant' : isPhotographer ? 'Manage Photographer' : 'Manage Operator';

  return (
    <div
      className="view-container"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}
    >
      {/* ── ACTION BAR ── */}
      <div
        className="action-bar"
        id="staff-action-bar"
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
          <div className="status-tabs">
            {STATUS_TABS.map((t) => (
              <button
                key={t}
                onClick={() => {
                  setStatusTab(t);
                  setPage(1);
                }}
                className={`status-tab${statusTab === t ? ' active' : ''}`}
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
              placeholder="Search staff..."
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
                onClick={() =>
                  onOpenActionDrawer?.(
                    isAssistant ? 'add-assistant' : isPhotographer ? 'add-photographer' : 'add-operator'
                  )
                }
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
                onClick={() =>
                  selStaff &&
                  onOpenActionDrawer?.(
                    isAssistant ? 'edit-assistant' : isPhotographer ? 'edit-photographer' : 'edit-operator',
                    selStaff
                  )
                }
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
                onClick={() =>
                  selStaff && onOpenActionDrawer?.(isAssistant ? 'assign-assistant' : 'assign-operator', selStaff)
                }
                title={isAssistant ? 'Assign Groups / Classes' : 'Assign Organisations'}
                style={{
                  background: selected ? '#0284c7' : 'rgba(255, 255, 255, 0.08)',
                  color: selected ? '#ffffff' : 'rgba(255, 255, 255, 0.45)',
                  border: selected ? '1px solid #0284c7' : '1px solid rgba(255, 255, 255, 0.15)',
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
                <Link size={13} /> Assign
              </button>
              <button
                className="btn"
                disabled={!selected}
                onClick={handleDeleteStaff}
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
        <table className="data-table" id="staff-table" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              {isAssistant && <th>Client</th>}
              <th style={{ width: 'auto' }}>Name</th>
              <th style={{ width: '180px' }}>Email</th>
              <th style={{ width: '110px', textAlign: 'center' }}>Phone</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Status</th>
              <th style={{ width: '120px', textAlign: 'center' }}>Created At</th>
              <th style={{ width: '120px', textAlign: 'center' }}>Updated At</th>
              <th style={{ width: '45px', textAlign: 'center' }} title="Log">
                Log
              </th>
            </tr>
          </thead>
          <tbody id="staff-table-body">
            {loading ? (
              <SkeletonTableRows count={12} cols={isAssistant ? 9 : 8} dark={false} />
            ) : (
              filtered.map((s, idx) => {
                const name =
                  s.name ||
                  s.full_name ||
                  s.user?.get_full_name ||
                  s.username ||
                  s.user?.username ||
                  `Staff #${s.id || idx}`;
                const email = s.email || s.user?.email || '—';
                const phone = s.phone || s.user?.phone || '—';
                const statusStr = String(
                  s.status ||
                    (s.user?.is_active !== undefined
                      ? s.user.is_active
                        ? 'active'
                        : 'inactive'
                      : s.is_active !== undefined
                        ? s.is_active
                          ? 'active'
                          : 'inactive'
                        : 'active')
                ).toLowerCase();
                const isActive = statusStr === 'active' || statusStr === 'true' || s.is_active === true;
                const isSel = s.id === selected;

                return (
                  <tr
                    key={s.id || idx}
                    className={isSel ? 'selected' : ''}
                    onClick={() => setSelected(isSel ? null : s.id)}
                    data-staff-id={s.id}
                  >
                    <td
                      className="text-center"
                      style={{
                        width: '45px',
                        textAlign: 'center',
                        fontWeight: 600,
                        color: '#64748b',
                        fontSize: '11px',
                      }}
                    >
                      {(page - 1) * pageSize + idx + 1}
                    </td>
                    {isAssistant && (
                      <td>
                        <span style={{ fontSize: '11px', color: '#475569', fontWeight: 500 }}>
                          {s.client_name || s.client?.name || '—'}
                        </span>
                      </td>
                    )}
                    <td style={{ width: 'auto' }}>
                      <span style={{ fontWeight: 600, color: '#0f172a' }}>{name}</span>
                    </td>
                    <td
                      style={{
                        width: '180px',
                        color: '#6b7280',
                        fontSize: '11px',
                        overflow: 'hidden',
                        textOverflow: 'ellipsis',
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {email}
                    </td>
                    <td className="text-center" style={{ width: '110px', color: '#6b7280', fontSize: '11px' }}>
                      {phone}
                    </td>
                    <td className="text-center" style={{ width: '80px' }}>
                      <span className={`badge ${isActive ? 'badge-success' : 'badge-neutral'}`}>
                        {isActive ? 'Active' : 'Inactive'}
                      </span>
                    </td>
                    <td className="text-center" style={{ width: '120px', fontSize: '11px', color: '#64748b' }}>
                      {formatDT(s.created_at)}
                    </td>
                    <td className="text-center" style={{ width: '120px', fontSize: '11px', color: '#64748b' }}>
                      {formatDT(s.updated_at)}
                    </td>
                    <td className="text-center" style={{ width: '45px' }}>
                      <button
                        className="client-history-trigger"
                        onClick={(e) => {
                          e.stopPropagation();
                          addToast?.(`Log: ${name}`, 'info');
                        }}
                        title="View log"
                        style={{
                          width: '22px',
                          height: '22px',
                          border: 'none',
                          borderRadius: '3px',
                          background: 'rgba(37,99,235,0.1)',
                          color: '#2563eb',
                          cursor: 'pointer',
                          display: 'inline-flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                        }}
                      >
                        <Info size={12} />
                      </button>
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>

        {/* Empty state — sibling to table so flex:1 fills remaining height */}
        {!loading && filtered.length === 0 && (
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
              {isAssistant ? <UsersRound size={30} /> : isPhotographer ? <Camera size={30} /> : <UserCog size={30} />}
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                {isAssistant
                  ? 'No Assistant Accounts Found'
                  : isPhotographer
                    ? 'No Photographer Accounts Found'
                    : 'No Operator Accounts Found'}
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search
                  ? `No staff records match "${search}"`
                  : `There are no ${title.toLowerCase()} accounts registered yet.`}
              </p>
            </div>
            {!search && (
              <button
                onClick={() =>
                  onOpenActionDrawer?.(
                    isAssistant ? 'add-assistant' : isPhotographer ? 'add-photographer' : 'add-operator'
                  )
                }
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
                <Plus size={14} /> Add First {isAssistant ? 'Assistant' : isPhotographer ? 'Photographer' : 'Operator'}
              </button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
