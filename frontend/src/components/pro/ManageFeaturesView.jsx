import React, { useState, useEffect, useCallback } from 'react';
import {
  UserCog, Search, LogIn, UserCheck, Activity, RefreshCw, CheckCircle2,
  Clock, Play, Plus, Filter, ShieldCheck, ArrowUpRight, Zap, BarChart3, X,
  Users, Smartphone, TrendingUp, AlertTriangle, FileText, CheckCircle, RotateCw,
  FileDown, ChevronsLeft, ChevronsRight, ChevronLeft, ChevronRight, Loader2
} from 'lucide-react';

import { clientApi, assistantApi, panelApi } from '../../services/api';

const PAGE_SIZE_OPTIONS = [10, 25, 50, 100];

function PaginationBar() {
  return null;
}

export default function ManageFeaturesView({ addToast }) {
  const [activeTab, setActiveTab] = useState('impersonate');
  const [search, setSearch] = useState('');
  const [roleFilter, setRoleFilter] = useState('all');
  const [statsRange, setStatsRange] = useState('Hours');
  const [impersonatingUser, setImpersonatingUser] = useState(null);

  /* Batch Jobs Filters */
  const [batchSearch, setBatchSearch] = useState('');
  const [batchStatusFilter, setBatchStatusFilter] = useState('all');
  const [batchTypeFilter, setBatchTypeFilter] = useState('all');

  /* Pagination States */
  const [impPage, setImpPage] = useState(1);
  const [impPageSize, setImpPageSize] = useState(25);

  const [guestPage, setGuestPage] = useState(1);
  const [guestPageSize, setGuestPageSize] = useState(25);

  const [batchPage, setBatchPage] = useState(1);
  const [batchPageSize, setBatchPageSize] = useState(25);

  const [usersList, setUsersList] = useState([]);
  const [guestUsers, setGuestUsers] = useState([
    { id: 'GST-101', name: 'Sanjay Verma', email: 'sanjay.guest@cardflow.com', expires: '2026-08-10 18:00', status: 'Active' },
    { id: 'GST-102', name: 'Vikram Mehta', email: 'vikram.guest@cardflow.com', expires: '2026-08-05 23:59', status: 'Active' },
    { id: 'GST-103', name: 'Ritu Sharma', email: 'ritu.guest@cardflow.com', expires: '2026-08-01 12:00', status: 'Expired' },
  ]);
  const [batchJobs, setBatchJobs] = useState([
    { id: '#JOB-8841', name: 'Bulk Student Excel Data Ingestion', type: 'Bulk Upload', user: 'admin@dpsd.edu.in', records: '450 / 450 records', progress: 100, status: 'completed', started: '2026-08-03T14:20:00Z', download_url: '#', duration: '14s' },
    { id: '#JOB-8840', name: 'Student Photo ZIP Auto Match & Sync', type: 'Photo Sync', user: 'rajesh.k@cardflow.com', records: '320 / 320 photos', progress: 100, status: 'completed', started: '2026-08-03T12:05:00Z', download_url: '#', duration: '48s' },
    { id: '#JOB-8839', name: 'ID Card Batch Print PDF Generation', type: 'Bulk Export', user: 'amit.op@cardflow.com', records: '1,250 / 1,250 cards', progress: 65, status: 'processing', started: '2026-08-03T15:10:00Z', download_url: null, duration: '1m 20s' },
    { id: '#JOB-8838', name: 'Field Schema Re-upload Data Patch', type: 'Re-upload Patch', user: 'priya.asst@cardflow.com', records: '85 / 85 records', progress: 100, status: 'completed', started: '2026-08-02T18:45:00Z', download_url: '#', duration: '6s' },
    { id: '#JOB-8837', name: 'Bulk Staff Ingestion & Account Provisioning', type: 'Bulk Upload', user: 'admin@dpsd.edu.in', records: '50 / 50 records', progress: 100, status: 'completed', started: '2026-08-01T09:30:00Z', download_url: '#', duration: '9s' },
    { id: '#JOB-8836', name: 'Archived Card Records ZIP Backup Export', type: 'Bulk Export', user: 'sanjay.guest@cardflow.com', records: '0 / 200 records', progress: 20, status: 'failed', started: '2026-07-31T11:15:00Z', download_url: null, duration: '3s' },
  ]);
  const [loading, setLoading] = useState(false);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const [clientsRes, staffRes, opsRes] = await Promise.allSettled([
        clientApi.getActive({ page_size: 100 }),
        assistantApi.list({ page_size: 100 }),
        panelApi.getOperationsFeed()
      ]);

      let list = [];
      if (clientsRes.status === 'fulfilled' && clientsRes.value) {
        const clientItems = clientsRes.value.clients || clientsRes.value.results || (Array.isArray(clientsRes.value) ? clientsRes.value : []);
        clientItems.forEach(c => {
          list.push({
            id: `client-${c.id}`,
            name: c.name || c.school_name || 'Client Account',
            email: c.email || c.user?.email || 'N/A',
            role: c.client_type === 'manager' ? 'Manage Manager' : 'Manage Organisation',
            rawRole: 'client',
            status: c.status ? (c.status.charAt(0).toUpperCase() + c.status.slice(1)) : 'Active'
          });
        });
      }

      if (staffRes.status === 'fulfilled' && staffRes.value) {
        const staffItems = staffRes.value.staff || staffRes.value.results || (Array.isArray(staffRes.value) ? staffRes.value : []);
        staffItems.forEach(s => {
          list.push({
            id: `staff-${s.id}`,
            name: s.name || s.user?.get_full_name || s.user?.username || 'Assistant',
            email: s.email || s.user?.email || 'N/A',
            role: s.role_display || 'Manage Assistant',
            rawRole: 'client_staff',
            status: 'Active'
          });
        });
      }

      const localClients = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
      const localMgrs = JSON.parse(localStorage.getItem('cf_custom_managers') || '[]');
      const localStaff = JSON.parse(localStorage.getItem('cf_custom_staff') || '[]');

      localClients.forEach(c => {
        if (!list.some(u => String(u.id) === `client-${c.id}` || (u.email && c.email && u.email === c.email))) {
          list.push({
            id: `client-${c.id}`,
            name: c.name || 'Organisation Account',
            email: c.email || 'N/A',
            role: 'Manage Organisation',
            rawRole: 'client',
            status: c.status ? (c.status.charAt(0).toUpperCase() + c.status.slice(1)) : 'Active'
          });
        }
      });

      localMgrs.forEach(m => {
        if (!list.some(u => String(u.id) === `mgr-${m.id}` || (u.email && m.email && u.email === m.email))) {
          list.push({
            id: `mgr-${m.id}`,
            name: m.name || 'Manager Account',
            email: m.email || 'N/A',
            role: m.client_type === 'primary' ? 'Client (Primary Owner)' : 'Manager Account',
            rawRole: 'client',
            status: m.status ? (m.status.charAt(0).toUpperCase() + m.status.slice(1)) : 'Active'
          });
        }
      });

      localStaff.forEach(s => {
        if (!list.some(u => String(u.id) === `staff-${s.id}` || (u.email && s.email && u.email === s.email))) {
          list.push({
            id: `staff-${s.id}`,
            name: s.name || 'Staff Account',
            email: s.email || 'N/A',
            role: s.designation === 'Assistant' ? 'Manage Assistant' : 'Manage Operator',
            rawRole: s.designation === 'Assistant' ? 'client_staff' : 'admin_staff',
            status: s.status ? (s.status.charAt(0).toUpperCase() + s.status.slice(1)) : 'Active'
          });
        }
      });

      if (list.length === 0) {
        list = [
          { id: 'usr-1', name: 'Delhi Public School (Organisation)', email: 'admin@dpsd.edu.in', role: 'Manage Organisation', rawRole: 'client', status: 'Active' },
          { id: 'usr-2', name: 'Rajesh Kumar (Manager)', email: 'rajesh.k@cardflow.com', role: 'Manage Manager', rawRole: 'client', status: 'Active' },
          { id: 'usr-3', name: 'Amit Sharma (Operator)', email: 'amit.op@cardflow.com', role: 'Manage Operator', rawRole: 'client_staff', status: 'Active' },
          { id: 'usr-4', name: 'Priya Singh (Assistant)', email: 'priya.asst@cardflow.com', role: 'Manage Assistant', rawRole: 'client_staff', status: 'Active' },
          { id: 'usr-5', name: 'Sanjay Verma (Guest User)', email: 'sanjay.guest@cardflow.com', role: 'Guest User', rawRole: 'guest_user', status: 'Active' },
        ];
      }
      setUsersList(list);

      if (opsRes.status === 'fulfilled' && opsRes.value) {
        const jobs = opsRes.value.tasks || opsRes.value.operations || (Array.isArray(opsRes.value) ? opsRes.value : []);
        if (jobs.length > 0) {
          setBatchJobs(jobs.map((j, idx) => ({
            id: j.job_id || `#JOB-${8840 - idx}`,
            name: j.name || j.task_name || 'Bulk Task Operation',
            type: j.type || j.task_type || 'Bulk Task',
            user: j.user || j.triggered_by || 'Admin',
            records: j.records || `${j.processed || 100} / ${j.total || 100} records`,
            progress: j.progress !== undefined ? j.progress : 100,
            status: (j.status || 'completed').toLowerCase(),
            started: j.created_at || new Date().toISOString(),
            download_url: j.download_url || '#',
            duration: j.duration || '12s'
          })));
        }
      }
    } catch (_) {}
    finally { setLoading(false); }
  }, []);

  useEffect(() => {
    loadData();
  }, [loadData]);

  const handleImpersonate = (user) => {
    setImpersonatingUser(user);
    addToast?.(`Now impersonating ${user.name} (${user.role})`, 'info');
  };

  const handleStopImpersonate = () => {
    setImpersonatingUser(null);
    addToast?.('Returned to Super Admin session', 'success');
  };

  /* Impersonate filtered */
  const filteredUsers = usersList.filter((u) => {
    const matchesSearch =
      u.name.toLowerCase().includes(search.toLowerCase()) ||
      u.email.toLowerCase().includes(search.toLowerCase()) ||
      u.role.toLowerCase().includes(search.toLowerCase());
    const matchesRole = roleFilter === 'all' || u.rawRole === roleFilter;
    return matchesSearch && matchesRole;
  });

  /* Batch jobs filtered */
  const filteredBatchJobs = batchJobs.filter((j) => {
    const q = batchSearch.toLowerCase().trim();
    const matchQ = !q || j.id.toLowerCase().includes(q) || j.name.toLowerCase().includes(q) || j.type.toLowerCase().includes(q) || j.user.toLowerCase().includes(q);
    const matchStatus = batchStatusFilter === 'all' || j.status === batchStatusFilter;
    const matchType = batchTypeFilter === 'all' || j.type.toLowerCase().replace(/\s+/g, '_') === batchTypeFilter;
    return matchQ && matchStatus && matchType;
  });

  /* Statistics state from API */
  const [statsData, setStatsData] = useState(null);
  const [statsLoading, setStatsLoading] = useState(false);

  const loadStatsData = useCallback(async () => {
    setStatsLoading(true);
    try {
      const res = await panelApi.getMonitoring();
      setStatsData(res || null);
    } catch (_) {}
    finally { setStatsLoading(false); }
  }, []);

  useEffect(() => {
    if (activeTab === 'statistics') loadStatsData();
  }, [activeTab, loadStatsData]);

  /* Per-range chart datasets */
  const CHART_RANGES = {
    Hours: {
      labels: ['22:00','23:00','00:00','01:00','02:00','03:00','04:00','05:00','06:00','07:00','08:00','09:00','10:00','11:00','12:00','13:00','14:00','15:00','16:00','17:00','18:00','19:00','20:00','21:00'],
      web:   [1,2,0,0,0,0,0,1,0,0,4,10,14,17,19,23,27,13,9,5,4,3,2,2],
      mob:   [3,3,3,0,0,0,0,1,1,1,8,10,11,8,12,9,12,6,7,8,3,3,3,2],
    },
    Days: {
      labels: ['Mon','Tue','Wed','Thu','Fri','Sat','Sun'],
      web:   [42,58,51,67,74,30,18],
      mob:   [28,35,40,38,55,22,12],
    },
    Weeks: {
      labels: ['Wk 1','Wk 2','Wk 3','Wk 4'],
      web:   [210,285,340,295],
      mob:   [140,180,220,190],
    },
    Months: {
      labels: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'],
      web:   [120,98,145,160,200,185,240,195,0,0,0,0],
      mob:   [80,70,95,110,140,120,160,135,0,0,0,0],
    },
  };

  const currentRange = CHART_RANGES[statsRange] || CHART_RANGES.Hours;
  const timeLabels = currentRange.labels;
  const webData    = currentRange.web;
  const mobData    = currentRange.mob;
  const chartMaxVal = Math.max(...webData, ...mobData, 10);

  /* Helper to generate SVG cubic spline curve */
  const getSplinePath = (data, width, height, maxVal) => {
    const points = data.map((val, idx) => {
      const x = (idx / (data.length - 1)) * width;
      const y = height - (val / maxVal) * height;
      return { x, y };
    });
    let d = `M ${points[0].x} ${points[0].y}`;
    for (let i = 0; i < points.length - 1; i++) {
      const curr = points[i];
      const next = points[i + 1];
      const cp1x = curr.x + (next.x - curr.x) / 2;
      const cp1y = curr.y;
      const cp2x = curr.x + (next.x - curr.x) / 2;
      const cp2y = next.y;
      d += ` C ${cp1x} ${cp1y}, ${cp2x} ${cp2y}, ${next.x} ${next.y}`;
    }
    return { path: d, points };
  };

  const chartWidth  = 900;
  const chartHeight = 240;
  const webSpline   = getSplinePath(webData, chartWidth, chartHeight, chartMaxVal);
  const mobSpline   = getSplinePath(mobData, chartWidth, chartHeight, chartMaxVal);
  const webAreaD    = `${webSpline.path} L ${chartWidth} ${chartHeight} L 0 ${chartHeight} Z`;

  /* Derive metric values from API or fallback */
  const liveSessionsVal = statsData?.active_sessions ?? statsData?.concurrent_users ?? statsData?.online_users ?? '—';
  const peakVal         = statsData?.peak_sessions ?? statsData?.peak_concurrent ?? statsData?.today_peak ?? '—';
  const busiestInterval = statsData?.busiest_interval ?? statsData?.busiest_hour ?? '13:00 – 15:00';
  const mobileLive      = statsData?.mobile_users ?? statsData?.active_mobile ?? statsData?.mobile_sessions ?? '—';


  return (
    <div style={{ width: '100%', height: '100%', padding: 0, margin: 0, background: 'transparent', overflow: 'hidden', display: 'flex', flexDirection: 'column' }}>
      
      {/* ── Top Bar Navigation Tabs ── */}
      <div className="action-bar" style={{ background: '#1e1e2e', borderBottom: '1px solid rgba(255, 255, 255, 0.08)', height: '50px', padding: '0 16px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', boxSizing: 'border-box', flexShrink: 0 }}>
        <div className="status-tabs" style={{ display: 'inline-flex', alignItems: 'center', background: 'rgba(255, 255, 255, 0.08)', border: '1px solid rgba(255, 255, 255, 0.18)', borderRadius: '5px', padding: '2px', gap: '2px', height: '28px', boxSizing: 'border-box' }}>
          {[
            { id: 'impersonate', label: 'Impersonate User', Icon: UserCog },
            { id: 'guests', label: 'Manage Guest Users', Icon: ShieldCheck },
            { id: 'statistics', label: 'Statistics', Icon: Activity },
            { id: 'batch', label: 'Batch Jobs', Icon: Zap },
          ].map(({ id, label, Icon }) => (
            <button
              key={id}
              onClick={() => setActiveTab(id)}
              className={`status-tab${activeTab === id ? ' active' : ''}`}
              style={{
                padding: '0 10px', height: '22px', fontSize: '11px', lineHeight: '22px', borderRadius: '3px',
                border: 'none', cursor: 'pointer', background: activeTab === id ? '#2563eb' : 'transparent',
                color: activeTab === id ? '#ffffff' : '#cbd5e1', fontWeight: activeTab === id ? 700 : 600,
                fontFamily: 'var(--font-family)', transition: 'all 0.15s',
                boxShadow: activeTab === id ? '0 1px 3px rgba(0,0,0,0.3)' : 'none',
                display: 'inline-flex', alignItems: 'center', gap: '5px'
              }}
            >
              <Icon size={12} />
              <span>{label}</span>
            </button>
          ))}
        </div>

        {/* Impersonation Session Badge */}
        {impersonatingUser && (
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px', background: '#fef2f2', border: '1px solid #fca5a5', padding: '4px 10px', borderRadius: '4px', fontSize: '11px' }}>
            <span style={{ fontWeight: 700, color: '#991b1b' }}>Active Session: {impersonatingUser.name}</span>
            <button
              onClick={handleStopImpersonate}
              style={{ background: '#dc2626', color: '#fff', border: 'none', borderRadius: '3px', padding: '2px 6px', fontSize: '10px', fontWeight: 700, cursor: 'pointer' }}
            >
              Exit
            </button>
          </div>
        )}
      </div>

      {/* ── TAB 1: IMPERSONATE USER ── */}
      {activeTab === 'impersonate' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          {/* Action Bar */}
          <div className="action-bar-light" id="impersonate-action-bar">
            <div className="action-bar-left" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              {/* Search Input Box */}
              <div className="notif-search-box" style={{ width: '240px' }}>
                <Search size={13} style={{ color: '#94a3b8', flexShrink: 0, marginRight: '6px' }} />
                <input
                  type="text"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder="Search by name, email or role..."
                />
                {search && (
                  <button
                    onClick={() => setSearch('')}
                    style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#94a3b8', display: 'flex', alignItems: 'center', padding: '0 2px' }}
                    title="Clear search"
                  >
                    <X size={12} />
                  </button>
                )}
              </div>

              {/* Separator */}
              <div style={{ width: '1px', height: '16px', background: '#e2e8f0', flexShrink: 0 }} />

              {/* Filter Pills */}
              <div className="status-tabs">
                {[
                  { id: 'all', label: `All (${usersList.length})` },
                  { id: 'client', label: `Organisation/Manager (${usersList.filter(u => u.rawRole === 'client').length})` },
                  { id: 'client_staff', label: `Assistant (${usersList.filter(u => u.rawRole === 'client_staff').length})` },
                  { id: 'guest_user', label: `Guest User (${usersList.filter(u => u.rawRole === 'guest_user').length})` },
                ].map((pill) => (
                  <button
                    key={pill.id}
                    onClick={() => setRoleFilter(pill.id)}
                    className={`status-tab${roleFilter === pill.id ? ' active' : ''}`}
                  >
                    {pill.label}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* User Table */}
          <div className="table-wrapper" style={{ flex: 1, overflowY: 'auto', background: '#ffffff', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <table className="data-table" style={{ flexShrink: 0 }}>
              <thead>
                <tr>
                  <th style={{ width: '50px', textAlign: 'center' }}>S. NO.</th>
                  <th>NAME</th>
                  <th>EMAIL</th>
                  <th style={{ width: '180px' }}>ROLE</th>
                  <th style={{ width: '100px', textAlign: 'center' }}>STATUS</th>
                  <th style={{ width: '130px', textAlign: 'center' }}>OPTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filteredUsers.map((u, i) => (
                  <tr key={u.id}>
                    <td style={{ textAlign: 'center', color: '#64748b', fontWeight: 600 }}>{i + 1}</td>
                    <td style={{ fontWeight: 700, color: '#0f172a' }}>{u.name}</td>
                    <td style={{ color: '#475569', fontSize: '12px' }}>{u.email}</td>
                    <td>
                      <span className="badge badge-neutral">{u.role}</span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className="badge badge-success">{u.status}</span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <button
                        onClick={() => handleImpersonate(u)}
                        className="btn btn-sm btn-primary"
                        style={{ display: 'inline-flex', alignItems: 'center', gap: '4px', fontSize: '11px', padding: '3px 10px' }}
                      >
                        <LogIn size={11} /> Login As User
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredUsers.length === 0 && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
                <div style={{
                  width: '64px', height: '64px', borderRadius: '50%',
                  background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                  color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
                }}>
                  <UserCog size={30} />
                </div>
                <div style={{ maxWidth: '340px' }}>
                  <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                    No Users Found
                  </h4>
                  <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                    {search ? `No accounts match "${search}"` : 'There are no active user accounts available to manage or impersonate.'}
                  </p>
                </div>
              </div>
            )}
          </div>
          <PaginationBar page={impPage} setPage={setImpPage} total={filteredUsers.length} pageSize={impPageSize} setPageSize={setImpPageSize} loading={loading} />
        </div>
      )}

      {/* ── TAB 2: MANAGE GUEST USERS ── */}
      {activeTab === 'guests' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          
          <div className="action-bar-light">
            <span style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b' }}>Temporary Guest Pass Records</span>
            <button
              onClick={() => addToast?.('New guest pass generated', 'success')}
              className="btn btn-sm btn-primary"
            >
              <Plus size={13} /> Issue Guest Pass
            </button>
          </div>

          <div className="table-wrapper" style={{ flex: 1, overflowY: 'auto', background: '#ffffff', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <table className="data-table" style={{ flexShrink: 0 }}>
              <thead>
                <tr>
                  <th style={{ width: '60px', textAlign: 'center' }}>SR NO.</th>
                  <th>Guest User</th>
                  <th>Email</th>
                  <th>Expires On</th>
                  <th style={{ width: '100px', textAlign: 'center' }}>Status</th>
                </tr>
              </thead>
              <tbody>
                {guestUsers.map((g, i) => (
                  <tr key={g.id}>
                    <td style={{ textAlign: 'center', color: '#64748b', fontWeight: 600 }}>{i + 1}</td>
                    <td style={{ fontWeight: 700, color: '#0f172a' }}>{g.name}</td>
                    <td style={{ color: '#334155' }}>{g.email}</td>
                    <td style={{ color: '#475569' }}>{g.expires}</td>
                    <td style={{ textAlign: 'center' }}>
                      <span className={`badge ${g.status === 'Active' ? 'badge-success' : 'badge-danger'}`}>
                        {g.status}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {guestUsers.length === 0 && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
                <div style={{
                  width: '64px', height: '64px', borderRadius: '50%',
                  background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                  color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
                }}>
                  <ShieldCheck size={30} />
                </div>
                <div style={{ maxWidth: '340px' }}>
                  <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                    No Guest Pass Records
                  </h4>
                  <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                    No temporary guest passes have been issued yet. Issue a pass to grant temporary access.
                  </p>
                </div>
                <button
                  onClick={() => addToast?.('New guest pass generated', 'success')}
                  className="btn btn-primary btn-sm"
                  style={{ marginTop: '14px', display: 'inline-flex', alignItems: 'center', gap: '6px', fontSize: '11px', padding: '7px 16px', borderRadius: '5px' }}
                >
                  <Plus size={14} /> Issue First Guest Pass
                </button>
              </div>
            )}
          </div>
          <PaginationBar page={guestPage} setPage={setGuestPage} total={guestUsers.length} pageSize={guestPageSize} setPageSize={setGuestPageSize} loading={loading} />
        </div>
      )}

      {/* ── TAB 3: STATISTICS (Faithful replica of panel.adarshbhopal.in/panel/stats/ 3rd screenshot) ── */}
      {activeTab === 'statistics' && (
        <div style={{ flex: 1, overflowY: 'auto', background: '#f8fafc', display: 'flex', flexDirection: 'column' }}>
          
          {/* Top 4 Metrics Bar */}
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', borderBottom: '1px solid #e2e8f0', background: '#ffffff' }}>
            
            <div style={{ padding: '16px 20px', borderRight: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: '24px', fontWeight: 800, color: '#0f172a', lineHeight: 1.1 }}>{statsLoading ? '…' : liveSessionsVal}</div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155', margin: '4px 0 2px' }}>Live Active Sessions</div>
                <div style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#22c55e', animation: 'pulse 2s infinite' }} />
                  <span>All concurrent online users</span>
                </div>
              </div>
              <div style={{ width: '42px', height: '42px', borderRadius: '8px', background: '#6366f1', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 10px rgba(99,102,241,0.25)' }}>
                <Users size={20} />
              </div>
            </div>

            <div style={{ padding: '16px 20px', borderRight: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: '24px', fontWeight: 800, color: '#0f172a', lineHeight: 1.1 }}>{statsLoading ? '…' : peakVal}</div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155', margin: '4px 0 2px' }}>Today's Peak Active</div>
                <div style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <TrendingUp size={11} style={{ color: '#22c55e' }} />
                  <span>Max concurrent sessions today</span>
                </div>
              </div>
              <div style={{ width: '42px', height: '42px', borderRadius: '8px', background: '#10b981', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 10px rgba(16,185,129,0.25)' }}>
                <Activity size={20} />
              </div>
            </div>

            <div style={{ padding: '16px 20px', borderRight: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: '18px', fontWeight: 800, color: '#0f172a', lineHeight: 1.2 }}>{statsLoading ? '…' : busiestInterval}</div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155', margin: '4px 0 2px' }}>Busiest Interval (Today)</div>
                <div style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <Clock size={11} style={{ color: '#f59e0b' }} />
                  <span>Highest-traffic 2-hour window</span>
                </div>
              </div>
              <div style={{ width: '42px', height: '42px', borderRadius: '8px', background: '#f59e0b', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 10px rgba(245,158,11,0.25)' }}>
                <Clock size={20} />
              </div>
            </div>

            <div style={{ padding: '16px 20px', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
              <div>
                <div style={{ fontSize: '24px', fontWeight: 800, color: '#0f172a', lineHeight: 1.1 }}>{statsLoading ? '…' : mobileLive}</div>
                <div style={{ fontSize: '12px', fontWeight: 700, color: '#334155', margin: '4px 0 2px' }}>Live Mobile Users</div>
                <div style={{ fontSize: '11px', color: '#94a3b8', display: 'flex', alignItems: 'center', gap: '4px' }}>
                  <span style={{ width: '6px', height: '6px', borderRadius: '50%', background: '#06b6d4' }} />
                  <span>Mobile app concurrent users</span>
                </div>
              </div>
              <div style={{ width: '42px', height: '42px', borderRadius: '8px', background: '#06b6d4', color: '#ffffff', display: 'flex', alignItems: 'center', justifyContent: 'center', boxShadow: '0 4px 10px rgba(6,182,212,0.25)' }}>
                <Smartphone size={20} />
              </div>
            </div>

          </div>

          {/* Chart Header & Filters */}
          <div style={{ padding: '14px 24px', background: '#ffffff', borderBottom: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>User Activities Overview</h3>
              <p style={{ margin: '3px 0 0', fontSize: '11px', color: '#64748b' }}>Active Web Desktop vs Mobile App users per {statsRange.toLowerCase()}</p>
            </div>

            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <button onClick={loadStatsData} title="Refresh statistics" style={{ display: 'inline-flex', alignItems: 'center', gap: '5px', height: '28px', padding: '0 10px', fontSize: '11px', fontWeight: 600, borderRadius: '4px', border: '1px solid #cbd5e1', background: '#f8fafc', color: '#475569', cursor: 'pointer' }}>
                {statsLoading ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <RefreshCw size={12} />}
                Refresh
              </button>
              <div style={{ display: 'flex', alignItems: 'center', gap: '2px', background: '#f1f5f9', padding: '3px', borderRadius: '6px', border: '1px solid #cbd5e1' }}>
                {['Hours', 'Days', 'Weeks', 'Months'].map((r) => (
                  <button
                    key={r}
                    onClick={() => setStatsRange(r)}
                    style={{
                      padding: '4px 12px', fontSize: '11px', fontWeight: statsRange === r ? 700 : 500,
                      borderRadius: '4px', border: 'none', cursor: 'pointer',
                      background: statsRange === r ? '#ffffff' : 'transparent',
                      color: statsRange === r ? '#2563eb' : '#64748b',
                      boxShadow: statsRange === r ? '0 1px 3px rgba(0,0,0,0.1)' : 'none',
                      transition: 'all 0.15s'
                    }}
                  >
                    {r}
                  </button>
                ))}
              </div>
            </div>
          </div>

          {/* Smooth Area Chart Canvas matching 3rd screenshot */}
          <div style={{ padding: '24px', flex: 1, display: 'flex', flexDirection: 'column', background: '#ffffff' }}>
            
            {/* Chart Legend */}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', gap: '24px', marginBottom: '16px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#334155', fontWeight: 600 }}>
                <span style={{ width: '12px', height: '12px', background: '#6366f1', borderRadius: '2px', display: 'inline-block' }} />
                <span>Active Desktop (Web) Users</span>
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', color: '#334155', fontWeight: 600 }}>
                <span style={{ width: '12px', height: '12px', background: '#10b981', borderRadius: '2px', display: 'inline-block' }} />
                <span>Active Mobile App Users</span>
              </div>
            </div>

            {/* SVG Chart Wrapper */}
            <div style={{ position: 'relative', width: '100%', height: '300px', display: 'flex' }}>
              
                {/* Y-Axis Labels — dynamic max */}
                <div style={{ width: '35px', height: `${chartHeight}px`, display: 'flex', flexDirection: 'column', justifyContent: 'space-between', fontSize: '11px', color: '#94a3b8', textAlign: 'right', paddingRight: '8px', fontWeight: 600 }}>
                  {[1, 0.857, 0.714, 0.571, 0.428, 0.285, 0.142, 0].map((r, i) => (
                    <span key={i}>{Math.round(chartMaxVal * r)}</span>
                  ))}
                </div>

                {/* Chart SVG */}
                <div style={{ flex: 1, position: 'relative', height: `${chartHeight + 35}px` }}>
                  <svg viewBox={`0 0 ${chartWidth} ${chartHeight}`} preserveAspectRatio="none" style={{ width: '100%', height: `${chartHeight}px`, overflow: 'visible' }}>
                    <defs>
                      <linearGradient id="purpleGrad" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="0%" stopColor="#6366f1" stopOpacity="0.35" />
                        <stop offset="100%" stopColor="#6366f1" stopOpacity="0.02" />
                      </linearGradient>
                    </defs>

                    {/* Horizontal Grid lines */}
                    {[0, 0.14, 0.28, 0.42, 0.57, 0.71, 0.85, 1].map((ratio, idx) => (
                      <line key={idx} x1="0" y1={chartHeight * ratio} x2={chartWidth} y2={chartHeight * ratio}
                        stroke="#e2e8f0" strokeDasharray="3 3" strokeWidth="1" />
                    ))}

                    {/* Web Gradient Area & Smooth Line */}
                    <path d={webAreaD} fill="url(#purpleGrad)" />
                    <path d={webSpline.path} fill="none" stroke="#6366f1" strokeWidth="2.5" />

                    {/* Mobile Green Smooth Line */}
                    <path d={mobSpline.path} fill="none" stroke="#10b981" strokeWidth="2.5" />

                    {/* Data Points */}
                    {webSpline.points.map((pt, i) => (
                      <circle key={`web-${i}`} cx={pt.x} cy={pt.y} r="3" fill="#ffffff" stroke="#6366f1" strokeWidth="2" />
                    ))}
                    {mobSpline.points.map((pt, i) => (
                      <circle key={`mob-${i}`} cx={pt.x} cy={pt.y} r="3" fill="#ffffff" stroke="#10b981" strokeWidth="2" />
                    ))}
                  </svg>

                  {/* X-Axis Labels */}
                  <div style={{ display: 'flex', justifyContent: 'space-between', width: '100%', marginTop: '8px', fontSize: '10px', color: '#94a3b8', fontWeight: 600 }}>
                    {timeLabels.map((t) => <span key={t}>{t}</span>)}
                  </div>
                </div>

            </div>

          </div>

        </div>
      )}

      {/* ── TAB 4: BATCH JOBS (Action Bar, Table, Sticky Pagination Bar) ── */}
      {activeTab === 'batch' && (
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', overflow: 'hidden' }}>
          
          {/* Action Bar Header */}
          <div className="action-bar-light">
            <div className="action-bar-left" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
              <div className="notif-search-box" style={{ width: '240px' }}>
                <Search size={13} style={{ color: '#94a3b8', flexShrink: 0, marginRight: '6px' }} />
                <input
                  type="text"
                  value={batchSearch}
                  onChange={(e) => setBatchSearch(e.target.value)}
                  placeholder="Search Job ID, task, operator, type..."
                />
                {batchSearch && (
                  <button onClick={() => setBatchSearch('')} style={{ border: 'none', background: 'transparent', cursor: 'pointer', color: '#9ca3af', display: 'flex', alignItems: 'center', padding: '0 2px' }} title="Clear search">
                    <X size={13} />
                  </button>
                )}
              </div>

              {/* Status Filter */}
              <select
                value={batchStatusFilter}
                onChange={(e) => setBatchStatusFilter(e.target.value)}
                className="form-select form-select-sm"
                style={{ height: '28px', fontSize: '12px', padding: '0 8px', width: 'auto' }}
              >
                <option value="all">All Status</option>
                <option value="processing">Processing</option>
                <option value="pending">Pending</option>
                <option value="completed">Completed</option>
                <option value="failed">Failed</option>
              </select>

              {/* Type Filter */}
              <select
                value={batchTypeFilter}
                onChange={(e) => setBatchTypeFilter(e.target.value)}
                className="form-select form-select-sm"
                style={{ height: '28px', fontSize: '12px', padding: '0 8px', width: 'auto' }}
              >
                <option value="all">All Operation Types</option>
                <option value="bulk_upload">Bulk Upload</option>
                <option value="photo_sync">Photo Sync</option>
                <option value="bulk_export">Bulk Export</option>
                <option value="re-upload_patch">Re-upload Patch</option>
              </select>
            </div>
          </div>

          {/* Full Width Data Table */}
          <div className="table-wrapper" style={{ flex: 1, overflowY: 'auto', background: '#ffffff', display: 'flex', flexDirection: 'column', minHeight: 0 }}>
            <table className="data-table" style={{ flexShrink: 0 }}>
              <thead>
                <tr>
                  <th style={{ width: '45px', textAlign: 'center' }}>S. NO.</th>
                  <th style={{ width: '90px' }}>JOB ID</th>
                  <th>TASK NAME</th>
                  <th style={{ width: '120px' }}>TYPE</th>
                  <th>TRIGGERED BY</th>
                  <th style={{ width: '170px' }}>PROGRESS & RECORDS</th>
                  <th style={{ width: '100px', textAlign: 'center' }}>STATUS</th>
                  <th style={{ width: '110px', textAlign: 'center' }}>ACTIONS</th>
                </tr>
              </thead>
              <tbody>
                {filteredBatchJobs.map((j, i) => (
                  <tr key={j.id}>
                    <td style={{ textAlign: 'center', color: '#64748b', fontWeight: 600 }}>{i + 1}</td>
                    <td style={{ fontFamily: 'monospace', fontSize: '12px', fontWeight: 700, color: '#1e293b' }}>{j.id}</td>
                    <td style={{ fontWeight: 700, color: '#0f172a' }}>{j.name}</td>
                    <td><span className="badge badge-neutral">{j.type}</span></td>
                    <td style={{ color: '#475569', fontSize: '12px' }}>{j.user}</td>
                    <td>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: '3px' }}>
                        <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '11px', color: '#475569', fontWeight: 600 }}>
                          <span>{j.records}</span>
                          <span>{j.progress}%</span>
                        </div>
                        <div style={{ width: '100%', height: '6px', background: '#e2e8f0', borderRadius: '3px', overflow: 'hidden' }}>
                          <div style={{ width: `${j.progress}%`, height: '100%', background: j.status === 'completed' ? '#16a34a' : j.status === 'failed' ? '#dc2626' : 'rgb(0, 80, 210)', transition: 'width 0.3s ease' }} />
                        </div>
                      </div>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <span className={`badge ${j.status === 'completed' ? 'badge-success' : j.status === 'processing' ? 'badge-primary' : j.status === 'failed' ? 'badge-danger' : 'badge-warning'}`}>
                        {j.status}
                      </span>
                    </td>
                    <td style={{ textAlign: 'center' }}>
                      <div style={{ display: 'flex', gap: '4px', justifyContent: 'center' }}>
                        {j.download_url && (
                          <button className="btn btn-sm btn-neutral" style={{ width: '24px', height: '24px', padding: 0 }} onClick={() => addToast?.(`Downloading batch report for ${j.id}...`, 'info')} title="Download Result ZIP/Report">
                            <FileDown size={11} />
                          </button>
                        )}
                        <button className="btn btn-sm btn-neutral" style={{ width: '24px', height: '24px', padding: 0 }} onClick={() => addToast?.(`Viewing logs for ${j.id}`, 'info')} title="View Execution Logs">
                          <FileText size={11} />
                        </button>
                        {j.status === 'failed' && (
                          <button className="btn btn-sm btn-danger" style={{ width: '24px', height: '24px', padding: 0 }} onClick={() => addToast?.(`Retrying batch job ${j.id}...`, 'info')} title="Retry Failed Task">
                            <RotateCw size={11} />
                          </button>
                        )}
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>

            {filteredBatchJobs.length === 0 && (
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', padding: '40px 20px', textAlign: 'center', minHeight: '240px' }}>
                <div style={{
                  width: '64px', height: '64px', borderRadius: '50%',
                  background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                  color: '#2563eb', display: 'flex', alignItems: 'center', justifyContent: 'center',
                  boxShadow: '0 4px 14px rgba(37,99,235,0.12)', border: '1px solid #bfdbfe', marginBottom: '12px'
                }}>
                  <Zap size={30} />
                </div>
                <div style={{ maxWidth: '340px' }}>
                  <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                    No Batch Jobs Found
                  </h4>
                  <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                    {batchSearch ? `No batch jobs match "${batchSearch}"` : 'No background bulk task operations have been recorded.'}
                  </p>
                </div>
              </div>
            )}
          </div>
          <PaginationBar page={batchPage} setPage={setBatchPage} total={filteredBatchJobs.length} pageSize={batchPageSize} setPageSize={setBatchPageSize} loading={loading} />
        </div>
      )}

    </div>
  );
}
