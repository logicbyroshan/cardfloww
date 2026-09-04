import React, { useState, useEffect, useCallback } from 'react';
import {
  Plus,
  Pen,
  Trash2,
  ToggleRight,
  Link,
  UsersRound,
  UserCog,
  Camera,
  Search,
  X,
  Info,
} from 'lucide-react';

import WatermarkLogo from '../common/WatermarkLogo';
import { SkeletonTableRows } from '../common/Skeleton';
import Button from '../common/Button';
import Input from '../common/Input';
import { operatorApi, assistantApi, photographerApi } from '../../services/api';
import { formatDT } from '../../utils/formatters';
import { STATUS_TABS } from '../../utils/constants';

export default function StaffManagementView({
  addToast,
  staffType = 'operator',
  onOpenActionDrawer,
  _onNavigate,
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

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);

    try {
      let apiItems = [];
      let totalCount = 0;
      const queryParams = {
        page,
        search,
        status: statusTab !== 'All' ? statusTab.toLowerCase() : '',
        page_size: pageSize,
      };

      if (isAssistant) {
        const res = await assistantApi.list(queryParams);
        const raw = res?.data?.staff || res?.staff || res?.results || (Array.isArray(res) ? res : []);
        apiItems = Array.isArray(raw) ? raw : [];
        totalCount = res?.total || res?.count || apiItems.length;
      } else if (isPhotographer) {
        const res = await photographerApi.list(queryParams);
        const raw = res?.photographers || res?.data?.photographers || res?.staff || res?.results || (Array.isArray(res) ? res : []);
        apiItems = Array.isArray(raw) ? raw : [];
        totalCount = res?.total || res?.count || apiItems.length;
      } else {
        const res = await operatorApi.list(queryParams);
        const raw = res?.operators || res?.results || res?.staff || (Array.isArray(res) ? res : []);
        apiItems = Array.isArray(raw) ? raw : [];
        totalCount = res?.total || res?.count || apiItems.length;
      }
      setStaffList(apiItems);
      setTotal(totalCount);
    } catch (err) {
      console.error('Load staff list API error:', err);
      setError(true);
      setStaffList([]);
      setTotal(0);
    } finally {
      setLoading(false);
    }
  }, [page, search, statusTab, pageSize, isAssistant, isPhotographer]);

  useEffect(() => {
    load();
    window.__reloadStaffList = load;
    return () => {
      if (window.__reloadStaffList === load) delete window.__reloadStaffList;
    };
  }, [load]);

  /* Dispatch footer data count & selection */
  useEffect(() => {
    const label = isAssistant ? 'Total Assistants' : isPhotographer ? 'Total Photographers' : 'Total Operators';
    let selectedText = '';
    if (selected) {
      const selStaff = staffList.find((s) => String(s.id) === String(selected));
      if (selStaff) {
        const staffName = selStaff.name || selStaff.full_name || selStaff.username || `Staff #${selected}`;
        selectedText = `Selected: ${staffName}`;
      }
    }
    window.dispatchEvent(
      new CustomEvent('cardflow:data-count', {
        detail: {
          text: `${label}: ${staffList.length}`,
          selectedText,
          count: staffList.length,
        },
      })
    );
  }, [staffList, selected, isAssistant, isPhotographer]);

  const handleToggleStatus = async () => {
    if (!selected) return;
    const selStaff = staffList.find((s) => s.id === selected);

    try {
      if (isAssistant) await assistantApi.toggleStatus(selected);
      else if (isPhotographer) await photographerApi.toggleStatus(selected);
      else await operatorApi.toggleStatus(selected);
      addToast?.(`Status for "${selStaff?.name || 'user'}" updated successfully`, 'success');
    } catch (err) {
      const msg = err?.response?.data?.message || err?.message || 'Failed to update status';
      addToast?.(msg, 'error');
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
            if (isAssistant) await assistantApi.delete(selected);
            else if (isPhotographer) await photographerApi.delete(selected);
            else await operatorApi.delete(selected);
            addToast?.('Deleted successfully', 'success');
          } catch (err) {
            const msg = err?.response?.data?.message || err?.message || 'Failed to delete';
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

          <Input
            size="sm"
            variant="dark"
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(1);
            }}
            onClear={() => {
              setSearch('');
              setPage(1);
            }}
            placeholder={`Search ${isAssistant ? 'assistants' : isPhotographer ? 'photographers' : 'operators'}...`}
            icon={<Search size={12} />}
            clearable
            style={{ width: '220px' }}
          />
        </div>

        {/* Right */}
        <div className="action-bar-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <div className="actions" style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <div className="btn-group" style={{ display: 'flex', alignItems: 'center', gap: '4px' }}>
              <Button
                size="sm"
                variant="primary"
                icon={<Plus size={13} />}
                onClick={() =>
                  onOpenActionDrawer?.(
                    isAssistant ? 'add-assistant' : isPhotographer ? 'add-photographer' : 'add-operator'
                  )
                }
              >
                Add
              </Button>
              <Button
                size="sm"
                variant={selected ? 'primary' : 'neutral'}
                disabled={!selected}
                icon={<Pen size={13} />}
                onClick={() =>
                  selStaff &&
                  onOpenActionDrawer?.(
                    isAssistant ? 'edit-assistant' : isPhotographer ? 'edit-photographer' : 'edit-operator',
                    selStaff
                  )
                }
              >
                Edit
              </Button>
              <Button
                size="sm"
                variant={selected ? 'primary' : 'neutral'}
                disabled={!selected}
                icon={<Link size={13} />}
                onClick={() =>
                  selStaff && onOpenActionDrawer?.(isAssistant ? 'assign-assistant' : 'assign-operator', selStaff)
                }
                title={isAssistant ? 'Assign Groups / Classes' : 'Assign Organisations'}
              >
                Assign
              </Button>
              <Button
                size="sm"
                variant={selected ? 'danger' : 'neutral'}
                disabled={!selected}
                icon={<Trash2 size={13} />}
                onClick={handleDeleteStaff}
              >
                Delete
              </Button>
              <Button
                size="sm"
                variant={selected ? 'warning' : 'neutral'}
                disabled={!selected}
                icon={<ToggleRight size={13} />}
                onClick={handleToggleStatus}
              >
                Active
              </Button>
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
                  `${isAssistant ? 'Manager' : 'Operator'} #${s.id || idx + 1}`;
                const email = s.email || s.user?.email || '-';
                const phone = s.phone || s.user?.phone || '-';
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
                          {s.client_name || s.client?.name || '-'}
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
                  ? `No ${isAssistant ? 'assistant' : isPhotographer ? 'photographer' : 'operator'} records match "${search}"`
                  : `There are no ${isAssistant ? 'assistant' : isPhotographer ? 'photographer' : 'operator'} accounts registered yet.`}
              </p>
            </div>
            {!search && (
              <Button
                variant="primary"
                size="md"
                onClick={() =>
                  onOpenActionDrawer?.(
                    isAssistant ? 'add-assistant' : isPhotographer ? 'add-photographer' : 'add-operator'
                  )
                }
                icon={<Plus size={14} />}
                style={{ marginTop: '14px' }}
              >
                Add First {isAssistant ? 'Assistant' : isPhotographer ? 'Photographer' : 'Operator'}
              </Button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

export {
  StaffManagementView as OperatorManagementView,
  StaffManagementView as AssistantManagementView,
  StaffManagementView as PhotographerManagementView,
};
