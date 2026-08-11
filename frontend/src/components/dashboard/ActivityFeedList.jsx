import React, { useState, useEffect, useCallback } from 'react';
import { RefreshCw, Loader2, AlertCircle } from 'lucide-react';
import { dashboardApi } from '../../services/api';

function timeAgo(dateStr) {
  if (!dateStr) return '';
  const diff = Math.floor((Date.now() - new Date(dateStr).getTime()) / 1000);
  if (diff < 60) return `${diff}s ago`;
  if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
  if (diff < 86400) return `${Math.floor(diff / 3600)}h ago`;
  return `${Math.floor(diff / 86400)}d ago`;
}

const ACTION_COLORS = {
  upload: { bg: '#eff6ff', color: '#3b82f6' },
  download: { bg: '#f0fdf4', color: '#22c55e' },
  delete: { bg: '#fef2f2', color: '#ef4444' },
  update: { bg: '#fef3c7', color: '#f59e0b' },
  login: { bg: '#ede9fe', color: '#8b5cf6' },
  create: { bg: '#d1fae5', color: '#059669' },
  approve: { bg: '#dbeafe', color: '#2563eb' },
  default: { bg: '#f9fafb', color: '#6b7280' },
};

function getActionColor(action) {
  const a = (action || '').toLowerCase();
  for (const [key, val] of Object.entries(ACTION_COLORS)) {
    if (a.includes(key)) return val;
  }
  return ACTION_COLORS.default;
}

export default function ActivityFeedList() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await dashboardApi.getRecentActivity();
      const list = data.activities || data.results || data || [];
      setItems(list.slice(0, 40));
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 20_000);
    return () => clearInterval(t);
  }, [load]);

  return (
    <div className="data-card" style={{ borderRadius: 0 }}>
      {/* Header */}
      <div className="card-header-row">
        <h3>Recent Activity</h3>
        <button
          onClick={load}
          className="btn btn-outline btn-sm"
          style={{ display: 'flex', alignItems: 'center', gap: '4px' }}
        >
          {loading ? <Loader2 size={12} style={{ animation: 'spin 1s linear infinite' }} /> : <RefreshCw size={12} />}
          Refresh
        </button>
      </div>

      {/* Error */}
      {error && (
        <div
          style={{
            padding: '8px 14px',
            background: '#fef2f2',
            borderBottom: '1px solid #fca5a5',
            fontSize: '12px',
            color: '#dc2626',
            display: 'flex',
            alignItems: 'center',
            gap: '6px',
          }}
        >
          <AlertCircle size={12} /> Could not load activity feed.
        </div>
      )}

      {/* Activity list */}
      <div className="activity-list" style={{ padding: '0 14px', maxHeight: '340px', overflowY: 'auto' }}>
        {loading && items.length === 0 ? (
          Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="activity-item">
              <div
                style={{
                  width: '30px',
                  height: '30px',
                  borderRadius: '6px',
                  background: '#f0f0f0',
                  animation: 'shimmer 1.5s infinite',
                  flexShrink: 0,
                }}
              />
              <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '5px' }}>
                <div
                  style={{
                    width: '60%',
                    height: '12px',
                    borderRadius: '2px',
                    background: '#f0f0f0',
                    animation: 'shimmer 1.5s infinite',
                  }}
                />
                <div
                  style={{
                    width: '40%',
                    height: '11px',
                    borderRadius: '2px',
                    background: '#f0f0f0',
                    animation: 'shimmer 1.5s infinite',
                  }}
                />
              </div>
            </div>
          ))
        ) : items.length === 0 ? (
          <div className="empty-state">
            <p>No recent activity found.</p>
          </div>
        ) : (
          items.map((item, idx) => {
            const action = item.action || item.event_type || item.activity_type || 'Action';
            const desc = item.description || item.message || item.details || '';
            const time = item.created_at || item.timestamp || item.date || '';
            const user = item.user || item.performed_by || item.username || '';
            const col = getActionColor(action);
            const initials = (user || action).slice(0, 2).toUpperCase();

            return (
              <div key={item.id || idx} className="activity-item">
                <div className="activity-icon" style={{ background: col.bg, color: col.color }}>
                  {initials}
                </div>
                <div className="activity-info">
                  <div className="activity-action">{action}</div>
                  {desc && <div className="activity-desc">{desc}</div>}
                  <div className="activity-meta">
                    {user && <span style={{ fontWeight: 500 }}>{user}</span>}
                    {user && time && ' · '}
                    {time && timeAgo(time)}
                  </div>
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
