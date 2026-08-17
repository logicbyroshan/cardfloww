import React, { useState, useEffect, useCallback } from 'react';
import { createPortal } from 'react-dom';
import {
  X,
  Layers,
  Search,
  RotateCcw,
  Download,
  Clock,
  User,
  Shield,
  ArrowRight,
  CheckCircle2,
  AlertTriangle,
  RefreshCw,
  Eye,
  FileText,
} from 'lucide-react';
import { auditApi } from '../../services/api';

export default function BulkTransactionsModal({
  isOpen,
  onClose,
  tableId,
  tableName = 'Table',
  initialTransactionId = null,
  onTransactionReverted,
  addToast,
}) {
  const [transactions, setTransactions] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [selectedTxId, setSelectedTxId] = useState(initialTransactionId);
  const [txDetail, setTxDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [cardSearch, setCardSearch] = useState('');
  const [reversing, setReversing] = useState(false);

  /* ── Load Bulk Transactions List ── */
  const fetchTransactions = useCallback(async () => {
    if (!isOpen) return;
    setLoading(true);
    try {
      const res = await auditApi.getTransactions({ table_id: tableId, limit: 100 });
      if (res && res.success) {
        setTransactions(res.transactions || []);
        setTotalCount(res.total_count || 0);
      } else {
        setTransactions([]);
      }
    } catch {
      setTransactions([]);
    } finally {
      setLoading(false);
    }
  }, [isOpen, tableId]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

  /* ── Load Transaction Detail when selected ── */
  const fetchDetail = useCallback(async (txId) => {
    if (!txId) {
      setTxDetail(null);
      return;
    }
    setDetailLoading(true);
    try {
      const res = await auditApi.getTransactionDetail(txId, { search: cardSearch, limit: 200 });
      if (res && res.success) {
        setTxDetail(res);
      } else {
        setTxDetail(null);
      }
    } catch {
      setTxDetail(null);
    } finally {
      setDetailLoading(false);
    }
  }, [cardSearch]);

  useEffect(() => {
    if (selectedTxId) {
      fetchDetail(selectedTxId);
    }
  }, [selectedTxId, fetchDetail]);

  /* ── Handle Safe Transaction Reversal ── */
  const handleReverseTransaction = async (txId, txCode) => {
    if (!window.confirm(`Are you sure you want to reverse Transaction "${txCode}"?\n\nNon-conflicted cards will revert to their previous status. Cards with subsequent modifications will be safely protected.`)) {
      return;
    }

    setReversing(true);
    try {
      const res = await auditApi.reverseTransaction(txId);
      if (res && res.success) {
        addToast?.(res.message || 'Transaction successfully reversed!', 'success');
        onTransactionReverted?.();
        await Promise.all([fetchTransactions(), fetchDetail(txId)]);
      } else {
        addToast?.(res?.message || 'Could not reverse transaction.', 'warning');
      }
    } catch (err) {
      addToast?.(err.response?.data?.message || 'Failed to reverse transaction.', 'error');
    } finally {
      setReversing(false);
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div
      style={{
        position: 'fixed',
        inset: 0,
        background: 'rgba(15, 23, 42, 0.65)',
        backdropFilter: 'blur(4px)',
        zIndex: 9999,
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '20px',
        animation: 'fadeIn 0.2s ease',
        fontFamily: 'var(--font-family, system-ui, -apple-system, sans-serif)',
      }}
    >
      <div
        style={{
          width: '980px',
          maxWidth: '96vw',
          maxHeight: '90vh',
          background: '#ffffff',
          borderRadius: '12px',
          boxShadow: '0 20px 48px rgba(0,0,0,0.3)',
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
        }}
      >
        {/* Header */}
        <div
          style={{
            padding: '16px 24px',
            background: '#1e293b',
            color: '#ffffff',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            borderBottom: '1px solid #334155',
            flexShrink: 0,
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
            <div
              style={{
                width: '38px',
                height: '38px',
                borderRadius: '8px',
                background: 'linear-gradient(135deg, #6366f1 0%, #4f46e5 100%)',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 2px 8px rgba(99, 102, 241, 0.4)',
              }}
            >
              <Layers size={20} color="#ffffff" />
            </div>
            <div>
              <h2 style={{ margin: 0, fontSize: '17px', fontWeight: 700 }}>
                Bulk Transactions & Activity History
              </h2>
              <p style={{ margin: '2px 0 0', fontSize: '12px', color: '#94a3b8' }}>
                Table: {tableName} · {totalCount} total batch transactions
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <a
              href={auditApi.exportAuditUrl(tableId)}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 12px',
                background: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '6px',
                color: '#ffffff',
                fontSize: '12px',
                fontWeight: 600,
                textDecoration: 'none',
                cursor: 'pointer',
              }}
              title="Download full audit log as CSV"
            >
              <Download size={14} />
              <span>Export CSV</span>
            </a>

            <button
              type="button"
              onClick={onClose}
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                border: 'none',
                borderRadius: '6px',
                width: '32px',
                height: '32px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#cbd5e1',
                cursor: 'pointer',
              }}
            >
              <X size={18} />
            </button>
          </div>
        </div>

        {/* Content Area: Split View (Transactions List on Left, Detail on Right) */}
        <div style={{ display: 'flex', flex: 1, overflow: 'hidden', minHeight: '440px' }}>
          {/* Left Panel: Transactions List */}
          <div
            style={{
              width: selectedTxId ? '40%' : '100%',
              borderRight: selectedTxId ? '1px solid #e2e8f0' : 'none',
              display: 'flex',
              flexDirection: 'column',
              background: '#f8fafc',
              overflowY: 'auto',
            }}
          >
            {loading ? (
              <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px', gap: '10px' }}>
                <RefreshCw size={20} className="spin" color="#64748b" />
                <span style={{ fontSize: '13px', color: '#64748b' }}>Loading transactions...</span>
              </div>
            ) : transactions.length === 0 ? (
              <div style={{ textAlign: 'center', padding: '60px 20px', color: '#64748b' }}>
                <Layers size={36} color="#cbd5e1" style={{ margin: '0 auto 12px' }} />
                <p style={{ margin: 0, fontSize: '14px', fontWeight: 600, color: '#334155' }}>No bulk transactions recorded yet</p>
                <p style={{ margin: '4px 0 0', fontSize: '12px' }}>Mass card status movements and imports will appear here.</p>
              </div>
            ) : (
              <div style={{ padding: '12px' }}>
                {transactions.map((tx) => {
                  const isSelected = selectedTxId === tx.id;
                  const dt = new Date(tx.created_at);
                  const timeStr = dt.toLocaleString('en-IN', {
                    day: '2-digit',
                    month: 'short',
                    year: 'numeric',
                    hour: '2-digit',
                    minute: '2-digit',
                  });

                  return (
                    <div
                      key={tx.id}
                      onClick={() => setSelectedTxId(tx.id)}
                      style={{
                        padding: '12px 14px',
                        marginBottom: '8px',
                        background: isSelected ? '#ffffff' : '#ffffff',
                        border: isSelected ? '2px solid #3b82f6' : '1px solid #e2e8f0',
                        borderRadius: '8px',
                        cursor: 'pointer',
                        boxShadow: isSelected ? '0 2px 8px rgba(59, 130, 246, 0.15)' : '0 1px 2px rgba(0,0,0,0.04)',
                        transition: 'all 0.15s ease',
                      }}
                    >
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '4px' }}>
                        <strong style={{ fontSize: '13px', color: '#0f172a' }}>{tx.tx_code}</strong>
                        <span
                          style={{
                            fontSize: '10px',
                            fontWeight: 700,
                            padding: '1px 6px',
                            borderRadius: '4px',
                            textTransform: 'uppercase',
                            background: tx.status === 'completed' ? '#dcfce7' : (tx.status.includes('reversed') ? '#fef3c7' : '#fee2e2'),
                            color: tx.status === 'completed' ? '#16a34a' : (tx.status.includes('reversed') ? '#d97706' : '#dc2626'),
                          }}
                        >
                          {tx.status}
                        </span>
                      </div>

                      {/* Transition description */}
                      <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '12px', margin: '4px 0' }}>
                        <span style={{ fontWeight: 600, color: '#3b82f6', textTransform: 'capitalize' }}>
                          {tx.source_state || 'start'}
                        </span>
                        <ArrowRight size={12} color="#94a3b8" />
                        <span style={{ fontWeight: 600, color: '#16a34a', textTransform: 'capitalize' }}>
                          {tx.destination_state || 'end'}
                        </span>
                        <span style={{ color: '#64748b', fontSize: '11px', marginLeft: 'auto' }}>
                          <strong>{tx.success_count}</strong> cards
                        </span>
                      </div>

                      {/* Actor & Timestamp */}
                      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', color: '#64748b', marginTop: '6px' }}>
                        <span>By: <strong>{tx.actor_name}</strong> {tx.actor_role && `(${tx.actor_role})`}</span>
                        <span>{timeStr}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </div>

          {/* Right Panel: Transaction Detail & Affected Cards */}
          {selectedTxId && (
            <div style={{ width: '60%', display: 'flex', flexDirection: 'column', background: '#ffffff', overflowY: 'auto' }}>
              {detailLoading ? (
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', height: '200px', gap: '10px' }}>
                  <RefreshCw size={20} className="spin" color="#64748b" />
                  <span style={{ fontSize: '13px', color: '#64748b' }}>Loading batch details...</span>
                </div>
              ) : txDetail ? (
                <div style={{ padding: '20px', display: 'flex', flexDirection: 'column', height: '100%', boxSizing: 'border-box' }}>
                  {/* Transaction Detail Card */}
                  <div
                    style={{
                      background: '#f8fafc',
                      border: '1px solid #e2e8f0',
                      borderRadius: '8px',
                      padding: '14px',
                      marginBottom: '16px',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
                      <h4 style={{ margin: 0, fontSize: '15px', color: '#0f172a' }}>
                        {txDetail.transaction.tx_code}
                      </h4>

                      {txDetail.transaction.can_reverse && (
                        <button
                          type="button"
                          disabled={reversing}
                          onClick={() => handleReverseTransaction(txDetail.transaction.id, txDetail.transaction.tx_code)}
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '5px',
                            padding: '5px 12px',
                            background: '#dc2626',
                            color: '#ffffff',
                            border: 'none',
                            borderRadius: '6px',
                            fontSize: '12px',
                            fontWeight: 600,
                            cursor: reversing ? 'not-allowed' : 'pointer',
                          }}
                          title="Safely reverse this batch move back to source state"
                        >
                          {reversing ? <RefreshCw size={13} className="spin" /> : <RotateCcw size={13} />}
                          <span>Reverse Transaction</span>
                        </button>
                      )}
                    </div>

                    <div style={{ display: 'grid', gridTemplateColumns: 'repeat(3, 1fr)', gap: '8px', fontSize: '12px', color: '#475569' }}>
                      <div>
                        <span>Status: </span>
                        <strong style={{ color: '#0f172a' }}>{txDetail.transaction.status}</strong>
                      </div>
                      <div>
                        <span>Affected Cards: </span>
                        <strong style={{ color: '#0f172a' }}>{txDetail.total_affected}</strong>
                      </div>
                      <div>
                        <span>Actor: </span>
                        <strong style={{ color: '#0f172a' }}>{txDetail.transaction.actor_name}</strong>
                      </div>
                    </div>
                  </div>

                  {/* Search inside affected cards */}
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
                    <div
                      style={{
                        flex: 1,
                        display: 'flex',
                        alignItems: 'center',
                        gap: '6px',
                        background: '#f1f5f9',
                        borderRadius: '6px',
                        padding: '6px 10px',
                        border: '1px solid #e2e8f0',
                      }}
                    >
                      <Search size={14} color="#64748b" />
                      <input
                        type="text"
                        placeholder="Search affected cards by name or ID..."
                        value={cardSearch}
                        onChange={(e) => setCardSearch(e.target.value)}
                        style={{
                          border: 'none',
                          background: 'transparent',
                          outline: 'none',
                          fontSize: '12px',
                          width: '100%',
                        }}
                      />
                    </div>
                  </div>

                  {/* Affected Cards Grid */}
                  <div style={{ flex: 1, overflowY: 'auto', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                    <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px', textAlign: 'left' }}>
                      <thead style={{ background: '#f8fafc', borderBottom: '1px solid #e2e8f0', position: 'sticky', top: 0 }}>
                        <tr>
                          <th style={{ padding: '8px 12px', fontWeight: 600, color: '#475569' }}>Card ID</th>
                          <th style={{ padding: '8px 12px', fontWeight: 600, color: '#475569' }}>Student / Entity</th>
                          <th style={{ padding: '8px 12px', fontWeight: 600, color: '#475569' }}>Change</th>
                        </tr>
                      </thead>
                      <tbody>
                        {txDetail.affected_cards.length === 0 ? (
                          <tr>
                            <td colSpan={3} style={{ padding: '20px', textAlign: 'center', color: '#94a3b8' }}>
                              No cards found matching search.
                            </td>
                          </tr>
                        ) : (
                          txDetail.affected_cards.map((c, idx) => (
                            <tr key={c.event_id || idx} style={{ borderBottom: '1px solid #f1f5f9' }}>
                              <td style={{ padding: '7px 12px', fontWeight: 600, color: '#0f172a' }}>#{c.card_id}</td>
                              <td style={{ padding: '7px 12px', color: '#334155' }}>{c.target_name || `Card #${c.card_id}`}</td>
                              <td style={{ padding: '7px 12px', color: '#16a34a', fontWeight: 600 }}>
                                {txDetail.transaction.source_state} → {txDetail.transaction.destination_state}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                </div>
              ) : null}
            </div>
          )}
        </div>

        {/* Footer */}
        <div
          style={{
            padding: '12px 24px',
            background: '#f8fafc',
            borderTop: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'flex-end',
            flexShrink: 0,
          }}
        >
          <button
            type="button"
            onClick={onClose}
            style={{
              padding: '7px 18px',
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
      </div>
    </div>,
    document.body
  );
}
