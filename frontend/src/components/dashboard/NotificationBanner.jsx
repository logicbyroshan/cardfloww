import React, { useState, useEffect, useCallback } from 'react';
import { X, Info, CheckCircle, AlertTriangle, Sparkles, Loader2 } from 'lucide-react';
import { dashboardApi } from '../../services/api';

const TYPE_CFG = {
  info: { cls: 'notif-banner-info', Icon: Info },
  success: { cls: 'notif-banner-success', Icon: CheckCircle },
  warning: { cls: 'notif-banner-warning', Icon: AlertTriangle },
  announce: { cls: 'notif-banner-info', Icon: Sparkles },
};

export default function NotificationBanner() {
  const [banners, setBanners] = useState([]);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(new Set());

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const data = await dashboardApi.getNotifications();
      const list = data.notifications || data.results || data || [];
      setBanners(list.filter((n) => !n.is_read).slice(0, 3));
    } catch {
      setBanners([
        {
          id: '__default',
          title: 'CardFlow Online',
          message: 'System is running normally.',
          type: 'success',
        },
      ]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const dismiss = async (n) => {
    setDismissed((prev) => new Set([...prev, n.id]));
    if (n.id !== '__default') {
      try {
        await dashboardApi.markAllRead();
      } catch (_) {}
    }
  };

  const visible = banners.filter((n) => !dismissed.has(n.id));
  if (!loading && visible.length === 0) return null;

  if (loading) {
    return (
      <div
        style={{
          height: '34px',
          background: '#eff6ff',
          borderBottom: '1px solid #bfdbfe',
          display: 'flex',
          alignItems: 'center',
          padding: '0 14px',
          gap: '8px',
        }}
      >
        <Loader2 size={12} style={{ animation: 'spin 1s linear infinite', color: '#3b82f6' }} />
        <span style={{ fontSize: '12px', color: '#6b7280' }}>Loading notifications…</span>
      </div>
    );
  }

  return (
    <>
      {visible.map((n) => {
        const kind = (n.type || n.notification_type || 'info').toLowerCase();
        const cfg = TYPE_CFG[kind] || TYPE_CFG.info;
        const Icon = cfg.Icon;
        return (
          <div key={n.id} className={`notif-banner ${cfg.cls}`}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Icon size={13} />
              <span style={{ fontWeight: 600, fontSize: '13px' }}>{n.title || 'Notice'}</span>
              {n.message && (
                <span style={{ fontSize: '12px', color: '#6b7280', marginLeft: '4px' }}>— {n.message}</span>
              )}
            </div>
            <button className="notif-banner-dismiss" onClick={() => dismiss(n)}>
              <X size={13} />
            </button>
          </div>
        );
      })}
    </>
  );
}
