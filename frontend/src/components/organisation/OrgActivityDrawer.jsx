import React, { useState, useEffect, useCallback } from 'react';
import {
  X,
  Activity,
  Search,
  RotateCcw,
  Download,
  Clock,
  User,
  ArrowRight,
  RefreshCw,
  FileText,
  Layers,
  ChevronDown,
  ChevronUp,
} from 'lucide-react';
import { auditApi } from '../../services/api';
import { formatDT } from '../../utils/formatters';
import Input from '../common/Input';
import Button from '../common/Button';

export default function OrgActivityDrawer({ isOpen, onClose, org, addToast }) {
  const [transactions, setTransactions] = useState([]);
  const [totalCount, setTotalCount] = useState(0);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState('');
  const [expandedTxId, setExpandedTxId] = useState(null);
  const [txDetail, setTxDetail] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [cardSearch, setCardSearch] = useState('');
  const [reversing, setReversing] = useState(false);

  const orgId = org?.id;
  const orgName = org?.name || org?.school_name || `Org #${orgId || ''}`;

  const fetchTransactions = useCallback(async () => {
    if (!isOpen || !orgId) return;
    setLoading(true);
    try {
      const res = await auditApi.getTransactions({ client_id: orgId, org_id: orgId, limit: 100 });
      if (res && res.success) {
        setTransactions(res.transactions || []);
        setTotalCount(res.total_count || 0);
      } else {
        setTransactions([]);
        setTotalCount(0);
      }
    } catch (err) {
      console.error('Failed to load org transactions:', err);
      setTransactions([]);
      setTotalCount(0);
    } finally {
      setLoading(false);
    }
  }, [isOpen, orgId]);

  useEffect(() => {
    fetchTransactions();
  }, [fetchTransactions]);

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
    if (expandedTxId) {
      fetchDetail(expandedTxId);
    }
  }, [expandedTxId, fetchDetail]);

  const handleToggleExpand = (txId) => {
    if (expandedTxId === txId) {
      setExpandedTxId(null);
      setTxDetail(null);
    } else {
      setExpandedTxId(txId);
    }
  };

  const handleReverseTransaction = async (txId, txCode) => {
    if (!window.confirm(`Are you sure you want to reverse Transaction "${txCode}"?\n\nNon-conflicted cards will safely revert to their previous status.`)) {
      return;
    }
    setReversing(true);
    try {
      const res = await auditApi.reverseTransaction(txId);
      if (res && res.success) {
        addToast?.(res.message || 'Transaction successfully reversed!', 'success');
        fetchTransactions();
        if (expandedTxId === txId) {
          fetchDetail(txId);
        }
      } else {
        addToast?.(res?.error || 'Failed to reverse transaction', 'error');
      }
    } catch (err) {
      addToast?.(err?.response?.data?.error || err?.message || 'Error reversing transaction', 'error');
    } finally {
      setReversing(false);
    }
  };

  if (!isOpen) return null;

  const filteredTx = transactions.filter((tx) => {
    if (!search) return true;
    const q = search.toLowerCase();
    return (
      (tx.transaction_code || '').toLowerCase().includes(q) ||
      (tx.action_display || tx.action || '').toLowerCase().includes(q) ||
      (tx.user_name || '').toLowerCase().includes(q) ||
      (tx.notes || '').toLowerCase().includes(q)
    );
  });

  return (
    <>
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: 'fixed',
          top: 0,
          left: 0,
          right: 0,
          bottom: 0,
          background: 'rgba(15, 23, 42, 0.45)',
          backdropFilter: 'blur(2px)',
          zIndex: 999,
        }}
      />

      {/* Drawer Container */}
      <div
        style={{
          position: 'fixed',
          top: 0,
          right: 0,
          bottom: 0,
          width: '660px',
          minWidth: '560px',
          maxWidth: '95vw',
          background: '#ffffff',
          boxShadow: '-8px 0 25px rgba(0,0,0,0.15)',
          zIndex: 1000,
          display: 'flex',
          flexDirection: 'column',
          animation: 'drawerSlideInRight 0.2s ease-out',
        }}
      >
        {/* Drawer Header */}
        <div
          style={{
            background: 'linear-gradient(135deg, #1e293b 0%, #0f172a 100%)',
            color: '#ffffff',
            padding: '16px 20px',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            flexShrink: 0,
            borderBottom: '1px solid #334155',
          }}
        >
          <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
            <div
              style={{
                width: '36px',
                height: '36px',
                borderRadius: '8px',
                background: 'rgba(56, 189, 248, 0.15)',
                color: '#38bdf8',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                border: '1px solid rgba(56, 189, 248, 0.3)',
              }}
            >
              <Activity size={18} />
            </div>
            <div>
              <div style={{ fontWeight: 700, fontSize: '15px', color: '#ffffff' }}>
                Activity & Transaction Log
              </div>
              <p style={{ margin: '2px 0 0', fontSize: '11.5px', color: '#94a3b8' }}>
                Organisation: <strong style={{ color: '#e2e8f0' }}>{orgName}</strong>
              </p>
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <a
              href={`${auditApi.exportAuditUrl()}?client_id=${orgId || ''}&org_id=${orgId || ''}`}
              target="_blank"
              rel="noopener noreferrer"
              style={{
                display: 'inline-flex',
                alignItems: 'center',
                gap: '5px',
                padding: '4px 10px',
                background: 'rgba(255, 255, 255, 0.1)',
                border: '1px solid rgba(255, 255, 255, 0.2)',
                borderRadius: '5px',
                color: '#ffffff',
                fontSize: '11px',
                fontWeight: 600,
                textDecoration: 'none',
              }}
              title="Download audit log as CSV"
            >
              <Download size={12} />
              <span>Export CSV</span>
            </a>

            <button
              onClick={onClose}
              style={{
                background: 'rgba(255, 255, 255, 0.1)',
                border: 'none',
                borderRadius: '5px',
                width: '28px',
                height: '28px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                color: '#cbd5e1',
                cursor: 'pointer',
              }}
            >
              <X size={16} />
            </button>
          </div>
        </div>

        {/* Toolbar / Search */}
        <div
          style={{
            padding: '10px 16px',
            background: '#f8fafc',
            borderBottom: '1px solid #e2e8f0',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
            gap: '10px',
            flexShrink: 0,
          }}
        >
          <Input
            size="sm"
            variant="light"
            placeholder="Search transactions by code, action, user..."
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
            icon={<Search size={12} />}
            clearable
            style={{ width: '320px' }}
          />

          <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
            <span style={{ fontSize: '11px', fontWeight: 600, color: '#64748b' }}>
              Total: {totalCount}
            </span>
            <Button
              size="icon-sm"
              variant="outline"
              onClick={fetchTransactions}
              title="Refresh log"
              icon={<RefreshCw size={12} className={loading ? 'spin-infinite' : ''} />}
            />
          </div>
        </div>

        {/* Drawer Body: Transactions List */}
        <div
          style={{
            flex: 1,
            overflowY: 'auto',
            padding: '16px',
            display: 'flex',
            flexDirection: 'column',
            gap: '10px',
            background: '#f1f5f9',
          }}
        >
          {loading ? (
            <div style={{ padding: '40px', textAlign: 'center', color: '#64748b' }}>
              <RefreshCw size={20} className="spin-infinite" style={{ margin: '0 auto 8px', display: 'block' }} />
              <span style={{ fontSize: '12px' }}>Loading organisation logs…</span>
            </div>
          ) : filteredTx.length === 0 ? (
            <div
              style={{
                padding: '50px 20px',
                textAlign: 'center',
                background: '#ffffff',
                borderRadius: '8px',
                border: '1px solid #e2e8f0',
              }}
            >
              <FileText size={32} style={{ color: '#94a3b8', margin: '0 auto 10px', display: 'block' }} />
              <h4 style={{ margin: '0 0 4px', fontSize: '14px', fontWeight: 600, color: '#334155' }}>
                No Activity Records Found
              </h4>
              <p style={{ margin: 0, fontSize: '12px', color: '#64748b' }}>
                {search ? `No transactions match "${search}"` : 'There are no batch transactions or audit entries recorded for this organisation yet.'}
              </p>
            </div>
          ) : (
            filteredTx.map((tx) => {
              const isExpanded = expandedTxId === tx.id;
              const isReverted = tx.is_reverted || tx.status === 'reverted';
              const canReverse = tx.can_reverse && !isReverted;

              return (
                <div
                  key={tx.id}
                  style={{
                    background: '#ffffff',
                    border: '1px solid #e2e8f0',
                    borderRadius: '8px',
                    boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                    overflow: 'hidden',
                  }}
                >
                  {/* Card Header */}
                  <div
                    onClick={() => handleToggleExpand(tx.id)}
                    style={{
                      padding: '12px 14px',
                      cursor: 'pointer',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'space-between',
                      background: isExpanded ? '#f8fafc' : '#ffffff',
                      borderBottom: isExpanded ? '1px solid #e2e8f0' : 'none',
                    }}
                  >
                    <div style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                      <div
                        style={{
                          width: '30px',
                          height: '30px',
                          borderRadius: '6px',
                          background: isReverted ? '#fee2e2' : '#eff6ff',
                          color: isReverted ? '#dc2626' : '#2563eb',
                          display: 'flex',
                          alignItems: 'center',
                          justifyContent: 'center',
                          flexShrink: 0,
                        }}
                      >
                        {isReverted ? <RotateCcw size={14} /> : <Layers size={14} />}
                      </div>

                      <div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                          <span style={{ fontWeight: 700, fontSize: '12.5px', color: '#0f172a' }}>
                            {tx.transaction_code || `TX #${tx.id}`}
                          </span>
                          <span
                            style={{
                              fontSize: '10px',
                              fontWeight: 700,
                              padding: '2px 6px',
                              borderRadius: '4px',
                              background: '#f1f5f9',
                              color: '#334155',
                              border: '1px solid #cbd5e1',
                              textTransform: 'uppercase',
                            }}
                          >
                            {tx.action_display || tx.action || 'Action'}
                          </span>
                          {isReverted ? (
                            <span
                              style={{
                                fontSize: '10px',
                                fontWeight: 700,
                                padding: '2px 6px',
                                borderRadius: '4px',
                                background: '#fee2e2',
                                color: '#b91c1c',
                                border: '1px solid #fca5a5',
                              }}
                            >
                              REVERTED
                            </span>
                          ) : (
                            <span
                              style={{
                                fontSize: '10px',
                                fontWeight: 700,
                                padding: '2px 6px',
                                borderRadius: '4px',
                                background: '#dcfce7',
                                color: '#15803d',
                                border: '1px solid #86efac',
                              }}
                            >
                              COMPLETED
                            </span>
                          )}
                        </div>

                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '10px',
                            marginTop: '4px',
                            fontSize: '11px',
                            color: '#64748b',
                          }}
                        >
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                            <Clock size={11} /> {formatDT(tx.created_at)}
                          </span>
                          <span>•</span>
                          <span style={{ display: 'inline-flex', alignItems: 'center', gap: '3px' }}>
                            <User size={11} /> {tx.user_name || 'System'}
                          </span>
                          {tx.card_count ? (
                            <>
                              <span>•</span>
                              <span style={{ fontWeight: 600, color: '#2563eb' }}>
                                {tx.card_count} cards affected
                              </span>
                            </>
                          ) : null}
                        </div>
                      </div>
                    </div>

                    <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {canReverse && (
                        <Button
                          size="sm"
                          variant="danger"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleReverseTransaction(tx.id, tx.transaction_code);
                          }}
                          disabled={reversing}
                          icon={<RotateCcw size={11} />}
                          title="Reverse this batch transaction"
                        >
                          Revert
                        </Button>
                      )}

                      <button
                        type="button"
                        style={{
                          background: 'none',
                          border: 'none',
                          color: '#64748b',
                          cursor: 'pointer',
                          display: 'flex',
                          alignItems: 'center',
                          padding: '4px',
                        }}
                      >
                        {isExpanded ? <ChevronUp size={16} /> : <ChevronDown size={16} />}
                      </button>
                    </div>
                  </div>

                  {/* Expanded Detail Panel */}
                  {isExpanded && (
                    <div style={{ padding: '12px 16px', background: '#fafafa' }}>
                      {/* State Transition Badge */}
                      {(tx.prev_status || tx.new_status) && (
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            gap: '8px',
                            padding: '6px 10px',
                            background: '#ffffff',
                            border: '1px solid #e2e8f0',
                            borderRadius: '6px',
                            marginBottom: '10px',
                            fontSize: '11.5px',
                          }}
                        >
                          <span style={{ fontWeight: 600, color: '#64748b' }}>Status Transition:</span>
                          <span
                            style={{
                              fontWeight: 700,
                              padding: '2px 6px',
                              borderRadius: '4px',
                              background: '#f1f5f9',
                              color: '#334155',
                            }}
                          >
                            {(tx.prev_status || 'initial').toUpperCase()}
                          </span>
                          <ArrowRight size={13} style={{ color: '#94a3b8' }} />
                          <span
                            style={{
                              fontWeight: 700,
                              padding: '2px 6px',
                              borderRadius: '4px',
                              background: '#dbeafe',
                              color: '#1d4ed8',
                            }}
                          >
                            {(tx.new_status || 'updated').toUpperCase()}
                          </span>
                        </div>
                      )}

                      {/* Notes / Description */}
                      {tx.notes && (
                        <div style={{ fontSize: '11.5px', color: '#475569', marginBottom: '8px' }}>
                          <strong>Notes:</strong> {tx.notes}
                        </div>
                      )}

                      {/* Affected Cards List */}
                      <div style={{ marginTop: '8px' }}>
                        <div
                          style={{
                            display: 'flex',
                            alignItems: 'center',
                            justifyContent: 'space-between',
                            marginBottom: '6px',
                          }}
                        >
                          <span style={{ fontSize: '11px', fontWeight: 700, color: '#334155' }}>
                            Affected Cards List:
                          </span>
                          <input
                            type="text"
                            placeholder="Filter cards in this TX…"
                            value={cardSearch}
                            onChange={(e) => setCardSearch(e.target.value)}
                            style={{
                              fontSize: '11px',
                              padding: '2px 6px',
                              borderRadius: '4px',
                              border: '1px solid #cbd5e1',
                              outline: 'none',
                              width: '160px',
                            }}
                          />
                        </div>

                        {detailLoading ? (
                          <div style={{ padding: '16px', textAlign: 'center', color: '#64748b', fontSize: '11px' }}>
                            Loading card details…
                          </div>
                        ) : txDetail?.cards?.length > 0 ? (
                          <div
                            style={{
                              maxHeight: '180px',
                              overflowY: 'auto',
                              border: '1px solid #e2e8f0',
                              borderRadius: '6px',
                              background: '#ffffff',
                            }}
                          >
                            <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '11px' }}>
                              <thead>
                                <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #e2e8f0' }}>
                                  <th style={{ padding: '4px 8px', textAlign: 'left' }}>S.N.</th>
                                  <th style={{ padding: '4px 8px', textAlign: 'left' }}>Identifier / Name</th>
                                  <th style={{ padding: '4px 8px', textAlign: 'center' }}>Transition</th>
                                  <th style={{ padding: '4px 8px', textAlign: 'center' }}>Conflicted</th>
                                </tr>
                              </thead>
                              <tbody>
                                {txDetail.cards.map((c, cIdx) => (
                                  <tr key={c.id || cIdx} style={{ borderBottom: '1px solid #f8fafc' }}>
                                    <td style={{ padding: '4px 8px', color: '#64748b' }}>{cIdx + 1}</td>
                                    <td style={{ padding: '4px 8px', fontWeight: 600, color: '#0f172a' }}>
                                      {c.name || c.identifier || `Card #${c.card_id || c.id}`}
                                    </td>
                                    <td style={{ padding: '4px 8px', textAlign: 'center', color: '#475569' }}>
                                      {c.prev_status || '—'} → {c.new_status || '—'}
                                    </td>
                                    <td style={{ padding: '4px 8px', textAlign: 'center' }}>
                                      {c.is_conflicted ? (
                                        <span style={{ color: '#dc2626', fontWeight: 700 }}>Yes</span>
                                      ) : (
                                        <span style={{ color: '#16a34a', fontWeight: 600 }}>No</span>
                                      )}
                                    </td>
                                  </tr>
                                ))}
                              </tbody>
                            </table>
                          </div>
                        ) : (
                          <div style={{ padding: '12px', textAlign: 'center', color: '#94a3b8', fontSize: '11px' }}>
                            No card-level audit entries available.
                          </div>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              );
            })
          )}
        </div>
      </div>
    </>
  );
}
