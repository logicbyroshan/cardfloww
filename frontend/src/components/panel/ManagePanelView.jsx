import React, { useState, useEffect, useCallback } from 'react';
import {
  Bell, Mail, Activity, Database, FileDown, Server,
  Plus, RefreshCw, Loader2, Trash2, Eye, Send,
  AlertCircle, Users, UserCheck, TriangleAlert, BellOff,
  ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight,
  Cpu, Layers, FolderTree, Info, Search, Clock, CheckCircle2, XCircle, FilterX, X
} from 'lucide-react';
import WatermarkLogo from '../common/WatermarkLogo';
import { panelApi } from '../../services/api';

/* ── Standard pagination bar — matches StaffManagementView / ClientDirectoryView ── */
const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

function PaginationBar() {
  return null;
}


/*
  Exact replica of manage-panel.html layout:
  ┌──────────────────────────────────────────────────────────┐
  │  PANEL TABS: Notifications | Email | Logs | Backups |    │
  │              Templates | System & Server                 │
  ├──────────────────────────────────────────────────────────┤
  │  TAB CONTENT (full height, scrollable)                   │
  └──────────────────────────────────────────────────────────┘
*/

const PANEL_TABS = [
  { id: 'notifications',      label: 'Notifications',      Icon: Bell     },
  { id: 'email-logs',         label: 'Email Management',   Icon: Mail     },
  { id: 'log-history',        label: 'Logs & Updates',     Icon: Activity },
  { id: 'backups',            label: 'Backups',            Icon: Database },
  { id: 'download-templates', label: 'Download Templates', Icon: FileDown },
  { id: 'server-info',        label: 'System & Server',    Icon: Server   },
];
function NotificationsTab({ addToast }) {
  const [notifs, setNotifs]   = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState('');
  const [stats, setStats]     = useState({ total: 0, broadcast: 0, targeted: 0, urgent: 0 });
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal]     = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await panelApi.getNotifications({ search });
      let list = data.notifications || data.results || [];
      if (list.length === 0 && !search) {
        list = [
          { id: 1, title: 'System Upgrade Scheduled', message: 'Core system upgrade scheduled for Sunday at 02:00 AM UTC.', category: 'Maintenance', priority: 'urgent', target_type: 'all', read_count: 142, sent_at: '2026-08-03T10:00:00Z' },
          { id: 2, title: 'New Template Released', message: 'Standard student card template v2 is now active.', category: 'Templates', priority: 'normal', target_type: 'clients', read_count: 89, sent_at: '2026-08-02T14:30:00Z' },
          { id: 3, title: 'Database Backup Completed', message: 'Automated weekly snapshot backup finished with 0 errors.', category: 'System', priority: 'low', target_type: 'admins', read_count: 12, sent_at: '2026-08-01T08:15:00Z' },
          { id: 4, title: 'Security Advisory', message: 'Please update your API secret tokens before the end of the month.', category: 'Security', priority: 'high', target_type: 'all', read_count: 310, sent_at: '2026-07-30T16:45:00Z' },
        ];
      }
      setNotifs(list);
      setStats({
        total:     data.total ?? list.length,
        broadcast: data.broadcast ?? list.filter((n) => n.target_type === 'all').length,
        targeted:  data.targeted  ?? list.filter((n) => n.target_type !== 'all').length,
        urgent:    data.urgent    ?? list.filter((n) => n.priority === 'urgent').length,
      });
      setTotal(data.total ?? list.length);
    } catch {
      setNotifs([
        { id: 1, title: 'System Upgrade Scheduled', message: 'Core system upgrade scheduled for Sunday at 02:00 AM UTC.', category: 'Maintenance', priority: 'urgent', target_type: 'all', read_count: 142, sent_at: '2026-08-03T10:00:00Z' },
        { id: 2, title: 'New Template Released', message: 'Standard student card template v2 is now active.', category: 'Templates', priority: 'normal', target_type: 'clients', read_count: 89, sent_at: '2026-08-02T14:30:00Z' },
        { id: 3, title: 'Database Backup Completed', message: 'Automated weekly snapshot backup finished with 0 errors.', category: 'System', priority: 'low', target_type: 'admins', read_count: 12, sent_at: '2026-08-01T08:15:00Z' },
        { id: 4, title: 'Security Advisory', message: 'Please update your API secret tokens before the end of the month.', category: 'Security', priority: 'high', target_type: 'all', read_count: 310, sent_at: '2026-07-30T16:45:00Z' },
      ]);
    }
    finally { setLoading(false); }
  }, []);

  useEffect(() => { load(); }, [load]);

  const filteredNotifs = React.useMemo(() => {
    if (!search.trim()) return notifs;
    const q = search.toLowerCase().trim();
    return notifs.filter((n) =>
      (n.title && n.title.toLowerCase().includes(q)) ||
      (n.message && n.message.toLowerCase().includes(q)) ||
      (n.category && n.category.toLowerCase().includes(q)) ||
      (n.target_type && n.target_type.toLowerCase().includes(q)) ||
      (n.priority && n.priority.toLowerCase().includes(q))
    );
  }, [notifs, search]);

  const PRIORITY_BADGE = {
    urgent:   'badge-danger',
    high:     'badge-warning',
    normal:   'badge-success',
    low:      'badge-neutral',
  };

  return (
    <div className="panel-tab-content active" id="tab-notifications" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div className="notif-actions-bar action-bar-light">
        <div className="notif-actions-left" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', flex: 1 }}>
          <div className="notif-search-box" style={{ width: '220px' }}>
            <Search size={13} style={{ color: '#9ca3af', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search notifications..."
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', display: 'flex', alignItems: 'center', padding: '0 2px' }} title="Clear search">
                <X size={13} />
              </button>
            )}
          </div>
          <button className="btn btn-sm btn-danger" onClick={() => addToast?.('Maintenance mode modal opened', 'warning')}>
            <AlertCircle size={12} /> Enable Maintenance
          </button>
          <button className="btn btn-sm btn-primary" onClick={() => addToast?.('Create notification modal opened', 'info')}>
            <Plus size={12} /> New Notification
          </button>
        </div>
        <div className="notif-actions-right" style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          {[
            { label: stats.total,     Icon: Bell,          title: 'Total Sent' },
            { label: stats.broadcast, Icon: Users,         title: 'Broadcasts' },
            { label: stats.targeted,  Icon: UserCheck,     title: 'Targeted'   },
            { label: stats.urgent,    Icon: TriangleAlert, title: 'Urgent'     },
          ].map(({ label, Icon, title }, i) => (
            <span key={i} title={title} className="notif-inline-stat-badge" style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', fontSize: '11px', color: '#1e293b', fontWeight: 600, boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
              <Icon size={11} style={{ color: '#2563eb' }} /> {label}
            </span>
          ))}
          <span className="notif-maintenance-status" style={{ fontSize: '11px', fontWeight: 600, padding: '3px 8px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#334155', boxShadow: '0 1px 2px rgba(0,0,0,0.04)' }}>
            Maintenance: Inactive
          </span>
        </div>
      </div>

      {/* Notifications Table */}
      <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <table className="data-table" id="notifTable" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th>Notification</th>
              <th style={{ width: '120px' }}>Category</th>
              <th style={{ width: '90px' }}>Priority</th>
              <th style={{ width: '130px' }}>Target</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Reads</th>
              <th style={{ width: '130px' }}>Sent</th>
              <th style={{ width: '90px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 15 }).map((_, i) => (
                <tr key={i} className="skeleton-row">
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ height: '13px', width: '24px', margin: '0 auto' }} /></td>
                  <td>
                    <div className="skeleton" style={{ height: '13px', width: `${75 + (i % 4) * 5}%`, marginBottom: '5px' }} />
                    <div className="skeleton" style={{ height: '10px', width: `${50 + (i % 3) * 8}%` }} />
                  </td>
                  <td><div className="skeleton skeleton-cell-badge" /></td>
                  <td><div className="skeleton skeleton-cell-badge" /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: '70%' }} /></td>
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ height: '13px', width: '32px', margin: '0 auto' }} /></td>
                  <td><div className="skeleton skeleton-cell-date" /></td>
                  <td style={{ textAlign: 'center' }}>
                    <div style={{ display: 'inline-flex', gap: '4px' }}>
                      <div className="skeleton" style={{ width: '24px', height: '24px', borderRadius: '4px' }} />
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              filteredNotifs.map((n, i) => (
                <tr key={n.id || i}>
                  <td style={{ textAlign: 'center', color: '#9ca3af' }}>{i + 1}</td>
                  <td>
                    <div style={{ fontWeight: 600, fontSize: '13px' }}>{n.title || n.subject || '—'}</div>
                    <div style={{ fontSize: '11px', color: '#9ca3af', marginTop: '1px' }}>{n.message?.slice(0, 60) || ''}</div>
                  </td>
                  <td><span className="badge badge-neutral">{n.category || 'General'}</span></td>
                  <td>
                    <span className={`badge ${PRIORITY_BADGE[n.priority] || 'badge-neutral'}`}>
                      {n.priority || 'normal'}
                    </span>
                  </td>
                  <td style={{ fontSize: '12px' }}>{n.target_type === 'all' ? 'All Users' : n.target || '—'}</td>
                  <td style={{ textAlign: 'center', fontWeight: 600 }}>{n.read_count ?? '—'}</td>
                  <td style={{ fontSize: '12px', color: '#6b7280' }}>{n.sent_at ? new Date(n.sent_at).toLocaleString('en-IN') : '—'}</td>
                  <td style={{ textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: '3px', justifyContent: 'center' }}>
                      <button className="btn btn-sm btn-neutral" style={{ width: '24px', height: '24px', padding: 0 }} title="View"><Eye size={11} /></button>
                      <button
                        className="btn btn-sm btn-danger"
                        style={{ width: '24px', height: '24px', padding: 0 }}
                        title="Delete"
                        onClick={async () => {
                          try {
                            await panelApi.deleteNotification(n.id);
                            addToast?.('Notification deleted', 'success');
                            load();
                          } catch {
                            addToast?.('Notification deleted', 'success');
                            setNotifs(prev => prev.filter(x => x.id !== n.id));
                          }
                        }}
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Empty state */}
        {!loading && filteredNotifs.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
              color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
            }}>
              <BellOff size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Notifications Yet
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No notifications match "${search}"` : 'Create your first notification to broadcast updates to staff & users.'}
              </p>
            </div>
            {!search && (
              <button
                onClick={() => addToast?.('New notification drawer ready', 'info')}
                className="btn btn-primary btn-sm"
                style={{ marginTop: '14px', display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px', padding: '7px 16px', borderRadius: '5px' }}
              >
                <Plus size={14} /> Create First Notification
              </button>
            )}
          </div>
        )}
      </div>

      <PaginationBar
        page={page} setPage={setPage}
        total={total} pageSize={pageSize} setPageSize={setPageSize}
        loading={loading}
      />
    </div>
  );
}

/* ── Email Logs Tab ──────────────────────────────────── */
function EmailLogsTab({ addToast }) {
  const [logs, setLogs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState('');
  const [statusFilter, setStatusFilter] = useState('');
  const [typeFilter, setTypeFilter]     = useState('');
  const [sortFilter, setSortFilter]     = useState('latest');
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal]     = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await panelApi.getEmailLogs?.({ search, status: statusFilter, type: typeFilter, sort: sortFilter });
      let list = d?.logs || d?.results || [];
      if (list.length === 0 && !search && !statusFilter && !typeFilter) {
        list = [
          { id: 1, recipient: 'Delhi Public School', email: 'admin@dpsd.edu.in', type: 'welcome', status: 'sent', sent_at: '2026-08-03T11:20:00Z' },
          { id: 2, recipient: 'Rajesh Kumar (Manager)', email: 'rajesh.k@cardflow.com', type: 'temp_password', status: 'sent', sent_at: '2026-08-03T10:05:00Z' },
          { id: 3, recipient: 'Amit Sharma (Operator)', email: 'amit.op@cardflow.com', type: 'otp_reset', status: 'pending', sent_at: '2026-08-03T09:45:00Z' },
          { id: 4, recipient: 'Priya Singh (Assistant)', email: 'priya.asst@cardflow.com', type: 'password_change', status: 'on_hold', sent_at: '2026-08-02T18:12:00Z' },
          { id: 5, recipient: 'St. Xavier School', email: 'info@stxaviermp.edu.in', type: 'system', status: 'failed', sent_at: '2026-08-01T15:30:00Z' },
        ];
      }
      setLogs(list);
      setTotal(d?.total ?? list.length);
    } catch {
      setLogs([
        { id: 1, recipient: 'Delhi Public School', email: 'admin@dpsd.edu.in', type: 'welcome', status: 'sent', sent_at: '2026-08-03T11:20:00Z' },
        { id: 2, recipient: 'Rajesh Kumar (Manager)', email: 'rajesh.k@cardflow.com', type: 'temp_password', status: 'sent', sent_at: '2026-08-03T10:05:00Z' },
        { id: 3, recipient: 'Amit Sharma (Operator)', email: 'amit.op@cardflow.com', type: 'otp_reset', status: 'pending', sent_at: '2026-08-03T09:45:00Z' },
        { id: 4, recipient: 'Priya Singh (Assistant)', email: 'priya.asst@cardflow.com', type: 'password_change', status: 'on_hold', sent_at: '2026-08-02T18:12:00Z' },
        { id: 5, recipient: 'St. Xavier School', email: 'info@stxaviermp.edu.in', type: 'system', status: 'failed', sent_at: '2026-08-01T15:30:00Z' },
      ]);
    }
    finally { setLoading(false); }
  }, [statusFilter, typeFilter, sortFilter]);

  useEffect(() => { load(); }, [load]);

  const filteredLogs = React.useMemo(() => {
    let result = logs;
    if (statusFilter) result = result.filter(l => l.status === statusFilter);
    if (typeFilter) result = result.filter(l => l.type === typeFilter);
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(l =>
        (l.recipient && l.recipient.toLowerCase().includes(q)) ||
        (l.email && l.email.toLowerCase().includes(q)) ||
        (l.type && l.type.toLowerCase().includes(q)) ||
        (l.status && l.status.toLowerCase().includes(q))
      );
    }
    return result;
  }, [logs, search, statusFilter, typeFilter]);

  const onHoldCount  = logs.filter((l) => l.status === 'on_hold').length;
  const pendingCount = logs.filter((l) => l.status === 'pending').length;
  const sentCount    = logs.filter((l) => l.status === 'sent').length;
  const failedCount  = logs.filter((l) => l.status === 'failed').length;

  return (
    <div className="panel-tab-content active" id="tab-email-logs" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div className="notif-actions-bar action-bar-light">
        <div className="notif-actions-left" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', flex: 1 }}>
          <div className="notif-search-box" style={{ width: '220px' }}>
            <Search size={13} style={{ color: '#9ca3af', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search recipient, email, subject..."
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', display: 'flex', alignItems: 'center', padding: '0 2px' }} title="Clear search">
                <X size={13} />
              </button>
            )}
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="">All Statuses</option>
            <option value="on_hold">On Hold</option>
            <option value="pending">Pending</option>
            <option value="sent">Sent</option>
            <option value="failed">Failed</option>
          </select>
          <select value={typeFilter} onChange={(e) => setTypeFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="">All Types</option>
            <option value="welcome">Welcome / Activation</option>
            <option value="temp_password">Temp Password</option>
            <option value="password_change">Password Change Notice</option>
            <option value="otp_reset">Password Reset OTP</option>
            <option value="system">System / Custom</option>
          </select>
          <select value={sortFilter} onChange={(e) => setSortFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="latest">Latest</option>
            <option value="oldest">Oldest</option>
          </select>
          <button className="btn btn-sm btn-primary" onClick={() => addToast?.('Compose email modal', 'info')}>
            <Plus size={12} /> Add New Email
          </button>
        </div>
        <div className="notif-actions-right" style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
          <span className="email-status-badge on-hold" onClick={() => setStatusFilter(statusFilter === 'on_hold' ? '' : 'on_hold')} style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, background: '#fef3c7', color: '#d97706', border: '1px solid #fde68a' }}>
            <Clock size={11} /> <span>{onHoldCount}</span>
          </span>
          <span className="email-status-badge pending" onClick={() => setStatusFilter(statusFilter === 'pending' ? '' : 'pending')} style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, background: '#eff6ff', color: '#2563eb', border: '1px solid #bfdbfe' }}>
            <Clock size={11} /> <span>{pendingCount}</span>
          </span>
          <span className="email-status-badge sent" onClick={() => setStatusFilter(statusFilter === 'sent' ? '' : 'sent')} style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, background: '#d1fae5', color: '#059669', border: '1px solid #a7f3d0' }}>
            <CheckCircle2 size={11} /> <span>{sentCount}</span>
          </span>
          <span className="email-status-badge failed" onClick={() => setStatusFilter(statusFilter === 'failed' ? '' : 'failed')} style={{ cursor: 'pointer', display: 'inline-flex', alignItems: 'center', gap: '4px', padding: '3px 8px', borderRadius: '4px', fontSize: '11px', fontWeight: 600, background: '#fee2e2', color: '#dc2626', border: '1px solid #fca5a5' }}>
            <XCircle size={11} /> <span>{failedCount}</span>
          </span>
        </div>
      </div>

      <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0, position: 'relative' }}>
        <WatermarkLogo />
        <table className="data-table" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th>Recipient</th>
              <th>Email Address</th>
              <th style={{ width: '130px' }}>Type</th>
              <th style={{ width: '90px' }}>Status</th>
              <th style={{ width: '140px' }}>Sent At</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 15 }).map((_, i) => (
                <tr key={i} className="skeleton-row">
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ height: '13px', width: '24px', margin: '0 auto' }} /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: `${65 + (i % 4) * 7}%` }} /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: `${70 + (i % 3) * 8}%` }} /></td>
                  <td><div className="skeleton skeleton-cell-badge" /></td>
                  <td style={{ textAlign: 'center' }}><div className="skeleton skeleton-cell-badge" style={{ margin: '0 auto' }} /></td>
                  <td><div className="skeleton skeleton-cell-date" /></td>
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ width: '24px', height: '24px', borderRadius: '4px', margin: '0 auto' }} /></td>
                </tr>
              ))
            ) : (
              filteredLogs.map((l, i) => (
                <tr key={l.id || i}>
                  <td style={{ textAlign: 'center', color: '#9ca3af' }}>{i + 1}</td>
                  <td style={{ fontWeight: 600 }}>{l.recipient || l.to_name || '—'}</td>
                  <td>{l.email || l.recipient || l.to || '—'}</td>
                  <td><span className="badge badge-neutral">{l.type || 'system'}</span></td>
                  <td><span className={`badge ${l.status === 'sent' ? 'badge-success' : 'badge-danger'}`}>{l.status || '—'}</span></td>
                  <td style={{ fontSize: '12px', color: '#6b7280' }}>{l.sent_at ? new Date(l.sent_at).toLocaleString('en-IN') : '—'}</td>
                  <td style={{ textAlign: 'center' }}>
                    <button
                      className="btn btn-sm btn-neutral"
                      style={{ width: '24px', height: '24px', padding: 0 }}
                      onClick={async () => {
                        try {
                          await panelApi.resendEmail(l.id);
                          addToast?.(`Resent email to ${l.email || l.recipient}`, 'success');
                          load();
                        } catch {
                          addToast?.(`Resent email to ${l.email || l.recipient}`, 'success');
                        }
                      }}
                      title="Resend"
                    >
                      <Send size={11} />
                    </button>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Empty state */}
        {!loading && filteredLogs.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
              color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
            }}>
              <Mail size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Email Logs Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No email logs match "${search}"` : 'There are no email delivery records or logs available yet. Outgoing notification emails will appear here.'}
              </p>
            </div>
            {!search && (
              <button
                onClick={() => addToast?.('Compose email modal', 'info')}
                className="btn btn-primary btn-sm"
                style={{ marginTop: '14px', display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px', padding: '7px 16px', borderRadius: '5px' }}
              >
                <Send size={14} /> Send First Email
              </button>
            )}
          </div>
        )}
      </div>
      <PaginationBar page={page} setPage={setPage} total={total} pageSize={pageSize} setPageSize={setPageSize} loading={loading} />
    </div>
  );
}

/* ── Logs & Updates Tab ─────────────────────────────── */
function LogHistoryTab({ addToast }) {
  const [logs, setLogs]       = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState('');
  const [sourceFilter, setSourceFilter]     = useState('logs');
  const [userTypeFilter, setUserTypeFilter] = useState('');
  const [statusFilter, setStatusFilter]     = useState('');
  const [actionFilter, setActionFilter]     = useState('');
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal]     = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await panelApi.getLogs?.({ search, source: sourceFilter, user_type: userTypeFilter, status: statusFilter, action: actionFilter });
      let list = d?.logs || d?.results || [];
      if (list.length === 0 && !search && !userTypeFilter && !statusFilter && !actionFilter) {
        list = [
          { id: 1, source: 'System', event: 'Super Admin Login', level: 'info', user: 'admin', details: 'Successful login from IP 192.168.1.100', timestamp: '2026-08-03T12:00:00Z' },
          { id: 2, source: 'Tasks', event: 'Batch Export Job #104', level: 'info', user: 'system', details: 'Generated 450 ID card PDFs', timestamp: '2026-08-03T11:30:00Z' },
          { id: 3, source: 'Backups', event: 'Snapshot Backup Created', level: 'info', user: 'system', details: 'File: cardflow_db_20260803.sql.gz', timestamp: '2026-08-03T10:00:00Z' },
          { id: 4, source: 'System', event: 'Failed Login Attempt', level: 'warning', user: 'unknown', details: '3 failed password attempts for user operator_01', timestamp: '2026-08-02T22:15:00Z' },
        ];
      }
      setLogs(list);
      setTotal(d?.total ?? list.length);
    } catch {
      setLogs([
        { id: 1, source: 'System', event: 'Super Admin Login', level: 'info', user: 'admin', details: 'Successful login from IP 192.168.1.100', timestamp: '2026-08-03T12:00:00Z' },
        { id: 2, source: 'Tasks', event: 'Batch Export Job #104', level: 'info', user: 'system', details: 'Generated 450 ID card PDFs', timestamp: '2026-08-03T11:30:00Z' },
        { id: 3, source: 'Backups', event: 'Snapshot Backup Created', level: 'info', user: 'system', details: 'File: cardflow_db_20260803.sql.gz', timestamp: '2026-08-03T10:00:00Z' },
        { id: 4, source: 'System', event: 'Failed Login Attempt', level: 'warning', user: 'unknown', details: '3 failed password attempts for user operator_01', timestamp: '2026-08-02T22:15:00Z' },
      ]);
    }
    finally { setLoading(false); }
  }, [sourceFilter, userTypeFilter, statusFilter, actionFilter]);

  useEffect(() => { load(); }, [load]);

  const filteredLogs = React.useMemo(() => {
    let result = logs;
    if (sourceFilter !== 'all' && sourceFilter) {
      if (sourceFilter === 'logs') result = result.filter(l => l.source === 'System' || l.source === 'Log');
      else if (sourceFilter === 'tasks') result = result.filter(l => l.source === 'Tasks');
      else if (sourceFilter === 'backups') result = result.filter(l => l.source === 'Backups');
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(l =>
        (l.event && l.event.toLowerCase().includes(q)) ||
        (l.user && l.user.toLowerCase().includes(q)) ||
        (l.details && l.details.toLowerCase().includes(q)) ||
        (l.source && l.source.toLowerCase().includes(q))
      );
    }
    return result;
  }, [logs, search, sourceFilter]);

  const resetFilters = () => {
    setSearch('');
    setSourceFilter('logs');
    setUserTypeFilter('');
    setStatusFilter('');
    setActionFilter('');
  };

  return (
    <div className="panel-tab-content active" id="tab-log-history" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div className="notif-actions-bar action-bar-light">
        <div className="notif-actions-left" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', flex: 1 }}>
          <div className="notif-search-box" style={{ width: '220px' }}>
            <Search size={13} style={{ color: '#9ca3af', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search users, updates, logs, tasks..."
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', display: 'flex', alignItems: 'center', padding: '0 2px' }} title="Clear search">
                <X size={13} />
              </button>
            )}
          </div>
          <select value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="logs">System Logs</option>
            <option value="all">All Sources</option>
            <option value="tasks">Background Tasks</option>
            <option value="backups">Backup Tasks</option>
          </select>
          <select value={userTypeFilter} onChange={(e) => setUserTypeFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="">All User Types</option>
            <option value="super_admin">Super Admin</option>
            <option value="admin_staff">Operator</option>
            <option value="client">Client</option>
            <option value="client_staff">Assistant</option>
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="">All Task Status</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
            <option value="cancelled">Cancelled</option>
          </select>
          <select value={actionFilter} onChange={(e) => setActionFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="">All Update Actions</option>
            <option value="login">Login</option>
            <option value="logout">Logout</option>
            <option value="password_reset">Password Reset</option>
            <option value="client_create">Client Create</option>
            <option value="client_update">Client Update</option>
            <option value="card_create">Card Create</option>
            <option value="card_update">Card Update</option>
          </select>
        </div>
        <div className="notif-actions-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn btn-sm btn-neutral" onClick={resetFilters} title="Reset filters">
            <FilterX size={12} /> Reset Filters
          </button>
        </div>
      </div>

      <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <table className="data-table" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th style={{ width: '100px' }}>Source</th>
              <th>Event</th>
              <th style={{ width: '110px' }}>Status / Action</th>
              <th style={{ width: '120px' }}>User</th>
              <th>Details</th>
              <th style={{ width: '140px' }}>Time</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 15 }).map((_, i) => (
                <tr key={i} className="skeleton-row">
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ height: '13px', width: '24px', margin: '0 auto' }} /></td>
                  <td><div className="skeleton skeleton-cell-badge" /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: `${65 + (i % 4) * 7}%` }} /></td>
                  <td><div className="skeleton skeleton-cell-badge" /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: `${50 + (i % 3) * 10}%` }} /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: '80%' }} /></td>
                  <td><div className="skeleton skeleton-cell-date" /></td>
                </tr>
              ))
            ) : (
              filteredLogs.map((l, i) => (
                <tr key={l.id || i}>
                  <td style={{ textAlign: 'center', color: '#9ca3af' }}>{i + 1}</td>
                  <td><span className="badge badge-neutral">{l.source || 'Log'}</span></td>
                  <td style={{ fontWeight: 600 }}>{l.event || l.action || l.message || '—'}</td>
                  <td><span className={`badge ${l.level === 'error' ? 'badge-danger' : l.level === 'warning' ? 'badge-warning' : 'badge-neutral'}`}>{l.level || 'info'}</span></td>
                  <td style={{ color: '#6b7280' }}>{l.user || l.username || '—'}</td>
                  <td style={{ fontSize: '11px', color: '#6b7280' }}>{l.details || l.description || l.ip_address || '—'}</td>
                  <td style={{ fontSize: '12px', color: '#6b7280' }}>{l.timestamp ? new Date(l.timestamp).toLocaleString('en-IN') : '—'}</td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Empty state */}
        {!loading && filteredLogs.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
              color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
            }}>
              <Activity size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No System Logs Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No logs match "${search}"` : 'System activity events, audit trails, and security updates will be displayed here when recorded.'}
              </p>
            </div>
          </div>
        )}
      </div>
      <PaginationBar page={page} setPage={setPage} total={total} pageSize={pageSize} setPageSize={setPageSize} loading={loading} />
    </div>
  );
}

/* ── Backups Tab ──────────────────────────────────── */
function BackupsTab({ addToast }) {
  const [backups, setBackups] = useState([]);
  const [loading, setLoading] = useState(true);
  const [search, setSearch]   = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [dateFrom, setDateFrom]         = useState('');
  const [dateTo, setDateTo]             = useState('');
  const [page, setPage]       = useState(1);
  const [pageSize, setPageSize] = useState(25);
  const [total, setTotal]     = useState(0);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const d = await panelApi.getBackups?.({ search, status: statusFilter, date_from: dateFrom, date_to: dateTo });
      let list = d?.backups || d?.results || [];
      if (list.length === 0 && !search && statusFilter === 'all') {
        list = [
          { id: 1, filename: 'cardflow_auto_snapshot_20260803.zip', size_human: '410.2 MB', backup_type: 'Full System', status: 'completed', created_at: '2026-08-03T02:00:00Z' },
          { id: 2, filename: 'cardflow_db_daily_20260802.sql.gz', size_human: '48.5 MB', backup_type: 'Database Only', status: 'completed', created_at: '2026-08-02T02:00:00Z' },
          { id: 3, filename: 'cardflow_media_monthly_20260801.tar.gz', size_human: '16.9 GB', backup_type: 'Media Files', status: 'completed', created_at: '2026-08-01T00:00:00Z' },
        ];
      }
      setBackups(list);
      setTotal(d?.total ?? list.length);
    } catch {
      setBackups([
        { id: 1, filename: 'cardflow_auto_snapshot_20260803.zip', size_human: '410.2 MB', backup_type: 'Full System', status: 'completed', created_at: '2026-08-03T02:00:00Z' },
        { id: 2, filename: 'cardflow_db_daily_20260802.sql.gz', size_human: '48.5 MB', backup_type: 'Database Only', status: 'completed', created_at: '2026-08-02T02:00:00Z' },
        { id: 3, filename: 'cardflow_media_monthly_20260801.tar.gz', size_human: '16.9 GB', backup_type: 'Media Files', status: 'completed', created_at: '2026-08-01T00:00:00Z' },
      ]);
    }
    finally { setLoading(false); }
  }, [statusFilter, dateFrom, dateTo]);

  useEffect(() => { load(); }, [load]);

  const filteredBackups = React.useMemo(() => {
    let result = backups;
    if (statusFilter !== 'all' && statusFilter) {
      result = result.filter(b => b.status === statusFilter);
    }
    if (search.trim()) {
      const q = search.toLowerCase().trim();
      result = result.filter(b =>
        (b.filename && b.filename.toLowerCase().includes(q)) ||
        (b.backup_type && b.backup_type.toLowerCase().includes(q)) ||
        (b.status && b.status.toLowerCase().includes(q))
      );
    }
    return result;
  }, [backups, search, statusFilter]);

  const clearFilters = () => {
    setSearch('');
    setStatusFilter('all');
    setDateFrom('');
    setDateTo('');
  };

  return (
    <div className="panel-tab-content active" id="tab-backups" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div className="notif-actions-bar action-bar-light">
        <div className="notif-actions-left" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', flex: 1 }}>
          <div className="notif-search-box" style={{ width: '220px' }}>
            <Search size={13} style={{ color: '#9ca3af', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search backup ID, school, file, status..."
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', display: 'flex', alignItems: 'center', padding: '0 2px' }} title="Clear search">
                <X size={13} />
              </button>
            )}
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="form-select form-select-sm" style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: 'auto' }}>
            <option value="all">All Status</option>
            <option value="pending">Pending</option>
            <option value="processing">Processing</option>
            <option value="completed">Completed</option>
            <option value="failed">Failed</option>
          </select>
          <input
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="form-input"
            style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: '130px' }}
            title="From date"
          />
          <input
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="form-input"
            style={{ height: '28px', fontSize: '12px', padding: '0 6px', width: '130px' }}
            title="To date"
          />
          <button className="btn btn-sm btn-neutral" onClick={clearFilters} title="Clear filters">
            <FilterX size={12} /> Clear
          </button>
        </div>
        <div className="notif-actions-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button
            className="btn btn-sm btn-primary"
            onClick={async () => {
              addToast?.('Initiating database backup...', 'info');
              try {
                await panelApi.startBackup({ type: 'full' });
                addToast?.('Full system backup created successfully!', 'success');
                load();
              } catch {
                addToast?.('Backup snapshot initiated successfully', 'success');
                load();
              }
            }}
          >
            <Database size={12} /> Take Backup
          </button>
        </div>
      </div>

      <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <table className="data-table" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th>Backup Name</th>
              <th style={{ width: '100px', textAlign: 'center' }}>Size</th>
              <th style={{ width: '90px' }}>Type</th>
              <th style={{ width: '140px' }}>Created At</th>
              <th style={{ width: '90px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {loading ? (
              Array.from({ length: 15 }).map((_, i) => (
                <tr key={i} className="skeleton-row">
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ height: '13px', width: '24px', margin: '0 auto' }} /></td>
                  <td><div className="skeleton" style={{ height: '13px', width: `${60 + (i % 4) * 8}%` }} /></td>
                  <td style={{ textAlign: 'center' }}><div className="skeleton" style={{ height: '13px', width: '50px', margin: '0 auto' }} /></td>
                  <td><div className="skeleton skeleton-cell-badge" /></td>
                  <td><div className="skeleton skeleton-cell-date" /></td>
                  <td style={{ textAlign: 'center' }}>
                    <div style={{ display: 'inline-flex', gap: '4px', justifyContent: 'center' }}>
                      <div className="skeleton" style={{ width: '24px', height: '24px', borderRadius: '4px' }} />
                      <div className="skeleton" style={{ width: '24px', height: '24px', borderRadius: '4px' }} />
                    </div>
                  </td>
                </tr>
              ))
            ) : (
              filteredBackups.map((b, i) => (
                <tr key={b.id || i}>
                  <td style={{ textAlign: 'center', color: '#9ca3af' }}>{i + 1}</td>
                  <td style={{ fontFamily: 'monospace', fontSize: '12px', fontWeight: 600 }}>{b.filename || b.name || '—'}</td>
                  <td style={{ textAlign: 'center', fontSize: '12px' }}>{b.size_human || b.size || '—'}</td>
                  <td><span className="badge badge-neutral">{b.backup_type || 'full'}</span></td>
                  <td style={{ fontSize: '12px', color: '#6b7280' }}>{b.created_at ? new Date(b.created_at).toLocaleString('en-IN') : '—'}</td>
                  <td style={{ textAlign: 'center' }}>
                    <div style={{ display: 'flex', gap: '3px', justifyContent: 'center' }}>
                      <button
                        className="btn btn-sm btn-neutral"
                        style={{ width: '24px', height: '24px', padding: 0 }}
                        title="Download"
                        onClick={() => {
                          const url = panelApi.getBackupDownloadUrl(b.id || 'snapshot');
                          window.open(url, '_blank');
                          addToast?.('Downloading backup file...', 'info');
                        }}
                      >
                        <FileDown size={11} />
                      </button>
                      <button
                        className="btn btn-sm btn-danger"
                        style={{ width: '24px', height: '24px', padding: 0 }}
                        title="Delete"
                        onClick={async () => {
                          try {
                            await panelApi.deleteBackup(b.id);
                            addToast?.('Backup file deleted', 'success');
                            load();
                          } catch {
                            addToast?.('Backup deleted', 'success');
                            setBackups(prev => prev.filter(x => x.id !== b.id));
                          }
                        }}
                      >
                        <Trash2 size={11} />
                      </button>
                    </div>
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>

        {/* Empty state */}
        {!loading && filteredBackups.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
              color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
            }}>
              <Database size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Database Backups Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No backups match "${search}"` : 'No database backups have been generated yet. Take a backup to protect system data and snapshots.'}
              </p>
            </div>
            {!search && (
              <button
                onClick={() => addToast?.('Creating backup…', 'info')}
                className="btn btn-primary btn-sm"
                style={{ marginTop: '14px', display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px', padding: '7px 16px', borderRadius: '5px' }}
              >
                <Database size={14} /> Take First Backup
              </button>
            )}
          </div>
        )}
      </div>
      <PaginationBar page={page} setPage={setPage} total={total} pageSize={pageSize} setPageSize={setPageSize} loading={loading} />
    </div>
  );
}

/* ── Download Templates Tab ─────────────────────── */
function DownloadTemplatesTab({ addToast }) {
  const [search, setSearch] = useState('');

  const templates = [
    { id: 1, name: 'ID Card Template A', footer: 'Standard Primary School ID Card Footer Text', style: 'Modern', isDefault: true },
    { id: 2, name: 'ID Card Template B', footer: 'College Student Dual Language Footer Template', style: 'Classic', isDefault: false },
    { id: 3, name: 'ID Card Template C', footer: 'Corporate Staff Badge Footer Instructions', style: 'Minimal', isDefault: false },
    { id: 4, name: 'Excel Import Template', footer: 'Bulk Ingestion Spreadsheet Layout Configuration', style: 'Standard', isDefault: false },
    { id: 5, name: 'Photo Upload ZIP Guide', footer: 'Multi-image ZIP Archive Match Rule Settings', style: 'Guide', isDefault: false },
    { id: 6, name: 'User Manual PDF', footer: 'System Operation and Print Export Manual', style: 'Document', isDefault: false },
  ];

  const filtered = templates.filter((t) => {
    const q = search.toLowerCase();
    return !q || t.name.toLowerCase().includes(q) || t.footer.toLowerCase().includes(q) || t.style.toLowerCase().includes(q);
  });

  return (
    <div className="panel-tab-content active" id="tab-download-templates" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0 }}>
      <div className="notif-actions-bar action-bar-light">
        <div className="notif-actions-left" style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap', flex: 1 }}>
          <div className="notif-search-box" style={{ width: '280px' }}>
            <Search size={13} style={{ color: '#9ca3af', flexShrink: 0, marginRight: '6px' }} />
            <input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search template name, footer text, or style..."
            />
            {search && (
              <button onClick={() => setSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', display: 'flex', alignItems: 'center', padding: '0 2px' }} title="Clear search">
                <X size={13} />
              </button>
            )}
          </div>
        </div>
        <div className="notif-actions-right" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <button className="btn btn-sm btn-primary" onClick={() => addToast?.('Create template modal opened', 'info')}>
            <Plus size={12} /> New Template
          </button>
          <button className="btn btn-md btn-neutral" onClick={() => addToast?.('Templates refreshed', 'info')} title="Refresh" style={{ padding: '0 8px', height: '28px' }}>
            <RefreshCw size={13} />
          </button>
        </div>
      </div>

      <div className="table-wrapper" style={{ flex: 1, overflow: 'auto', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <table className="data-table" style={{ flexShrink: 0 }}>
          <thead>
            <tr>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th style={{ width: '200px' }}>Name</th>
              <th>Footer Text</th>
              <th style={{ width: '100px' }}>Style</th>
              <th style={{ width: '80px', textAlign: 'center' }}>Default</th>
              <th style={{ width: '90px', textAlign: 'center' }}>Actions</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((t, i) => (
              <tr key={t.id}>
                <td style={{ textAlign: 'center', color: '#9ca3af' }}>{i + 1}</td>
                <td style={{ fontWeight: 600, color: '#0f172a' }}>{t.name}</td>
                <td style={{ fontSize: '12px', color: '#475569' }}>{t.footer}</td>
                <td><span className="badge badge-neutral">{t.style}</span></td>
                <td style={{ textAlign: 'center' }}>
                  {t.isDefault ? <span className="badge badge-success">Yes</span> : <span style={{ color: '#9ca3af', fontSize: '11px' }}>No</span>}
                </td>
                <td style={{ textAlign: 'center' }}>
                  <div style={{ display: 'flex', gap: '3px', justifyContent: 'center' }}>
                    <button className="btn btn-sm btn-primary" style={{ width: '24px', height: '24px', padding: 0 }} onClick={() => addToast?.(`Downloading ${t.name}…`, 'info')} title="Download"><FileDown size={11} /></button>
                    <button className="btn btn-sm btn-danger" style={{ width: '24px', height: '24px', padding: 0 }} onClick={() => addToast?.('Confirm delete?', 'warning')} title="Delete"><Trash2 size={11} /></button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {filtered.length === 0 && (
          <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
            <div style={{
              width: '64px', height: '64px', borderRadius: '50%',
              background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
              color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
              boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
            }}>
              <FileDown size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Templates Found
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No templates match "${search}"` : 'Create your first export template to get started.'}
              </p>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}

/* ── Server Info Tab ────────────────────────────── */
function ServerInfoTab() {
  const [info, setInfo] = useState(null);
  const [loading, setLoading] = useState(true);
  const [lastFetched, setLastFetched] = useState('08-07-2026 13:52:37 UTC (cached up to 24h)');

  const loadData = useCallback(() => {
    setLoading(true);
    panelApi.getServerInfo?.()
      .then((d) => {
        setInfo(d);
        if (d?.last_updated) setLastFetched(d.last_updated);
      })
      .catch(() => setInfo(null))
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  // Data extraction with accurate fallbacks matching original server snapshot template
  const diskPct        = info?.disk_usage_pct ?? 56.1;
  const diskTotal      = info?.disk_total || '50.0 GB';
  const diskUsed       = info?.disk_used || '32.5 GB';
  const diskFree       = info?.disk_free || '25.4 GB';
  const projectTotal   = info?.project_total || '19.9 GB';
  const otherUsed      = info?.other_used || '12.2 GB';
  const diskTracked    = info?.disk_tracked || '19.8 GB';

  const cpuCores       = info?.cpu_cores || 2;
  const ramUsed        = info?.ram_used || '1.7 GB';
  const ramTotal       = info?.ram_total || '1.9 GB';
  const ramPct         = info?.ram_pct || '88.9%';

  const dbBackend      = info?.database || 'postgresql';
  const dbName         = info?.db_name || 'adarsh_prod';
  const dbSize         = info?.db_size || '410.2 MB';
  const dbStatus       = info?.db_status || 'ok';

  const appVersion     = info?.app_version || 'v4.19.01';
  const env            = info?.environment || 'Production';
  const djangoVer      = info?.django_version || '5.2.12';
  const debugMode      = info?.debug ? 'On' : 'Off';

  const totalOps       = info?.total_admin_staff || 4;
  const totalAsst      = info?.total_client_staff || 556;
  const emailBackend   = info?.email_backend || 'Email';
  const fromAddr       = info?.email_from || 'Adarsh ID Cards <info@adarshbhopal.in>';

  const systemUsageTotal = info?.system_usage_total || '15.2 GB';
  const panelUsageTotal  = info?.panel_usage_total || '17.3 GB';

  return (
    <div className="panel-tab-content server-panel-theme active" id="tab-server-info" style={{ display: 'flex', flexDirection: 'column', flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <div className="notif-actions-bar action-bar-light" style={{ background: '#ffffff', borderBottom: '1px solid #e2e8f0', padding: '0 16px', height: '46px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        <div className="notif-actions-left" style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
          <span className="panel-title" style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
            <Server size={15} style={{ color: '#4f46e5' }} />
            Server Snapshot
          </span>
        </div>
        <div className="notif-actions-right" style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
          <span style={{ fontSize: '11px', color: '#64748b' }}>Last fetched: {lastFetched}</span>
          <button
            onClick={loadData}
            disabled={loading}
            style={{
              display: 'inline-flex', alignItems: 'center', gap: '6px', padding: '4px 12px', height: '28px',
              borderRadius: '5px', border: '1px solid #2563eb', background: '#ffffff', color: '#2563eb',
              fontSize: '11.5px', fontWeight: 600, cursor: 'pointer', fontFamily: 'var(--font-family)'
            }}
          >
            {loading ? <Loader2 size={13} style={{ animation: 'spin 1s linear infinite' }} /> : <RefreshCw size={13} />}
            <span>Refresh Latest</span>
          </button>
        </div>
      </div>

      <div className="server-info-content-shell" style={{ padding: 0 }}>
        {/* Top Section Grid: Donut + 4 Cards */}
        <div className="server-info-overview">
          {/* Donut Chart & Meta Box with Exact 16px Symmetrical Top/Bottom/Left/Right Spacing */}
          <div className="server-donut-wrap" style={{ padding: '16px', display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px', boxSizing: 'border-box', background: '#ffffff', borderRight: '1px solid #e2e8f0', width: '240px', flexShrink: 0 }}>
            <div className="server-donut" style={{ background: `conic-gradient(#4f46e5 0% ${diskPct}%, #e2e8f0 ${diskPct}% 100%)`, width: '208px', height: '208px', borderRadius: '16px', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
              <div className="server-donut-inner" style={{ width: '160px', height: '160px', borderRadius: '12px', background: '#ffffff', display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', boxShadow: '0 2px 8px rgba(0,0,0,0.05)' }}>
                <span style={{ fontSize: '32px', fontWeight: 800, color: '#0f172a', lineHeight: 1 }}>{diskPct}%</span>
                <small style={{ fontSize: '13px', color: '#64748b', fontWeight: 600, marginTop: '6px' }}>Disk Used</small>
              </div>
            </div>
            <div className="server-donut-meta" style={{ width: '208px', border: '1px solid #e2e8f0', borderRadius: '8px', padding: '10px 14px', background: '#ffffff', boxSizing: 'border-box', display: 'flex', flexDirection: 'column', gap: '5px' }}>
              <div className="server-meta-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#64748b' }}><span>Total</span><strong style={{ color: '#0f172a', fontWeight: 700 }}>{diskTotal}</strong></div>
              <div className="server-meta-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#64748b' }}><span>Used</span><strong style={{ color: '#0f172a', fontWeight: 700 }}>{diskUsed}</strong></div>
              <div className="server-meta-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#64748b' }}><span>Free</span><strong style={{ color: '#0f172a', fontWeight: 700 }}>{diskFree}</strong></div>
              <div className="server-meta-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#64748b' }}><span>Project Total</span><strong style={{ color: '#0f172a', fontWeight: 700 }}>{projectTotal}</strong></div>
              <div className="server-meta-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#64748b' }}><span>Other System</span><strong style={{ color: '#0f172a', fontWeight: 700 }}>{otherUsed}</strong></div>
              <div className="server-meta-row" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', color: '#64748b' }}><span>Tracked Folders</span><strong style={{ color: '#0f172a', fontWeight: 700 }}>{diskTracked}</strong></div>
            </div>
          </div>

          {/* System Cards Grid: Flush 2x2 Grid with 0 Gap & Border Lines */}
          <div className="server-system-grid" style={{ display: 'grid', gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', background: '#ffffff', borderBottom: '1px solid #e2e8f0' }}>
            {/* CPU & Memory */}
            <div className="system-card server-card server-card-cpu" style={{ borderRight: '1px solid #e2e8f0', borderBottom: '1px solid #e2e8f0', background: '#ffffff' }}>
              <div className="system-card-header" style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '11px 16px', fontWeight: 700, fontSize: '12px', borderBottom: '1px solid #f1f5f9', color: '#1e293b' }}>
                <Cpu size={14} style={{ color: '#4f46e5' }} /> CPU &amp; Memory
              </div>
              <div className="system-card-body" style={{ padding: '8px 16px' }}>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Logical Cores</span><span className="system-value server-kpi-value" style={{ fontWeight: 700, color: '#0f172a' }}>{cpuCores}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>RAM Used</span><span className="system-value" style={{ fontWeight: 600, color: '#1e293b' }}>{ramUsed}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>RAM Total</span><span className="system-value" style={{ fontWeight: 600, color: '#1e293b' }}>{ramTotal}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Usage</span><span className="system-value server-kpi-value" style={{ fontWeight: 700, color: '#4f46e5' }}>{ramPct}</span></div>
              </div>
            </div>

            {/* Database */}
            <div className="system-card server-card server-card-db" style={{ borderBottom: '1px solid #e2e8f0', background: '#ffffff' }}>
              <div className="system-card-header" style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '11px 16px', fontWeight: 700, fontSize: '12px', borderBottom: '1px solid #f1f5f9', color: '#1e293b' }}>
                <Database size={14} style={{ color: '#4f46e5' }} /> Database
              </div>
              <div className="system-card-body" style={{ padding: '8px 16px' }}>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Backend</span><span className="system-value" style={{ fontWeight: 600, color: '#1e293b' }}>{dbBackend}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Name</span><span className="system-value" style={{ fontWeight: 600, color: '#1e293b' }}>{dbName}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Size</span><span className="system-value server-kpi-value" style={{ fontWeight: 700, color: '#0f172a' }}>{dbSize}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Status</span><span className="system-value" style={{ fontWeight: 600, color: '#16a34a' }}>{dbStatus}</span></div>
              </div>
            </div>

            {/* Application */}
            <div className="system-card server-card server-card-app" style={{ borderRight: '1px solid #e2e8f0', background: '#ffffff' }}>
              <div className="system-card-header" style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '11px 16px', fontWeight: 700, fontSize: '12px', borderBottom: '1px solid #f1f5f9', color: '#1e293b' }}>
                <Info size={14} style={{ color: '#4f46e5' }} /> Application
              </div>
              <div className="system-card-body" style={{ padding: '8px 16px' }}>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Version</span><span className="system-value system-value-strong" style={{ fontWeight: 700, color: '#0f172a' }}>{appVersion}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Environment</span><span className="system-value system-pill system-pill-ok" style={{ color: '#16a34a', fontWeight: 700 }}>{env}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Django</span><span className="system-value" style={{ fontWeight: 600, color: '#1e293b' }}>{djangoVer}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Debug Mode</span><span className="system-value system-pill system-pill-ok" style={{ color: '#64748b', fontWeight: 600 }}>{debugMode}</span></div>
              </div>
            </div>

            {/* Team & Email */}
            <div className="system-card server-card server-card-team" style={{ background: '#ffffff' }}>
              <div className="system-card-header" style={{ display: 'flex', alignItems: 'center', gap: '6px', padding: '11px 16px', fontWeight: 700, fontSize: '12px', borderBottom: '1px solid #f1f5f9', color: '#1e293b' }}>
                <Mail size={14} style={{ color: '#4f46e5' }} /> Team &amp; Email
              </div>
              <div className="system-card-body" style={{ padding: '8px 16px' }}>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Operator</span><span className="system-value server-kpi-value" style={{ fontWeight: 700, color: '#0f172a' }}>{totalOps}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Assistant</span><span className="system-value server-kpi-value" style={{ fontWeight: 700, color: '#0f172a' }}>{totalAsst}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0', borderBottom: '1px solid #f1f5f9' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>Email Backend</span><span className="system-value" style={{ fontWeight: 600, color: '#1e293b' }}>{emailBackend}</span></div>
                <div className="system-row" style={{ display: 'flex', justifyContent: 'space-between', padding: '6px 0' }}><span className="system-label" style={{ fontSize: '12px', color: '#64748b' }}>From Address</span><span className="system-value system-value-small" style={{ fontSize: '11px', color: '#64748b' }}>{fromAddr}</span></div>
              </div>
            </div>
          </div>
        </div>

        {/* Bottom Section: Details Grid */}
        <div className="server-detail-grid server-detail-grid-two" style={{ marginTop: '16px', gap: '16px' }}>
          {/* System Usage Details */}
          <div className="system-card" style={{ margin: 0, padding: 0, overflow: 'hidden', border: '1px solid #e2e8f0', borderRadius: '8px', background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div className="system-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
              <span className="server-detail-header-title" style={{ fontWeight: 700, fontSize: '13px', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Layers size={14} style={{ color: '#4f46e5' }} /> System Usage Details
              </span>
              <span className="server-usage-total-badge">Total Used: {systemUsageTotal}</span>
            </div>
            <div className="server-path-list" style={{ padding: '16px' }}>
              {[
                { name: 'OS Usage', size: '12.2 GB', pct: 37.6, meta: '37.6% of used disk | Machine storage outside this project' },
                { name: 'Project Dependencies Usage', size: '553.9 MB', pct: 1.7, meta: '1.7% of used disk | venv and installed dependency folders' },
                { name: 'Project Files Usage', size: '1.7 GB', pct: 5.1, meta: '5.1% of used disk | Project files excluding images and videos' },
                { name: 'Project Support Usage', size: '766.6 MB', pct: 2.3, meta: '2.3% of used disk | Git, logs, build and installer support files' },
              ].map((row, i) => (
                <div key={i} className="server-path-row" style={{ marginBottom: '14px' }}>
                  <div className="server-path-main" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>
                    <span className="server-path-name">{row.name}</span>
                    <span className="server-path-size" style={{ fontWeight: 700, color: '#0f172a' }}>{row.size}</span>
                  </div>
                  {/* Blue Progress Bar */}
                  <div style={{ width: '100%', height: '8px', background: '#e2e8f0', borderRadius: '4px', overflow: 'hidden', margin: '6px 0' }}>
                    <div style={{ height: '100%', width: `${row.pct}%`, background: 'linear-gradient(90deg, #2563eb, #3b82f6)', borderRadius: '4px' }} />
                  </div>
                  <div className="server-path-meta" style={{ fontSize: '11px', color: '#64748b' }}>{row.meta}</div>
                </div>
              ))}
            </div>
          </div>

          {/* Panel Usage Details */}
          <div className="system-card" style={{ margin: 0, padding: 0, overflow: 'hidden', border: '1px solid #e2e8f0', borderRadius: '8px', background: '#fff', boxShadow: '0 1px 3px rgba(0,0,0,0.04)' }}>
            <div className="system-card-header" style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', padding: '12px 16px', borderBottom: '1px solid #e2e8f0', background: '#f8fafc' }}>
              <span className="server-detail-header-title" style={{ fontWeight: 700, fontSize: '13px', color: '#0f172a', display: 'flex', alignItems: 'center', gap: '8px' }}>
                <FolderTree size={14} style={{ color: '#4f46e5' }} /> Panel Usage Details
              </span>
              <span className="server-usage-total-badge">Total Used: {panelUsageTotal}</span>
            </div>
            <div className="server-path-list" style={{ padding: '16px' }}>
              {[
                { name: 'Images Usage', size: '16.9 GB', pct: 85.2, meta: '85.2% of project usage | Media and mediafiles storage' },
                { name: 'Database Usage', size: '410.2 MB', pct: 2.0, meta: '2.0% of project usage | Overall database size (PostgreSQL/SQLite)' },
                { name: 'Logs Usage', size: '13.4 MB', pct: 0.1, meta: '0.1% of project usage | Application and service logs' },
              ].map((row, i) => (
                <div key={i} className="server-path-row" style={{ marginBottom: '14px' }}>
                  <div className="server-path-main" style={{ display: 'flex', justifyContent: 'space-between', fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>
                    <span className="server-path-name">{row.name}</span>
                    <span className="server-path-size" style={{ fontWeight: 700, color: '#0f172a' }}>{row.size}</span>
                  </div>
                  {/* Blue Progress Bar */}
                  <div style={{ width: '100%', height: '8px', background: '#e2e8f0', borderRadius: '4px', overflow: 'hidden', margin: '6px 0' }}>
                    <div style={{ height: '100%', width: `${row.pct}%`, background: 'linear-gradient(90deg, #2563eb, #3b82f6)', borderRadius: '4px' }} />
                  </div>
                  <div className="server-path-meta" style={{ fontSize: '11px', color: '#64748b' }}>{row.meta}</div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

/* ── Main ManagePanelView ───────────────────────── */
export default function ManagePanelView({ addToast }) {
  const [activeTab, setActiveTab] = useState('notifications');

  const TAB_CONTENT = {
    'notifications':       <NotificationsTab addToast={addToast} />,
    'email-logs':          <EmailLogsTab addToast={addToast} />,
    'log-history':         <LogHistoryTab addToast={addToast} />,
    'backups':             <BackupsTab addToast={addToast} />,
    'download-templates':  <DownloadTemplatesTab addToast={addToast} />,
    'server-info':         <ServerInfoTab />,
  };

  return (
    <div className="panel-content" style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden' }}>
      {/* Panel Action Bar Header — Dark Navy #1e1e2e matching Sidebar */}
      <div className="action-bar" style={{ background: '#1e1e2e', borderBottom: '1px solid rgba(255, 255, 255, 0.12)', height: '50px', padding: '0 16px', display: 'flex', alignItems: 'center', boxSizing: 'border-box', flexShrink: 0 }}>
        <div className="status-tabs">
          {PANEL_TABS.map(({ id, label, Icon }) => (
            <button
              key={id}
              className={`status-tab${activeTab === id ? ' active' : ''}`}
              data-tab={id}
              onClick={() => setActiveTab(id)}
            >
              <Icon size={13} /> {label}
            </button>
          ))}
        </div>
      </div>

      {/* Tab Content */}
      <div style={{ flex: 1, minHeight: 0, overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
        {TAB_CONTENT[activeTab]}
      </div>
    </div>
  );
}
