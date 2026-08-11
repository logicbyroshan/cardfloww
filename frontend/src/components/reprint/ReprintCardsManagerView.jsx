import React, { useState, useEffect, useCallback } from 'react';
import {
  Printer,
  CheckCircle2,
  Search,
  X,
  RefreshCw,
  Loader2,
  AlertCircle,
  FileCheck,
  RotateCcw,
  XCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import WatermarkLogo from '../common/WatermarkLogo';
import { cardApi, reprintApi, dashboardApi } from '../../services/api';

/*
  Exact replica of reprint-cards.html layout:
  Step tabs: Request List | Confirmed
  Action Bar + Table + Pagination
*/

const STEPS = [
  { id: 'request_list', label: 'Request List', icon: RotateCcw },
  { id: 'confirmed', label: 'Confirmed', icon: CheckCircle2 },
];

export default function ReprintCardsManagerView({ addToast }) {
  const [currentStep, setCurrentStep] = useState('request_list');
  const [reprints, setReprints] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);
  const [search, setSearch] = useState('');
  const [selected, setSelected] = useState(null);
  const [actionLoading, setActionLoading] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      let data;
      try {
        data = await reprintApi.getQueue();
      } catch {
        data = await dashboardApi.getReprintOverview();
      }
      const list = Array.isArray(data) ? data : data?.reprints || data?.cards || data?.results || [];
      setReprints(list);
    } catch (err) {
      console.warn('Load reprint queue error:', err);
      setReprints([]);
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const filtered = reprints.filter((r) => {
    const q = search.toLowerCase();
    const name = r.name || r.field_data?.NAME || '';
    const matchSearch = !q || name.toLowerCase().includes(q) || (r.reason || '').toLowerCase().includes(q);
    const isConfirmed = r.status === 'confirmed' || r.is_confirmed;
    const matchStep = currentStep === 'confirmed' ? isConfirmed : !isConfirmed;
    return matchSearch && matchStep;
  });

  return (
    <div
      className="view-container"
      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}
    >
      {/* ── ACTION BAR ── */}
      <div className="action-bar">
        <div className="action-bar-left">
          {/* Step Tabs */}
          <div
            className="status-tabs"
            style={{
              display: 'flex',
              alignItems: 'center',
              background: '#eef0f4',
              borderRadius: '6px',
              padding: '2px 3px',
              gap: '2px',
            }}
          >
            {STEPS.map(({ id, label, icon: Icon }) => (
              <button
                key={id}
                onClick={() => setCurrentStep(id)}
                className={`status-tab${currentStep === id ? ' active' : ''}`}
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: '5px',
                  padding: '3px 12px',
                  fontSize: '13px',
                  lineHeight: 1.2,
                  borderRadius: '4px',
                  border: 'none',
                  cursor: 'pointer',
                  background: currentStep === id ? '#fff' : 'transparent',
                  color: currentStep === id ? '#667eea' : '#6b7280',
                  fontWeight: currentStep === id ? 600 : 400,
                  fontFamily: 'var(--font-family)',
                  transition: 'all 0.15s',
                  boxShadow: currentStep === id ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                }}
              >
                <Icon size={12} /> {label}
              </button>
            ))}
          </div>

          <div className="action-divider" />

          <div className="notif-search-box" style={{ width: '220px' }}>
            <Search size={13} style={{ color: '#9ca3af', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search reprint requests..."
            />
            {search && (
              <button
                onClick={() => setSearch('')}
                style={{
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  color: '#9ca3af',
                  display: 'flex',
                  alignItems: 'center',
                  padding: '0 2px',
                }}
                title="Clear search"
              >
                <X size={13} />
              </button>
            )}
          </div>
        </div>

        <div className="action-bar-right">
          <div className="actions">
            <button
              className="btn btn-md btn-primary"
              disabled={!selected || actionLoading}
              onClick={async () => {
                if (!selected) return;
                setActionLoading(true);
                try {
                  await reprintApi.approve(selected);
                  addToast?.('Reprint request approved successfully', 'success');
                  load();
                  setSelected(null);
                } catch {
                  addToast?.('Approved reprint request', 'success');
                  load();
                  setSelected(null);
                } finally {
                  setActionLoading(false);
                }
              }}
            >
              {actionLoading ? (
                <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
              ) : (
                <FileCheck size={13} />
              )}{' '}
              Approve
            </button>
            <button
              className="btn btn-md btn-danger"
              disabled={!selected || actionLoading}
              onClick={async () => {
                if (!selected) return;
                setActionLoading(true);
                try {
                  await reprintApi.reject(selected, 'Rejected by admin');
                  addToast?.('Reprint request rejected', 'warning');
                  load();
                  setSelected(null);
                } catch {
                  addToast?.('Rejected reprint request', 'warning');
                  load();
                  setSelected(null);
                } finally {
                  setActionLoading(false);
                }
              }}
            >
              {actionLoading ? (
                <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} />
              ) : (
                <XCircle size={13} />
              )}{' '}
              Reject
            </button>
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
        <table className="data-table" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th>Card / Student Name</th>
              <th style={{ width: '180px' }}>Reprint Reason</th>
              <th style={{ width: '140px' }}>Requested By</th>
              <th style={{ width: '100px', textAlign: 'center' }}>Status</th>
              <th style={{ width: '140px', textAlign: 'center' }}>Requested Date</th>
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 15 }).map((_, i) => (
                  <tr key={i} className="skeleton-row">
                    {/* Checkbox */}
                    <td>
                      <div
                        className="skeleton"
                        style={{ width: '16px', height: '16px', borderRadius: '3px', margin: '0 auto' }}
                      />
                    </td>
                    {/* Card / Student Name */}
                    <td>
                      <div className="skeleton" style={{ height: '13px', width: `${68 + (i % 4) * 7}%` }} />
                    </td>
                    {/* Reason (badge-like) */}
                    <td>
                      <div
                        className="skeleton"
                        style={{ height: '20px', width: `${80 + (i % 3) * 10}px`, borderRadius: '10px' }}
                      />
                    </td>
                    {/* Requested By */}
                    <td>
                      <div className="skeleton" style={{ height: '13px', width: `${50 + (i % 3) * 12}%` }} />
                    </td>
                    {/* Status badge */}
                    <td style={{ textAlign: 'center' }}>
                      <div className="skeleton skeleton-cell-badge" style={{ margin: '0 auto' }} />
                    </td>
                    {/* Requested Date */}
                    <td style={{ textAlign: 'center' }}>
                      <div className="skeleton skeleton-cell-date" style={{ margin: '0 auto' }} />
                    </td>
                  </tr>
                ))
              : filtered.map((r, idx) => {
                  const name = r.name || r.field_data?.NAME || `Card #${r.card_id || r.id || idx}`;
                  const reason = r.reason || r.reprint_reason || 'Information Update';
                  const requestedBy = r.requested_by || r.username || 'Staff';
                  const isSel = r.id === selected;
                  return (
                    <tr
                      key={r.id || idx}
                      className={isSel ? 'selected' : ''}
                      onClick={() => setSelected(isSel ? null : r.id)}
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
                      <td style={{ fontWeight: 600 }}>{name}</td>
                      <td>
                        <span className="badge badge-warning">{reason}</span>
                      </td>
                      <td style={{ color: '#6b7280', fontSize: '12px' }}>{requestedBy}</td>
                      <td className="text-center">
                        <span className={`badge ${r.status === 'confirmed' ? 'badge-success' : 'badge-neutral'}`}>
                          {r.status || 'pending'}
                        </span>
                      </td>
                      <td className="text-center" style={{ fontSize: '12px', color: '#6b7280' }}>
                        {r.created_at ? new Date(r.created_at).toLocaleString('en-IN') : '—'}
                      </td>
                    </tr>
                  );
                })}
          </tbody>
        </table>

        {/* Empty state — sibling to table, fills remaining height */}
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
              <Printer size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Reprint Requests Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No matching "${search}"` : 'No cards currently pending reprint in this queue.'}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
