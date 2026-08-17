/**
 * OperationHistoryModal.jsx
 *
 * Reversible Operations & History Audit Modal for CardFlow.
 * Displays interactive timeline of all table mutations (edits, status changes,
 * deletions, restores, media reuploads) with granular field delta breakdown,
 * conflict indicators, and 1-click Undo/Redo actions.
 */

import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  History,
  RotateCcw,
  RotateCw,
  CheckCircle2,
  AlertTriangle,
  Clock,
  User,
  X,
  ChevronDown,
  ChevronUp,
  Layers,
  ArrowRight,
  ShieldAlert,
} from 'lucide-react';
import { operationsApi } from '../../services/api';

export default function OperationHistoryModal({
  isOpen,
  onClose,
  tableId,
  tableName = 'Table',
  onOperationReverted,
  addToast,
}) {
  const [operations, setOperations] = useState([]);
  const [loading, setLoading] = useState(false);
  const [actionLoadingId, setActionLoadingId] = useState(null);
  const [expandedOpId, setExpandedOpId] = useState(null);
  const [totalCount, setTotalCount] = useState(0);
  const [page, setPage] = useState(1);
  const limit = 30;

  const loadHistory = useCallback(async () => {
    if (!tableId || !isOpen) return;
    setLoading(true);
    try {
      const res = await operationsApi.getHistory({
        table_id: tableId,
        limit,
        offset: (page - 1) * limit,
      });
      if (res && res.success) {
        setOperations(res.operations || []);
        setTotalCount(res.total_count || 0);
      }
    } catch (err) {
      console.error('Failed to load operations history:', err);
    } finally {
      setLoading(false);
    }
  }, [tableId, isOpen, page]);

  useEffect(() => {
    if (isOpen) {
      loadHistory();
    }
  }, [isOpen, loadHistory]);

  const handleUndoSingle = async (opId) => {
    setActionLoadingId(opId);
    try {
      const res = await operationsApi.undo({ operation_id: opId, table_id: tableId });
      if (res && res.success) {
        addToast?.({
          type: 'success',
          message: res.message || `Successfully undone Op #${opId}.`,
        });
        loadHistory();
        onOperationReverted?.();
      } else {
        addToast?.({
          type: 'warning',
          message: res.message || `Could not undo Op #${opId}.`,
        });
        loadHistory();
      }
    } catch (err) {
      addToast?.({
        type: 'error',
        message: err.response?.data?.message || 'Failed to undo operation.',
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  const handleRedoSingle = async (opId) => {
    setActionLoadingId(opId);
    try {
      const res = await operationsApi.redo({ operation_id: opId, table_id: tableId });
      if (res && res.success) {
        addToast?.({
          type: 'success',
          message: res.message || `Successfully redone Op #${opId}.`,
        });
        loadHistory();
        onOperationReverted?.();
      } else {
        addToast?.({
          type: 'warning',
          message: res.message || `Could not redo Op #${opId}.`,
        });
        loadHistory();
      }
    } catch (err) {
      addToast?.({
        type: 'error',
        message: err.response?.data?.message || 'Failed to redo operation.',
      });
    } finally {
      setActionLoadingId(null);
    }
  };

  if (!isOpen) return null;

  const getStatusBadge = (status) => {
    switch (status) {
      case 'active':
        return (
          <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, background: '#dcfce7', color: '#15803d', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <CheckCircle2 size={11} /> Active
          </span>
        );
      case 'undone':
        return (
          <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, background: '#f1f5f9', color: '#64748b', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <RotateCcw size={11} /> Undone
          </span>
        );
      case 'partially_undone':
        return (
          <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, background: '#fef3c7', color: '#b45309', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <AlertTriangle size={11} /> Partial Undone
          </span>
        );
      case 'conflicted':
        return (
          <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, background: '#fee2e2', color: '#b91c1c', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <ShieldAlert size={11} /> Conflicted
          </span>
        );
      case 'redone':
        return (
          <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, background: '#e0f2fe', color: '#0369a1', display: 'inline-flex', alignItems: 'center', gap: '4px' }}>
            <RotateCw size={11} /> Redone
          </span>
        );
      default:
        return (
          <span style={{ padding: '2px 8px', borderRadius: '12px', fontSize: '11px', fontWeight: 600, background: '#f1f5f9', color: '#64748b' }}>
            {status}
          </span>
        );
    }
  };

  const formatTime = (isoString) => {
    if (!isoString) return '';
    try {
      const d = new Date(isoString);
      return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) + ' (' + d.toLocaleDateString() + ')';
    } catch {
      return isoString;
    }
  };

  return createPortal(
    <div
      style={{
        position: 'fixed',
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        zIndex: 9999,
        background: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(3px)',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '16px',
      }}
      onClick={onClose}
    >
      <div
        style={{
          width: '100%',
          maxWidth: '780px',
          maxHeight: '85vh',
          background: '#ffffff',
          borderRadius: '12px',
          boxShadow: '0 25px 50px -12px rgba(0, 0, 0, 0.25)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          border: '1px solid #e2e8f0',
        }}
        onClick={(e) => e.stopPropagation()}
      >
        {/* Header */}
        <div
          style={{
            padding: '14px 20px',
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '34px',
                height: '34px',
                borderRadius: '8px',
                background: 'rgba(59, 130, 246, 0.25)',
                border: '1px solid rgba(59, 130, 246, 0.4)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#60a5fa',
              }}
            >
              <History size={18} />
            </div>
            <div>
              <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 600, color: '#f8fafc' }}>
                Reversible Operations & History
              </h3>
              <p style={{ margin: 0, fontSize: '12px', color: '#94a3b8' }}>
                {tableName} — {totalCount} Recorded Operations (Live Rollback Engine)
              </p>
            </div>
          </div>

          <button
            onClick={onClose}
            style={{
              background: 'transparent',
              border: 'none',
              color: '#94a3b8',
              cursor: 'pointer',
              padding: '6px',
              borderRadius: '6px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
            }}
          >
            <X size={18} />
          </button>
        </div>

        {/* Content Body */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px 20px',
            background: '#f8fafc',
          }}
        >
          {loading ? (
            <div style={{ padding: '40px 0', textAlign: 'center', color: '#64748b', fontSize: '13px' }}>
              Loading operation timeline...
            </div>
          ) : operations.length === 0 ? (
            <div
              style={{
                padding: '48px 20px',
                textAlign: 'center',
                background: '#ffffff',
                borderRadius: '8px',
                border: '1px dashed #cbd5e1',
              }}
            >
              <History size={36} style={{ color: '#94a3b8', margin: '0 auto 10px' }} />
              <p style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#334155' }}>
                No Operations Recorded Yet
              </p>
              <p style={{ margin: '4px 0 0', fontSize: '12px', color: '#64748b' }}>
                Any edits, bulk actions, or photo updates in this table will appear here and can be undone at any time.
              </p>
            </div>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }}>
              {operations.map((op) => {
                const isExpanded = expandedOpId === op.id;
                const isActing = actionLoadingId === op.id;

                return (
                  <div
                    key={op.id}
                    style={{
                      background: '#ffffff',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '12px 14px',
                      boxShadow: '0 1px 2px rgba(0, 0, 0, 0.04)',
                      transition: 'all 0.15s ease',
                    }}
                  >
                    <div
                      style={{
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'space-between',
                        gap: '12px',
                        flexWrap: 'wrap',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', gap: '10px', flex: 1, minWidth: '240px' }}>
                        <div
                          style={{
                            width: '28px',
                            height: '28px',
                            borderRadius: '6px',
                            background: op.status === 'undone' ? '#f1f5f9' : '#eff6ff',
                            color: op.status === 'undone' ? '#64748b' : '#2563eb',
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'center',
                            fontSize: '11px',
                            fontWeight: 700,
                            flexShrink: 0,
                          }}
                        >
                          #{op.id}
                        </div>

                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                            <span style={{ fontSize: '13px', fontWeight: 600, color: '#1e293b' }}>
                              {op.description}
                            </span>
                            {getStatusBadge(op.status)}
                          </div>

                          <div
                            style={{
                              display: 'flex',
                              alignItems: 'center',
                              gap: '12px',
                              fontSize: '11px',
                              color: '#64748b',
                              marginTop: '3px',
                            }}
                          >
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                              <User size={11} /> {op.user_name || 'System'}
                            </span>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                              <Clock size={11} /> {formatTime(op.created_at)}
                            </span>
                            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                              <Layers size={11} /> {op.change_count} field change(s)
                            </span>
                          </div>
                        </div>
                      </div>

                      {/* Action Buttons */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        {op.can_undo && (
                          <button
                            disabled={isActing}
                            onClick={() => handleUndoSingle(op.id)}
                            style={{
                              padding: '5px 10px',
                              borderRadius: '6px',
                              border: '1px solid #cbd5e1',
                              background: '#ffffff',
                              color: '#2563eb',
                              fontSize: '11px',
                              fontWeight: 600,
                              cursor: isActing ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                            title="Safely reverse this operation"
                          >
                            <RotateCcw size={12} />
                            <span>Undo</span>
                          </button>
                        )}

                        {op.can_redo && (
                          <button
                            disabled={isActing}
                            onClick={() => handleRedoSingle(op.id)}
                            style={{
                              padding: '5px 10px',
                              borderRadius: '6px',
                              border: '1px solid #93c5fd',
                              background: '#eff6ff',
                              color: '#1d4ed8',
                              fontSize: '11px',
                              fontWeight: 600,
                              cursor: isActing ? 'not-allowed' : 'pointer',
                              display: 'flex',
                              alignItems: 'center',
                              gap: '4px',
                            }}
                            title="Re-apply this undone operation"
                          >
                            <RotateCw size={12} />
                            <span>Redo</span>
                          </button>
                        )}
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>

        {/* Footer with Keyboard Tip */}
        <div
          style={{
            padding: '10px 20px',
            background: '#ffffff',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            fontSize: '11px',
            color: '#64748b',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span>Keyboard Shortcuts:</span>
            <kbd style={{ padding: '2px 5px', borderRadius: '4px', background: '#f1f5f9', border: '1px solid #cbd5e1', color: '#334155', fontWeight: 600 }}>Ctrl+Z</kbd>
            <span>Undo</span>
            <kbd style={{ padding: '2px 5px', borderRadius: '4px', background: '#f1f5f9', border: '1px solid #cbd5e1', color: '#334155', fontWeight: 600 }}>Ctrl+Y</kbd>
            <span>Redo</span>
          </div>

          <button
            onClick={onClose}
            style={{
              padding: '5px 14px',
              borderRadius: '6px',
              background: '#f1f5f9',
              border: '1px solid #cbd5e1',
              color: '#334155',
              fontSize: '12px',
              fontWeight: 500,
              cursor: 'pointer',
            }}
          >
            Close
          </button>
        </div>
      </div>
    </div>,
    document.body
  );
}
