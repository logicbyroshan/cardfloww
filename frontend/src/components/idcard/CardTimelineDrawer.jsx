import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Clock,
  User,
  Shield,
  Layers,
  ArrowRight,
  RefreshCw,
  FileSpreadsheet,
  FileText,
  CheckCircle2,
  AlertCircle,
  Sparkles,
  Camera,
  Edit3,
} from 'lucide-react';
import { auditApi } from '../../services/api';

export default function CardTimelineDrawer({ card, table, onClose, onOpenTransaction }) {
  const [timeline, setTimeline] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);

  const cardId = card?.id;

  const fetchTimeline = useCallback(async () => {
    if (!cardId) return;
    setLoading(true);
    try {
      const res = await auditApi.getCardTimeline(cardId, { limit: 100 });
      if (res && res.success) {
        setTimeline(res.timeline || []);
        setTotalCount(res.total_count || 0);
      } else {
        setTimeline([]);
      }
    } catch {
      setTimeline([]);
    } finally {
      setLoading(false);
    }
  }, [cardId]);

  useEffect(() => {
    fetchTimeline();
  }, [fetchTimeline]);

  if (!card) return null;

  const studentName =
    card.field_data?.['FULL NAME'] ||
    card.field_data?.['NAME'] ||
    card.field_data?.['STUDENT NAME'] ||
    `Card #${card.id}`;

  const getRoleBadgeColor = (role) => {
    const r = String(role || '').toLowerCase();
    if (r.includes('super_admin') || r.includes('prime_admin')) return { bg: '#fee2e2', text: '#dc2626', border: '#fca5a5' };
    if (r.includes('operator') || r.includes('admin')) return { bg: '#e0e7ff', text: '#4338ca', border: '#c7d2fe' };
    if (r.includes('manager')) return { bg: '#fef3c7', text: '#d97706', border: '#fde68a' };
    if (r.includes('assistant')) return { bg: '#e0f2fe', text: '#0284c7', border: '#bae6fd' };
    return { bg: '#f1f5f9', text: '#475569', border: '#cbd5e1' };
  };

  const getEventIcon = (eventType) => {
    switch (eventType) {
      case 'status_change':
      case 'bulk_status':
        return <CheckCircle2 size={13} color="#2563eb" />;
      case 'media_upload':
      case 'media_replace':
      case 'crop_update':
        return <Camera size={13} color="#0d9488" />;
      case 'create':
        return <Sparkles size={13} color="#16a34a" />;
      default:
        return <Edit3 size={13} color="#6366f1" />;
    }
  };

  return createPortal(
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          inset: 0,
          background: 'rgba(15, 23, 42, 0.55)',
          backdropFilter: 'blur(3px)',
          zIndex: 9998,
          animation: 'fadeIn 0.2s ease',
        }}
      />

      {/* Drawer */}
      <aside
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '460px',
          maxWidth: '92vw',
          background: '#ffffff',
          boxShadow: '-8px 0 32px rgba(0, 0, 0, 0.2)',
          zIndex: 9999,
          display: 'flex',
          flexDirection: 'column',
          animation: 'slideInRight 0.25s cubic-bezier(0.16, 1, 0.3, 1)',
          fontFamily: 'var(--font-family, system-ui, -apple-system, sans-serif)',
        }}
      >
        {/* Drawer Header */}
        <div
          style={{
            padding: '16px 20px',
            background: '#1e293b',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #334155',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '34px',
                height: '34px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #3b82f6 0%, #2563eb 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 6px rgba(37, 99, 235, 0.4)',
              }}
            >
              <Clock size={18} color="#ffffff" />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, letterSpacing: '-0.01em' }}>
                Card Activity Timeline
              </h3>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
                {studentName} · ID #{card.id}
              </p>
            </div>
          </div>

          <button
            type="button"
            onClick={onClose}
            style={{
              background: 'rgba(255, 255, 255, 0.1)',
              border: 'none',
              borderRadius: '6px',
              width: '30px',
              height: '30px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              color: '#cbd5e1',
              cursor: 'pointer',
              transition: 'all 0.15s ease',
            }}
            title="Close"
          >
            <X size={18} />
          </button>
        </div>

        {/* Card Summary Mini-Bar */}
        <div
          style={{
            padding: '10px 20px',
            background: '#f8fafc',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '12px',
            color: '#475569',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
            <span>Status:</span>
            <span
              style={{
                display: 'inline-block',
                padding: '2px 8px',
                borderRadius: '4px',
                fontSize: '11px',
                fontWeight: 700,
                background: '#e0e7ff',
                color: '#3730a3',
                textTransform: 'uppercase',
              }}
            >
              {card.status || 'pending'}
            </span>
          </div>

          <div>
            <span>Events: </span>
            <strong style={{ color: '#0f172a' }}>{totalCount}</strong>
          </div>
        </div>

        {/* Timeline Body */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '20px',
            background: '#ffffff',
          }}
        >
          {loading ? (
            <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '200px', gap: '10px' }}>
              <RefreshCw size={24} className="spin" color="#64748b" />
              <span style={{ fontSize: '13px', color: '#64748b' }}>Loading timeline...</span>
            </div>
          ) : timeline.length === 0 ? (
            <div style={{ textAlign: 'center', padding: '40px 20px', color: '#64748b' }}>
              <Clock size={36} color="#cbd5e1" style={{ margin: '0 auto 12px' }} />
              <p style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#334155' }}>No activity records found</p>
              <p style={{ margin: '4px 0 0', fontSize: '12px' }}>Changes to this card will be tracked here in real-time.</p>
            </div>
          ) : (
            <div style={{ position: 'relative', paddingLeft: '24px' }}>
              {/* Vertical timeline spine */}
              <div
                style={{
                  position: 'absolute',
                  left: '11px',
                  top: '12px',
                  bottom: '12px',
                  width: '2px',
                  background: '#e2e8f0',
                }}
              />

              {timeline.map((ev, idx) => {
                const roleBadge = getRoleBadgeColor(ev.actor_role);
                const dt = new Date(ev.created_at);
                const timeStr = dt.toLocaleString('en-IN', {
                  day: '2-digit',
                  month: 'short',
                  year: 'numeric',
                  hour: '2-digit',
                  minute: '2-digit',
                });

                return (
                  <div
                    key={ev.id || idx}
                    style={{
                      position: 'relative',
                      marginBottom: '20px',
                    }}
                  >
                    {/* Node Dot */}
                    <div
                      style={{
                        position: 'absolute',
                        left: '-24px',
                        top: '4px',
                        width: '22px',
                        height: '22px',
                        borderRadius: '50%',
                        background: '#ffffff',
                        border: '2px solid #3b82f6',
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        boxShadow: '0 1px 3px rgba(0,0,0,0.1)',
                      }}
                    >
                      {getEventIcon(ev.event_type)}
                    </div>

                    {/* Timeline Card */}
                    <div
                      style={{
                        background: '#f8fafc',
                        border: '1px solid #e2e8f0',
                        borderRadius: '8px',
                        padding: '12px 14px',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      {/* Top Row: Actor & Timestamp */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '6px', flexWrap: 'wrap', gap: '4px' }}>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontSize: '13px', fontWeight: 700, color: '#0f172a' }}>
                            {ev.actor_name}
                          </span>
                          {ev.actor_role && (
                            <span
                              style={{
                                fontSize: '10px',
                                fontWeight: 700,
                                textTransform: 'uppercase',
                                padding: '1px 6px',
                                borderRadius: '4px',
                                background: roleBadge.bg,
                                color: roleBadge.text,
                                border: `1px solid ${roleBadge.border}`,
                              }}
                            >
                              {ev.actor_role}
                            </span>
                          )}
                        </div>

                        <span style={{ fontSize: '11px', color: '#64748b' }}>{timeStr}</span>
                      </div>

                      {/* Bulk Transaction Link Badge */}
                      {ev.bulk_transaction && (
                        <div
                          style={{
                            display: 'inline-flex',
                            alignItems: 'center',
                            gap: '5px',
                            background: 'rgba(37, 99, 235, 0.08)',
                            border: '1px solid rgba(37, 99, 235, 0.2)',
                            borderRadius: '4px',
                            padding: '3px 8px',
                            fontSize: '11px',
                            color: '#2563eb',
                            fontWeight: 600,
                            marginBottom: '8px',
                            cursor: onOpenTransaction ? 'pointer' : 'default',
                          }}
                          onClick={() => onOpenTransaction?.(ev.bulk_transaction.id)}
                          title="Click to view full bulk transaction details"
                        >
                          <Layers size={12} />
                          <span>Part of Bulk Transaction: <strong>{ev.bulk_transaction.tx_code}</strong></span>
                          {ev.bulk_transaction.requested_count && (
                            <span style={{ color: '#64748b', fontSize: '10px' }}>
                              ({ev.bulk_transaction.requested_count} cards)
                            </span>
                          )}
                        </div>
                      )}

                      {/* Human-Friendly Summary Banner */}
                      {ev.human_summary && (
                        <div style={{ fontSize: '12px', fontWeight: 600, color: '#1e293b', marginBottom: '6px' }}>
                          {ev.human_summary}
                        </div>
                      )}

                      {/* Granular Field Deltas */}
                      {ev.field_deltas && ev.field_deltas.length > 0 ? (
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '4px', marginTop: '4px' }}>
                          {ev.field_deltas.map((d, dIdx) => (
                            <div
                              key={dIdx}
                              style={{
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                fontSize: '12px',
                                background: '#ffffff',
                                border: '1px solid #f1f5f9',
                                padding: '4px 8px',
                                borderRadius: '4px',
                                flexWrap: 'wrap',
                              }}
                            >
                              <span style={{ fontWeight: 600, color: '#334155' }}>{d.field_name}:</span>
                              <span
                                style={{
                                  color: '#dc2626',
                                  textDecoration: d.before_value !== null ? 'line-through' : 'none',
                                  background: '#fee2e2',
                                  padding: '1px 4px',
                                  borderRadius: '3px',
                                  fontSize: '11px',
                                }}
                              >
                                {d.before_value !== null && d.before_value !== undefined && d.before_value !== ''
                                  ? String(d.before_value)
                                  : 'empty'}
                              </span>
                              <ArrowRight size={11} color="#94a3b8" />
                              <span
                                style={{
                                  color: '#16a34a',
                                  fontWeight: 600,
                                  background: '#dcfce7',
                                  padding: '1px 4px',
                                  borderRadius: '3px',
                                  fontSize: '11px',
                                }}
                              >
                                {d.after_value !== null && d.after_value !== undefined && d.after_value !== ''
                                  ? String(d.after_value)
                                  : 'empty'}
                              </span>
                            </div>
                          ))}
                        </div>
                      ) : null}

                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Drawer Footer */}
        <div
          style={{
            padding: '12px 20px',
            borderTop: '1px solid #e2e8f0',
            background: '#f8fafc',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
          }}
        >
          <span style={{ fontSize: '11px', color: '#64748b' }}>
            Event ID: {timeline[0]?.event_id || '—'}
          </span>
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '7px 16px',
              background: '#334155',
              color: '#ffffff',
              border: 'none',
              borderRadius: '6px',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </aside>
    </>,
    document.body
  );
}
