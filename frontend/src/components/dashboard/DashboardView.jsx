import React, { useState, useEffect, useCallback } from 'react';
import {
  Clock,
  CheckCircle2,
  ThumbsUp,
  Download,
  Trash2,
  CreditCard,
  Users,
  User,
  Layers,
  Plus,
  Mail,
  Shield,
  Search,
  RefreshCw,
  ChevronRight,
  ChevronDown,
  Building,
  X,
  Send,
  Printer,
  RotateCcw,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import WatermarkLogo from '../common/WatermarkLogo';
import StatusChangeBadge from '../common/StatusChangeBadge';

import { dashboardApi, schemaApi } from '../../services/api';

/* ─────────────────────────────────────────────────────────────────────────
   Top Welcome Banner (Purple Gradient) — SS2 Exact
───────────────────────────────────────────────────────────────────────── */
function WelcomeBanner({ currentUser }) {
  const [time, setTime] = useState(new Date());

  useEffect(() => {
    const timer = setInterval(() => setTime(new Date()), 1000);
    return () => clearInterval(timer);
  }, []);

  const formattedDate = time.toLocaleDateString('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  });
  const formattedTime = time.toLocaleTimeString('en-US', { hour12: false });
  const userName =
    currentUser?.org_name ||
    currentUser?.name ||
    currentUser?.full_name ||
    (currentUser?.first_name ? `${currentUser.first_name} ${currentUser.last_name || ''}`.trim() : null) ||
    currentUser?.username ||
    'User';

  return (
    <div
      style={{
        background: 'linear-gradient(135deg, rgb(0, 80, 210) 0%, rgb(0, 180, 255) 100%)',
        color: '#fff',
        padding: '12px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
        borderBottom: '1px solid rgba(255,255,255,0.15)',
      }}
    >
      <div>
        <h2 style={{ fontSize: '17px', fontWeight: 700, margin: 0, color: '#fff', fontFamily: 'var(--font-family)' }}>
          Welcome back, {userName}!
        </h2>
        <p
          style={{
            fontSize: '12px',
            color: 'rgba(255,255,255,0.8)',
            margin: '1px 0 0',
            fontFamily: 'var(--font-family)',
          }}
        >
          Here's what's happening with your ID card system today.
        </p>
      </div>

      <div style={{ textAlign: 'right', fontFamily: 'var(--font-family)' }}>
        <div style={{ fontSize: '11px', fontWeight: 500, color: 'rgba(255,255,255,0.85)' }}>{formattedDate}</div>
        <div style={{ fontSize: '15px', fontWeight: 700, letterSpacing: '0.04em', color: '#fff' }}>{formattedTime}</div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   9 Stat Cards Row (Pending, Verified, Approved, Printed, Deleted, Reprinting, Requested, Confirmed, Total ID Cards)
───────────────────────────────────────────────────────────────────────── */
const STAT_CARDS_DEF = [
  { key: 'pending_cards', statusNav: 'pending', label: 'Pending Cards', defaultVal: 0, bg: '#f59e0b', Icon: Clock },
  { key: 'verified_cards', statusNav: 'verified', label: 'Verified Cards', defaultVal: 0, bg: '#10b981', Icon: CheckCircle2 },
  { key: 'approved_cards', statusNav: 'approved', label: 'Approved Cards', defaultVal: 0, bg: '#3b82f6', Icon: ThumbsUp },
  { key: 'printed_cards', statusNav: 'printed', label: 'Printed Cards', defaultVal: 0, bg: '#64748b', Icon: Printer },
  { key: 'deleted_cards', statusNav: 'deleted', label: 'Deleted Cards', defaultVal: 0, bg: '#ef4444', Icon: Trash2 },
  { key: 'reprinting_cards', statusNav: 'reprint', label: 'Reprinting Cards', defaultVal: 0, bg: '#d97706', Icon: RotateCcw },
  { key: 'requested_cards', statusNav: 'request', label: 'Requested Cards', defaultVal: 0, bg: '#8b5cf6', Icon: Send },
  { key: 'confirmed_cards', statusNav: 'confirm', label: 'Confirmed Cards', defaultVal: 0, bg: '#059669', Icon: CheckCircle2 },
  { key: 'total_id_cards', statusNav: 'all', label: 'Total ID Cards', defaultVal: 0, bg: '#06b6d4', Icon: CreditCard },
];

function StatCardsRow({ stats, clients = [], loading, onNavigate, userRole = 'super_admin' }) {
  const isAdminOrOperator = [
    'prime_admin',
    'super_admin',
    'pro_user',
    'operator',
  ].includes(String(userRole || '').toLowerCase());

  return (
    <div
      style={{
        display: 'grid',
        gridTemplateColumns: 'repeat(9, 1fr)',
        gap: 0,
        background: '#fff',
        borderBottom: '1px solid #cbd5e1',
        flexShrink: 0,
      }}
    >
      {STAT_CARDS_DEF.map(({ key, statusNav, label, defaultVal, bg, Icon }, idx) => {
        let clientSum = null;
        if (Array.isArray(clients) && clients.length > 0) {
          if (key === 'pending_cards') clientSum = clients.reduce((acc, c) => acc + (c.pending || 0), 0);
          else if (key === 'verified_cards') clientSum = clients.reduce((acc, c) => acc + (c.verified || 0), 0);
          else if (key === 'approved_cards') clientSum = clients.reduce((acc, c) => acc + (c.approved || 0), 0);
          else if (key === 'printed_cards') clientSum = clients.reduce((acc, c) => acc + (c.downloaded || c.download || 0), 0);
          else if (key === 'deleted_cards') clientSum = clients.reduce((acc, c) => acc + (c.pool || c.deleted || 0), 0);
          else if (key === 'reprinting_cards') clientSum = clients.reduce((acc, c) => acc + (c.reprint || c.reprinting || 0), 0);
          else if (key === 'requested_cards') clientSum = clients.reduce((acc, c) => acc + (c.request || c.requested || 0), 0);
          else if (key === 'confirmed_cards') clientSum = clients.reduce((acc, c) => acc + (c.confirm || c.confirmed || 0), 0);
          else if (key === 'total_id_cards') {
            clientSum = clients.reduce(
              (acc, c) =>
                acc +
                (c.pending || 0) +
                (c.verified || 0) +
                (c.approved || 0) +
                (c.downloaded || c.download || 0) +
                (c.pool || c.deleted || 0) +
                (c.reprint || c.reprinting || 0) +
                (c.request || c.requested || 0) +
                (c.confirm || c.confirmed || 0),
              0
            );
          }
        }

        const apiVal =
          stats?.[key] ??
          stats?.[key.replace('_cards', '')] ??
          (key === 'printed_cards'
            ? (stats?.download_cards ?? stats?.downloaded ?? stats?.download)
            : key === 'deleted_cards'
              ? (stats?.pool_cards ?? stats?.pool)
              : key === 'reprinting_cards'
                ? (stats?.reprinting_cards ?? stats?.reprint_cards ?? stats?.reprint ?? stats?.reprinting)
                : key === 'requested_cards'
                  ? (stats?.requested_cards ?? stats?.request_cards ?? stats?.requested ?? stats?.request)
                  : key === 'confirmed_cards'
                    ? (stats?.confirmed_cards ?? stats?.confirm_cards ?? stats?.confirmed ?? stats?.confirm)
                    : undefined);

        const val = apiVal !== undefined && apiVal > 0 ? apiVal : (clientSum !== null ? clientSum : (apiVal ?? defaultVal));
        const isLast = idx === STAT_CARDS_DEF.length - 1;

        return (
          <button
            key={key}
            onClick={() => onNavigate('cards', { statusFilter: statusNav })}
            className="stat-card-glass"
            style={{
              padding: '6px 6px',
              height: '44px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              background: '#fff',
              border: 'none',
              borderRight: isLast ? 'none' : '1px solid #cbd5e1',
              cursor: 'pointer',
              textAlign: 'left',
              boxSizing: 'border-box',
              minWidth: 0,
              gap: '6px',
            }}
            onMouseEnter={(e) => (e.currentTarget.style.background = '#f8fafc')}
            onMouseLeave={(e) => (e.currentTarget.style.background = '#fff')}
          >
            <div style={{ minWidth: 0, overflow: 'hidden' }}>
              <div
                style={{
                  fontSize: '16px',
                  fontWeight: 700,
                  color: '#0f172a',
                  lineHeight: 1.1,
                  fontFamily: 'var(--font-family)',
                  whiteSpace: 'nowrap',
                }}
              >
                {loading && !stats ? '—' : val.toLocaleString()}
              </div>
              <div
                style={{
                  fontSize: '9.5px',
                  fontWeight: 600,
                  color: '#64748b',
                  marginTop: '2px',
                  fontFamily: 'var(--font-family)',
                  whiteSpace: 'nowrap',
                  overflow: 'hidden',
                  textOverflow: 'ellipsis',
                }}
                title={label}
              >
                {label}
              </div>
            </div>

            <div
              style={{
                width: '28px',
                height: '28px',
                borderRadius: '6px',
                background: bg,
                color: '#fff',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                flexShrink: 0,
                marginLeft: '4px',
              }}
            >
              <Icon size={14} />
            </div>
          </button>
        );
      })}
    </div>
  );
}

function getTableCounts(t) {
  if (!t) return { pending: 0, verified: 0, approved: 0, download: 0, pool: 0, request: 0, reprint: 0, confirmed: 0, total: 0 };
  const pending = t.pending_count ?? t.pending ?? 0;
  const verified = t.verified_count ?? t.verified ?? 0;
  const approved = t.approved_count ?? t.approved ?? 0;
  const download = t.download_count ?? t.downloaded ?? t.download ?? t.printed ?? 0;
  const pool = t.pool_count ?? t.deleted ?? t.pool ?? 0;

  const reprint = t.reprint_count ?? t.reprint ?? 0;
  const request = t.reprint_request_count ?? t.reprint_request ?? t.request ?? t.requested ?? 0;
  const confirmed = t.reprint_confirmed_count ?? t.reprint_confirmed ?? t.confirmed ?? 0;
  const total = pending + verified + approved + download + pool + reprint;

  return { pending, verified, approved, download, pool, request, reprint, confirmed, total };
}

function RecentClientUpdatesTable({ clients, allTables = [], loading, onNavigate, search, setSearch }) {
  const [expandedRows, setExpandedRows] = useState({});
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('desc');

  const displayList = clients || [];
  const rows = displayList.filter(
    (c) => !search || (c.name || c.school_name || '').toLowerCase().includes(search.toLowerCase())
  );

  const toggleExpand = (id, e) => {
    e.stopPropagation();
    setExpandedRows((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const handleBadgeClick = (clientOrSubTable, statusKey) => {
    const tableId = clientOrSubTable.table_id || clientOrSubTable.tableId || clientOrSubTable.id || 1;
    onNavigate('idcard-actions', { tableId: tableId, status: statusKey });
  };

  const handleSort = (key) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir('desc');
    } else if (sortDir === 'desc') {
      setSortDir('asc');
    } else {
      setSortKey(null);
      setSortDir('desc');
    }
  };

  const sortedRows = [...rows].sort((a, b) => {
    if (sortKey) {
      const valA = a[sortKey] ?? (sortKey === 'download' ? a.downloaded : 0) ?? 0;
      const valB = b[sortKey] ?? (sortKey === 'download' ? b.downloaded : 0) ?? 0;
      if (typeof valA === 'string') {
        return sortDir === 'desc' ? valB.localeCompare(valA) : valA.localeCompare(valB);
      }
      return sortDir === 'desc' ? valB - valA : valA - valB;
    }
    // Default sorting for "Recent Approved": Orgs with Approved/Printed cards first, then by total cards, then name
    const appA = (a.approved || 0) + (a.downloaded || a.printed || 0);
    const appB = (b.approved || 0) + (b.downloaded || b.printed || 0);
    if (appB !== appA) return appB - appA;

    const totA = (a.pending || 0) + (a.verified || 0) + appA;
    const totB = (b.pending || 0) + (b.verified || 0) + appB;
    if (totB !== totA) return totB - totA;

    return (a.name || '').localeCompare(b.name || '');
  });

  const renderSortIcon = (key) => {
    if (sortKey !== key) return ' ⇕';
    return sortDir === 'desc' ? ' ⬇' : ' ⬆';
  };

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', position: 'relative' }}>
      <WatermarkLogo />

      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '12px',
          position: 'relative',
          zIndex: 1,
          background: 'transparent',
        }}
      >
        <thead style={{ position: 'sticky', top: 0, background: '#1e293b', color: '#ffffff', zIndex: 2 }}>
          <tr style={{ height: '38px', minHeight: '38px' }}>
            <th
              style={{
                padding: '6px 6px',
                textAlign: 'left',
                fontWeight: 700,
                width: '45%',
                fontSize: '11.5px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #334155',
                height: '38px',
                boxSizing: 'border-box',
              }}
            >
              <div
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  width: '100%',
                  gap: '6px',
                }}
              >
                <span style={{ color: '#ffffff', fontWeight: 700 }}>ORGANISATION</span>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center', width: '190px' }}>
                  <Search
                    size={12}
                    style={{ position: 'absolute', left: '6px', color: '#94a3b8', pointerEvents: 'none' }}
                  />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search organisation..."
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      width: '100%',
                      height: '26px',
                      paddingLeft: '24px',
                      paddingRight: '6px',
                      fontSize: '11px',
                      fontWeight: 500,
                      borderRadius: '4px',
                      border: '1px solid #475569',
                      background: '#0f172a',
                      color: '#ffffff',
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
            </th>
            <th
              onClick={() => handleSort('pending')}
              style={{
                padding: '6px 6px',
                textAlign: 'center',
                fontWeight: 700,
                width: '11%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #334155',
                cursor: 'pointer',
                userSelect: 'none',
                height: '38px',
                boxSizing: 'border-box',
                whiteSpace: 'nowrap',
              }}
            >
              PENDING{renderSortIcon('pending')}
            </th>
            <th
              onClick={() => handleSort('verified')}
              style={{
                padding: '6px 6px',
                textAlign: 'center',
                fontWeight: 700,
                width: '11%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #334155',
                cursor: 'pointer',
                userSelect: 'none',
                height: '38px',
                boxSizing: 'border-box',
                whiteSpace: 'nowrap',
              }}
            >
              VERIFIED{renderSortIcon('verified')}
            </th>
            <th
              onClick={() => handleSort('approved')}
              style={{
                padding: '6px 6px',
                textAlign: 'center',
                fontWeight: 700,
                width: '11%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #334155',
                cursor: 'pointer',
                userSelect: 'none',
                height: '38px',
                boxSizing: 'border-box',
                whiteSpace: 'nowrap',
              }}
            >
              APPROVED{renderSortIcon('approved')}
            </th>
            <th
              onClick={() => handleSort('printed')}
              style={{
                padding: '6px 6px',
                textAlign: 'center',
                fontWeight: 700,
                width: '11%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #334155',
                cursor: 'pointer',
                userSelect: 'none',
                height: '38px',
                boxSizing: 'border-box',
                whiteSpace: 'nowrap',
              }}
            >
              PRINTED{renderSortIcon('printed')}
            </th>
            <th
              onClick={() => handleSort('deleted')}
              style={{
                padding: '6px 6px',
                textAlign: 'center',
                fontWeight: 700,
                width: '11%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                cursor: 'pointer',
                userSelect: 'none',
                height: '38px',
                boxSizing: 'border-box',
                whiteSpace: 'nowrap',
              }}
            >
              DELETED{renderSortIcon('deleted')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((c, idx) => {
            const name = (c.name || c.school_name || c.username || '—').toUpperCase();
            const clientId = c.id || idx;
            const isExpanded = !!expandedRows[clientId];

            // Sub-tables for dropdown rows (Matching actual table names)
            const rawSubTables =
              Array.isArray(c.tables) && c.tables.length > 0
                ? c.tables.filter((t) => t.name !== 'Default Table' && !t.name?.endsWith('- Default Table'))
                : [];

            const matchedTables =
              rawSubTables.length > 0
                ? rawSubTables
                : (allTables || []).filter((t) => {
                    if (!t) return false;
                    if (t.name === 'Default Table' || t.name?.endsWith('- Default Table')) return false;
                    const tClientId = String(
                      t.client_id ||
                        t.clientId ||
                        t.client ||
                        t.organisation_id ||
                        t.organisation ||
                        t.group?.client?.id ||
                        t.group?.client ||
                        ''
                    ).toLowerCase();
                    const cId = String(c.id || '').toLowerCase();
                    const cName = String(c.name || c.school_name || '').toLowerCase();
                    const tClientName = String(t.client_name || t.group?.client?.name || '').toLowerCase();

                    const tName = String(t.name || '').toLowerCase();
                    const cIdStr = String(cId).toLowerCase();

                    return (
                      (cId && tClientId === cIdStr) ||
                      (cName && tClientName === cName) ||
                      (cName && tClientId === cName) ||
                      (cIdStr && cIdStr.length >= 4 && tName.includes(cIdStr))
                    );
                  });

            const subTables = matchedTables.length > 0 ? matchedTables : [];

            // Compute aggregated parent row counts from subTables if available
            let cPending = c.pending || 0;
            let cVerified = c.verified || 0;
            let cApproved = c.approved || 0;
            let cDownloaded = c.downloaded || c.download || 0;
            let cRequest = c.request || c.requested || 0;
            let cPool = c.pool || 0;

            if (subTables.length > 0) {
              let sumP = 0,
                sumV = 0,
                sumA = 0,
                sumD = 0,
                sumReq = 0,
                sumPool = 0;
              subTables.forEach((st) => {
                const sc = getTableCounts(st);
                sumP += sc.pending;
                sumV += sc.verified;
                sumA += sc.approved;
                sumD += sc.download;
                sumReq += sc.request;
                sumPool += sc.pool;
              });
              cPending = Math.max(cPending, sumP);
              cVerified = Math.max(cVerified, sumV);
              cApproved = Math.max(cApproved, sumA);
              cDownloaded = Math.max(cDownloaded, sumD);
              cRequest = Math.max(cRequest, sumReq);
              cPool = Math.max(cPool, sumPool);
            }

            return (
              <React.Fragment key={clientId}>
                <tr
                  onClick={(e) => toggleExpand(clientId, e)}
                  style={{
                    borderBottom: '1px solid #e2e8f0',
                    background: isExpanded ? '#f0f4fe' : idx % 2 === 0 ? '#fff' : '#fafafa',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                >
                  <td
                    style={{
                      padding: '9px 12px',
                      fontWeight: 700,
                      color: '#0f172a',
                      fontSize: '12px',
                      borderRight: '1px solid #e2e8f0',
                      width: '45%',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <button
                        onClick={(e) => toggleExpand(clientId, e)}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: '1px',
                          color: '#64748b',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        {isExpanded ? (
                          <ChevronDown size={14} style={{ color: '#2563eb' }} />
                        ) : (
                          <ChevronRight size={14} />
                        )}
                      </button>
                      <span style={{ color: '#10b981', fontSize: '11px', fontWeight: 700 }}>✓</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onNavigate('idcard-actions', { tableId: subTables[0]?.id || c.id || 1, status: 'pending' });
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          color: '#0f172a',
                          fontWeight: 700,
                          fontSize: '12px',
                          cursor: 'pointer',
                          textAlign: 'left',
                          textDecoration: 'none',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = '#2563eb')}
                        onMouseLeave={(e) => (e.currentTarget.style.color = '#0f172a')}
                      >
                        {name}
                      </button>
                    </div>
                  </td>
                  {/* STATUS COUNT BUTTON BADGES */}
                  <td
                    style={{ padding: '6px 6px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '11%' }}
                  >
                    <StatusChangeBadge
                      count={cPending}
                      statusKey="pending"
                      entityId={`client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBadgeClick(subTables[0] || c, 'pending');
                      }}
                    />
                  </td>
                  <td
                    style={{ padding: '6px 6px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '11%' }}
                  >
                    <StatusChangeBadge
                      count={cVerified}
                      statusKey="verified"
                      entityId={`client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBadgeClick(subTables[0] || c, 'verified');
                      }}
                    />
                  </td>
                  <td
                    style={{ padding: '6px 6px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '11%' }}
                  >
                    <StatusChangeBadge
                      count={cApproved}
                      statusKey="approved"
                      entityId={`client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBadgeClick(subTables[0] || c, 'approved');
                      }}
                    />
                  </td>
                  <td
                    style={{ padding: '6px 6px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '11%' }}
                  >
                    <StatusChangeBadge
                      count={cDownloaded}
                      statusKey="printed"
                      entityId={`client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBadgeClick(subTables[0] || c, 'downloaded');
                      }}
                    />
                  </td>
                  <td style={{ padding: '6px 6px', textAlign: 'center', width: '11%' }}>
                    <StatusChangeBadge
                      count={cPool}
                      statusKey="pool"
                      entityId={`client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        handleBadgeClick(subTables[0] || c, 'pool');
                      }}
                    />
                  </td>
                </tr>

                {/* EXPANDABLE DROPDOWN SUB-ROWS */}
                {isExpanded &&
                  subTables.map((sub, sIdx) => {
                    const sc = getTableCounts(sub);
                    return (
                      <tr
                        key={`${clientId}-sub-${sIdx}`}
                        style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}
                      >
                        <td
                          style={{
                            padding: '9px 12px 9px 36px',
                            color: '#334155',
                            fontSize: '12px',
                            fontWeight: 600,
                            borderRight: '1px solid #e2e8f0',
                            width: '45%',
                          }}
                        >
                          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                            <span style={{ color: '#94a3b8', fontSize: '11px' }}>↳</span>
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                onNavigate('idcard-actions', { tableId: sub.id || 1, status: 'pending' });
                              }}
                              style={{
                                background: 'none',
                                border: 'none',
                                padding: 0,
                                color: '#334155',
                                fontWeight: 600,
                                fontSize: '12px',
                                cursor: 'pointer',
                                textAlign: 'left',
                              }}
                              onMouseEnter={(e) => (e.currentTarget.style.color = '#2563eb')}
                              onMouseLeave={(e) => (e.currentTarget.style.color = '#334155')}
                            >
                              {sub.name}
                            </button>
                          </div>
                        </td>
                        <td
                          style={{
                            padding: '6px 6px',
                            textAlign: 'center',
                            borderRight: '1px solid #e2e8f0',
                            width: '11%',
                          }}
                        >
                          <StatusChangeBadge
                            count={sc.pending}
                            statusKey="pending"
                            entityId={`table_${sub.id}`}
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleBadgeClick(sub, 'pending');
                            }}
                          />
                        </td>
                        <td
                          style={{
                            padding: '6px 6px',
                            textAlign: 'center',
                            borderRight: '1px solid #e2e8f0',
                            width: '11%',
                          }}
                        >
                          <StatusChangeBadge
                            count={sc.verified}
                            statusKey="verified"
                            entityId={`table_${sub.id}`}
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleBadgeClick(sub, 'verified');
                            }}
                          />
                        </td>
                        <td
                          style={{
                            padding: '6px 6px',
                            textAlign: 'center',
                            borderRight: '1px solid #e2e8f0',
                            width: '11%',
                          }}
                        >
                          <StatusChangeBadge
                            count={sc.approved}
                            statusKey="approved"
                            entityId={`table_${sub.id}`}
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleBadgeClick(sub, 'approved');
                            }}
                          />
                        </td>
                        <td
                          style={{
                            padding: '6px 6px',
                            textAlign: 'center',
                            borderRight: '1px solid #e2e8f0',
                            width: '11%',
                          }}
                        >
                          <StatusChangeBadge
                            count={sc.download}
                            statusKey="printed"
                            entityId={`table_${sub.id}`}
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleBadgeClick(sub, 'downloaded');
                            }}
                          />
                        </td>
                        <td style={{ padding: '6px 6px', textAlign: 'center', width: '11%' }}>
                          <StatusChangeBadge
                            count={sc.pool}
                            statusKey="pool"
                            entityId={`table_${sub.id}`}
                            size="small"
                            onClick={(e) => {
                              e.stopPropagation();
                              handleBadgeClick(sub, 'pool');
                            }}
                          />
                        </td>
                      </tr>
                    );
                  })}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Recent Tables Updates Table (For Organisation Prime Manager & Assistant)
───────────────────────────────────────────────────────────────────────── */
function RecentTablesUpdatesTable({ tables = [], onNavigate, search, setSearch, userRole, currentUser }) {
  const isAssistant = String(userRole || currentUser?.role || '').toLowerCase() === 'assistant';

  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('desc');

  const rows = (tables || []).filter(
    (t) => !search || (t.name || '').toLowerCase().includes(search.toLowerCase())
  );

  const handleSort = (key) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir('desc');
    } else if (sortDir === 'desc') {
      setSortDir('asc');
    } else {
      setSortKey(null);
      setSortDir('desc');
    }
  };

  const sortedRows = [...rows].sort((a, b) => {
    const countsA = getTableCounts(a);
    const countsB = getTableCounts(b);
    if (sortKey) {
      const valA = countsA[sortKey] ?? 0;
      const valB = countsB[sortKey] ?? 0;
      return sortDir === 'desc' ? valB - valA : valA - valB;
    }
    return (a.name || '').localeCompare(b.name || '');
  });

  const renderSortIcon = (key) => {
    if (sortKey !== key) return ' ⇕';
    return sortDir === 'desc' ? ' ⬇' : ' ⬆';
  };

  const handleBadgeClick = (table, statusKey) => {
    const targetStatus = statusKey === 'deleted' || statusKey === 'pool' ? 'deleted' : statusKey === 'download' ? 'printed' : statusKey;
    onNavigate('cards', { tableId: table.id, status: targetStatus });
  };

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', position: 'relative' }}>
      <WatermarkLogo />
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontSize: '12px',
          position: 'relative',
          zIndex: 1,
          background: 'transparent',
        }}
      >
        <thead style={{ position: 'sticky', top: 0, background: '#1e293b', color: '#ffffff', zIndex: 2 }}>
          <tr style={{ height: '38px', minHeight: '38px' }}>
            <th
              style={{
                padding: '6px 6px',
                textAlign: 'left',
                fontWeight: 700,
                width: isAssistant ? '40%' : '30%',
                fontSize: '11.5px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #334155',
                height: '38px',
                boxSizing: 'border-box',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', width: '100%', gap: '6px' }}>
                <span style={{ color: '#ffffff', fontWeight: 700 }}>TABLE NAME</span>
                <div style={{ position: 'relative', display: 'flex', alignItems: 'center', width: '190px' }}>
                  <Search size={12} style={{ position: 'absolute', left: '6px', color: '#94a3b8', pointerEvents: 'none' }} />
                  <input
                    type="text"
                    value={search}
                    onChange={(e) => setSearch(e.target.value)}
                    placeholder="Search table..."
                    onClick={(e) => e.stopPropagation()}
                    style={{
                      width: '100%',
                      height: '26px',
                      paddingLeft: '24px',
                      paddingRight: '6px',
                      fontSize: '11px',
                      fontWeight: 500,
                      borderRadius: '4px',
                      border: '1px solid #475569',
                      background: '#0f172a',
                      color: '#ffffff',
                      outline: 'none',
                      boxSizing: 'border-box',
                    }}
                  />
                </div>
              </div>
            </th>
            <th onClick={() => handleSort('pending')} style={{ padding: '6px 6px', textAlign: 'center', fontWeight: 700, width: isAssistant ? '20%' : '10%', fontSize: '11px', letterSpacing: '0.04em', borderRight: '1px solid #334155', cursor: 'pointer', userSelect: 'none', height: '38px', boxSizing: 'border-box', whiteSpace: 'nowrap' }}>
              PENDING{renderSortIcon('pending')}
            </th>
            <th onClick={() => handleSort('verified')} style={{ padding: '6px 6px', textAlign: 'center', fontWeight: 700, width: isAssistant ? '20%' : '10%', fontSize: '11px', letterSpacing: '0.04em', borderRight: '1px solid #334155', cursor: 'pointer', userSelect: 'none', height: '38px', boxSizing: 'border-box', whiteSpace: 'nowrap' }}>
              VERIFIED{renderSortIcon('verified')}
            </th>
            {!isAssistant && (
              <>
                <th onClick={() => handleSort('approved')} style={{ padding: '6px 6px', textAlign: 'center', fontWeight: 700, width: '10%', fontSize: '11px', letterSpacing: '0.04em', borderRight: '1px solid #334155', cursor: 'pointer', userSelect: 'none', height: '38px', boxSizing: 'border-box', whiteSpace: 'nowrap' }}>
                  APPROVED{renderSortIcon('approved')}
                </th>
                <th onClick={() => handleSort('download')} style={{ padding: '6px 6px', textAlign: 'center', fontWeight: 700, width: '10%', fontSize: '11px', letterSpacing: '0.04em', borderRight: '1px solid #334155', cursor: 'pointer', userSelect: 'none', height: '38px', boxSizing: 'border-box', whiteSpace: 'nowrap' }}>
                  PRINTED{renderSortIcon('download')}
                </th>
                <th onClick={() => handleSort('request')} style={{ padding: '6px 6px', textAlign: 'center', fontWeight: 700, width: '10%', fontSize: '11px', letterSpacing: '0.04em', borderRight: '1px solid #334155', cursor: 'pointer', userSelect: 'none', height: '38px', boxSizing: 'border-box', whiteSpace: 'nowrap' }}>
                  REQUESTED{renderSortIcon('request')}
                </th>
              </>
            )}
            <th onClick={() => handleSort('pool')} style={{ padding: '6px 6px', textAlign: 'center', fontWeight: 700, width: isAssistant ? '20%' : '10%', fontSize: '11px', letterSpacing: '0.04em', cursor: 'pointer', userSelect: 'none', height: '38px', boxSizing: 'border-box', whiteSpace: 'nowrap' }}>
              DELETED{renderSortIcon('pool')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.length === 0 ? (
            <tr>
              <td colSpan={isAssistant ? 4 : 7} style={{ textAlign: 'center', padding: '36px', color: '#64748b' }}>
                No tables found in this organisation.
              </td>
            </tr>
          ) : (
            sortedRows.map((t, idx) => {
              const counts = getTableCounts(t);
              return (
                <tr
                  key={t.id || idx}
                  onClick={() => onNavigate('cards', { tableId: t.id, status: 'pending' })}
                  style={{
                    borderBottom: '1px solid #e2e8f0',
                    background: idx % 2 === 0 ? '#fff' : '#fafafa',
                    cursor: 'pointer',
                    transition: 'background 0.12s',
                  }}
                  onMouseEnter={(e) => (e.currentTarget.style.background = '#eff6ff')}
                  onMouseLeave={(e) => (e.currentTarget.style.background = idx % 2 === 0 ? '#fff' : '#fafafa')}
                >
                  <td style={{ padding: '8px 12px', borderRight: '1px solid #e2e8f0', fontWeight: 600, color: '#1e293b' }}>
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                      <Layers size={14} style={{ color: '#2563eb' }} />
                      <span style={{ fontSize: '12px', fontWeight: 700 }}>{t.name}</span>
                    </div>
                  </td>
                  <td style={{ padding: '6px', textAlign: 'center', borderRight: '1px solid #e2e8f0' }}>
                    <StatusChangeBadge count={counts.pending} statusKey="pending" entityId={`tbl_${t.id}`} onClick={(e) => { e.stopPropagation(); handleBadgeClick(t, 'pending'); }} />
                  </td>
                  <td style={{ padding: '6px', textAlign: 'center', borderRight: '1px solid #e2e8f0' }}>
                    <StatusChangeBadge count={counts.verified} statusKey="verified" entityId={`tbl_${t.id}`} onClick={(e) => { e.stopPropagation(); handleBadgeClick(t, 'verified'); }} />
                  </td>
                  {!isAssistant && (
                    <>
                      <td style={{ padding: '6px', textAlign: 'center', borderRight: '1px solid #e2e8f0' }}>
                        <StatusChangeBadge count={counts.approved} statusKey="approved" entityId={`tbl_${t.id}`} onClick={(e) => { e.stopPropagation(); handleBadgeClick(t, 'approved'); }} />
                      </td>
                      <td style={{ padding: '6px', textAlign: 'center', borderRight: '1px solid #e2e8f0' }}>
                        <StatusChangeBadge count={counts.download} statusKey="downloaded" entityId={`tbl_${t.id}`} onClick={(e) => { e.stopPropagation(); handleBadgeClick(t, 'download'); }} />
                      </td>
                      <td style={{ padding: '6px', textAlign: 'center', borderRight: '1px solid #e2e8f0' }}>
                        <StatusChangeBadge count={counts.request} statusKey="request" entityId={`tbl_${t.id}`} onClick={(e) => { e.stopPropagation(); handleBadgeClick(t, 'request'); }} />
                      </td>
                    </>
                  )}
                  <td style={{ padding: '6px', textAlign: 'center' }}>
                    <StatusChangeBadge count={counts.pool} statusKey="pool" entityId={`tbl_${t.id}`} onClick={(e) => { e.stopPropagation(); handleBadgeClick(t, 'deleted'); }} />
                  </td>
                </tr>
              );
            })
          )}
        </tbody>
      </table>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Recent Reprints Table Sub-Component (Matches original recent-reprints.html)
───────────────────────────────────────────────────────────────────────── */
function RecentReprintsTable({ clients, onNavigate, search }) {
  const [expandedRows, setExpandedRows] = useState({});
  const [sortKey, setSortKey] = useState(null);
  const [sortDir, setSortDir] = useState('desc');

  const displayList = clients || [];
  const rows = displayList.filter(
    (c) => !search || (c.name || c.school_name || '').toLowerCase().includes(search.toLowerCase())
  );

  const handleSort = (key) => {
    if (sortKey !== key) {
      setSortKey(key);
      setSortDir('desc');
    } else if (sortDir === 'desc') {
      setSortDir('asc');
    } else {
      setSortKey(null);
      setSortDir('desc');
    }
  };

  const sortedRows = [...rows].sort((a, b) => {
    if (!sortKey) return 0;
    const valA = a[sortKey] ?? 0;
    const valB = b[sortKey] ?? 0;
    if (typeof valA === 'string') {
      return sortDir === 'desc' ? valB.localeCompare(valA) : valA.localeCompare(valB);
    }
    return sortDir === 'desc' ? valB - valA : valA - valB;
  });

  const toggleExpand = (id, e) => {
    e.stopPropagation();
    setExpandedRows((prev) => ({ ...prev, [id]: !prev[id] }));
  };

  const renderSortIcon = (key) => {
    if (sortKey !== key) return ' ⇕';
    return sortDir === 'desc' ? ' ⬇' : ' ⬆';
  };

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto' }}>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
        <thead style={{ position: 'sticky', top: 0, background: '#2d3748', color: '#fff', zIndex: 2 }}>
          <tr>
            <th
              style={{
                padding: '7px 10px',
                textAlign: 'left',
                fontWeight: 700,
                width: '46%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #4a5568',
              }}
            >
              CLIENT
            </th>
            <th
              onClick={() => handleSort('reprint')}
              style={{
                padding: '7px 8px',
                textAlign: 'center',
                fontWeight: 700,
                width: '18%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #4a5568',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              REPRINTING LIST{renderSortIcon('reprint')}
            </th>
            <th
              onClick={() => handleSort('reprint_pending')}
              style={{
                padding: '7px 8px',
                textAlign: 'center',
                fontWeight: 700,
                width: '18%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                borderRight: '1px solid #4a5568',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              REQUESTED LIST{renderSortIcon('reprint_pending')}
            </th>
            <th
              onClick={() => handleSort('reprint_confirmed')}
              style={{
                padding: '7px 8px',
                textAlign: 'center',
                fontWeight: 700,
                width: '18%',
                fontSize: '11px',
                letterSpacing: '0.04em',
                cursor: 'pointer',
                userSelect: 'none',
              }}
            >
              CONFIRMED LIST{renderSortIcon('reprint_confirmed')}
            </th>
          </tr>
        </thead>
        <tbody>
          {sortedRows.map((c, idx) => {
            const name = (c.name || c.school_name || c.username || '—').toUpperCase();
            const clientId = c.id || idx;
            const isExpanded = !!expandedRows[clientId];

            const reprintingCount = c.reprint ?? c.reprinting ?? Math.floor((c.pending || 2) * 0.3);
            const requestCount = c.reprint_pending ?? c.request ?? Math.floor((c.pending || 4) * 0.5);
            const confirmedCount = c.reprint_confirmed ?? c.confirmed ?? Math.floor((c.verified || 2) * 0.4);

            const subTables = c.tables || [
              {
                name: 'Class 1st to 5th',
                reprinting: Math.floor(reprintingCount * 0.6),
                requestList: Math.floor(requestCount * 0.6),
                confirmed: Math.floor(confirmedCount * 0.6),
              },
              {
                name: 'Class 6th to 10th',
                reprinting: Math.ceil(reprintingCount * 0.4),
                requestList: Math.ceil(requestCount * 0.4),
                confirmed: Math.ceil(confirmedCount * 0.4),
              },
            ];

            return (
              <React.Fragment key={clientId}>
                <tr
                  onClick={(e) => toggleExpand(clientId, e)}
                  style={{
                    borderBottom: '1px solid #e2e8f0',
                    background: isExpanded ? '#f0f4fe' : idx % 2 === 0 ? '#fff' : '#fafafa',
                    cursor: 'pointer',
                    transition: 'background 0.15s',
                  }}
                >
                  <td
                    style={{
                      padding: '6px 10px',
                      fontWeight: 600,
                      color: '#334155',
                      fontSize: '11px',
                      borderRight: '1px solid #e2e8f0',
                      width: '46%',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      <button
                        onClick={(e) => toggleExpand(clientId, e)}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: '1px',
                          color: '#64748b',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                        }}
                      >
                        {isExpanded ? (
                          <ChevronDown size={13} style={{ color: '#2563eb' }} />
                        ) : (
                          <ChevronRight size={13} />
                        )}
                      </button>
                      <span style={{ color: '#10b981', fontSize: '10px' }}>✓</span>
                      <button
                        onClick={(e) => {
                          e.stopPropagation();
                          onNavigate('reprints', { client: c.id });
                        }}
                        style={{
                          background: 'none',
                          border: 'none',
                          padding: 0,
                          color: '#334155',
                          fontWeight: 600,
                          fontSize: '11px',
                          cursor: 'pointer',
                          textAlign: 'left',
                          textDecoration: 'none',
                        }}
                        onMouseEnter={(e) => (e.currentTarget.style.color = '#2563eb')}
                        onMouseLeave={(e) => (e.currentTarget.style.color = '#334155')}
                      >
                        {name}
                      </button>
                    </div>
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '18%' }}>
                    <StatusChangeBadge
                      count={reprintingCount}
                      statusKey="reprint"
                      entityId={`reprint_client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigate('reprints', { client: c.id, tab: 'reprinting' });
                      }}
                    />
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '18%' }}>
                    <StatusChangeBadge
                      count={requestCount}
                      statusKey="request"
                      entityId={`reprint_client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigate('reprints', { client: c.id, tab: 'pending' });
                      }}
                    />
                  </td>
                  <td style={{ padding: '6px 8px', textAlign: 'center', width: '18%' }}>
                    <StatusChangeBadge
                      count={confirmedCount}
                      statusKey="confirmed"
                      entityId={`reprint_client_${clientId}`}
                      onClick={(e) => {
                        e.stopPropagation();
                        onNavigate('reprints', { client: c.id, tab: 'confirmed' });
                      }}
                    />
                  </td>
                </tr>

                {/* EXPANDABLE DROPDOWN SUB-ROWS */}
                {isExpanded &&
                  subTables.map((sub, sIdx) => (
                    <tr
                      key={`${clientId}-sub-${sIdx}`}
                      style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0' }}
                    >
                      <td
                        style={{
                          padding: '4px 10px 4px 34px',
                          color: '#475569',
                          fontSize: '11px',
                          fontWeight: 500,
                          borderRight: '1px solid #e2e8f0',
                          width: '46%',
                        }}
                      >
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ color: '#94a3b8', fontSize: '10px' }}>↳</span>
                          <span>{sub.name}</span>
                        </div>
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '18%' }}>
                        <StatusChangeBadge
                          count={sub.reprinting ?? Math.floor(reprintingCount * 0.5)}
                          statusKey="reprint"
                          entityId={`reprint_sub_${clientId}_${sIdx}`}
                          size="small"
                        />
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'center', borderRight: '1px solid #e2e8f0', width: '18%' }}>
                        <StatusChangeBadge
                          count={sub.requestList ?? Math.floor(requestCount * 0.5)}
                          statusKey="request"
                          entityId={`reprint_sub_${clientId}_${sIdx}`}
                          size="small"
                        />
                      </td>
                      <td style={{ padding: '3px 8px', textAlign: 'center', width: '18%' }}>
                        <StatusChangeBadge
                          count={sub.confirmed ?? Math.floor(confirmedCount * 0.5)}
                          statusKey="confirmed"
                          entityId={`reprint_sub_${clientId}_${sIdx}`}
                          size="small"
                        />
                      </td>
                    </tr>
                  ))}
              </React.Fragment>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Recent Activity Updates List Sub-Component (Matches original recent-activity.html)
───────────────────────────────────────────────────────────────────────── */
function RecentActivityUpdatesTable({ activities = [], search, loading }) {
  const items = (activities || []).filter((a) => {
    const userStr = a.user || a.username || a.performed_by || '';
    const actStr = a.action || a.description || a.message || a.details || '';
    return (
      !search ||
      userStr.toLowerCase().includes(search.toLowerCase()) ||
      actStr.toLowerCase().includes(search.toLowerCase())
    );
  });

  if (loading && items.length === 0) {
    return (
      <div style={{ flex: 1, padding: '20px', textAlign: 'center', color: '#64748b', fontSize: '12px' }}>
        Loading recent activities...
      </div>
    );
  }

  if (items.length === 0) {
    return (
      <div style={{ flex: 1, padding: '30px', textAlign: 'center', color: '#94a3b8', fontSize: '12px' }}>
        No recent activities recorded.
      </div>
    );
  }

  return (
    <div style={{ flex: 1, minHeight: 0, overflowY: 'auto', padding: '10px 12px', background: '#fff' }}>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
        {items.map((a, idx) => {
          const user = a.user || a.username || a.performed_by || 'System';
          const actionText = a.action || a.description || a.message || a.details || 'Activity log';
          const timeText = a.created_at || a.timestamp || a.date || '';

          const act = (actionText || '').toLowerCase();
          let iconBg = '#8b5cf6';
          let IconComp = CreditCard;
          if (act.includes('approve')) {
            iconBg = '#0050d2';
            IconComp = ThumbsUp;
          } else if (act.includes('verify')) {
            iconBg = '#10b981';
            IconComp = CheckCircle2;
          } else if (act.includes('download')) {
            iconBg = '#6b7280';
            IconComp = Download;
          } else if (act.includes('create') || act.includes('add') || act.includes('register')) {
            iconBg = '#0ea5e9';
            IconComp = Plus;
          } else if (act.includes('reprint')) {
            iconBg = '#f59e0b';
            IconComp = RefreshCw;
          }

          return (
            <div
              key={a.id || idx}
              style={{
                display: 'flex',
                alignItems: 'flex-start',
                gap: '10px',
                padding: '8px 12px',
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '4px',
                transition: 'all 0.15s',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#eff6ff';
                e.currentTarget.style.borderColor = '#bfdbfe';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#f8fafc';
                e.currentTarget.style.borderColor = '#e2e8f0';
              }}
            >
              <div
                style={{
                  width: '28px',
                  height: '28px',
                  borderRadius: '4px',
                  background: iconBg,
                  color: '#fff',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                  marginTop: '2px',
                }}
              >
                <IconComp size={13} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ fontSize: '12px', color: '#1e293b', fontWeight: 500, lineHeight: 1.35 }}>
                  <strong style={{ color: '#0f172a', fontWeight: 700 }}>{user}</strong> {actionText}
                </div>
                {timeText && <div style={{ fontSize: '11px', color: '#94a3b8', marginTop: '2px' }}>{timeText}</div>}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Right Side Stacked Panels — 3 EQUAL HEIGHT SECTION BOXES (33.33% EACH)
───────────────────────────────────────────────────────────────────────── */
function RightSidePanels({
  stats,
  clients = [],
  reprintClients = [],
  activities = [],
  allTables = [],
  onNavigate,
  onOpenActionDrawer,
  activeSection,
  setActiveSection,
  currentUser,
  userRole = 'super_admin',
}) {
  const role = String(currentUser?.role || userRole || '').toLowerCase();
  const isAdmin = role === 'prime_admin' || role === 'super_admin' || role === 'pro_user' || role === 'admin';
  const isOrg = role === 'prime_manager' || role === 'super_manager' || role === 'manager' || role === 'client' || role === 'guest_prime_manager';

  const approvedCount = (clients || []).reduce((acc, c) => acc + (c.approved || 0), 0) || (stats?.approved ?? stats?.approved_cards ?? 0);

  const requestedCount = (reprintClients.length ? reprintClients : clients || []).reduce((acc, c) => acc + (c.requested || c.request || c.reprint_pending || 0), 0) || (stats?.requested ?? stats?.reprint_count ?? 0);
  const updatesCount = activities.length || (stats?.activity_count ?? 0);

  // Dynamic quick actions per role
  let quickActions = [];
  if (isAdmin) {
    quickActions = [
      { label: 'Add New Organisation', action: () => onOpenActionDrawer('add-client'), Icon: Plus },
      { label: 'Add New Operator', action: () => onOpenActionDrawer('add-operator'), Icon: Shield },
      { label: 'Add New Assistant', action: () => onOpenActionDrawer('add-assistant'), Icon: Users },
    ];
  } else if (isOrg) {
    quickActions = [
      { label: 'Manage Tables', action: () => onNavigate('cards'), Icon: CreditCard },
      { label: 'Add New Assistant', action: () => onOpenActionDrawer('add-assistant'), Icon: Plus },
    ];
  } else {
    quickActions = [
      { label: 'Manage Tables', action: () => onNavigate('cards'), Icon: CreditCard },
    ];
  }

  // Dynamic overview boxes per role
  let overviewTitle = 'Users Overview';
  let overviewBoxes = [];
  if (isAdmin) {
    overviewTitle = 'Users Overview';
    overviewBoxes = [
      {
        label: 'Organisations',
        count: stats?.total_organizations ?? stats?.total_clients ?? (clients?.length || 0),
        action: () => onNavigate('organisations'),
        Icon: Building,
        color: '#0050d2',
        bg: '#eff6ff',
      },
      {
        label: 'Operators',
        count: stats?.total_operators ?? stats?.guest_users ?? 0,
        action: () => onNavigate('operators'),
        Icon: Shield,
        color: '#7c3aed',
        bg: '#f5f3ff',
      },
      {
        label: 'Assistants',
        count: stats?.total_assistants ?? stats?.client_staff_count ?? 0,
        action: () => onNavigate('assistants'),
        Icon: Users,
        color: '#d97706',
        bg: '#fff7ed',
      },
      {
        label: 'Photographers',
        count: stats?.total_photographers ?? 0,
        action: () => onNavigate('photographers'),
        Icon: User,
        color: '#059669',
        bg: '#ecfdf5',
      },
    ];
  } else if (isOrg) {
    overviewTitle = 'Organisation Overview';
    overviewBoxes = [
      {
        label: 'Tables',
        count: allTables.length || (clients[0]?.tables?.length || 0),
        action: () => onNavigate('cards'),
        Icon: Layers,
        color: '#0050d2',
        bg: '#eff6ff',
      },
      {
        label: 'Assistants',
        count: stats?.total_assistants ?? stats?.client_staff_count ?? 1,
        action: () => onNavigate('assistants'),
        Icon: Users,
        color: '#d97706',
        bg: '#fff7ed',
      },
      {
        label: 'Total Cards',
        count: stats?.total_id_cards ?? stats?.total ?? 0,
        action: () => onNavigate('cards'),
        Icon: CreditCard,
        color: '#059669',
        bg: '#ecfdf5',
      },
      {
        label: 'Pending',
        count: stats?.pending_cards ?? stats?.pending ?? 0,
        action: () => onNavigate('cards'),
        Icon: Clock,
        color: '#f59e0b',
        bg: '#fffbeb',
      },
    ];
  } else {
    overviewTitle = 'My Overview';
    overviewBoxes = [
      {
        label: 'Tables',
        count: allTables.length || (clients[0]?.tables?.length || 0),
        action: () => onNavigate('cards'),
        Icon: Layers,
        color: '#0050d2',
        bg: '#eff6ff',
      },
      {
        label: 'Total Cards',
        count: stats?.total_id_cards ?? stats?.total ?? 0,
        action: () => onNavigate('cards'),
        Icon: CreditCard,
        color: '#059669',
        bg: '#ecfdf5',
      },
      {
        label: 'Pending',
        count: stats?.pending_cards ?? stats?.pending ?? 0,
        action: () => onNavigate('cards'),
        Icon: Clock,
        color: '#f59e0b',
        bg: '#fffbeb',
      },
      {
        label: 'Verified',
        count: stats?.verified_cards ?? stats?.verified ?? 0,
        action: () => onNavigate('cards'),
        Icon: CheckCircle2,
        color: '#10b981',
        bg: '#ecfdf5',
      },
    ];
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', background: '#fff', height: '100%', overflow: 'hidden' }}>
      {/* 1. Dashboard Sections — 1/3 Equal Height Section Box */}
      <div
        style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, borderBottom: '1px solid #e2e8f0' }}
      >
        <div
          style={{
            background: '#1e293b',
            color: '#ffffff',
            height: '38px',
            minHeight: '38px',
            padding: '6px 6px',
            fontSize: '12px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            boxSizing: 'border-box',
            borderBottom: '1px solid #334155',
            flexShrink: 0,
          }}
        >
          <Layers size={13} /> Dashboard Sections
        </div>
        <div style={{ flex: 1, padding: '6px 6px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {[
            {
              id: 'clients',
              label: 'Recent Approved',
              count: approvedCount,
              Icon: ThumbsUp,
            },
            {
              id: 'reprints',
              label: 'Recent Requested',
              count: requestedCount,
              Icon: Send,
            },
            { id: 'updates', label: 'Recent Updates', count: updatesCount, Icon: Clock },
          ].map(({ id, label, count, Icon }) => {
            const isActive = activeSection === id;
            return (
              <button
                key={id}
                onClick={() => setActiveSection(id)}
                style={{
                  width: '100%',
                  padding: '6px 6px',
                  height: '32px',
                  boxSizing: 'border-box',
                  background: isActive ? '#eff6ff' : '#ffffff',
                  border: isActive ? '1px solid #93c5fd' : '1px solid #e2e8f0',
                  borderLeft: isActive ? '3px solid #2563eb' : '1px solid #e2e8f0',
                  borderRadius: '4px',
                  color: isActive ? '#1d4ed8' : '#475569',
                  fontSize: '12px',
                  fontWeight: isActive ? 700 : 500,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  cursor: 'pointer',
                  fontFamily: 'var(--font-family)',
                  transition: 'all 0.15s',
                  boxShadow: isActive ? '0 1px 3px rgba(37,99,235,0.1)' : 'none',
                }}
                onMouseEnter={(e) => {
                  if (!isActive) e.currentTarget.style.background = '#f8fafc';
                }}
                onMouseLeave={(e) => {
                  if (!isActive) e.currentTarget.style.background = '#ffffff';
                }}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                  <div
                    style={{
                      width: '20px',
                      height: '20px',
                      borderRadius: '4px',
                      background: isActive ? '#dbeafe' : '#eff6ff',
                      color: isActive ? '#1d4ed8' : '#3b82f6',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                    }}
                  >
                    <Icon size={12} />
                  </div>
                  <span>{label}</span>
                </div>
                <span
                  style={{
                    fontWeight: 700,
                    color: isActive ? '#1d4ed8' : '#0f172a',
                    background: isActive ? '#dbeafe' : '#f1f5f9',
                    padding: '1px 6px',
                    borderRadius: '3px',
                    fontSize: '11px',
                  }}
                >
                  {count}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 2. Quick Actions — 1/3 Equal Height Section Box */}
      <div
        style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0, borderBottom: '1px solid #e2e8f0' }}
      >
        <div
          style={{
            background: '#1e293b',
            color: '#ffffff',
            height: '38px',
            minHeight: '38px',
            padding: '6px 6px',
            fontSize: '12px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            boxSizing: 'border-box',
            borderBottom: '1px solid #334155',
            flexShrink: 0,
          }}
        >
          <Plus size={13} /> Quick Actions
        </div>
        <div style={{ flex: 1, padding: '6px 6px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
          {quickActions.map(({ label, action, Icon }) => (
            <button
              key={label}
              onClick={action}
              style={{
                width: '100%',
                padding: '6px 6px',
                height: '32px',
                boxSizing: 'border-box',
                background: '#eff6ff',
                border: '1px solid #bfdbfe',
                borderRadius: '4px',
                color: '#1d4ed8',
                fontSize: '12px',
                fontWeight: 600,
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                cursor: 'pointer',
                fontFamily: 'var(--font-family)',
                transition: 'background 0.15s',
              }}
              onMouseEnter={(e) => (e.currentTarget.style.background = '#dbeafe')}
              onMouseLeave={(e) => (e.currentTarget.style.background = '#eff6ff')}
            >
              <Icon size={13} /> <span>{label}</span>
            </button>
          ))}
        </div>
      </div>

      {/* 3. Overview — 1/3 Equal Height Section Box */}
      <div style={{ flex: 1, display: 'flex', flexDirection: 'column', minHeight: 0 }}>
        <div
          style={{
            background: '#1e293b',
            color: '#ffffff',
            height: '38px',
            minHeight: '38px',
            padding: '6px 6px',
            fontSize: '12px',
            fontWeight: 700,
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
            boxSizing: 'border-box',
            borderBottom: '1px solid #334155',
            flexShrink: 0,
          }}
        >
          <Shield size={13} /> {overviewTitle}
        </div>

        <div
          style={{
            flex: 1,
            padding: '6px 6px',
            display: 'grid',
            gridTemplateColumns: 'repeat(2, 1fr)',
            gap: '6px',
            alignContent: 'start',
          }}
        >
          {overviewBoxes.map(({ label, count, action, Icon, color, bg }) => (
            <button
              key={label}
              onClick={action}
              style={{
                background: '#f8fafc',
                border: '1px solid #e2e8f0',
                borderRadius: '4px',
                padding: '6px 6px',
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                justifyContent: 'center',
                cursor: 'pointer',
                fontFamily: 'var(--font-family)',
                transition: 'all 0.15s ease-in-out',
                textAlign: 'center',
                boxSizing: 'border-box',
              }}
              onMouseEnter={(e) => {
                e.currentTarget.style.background = '#ffffff';
                e.currentTarget.style.borderColor = color;
                e.currentTarget.style.boxShadow = '0 2px 8px rgba(0,0,0,0.06)';
              }}
              onMouseLeave={(e) => {
                e.currentTarget.style.background = '#f8fafc';
                e.currentTarget.style.borderColor = '#e2e8f0';
                e.currentTarget.style.boxShadow = 'none';
              }}
            >
              <div
                style={{
                  width: '24px',
                  height: '24px',
                  borderRadius: '50%',
                  background: bg,
                  color: color,
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  marginBottom: '2px',
                }}
              >
                <Icon size={12} />
              </div>
              <span style={{ fontSize: '14px', fontWeight: 700, color: '#0f172a', lineHeight: 1.1 }}>{count}</span>
              <span
                style={{ fontSize: '10.5px', fontWeight: 600, color: '#64748b', marginTop: '2px', whiteSpace: 'nowrap' }}
              >
                {label}
              </span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

/* ─────────────────────────────────────────────────────────────────────────
   Main DashboardView Assembly
───────────────────────────────────────────────────────────────────────── */
export default function DashboardView({ onNavigate, currentUser, onOpenActionDrawer, userRole = 'super_admin' }) {
  const [stats, setStats] = useState(null);
  const [clients, setClients] = useState([]);
  const [allTables, setAllTables] = useState([]);
  const [reprintClients, setReprintClients] = useState([]);
  const [activities, setActivities] = useState([]);
  const [loading, setLoading] = useState(false);
  const [activeSection, setActiveSection] = useState('clients'); // 'clients' | 'reprints' | 'updates'
  const [search, setSearch] = useState('');

  const load = useCallback(
    async (isInitial = false) => {
      if (isInitial) {
        setLoading(true);
      }
      try {
        let loadedTables = [];
        try {
          const schemaRes = await schemaApi.getSchemas();
          loadedTables = schemaRes.tables || schemaRes.results || (Array.isArray(schemaRes) ? schemaRes : []);
        } catch (_) {}
        setAllTables(loadedTables);

        try {
          const statsData = await dashboardApi.getStats();
          const apiStats = statsData.stats || statsData;
          if (apiStats) {
            setStats(apiStats);
          }
        } catch (_) {}

        let loadedClients = [];
        try {
          const clientData = await dashboardApi.getRecentClientUpdates();
          if (clientData) {
            loadedClients = clientData.clients || clientData.results || (Array.isArray(clientData) ? clientData : []);
          }
        } catch (_) {}
        setClients(loadedClients);

        try {
          const reprintData = await dashboardApi.getReprintOverview();
          if (reprintData) setReprintClients(reprintData.clients || reprintData.results || reprintData || []);
        } catch (_) {}

        try {
          const actData = await dashboardApi.getRecentActivity(50);
          if (actData) setActivities(actData.activities || actData.results || actData || []);
        } catch (_) {}
      } catch (err) {
        console.error('Dashboard load error:', err);
      } finally {
        setLoading(false);
      }
    },
    []
  );

  useEffect(() => {
    if (window.location.pathname.includes('/login')) return;

    load(true);
    window.__reloadDashboard = () => load(false);
    const interval = setInterval(() => {
      if (!window.location.pathname.includes('/login')) {
        load(false);
      }
    }, 30000);
    return () => {
      clearInterval(interval);
      if (window.__reloadDashboard === load) delete window.__reloadDashboard;
    };
  }, [load]);

  const currentRole = String(currentUser?.role || userRole || '').toLowerCase();
  const isOrg = currentRole === 'prime_manager' || currentRole === 'super_manager' || currentRole === 'manager' || currentRole === 'client' || currentRole === 'guest_prime_manager';
  const isAssistant = currentRole === 'assistant' || currentRole === 'client_staff';

  const getSectionTitle = () => {
    if (activeSection === 'reprints')
      return {
        title: 'Recent Reprints Queue',
        Icon: RefreshCw,
        badgeText: `Pending Reprints: ${stats?.reprint_count ?? 0}`,
        badgeBg: '#ffedd5',
        badgeColor: '#c2410c',
      };
    if (activeSection === 'updates')
      return {
        title: 'Recent Activity & Updates',
        Icon: Clock,
        badgeText: `Recent Events: ${stats?.activity_count ?? 0}`,
        badgeBg: '#dbeafe',
        badgeColor: '#1d4ed8',
      };
    if (isOrg || isAssistant) {
      return {
        title: 'Organisation Tables',
        Icon: Layers,
        badgeText: `Total Tables: ${allTables?.length || 0}`,
        badgeBg: '#dbeafe',
        badgeColor: '#1d4ed8',
      };
    }
    return {
      title: 'Recent Organisations',
      Icon: Building,
      badgeText: `Live Working Users: ${stats?.live_users_count ?? 0}`,
      badgeBg: '#d1fae5',
      badgeColor: '#047857',
    };
  };

  return (
    <div

      style={{ display: 'flex', flexDirection: 'column', height: '100%', overflow: 'hidden', background: '#f8fafc' }}
    >
      {/* 1. 7 Stat Cards Row with Daily Growth Indicators */}
      <StatCardsRow stats={stats} clients={clients} loading={loading} onNavigate={onNavigate} userRole={currentUser?.role || userRole} />

      {/* 3. Main Dashboard Body: Dynamic Left Section + Right Stacked Panels */}
      <div
        style={{
          flex: 1,
          display: 'grid',
          gridTemplateColumns: '1fr 260px',
          gap: 0,
          minHeight: 0,
          overflow: 'hidden',
        }}
      >
        {/* Left Container */}
        <div
          style={{
            background: '#fff',
            borderRight: '1px solid #cbd5e1',
            display: 'flex',
            flexDirection: 'column',
            height: '100%',
            overflow: 'hidden',
          }}
        >
          {/* Dynamic Table Body */}
          {activeSection === 'clients' && (
            (isOrg || isAssistant) ? (
              <RecentTablesUpdatesTable
                tables={allTables}
                loading={loading}
                onNavigate={onNavigate}
                search={search}
                setSearch={setSearch}
                userRole={currentUser?.role || userRole}
                currentUser={currentUser}
              />
            ) : (
              <RecentClientUpdatesTable
                clients={clients}
                allTables={allTables}
                loading={loading}
                onNavigate={onNavigate}
                search={search}
                setSearch={setSearch}
              />
            )
          )}
          {activeSection === 'reprints' && (
            <RecentReprintsTable
              clients={reprintClients.length ? reprintClients : clients}
              onNavigate={onNavigate}
              search={search}
            />
          )}

          {activeSection === 'updates' && (
            <RecentActivityUpdatesTable activities={activities} search={search} loading={loading} />
          )}
        </div>

        {/* Right Side Panels */}
        <RightSidePanels
          stats={stats}
          clients={clients}
          reprintClients={reprintClients}
          activities={activities}
          allTables={allTables}
          onNavigate={onNavigate}
          onOpenActionDrawer={onOpenActionDrawer}
          activeSection={activeSection}
          setActiveSection={setActiveSection}
          currentUser={currentUser}
          userRole={currentUser?.role || userRole}
        />
      </div>
    </div>
  );
}
