import React, { useState, useEffect, useCallback } from 'react';
import { FileText, Clock, CheckCircle, Download, ShieldCheck, AlertTriangle, RefreshCw, Loader2 } from 'lucide-react';
import { dashboardApi } from '../../services/api';

const STAT_DEFS = [
  { key: 'total', label: 'Total Cards', iconClass: 'indigo', Icon: FileText },
  { key: 'pending', label: 'Pending', iconClass: 'amber', Icon: Clock },
  { key: 'verified', label: 'Verified', iconClass: 'emerald', Icon: ShieldCheck },
  { key: 'approved', label: 'Approved', iconClass: 'blue', Icon: CheckCircle },
  { key: 'download', label: 'Downloaded', iconClass: 'teal', Icon: Download },
  { key: 'pool', label: 'Pool / Reprint', iconClass: 'orange', Icon: AlertTriangle },
];

export default function StatsGrid() {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(false);
    try {
      const data = await dashboardApi.getStats();
      setStats(data.stats || data);
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
    const t = setInterval(load, 30_000);
    return () => clearInterval(t);
  }, [load]);

  if (error && !stats) {
    return (
      <div className="stats-grid" style={{ gridTemplateColumns: '1fr' }}>
        <div
          style={{
            padding: '12px 16px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            fontSize: '13px',
            color: '#dc2626',
            background: '#fef2f2',
            border: '1px solid #fca5a5',
          }}
        >
          <AlertTriangle size={14} /> Could not load stats — retrying every 30s.
          <button
            onClick={load}
            style={{
              marginLeft: 'auto',
              fontSize: '12px',
              background: 'none',
              border: 'none',
              color: '#dc2626',
              cursor: 'pointer',
              display: 'flex',
              alignItems: 'center',
              gap: '4px',
            }}
          >
            <RefreshCw size={11} /> Retry
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="stats-grid">
      {STAT_DEFS.map(({ key, label, iconClass, Icon }) => {
        const value = stats?.[key] ?? stats?.[`${key}_count`] ?? 0;
        return (
          <div key={key} className="stat-card">
            <div className={`stat-icon ${iconClass}`}>
              {loading ? (
                <div
                  style={{
                    width: '18px',
                    height: '18px',
                    borderRadius: '2px',
                    background: 'rgba(0,0,0,0.08)',
                    animation: 'pulse 1.5s infinite',
                  }}
                />
              ) : (
                <Icon size={18} />
              )}
            </div>
            <div className="stat-info">
              <div className="stat-value">
                {loading ? (
                  <div
                    style={{
                      width: '48px',
                      height: '22px',
                      borderRadius: '2px',
                      background: 'rgba(0,0,0,0.08)',
                      animation: 'pulse 1.5s infinite',
                      display: 'inline-block',
                    }}
                  />
                ) : (
                  value.toLocaleString()
                )}
              </div>
              <div className="stat-label">{label}</div>
            </div>
          </div>
        );
      })}
    </div>
  );
}
