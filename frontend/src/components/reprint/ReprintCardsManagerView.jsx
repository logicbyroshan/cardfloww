import React, { useState, useEffect, useCallback, useMemo } from 'react';
import {
  Printer,
  CheckCircle2,
  Search,
  X,
  RefreshCw,
  Loader2,
  AlertCircle,
  FileCheck,
  RotateCcw,
  XCircle,
  Pencil,
  Eye,
  Filter,
  Layers,
  ChevronDown,
  ChevronRight,
  Clock,
  User,
  ShieldCheck,
  History,
  Building2,
  Table as TableIcon,
} from 'lucide-react';
import WatermarkLogo from '../common/WatermarkLogo';
import Button from '../common/Button';
import Input from '../common/Input';
import CustomSelect from '../common/CustomSelect';
import { reprintApi, tableApi, clientApi } from '../../services/api';

const STEPS = [
  { id: 'reprint_list', label: 'Reprint List', icon: Layers, color: '#06b6d4' },
  { id: 'request_list', label: 'Requested List', icon: RotateCcw, color: '#8b5cf6' },
  { id: 'confirmed', label: 'Confirmed List', icon: CheckCircle2, color: '#10b981' },
];

export default function ReprintCardsManagerView({ addToast }) {
  const [currentStep, setCurrentStep] = useState('reprint_list');
  const [clients, setClients] = useState([]);
  const [selectedClientId, setSelectedClientId] = useState('');
  const [tables, setTables] = useState([]);
  const [selectedTableId, setSelectedTableId] = useState('');

  const [stepCounts, setStepCounts] = useState({
    reprint_list: 0,
    request_list: 0,
    confirmed: 0,
    download_list: 0,
  });

  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(false);
  const [search, setSearch] = useState('');
  const [selectedIds, setSelectedIds] = useState(new Set());
  const [actionLoading, setActionLoading] = useState(false);

  // Edit / Request Modal State
  const [editModalCard, setEditModalCard] = useState(null);
  const [editFormData, setEditFormData] = useState({});
  const [editReason, setEditReason] = useState('');
  const [submittingRequest, setSubmittingRequest] = useState(false);

  // Changes Preview Modal State
  const [changesPreviewItem, setChangesPreviewItem] = useState(null);

  // 1. Fetch Clients on Mount
  useEffect(() => {
    let isMounted = true;
    (async () => {
      try {
        const res = await clientApi.list();
        const clientList = res?.clients || res?.data || (Array.isArray(res) ? res : []);
        if (isMounted) {
          setClients(clientList);
          if (clientList.length > 0) {
            setSelectedClientId(String(clientList[0].id));
          }
        }
      } catch (err) {
        console.warn('Failed to load clients:', err);
      }
    })();
    return () => {
      isMounted = false;
    };
  }, []);

  // 2. Fetch Tables when Client changes
  useEffect(() => {
    if (!selectedClientId) {
      setTables([]);
      setSelectedTableId('');
      return;
    }
    let isMounted = true;
    (async () => {
      try {
        const res = await tableApi.list(selectedClientId);
        const tblList = res?.tables || res?.data || (Array.isArray(res) ? res : []);
        if (isMounted) {
          setTables(tblList);
          if (tblList.length > 0) {
            setSelectedTableId(String(tblList[0].id));
          } else {
            setSelectedTableId('');
          }
        }
      } catch (err) {
        console.warn('Failed to load tables for client:', err);
        if (isMounted) {
          setTables([]);
          setSelectedTableId('');
        }
      }
    })();
    return () => {
      isMounted = false;
    };
  }, [selectedClientId]);

  // 3. Fetch Step Counts when Table changes
  const loadStepCounts = useCallback(async () => {
    if (!selectedTableId) return;
    try {
      const counts = await reprintApi.getStepCounts(selectedTableId);
      if (counts?.status === 'ok') {
        setStepCounts({
          reprint_list: counts.reprint_list || 0,
          request_list: counts.request_list || 0,
          confirmed: counts.confirmed || 0,
          download_list: counts.download_list || 0,
        });
      }
    } catch (err) {
      console.warn('Failed to load step counts:', err);
    }
  }, [selectedTableId]);

  // 4. Fetch Items for Active Step
  const loadItems = useCallback(async () => {
    if (!selectedTableId) {
      setItems([]);
      return;
    }
    setLoading(true);
    setSelectedIds(new Set());
    try {
      let res;
      if (currentStep === 'reprint_list') {
        res = await reprintApi.getReprintList(selectedTableId, { q: search });
      } else if (currentStep === 'request_list') {
        res = await reprintApi.getRequestList(selectedTableId, { q: search });
      } else {
        res = await reprintApi.getConfirmedList(selectedTableId, { q: search });
      }

      if (res?.status === 'ok') {
        setItems(res.items || []);
      } else {
        setItems([]);
      }
      loadStepCounts();
    } catch (err) {
      console.warn('Failed to load reprint items:', err);
      setItems([]);
    } finally {
      setLoading(false);
    }
  }, [selectedTableId, currentStep, search, loadStepCounts]);

  useEffect(() => {
    loadItems();
  }, [loadItems]);

  // Selection helpers
  const handleToggleSelect = (id) => {
    setSelectedIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  const handleSelectAll = () => {
    if (selectedIds.size === items.length) {
      setSelectedIds(new Set());
    } else {
      const idKey = currentStep === 'reprint_list' ? 'card_id' : 'rr_id';
      setSelectedIds(new Set(items.map((it) => it[idKey])));
    }
  };

  // Open Edit & Request Modal
  const openEditModal = (cardItem) => {
    setEditModalCard(cardItem);
    const initialFields = {};
    (cardItem.ordered_fields || []).forEach((f) => {
      initialFields[f.name] = f.value || '';
    });
    setEditFormData(initialFields);
    setEditReason(cardItem.reason || '');
  };

  // Submit Reprint Request with optional edits
  const handleSaveAndRequestReprint = async () => {
    if (!editModalCard || !selectedTableId) return;
    setSubmittingRequest(true);

    try {
      const cardId = editModalCard.card_id;
      const initialFields = editModalCard.field_data || {};
      const changes = {};

      // Compute changed fields diff
      Object.entries(editFormData).forEach(([k, val]) => {
        if (String(val ?? '').trim() !== String(initialFields[k] ?? '').trim()) {
          changes[k] = val;
        }
      });

      const payload = {
        card_ids: [cardId],
        reason: editReason.trim() || 'Reprint request with updates',
        changes: Object.keys(changes).length > 0 ? { [String(cardId)]: changes } : {},
      };

      const res = await reprintApi.requestReprint(selectedTableId, payload);
      if (res?.status === 'ok') {
        addToast?.(res.message || 'Reprint request submitted successfully', 'success');
        setEditModalCard(null);
        loadItems();
      } else {
        addToast?.(res?.message || 'Failed to submit request', 'danger');
      }
    } catch (err) {
      addToast?.('Error submitting reprint request: ' + (err.response?.data?.message || err.message), 'danger');
    } finally {
      setSubmittingRequest(false);
    }
  };

  // Bulk Request Selected (Reprint List)
  const handleBulkRequest = async () => {
    if (selectedIds.size === 0 || !selectedTableId) return;
    setActionLoading(true);
    try {
      const payload = {
        card_ids: Array.from(selectedIds),
        reason: 'Bulk reprint request',
      };
      const res = await reprintApi.requestReprint(selectedTableId, payload);
      if (res?.status === 'ok') {
        addToast?.(res.message || `${selectedIds.size} card(s) requested for reprint`, 'success');
        loadItems();
      } else {
        addToast?.(res?.message || 'Request failed', 'danger');
      }
    } catch (err) {
      addToast?.('Bulk request error: ' + (err.response?.data?.message || err.message), 'danger');
    } finally {
      setActionLoading(false);
    }
  };

  // Admin Confirm Selected (Requested List)
  const handleConfirmSelected = async () => {
    if (selectedIds.size === 0 || !selectedTableId) return;
    setActionLoading(true);
    try {
      const res = await reprintApi.confirmReprint(selectedTableId, Array.from(selectedIds));
      if (res?.status === 'ok') {
        addToast?.(res.message || `${selectedIds.size} request(s) confirmed and applied`, 'success');
        loadItems();
      } else {
        addToast?.(res?.message || 'Confirmation failed', 'danger');
      }
    } catch (err) {
      addToast?.('Confirm error: ' + (err.response?.data?.message || err.message), 'danger');
    } finally {
      setActionLoading(false);
    }
  };

  // Admin Reject Selected (Requested List)
  const handleRejectSelected = async () => {
    if (selectedIds.size === 0 || !selectedTableId) return;
    setActionLoading(true);
    try {
      const res = await reprintApi.rejectReprint(selectedTableId, Array.from(selectedIds), 'Cancelled by admin');
      if (res?.status === 'ok') {
        addToast?.(res.message || `${selectedIds.size} request(s) returned to reprint list`, 'warning');
        loadItems();
      } else {
        addToast?.(res?.message || 'Rejection failed', 'danger');
      }
    } catch (err) {
      addToast?.('Reject error: ' + (err.response?.data?.message || err.message), 'danger');
    } finally {
      setActionLoading(false);
    }
  };

  // Footer data count dispatch
  useEffect(() => {
    const totalCount = items.length;
    const selCount = selectedIds.size;
    const selectedText = selCount > 0 ? `Selected: ${selCount} of ${totalCount}` : '';
    window.dispatchEvent(
      new CustomEvent('cardflow:data-count', {
        detail: {
          text: `Total: ${totalCount}`,
          selectedText,
          count: totalCount,
        },
      })
    );
  }, [items.length, selectedIds.size]);

  const currentTable = useMemo(() => {
    return tables.find((t) => String(t.id) === String(selectedTableId));
  }, [tables, selectedTableId]);

  return (
    <div
      className="view-container"
      style={{
        display: 'flex',
        flexDirection: 'column',
        height: '100%',
        overflow: 'hidden',
        background: '#f8fafc',
      }}
    >
      {/* ── CLIENT & TABLE SELECTOR BAR ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          padding: '8px 16px',
          background: '#ffffff',
          borderBottom: '1px solid #e2e8f0',
          gap: '12px',
          flexWrap: 'wrap',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: '14px', flexWrap: 'wrap' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#475569', fontSize: '13px', fontWeight: 600 }}>
            <Building2 size={16} style={{ color: '#2563eb' }} />
            <span>Client:</span>
            <div style={{ width: '200px' }}>
              <CustomSelect
                size="sm"
                value={selectedClientId}
                onChange={(val) => setSelectedClientId(val)}
                options={clients.map((c) => ({
                  value: c.id,
                  label: c.name || c.school_name || c.username,
                }))}
              />
            </div>
          </div>

          <div style={{ display: 'flex', alignItems: 'center', gap: '6px', color: '#475569', fontSize: '13px', fontWeight: 600 }}>
            <TableIcon size={16} style={{ color: '#0d9488' }} />
            <span>Table:</span>
            <div style={{ width: '200px' }}>
              <CustomSelect
                size="sm"
                value={selectedTableId}
                onChange={(val) => setSelectedTableId(val)}
                disabled={tables.length === 0}
                placeholder={tables.length === 0 ? 'No Tables' : 'Select Table'}
                options={tables.map((t) => ({
                  value: t.id,
                  label: t.name,
                }))}
              />
            </div>
          </div>
        </div>

        {/* Step Counts Pill */}
        <div style={{ display: 'flex', alignItems: 'center', gap: '6px', fontSize: '11px', color: '#64748b' }}>
          <span style={{ padding: '2px 8px', borderRadius: '12px', background: '#ecfeff', color: '#0891b2', fontWeight: 600 }}>
            Reprint: {stepCounts.reprint_list}
          </span>
          <span style={{ padding: '2px 8px', borderRadius: '12px', background: '#f5f3ff', color: '#7c3aed', fontWeight: 600 }}>
            Requested: {stepCounts.request_list}
          </span>
          <span style={{ padding: '2px 8px', borderRadius: '12px', background: '#ecfdf5', color: '#059669', fontWeight: 600 }}>
            Confirmed: {stepCounts.confirmed}
          </span>
        </div>
      </div>

      {/* ── ACTION BAR & STEP TABS ── */}
      <div className="action-bar" style={{ borderBottom: '1px solid #e2e8f0' }}>
        <div className="action-bar-left">
          {/* Step Tabs */}
          <div
            className="status-tabs"
            style={{
              display: 'flex',
              alignItems: 'center',
              background: '#f1f5f9',
              borderRadius: '8px',
              padding: '3px',
              gap: '4px',
            }}
          >
            {STEPS.map(({ id, label, icon: Icon, color }) => {
              const isActive = currentStep === id;
              const count = stepCounts[id] ?? 0;
              return (
                <button
                  key={id}
                  onClick={() => setCurrentStep(id)}
                  className={`status-tab${isActive ? ' active' : ''}`}
                  style={{
                    display: 'inline-flex',
                    alignItems: 'center',
                    gap: '6px',
                    padding: '5px 14px',
                    fontSize: '12px',
                    borderRadius: '6px',
                    border: 'none',
                    cursor: 'pointer',
                    background: isActive ? '#ffffff' : 'transparent',
                    color: isActive ? color : '#64748b',
                    fontWeight: isActive ? 700 : 500,
                    boxShadow: isActive ? '0 1px 3px rgba(0,0,0,0.08)' : 'none',
                    transition: 'all 0.15s ease',
                  }}
                >
                  <Icon size={14} />
                  <span>{label}</span>
                  <span
                    style={{
                      background: isActive ? color : '#cbd5e1',
                      color: '#ffffff',
                      borderRadius: '10px',
                      padding: '1px 6px',
                      fontSize: '10px',
                      fontWeight: 700,
                      marginLeft: '2px',
                    }}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>

          <div className="action-divider" />

          {/* Search Box */}
          <Input
            size="sm"
            variant="dark"
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            onClear={() => setSearch('')}
            placeholder={`Search ${currentStep.replace('_', ' ')}...`}
            icon={<Search size={13} />}
            clearable
            style={{ width: '220px' }}
          />
        </div>

        {/* Action Buttons Right */}
        <div className="action-bar-right">
          <div className="actions" style={{ display: 'flex', gap: '8px' }}>
            {currentStep === 'reprint_list' && (
              <Button
                size="sm"
                variant="primary"
                disabled={selectedIds.size === 0 || actionLoading}
                loading={actionLoading}
                onClick={handleBulkRequest}
                icon={<RotateCcw size={13} />}
              >
                Request Selected ({selectedIds.size})
              </Button>
            )}

            {currentStep === 'request_list' && (
              <>
                <Button
                  size="sm"
                  variant="success"
                  disabled={selectedIds.size === 0 || actionLoading}
                  loading={actionLoading}
                  onClick={handleConfirmSelected}
                  icon={<CheckCircle2 size={13} />}
                >
                  Confirm Selected ({selectedIds.size})
                </Button>
                <Button
                  size="sm"
                  variant="danger"
                  disabled={selectedIds.size === 0 || actionLoading}
                  loading={actionLoading}
                  onClick={handleRejectSelected}
                  icon={<XCircle size={13} />}
                >
                  Reject to Reprint ({selectedIds.size})
                </Button>
              </>
            )}

            <Button
              size="icon-sm"
              variant="neutral"
              onClick={loadItems}
              disabled={loading}
              title="Refresh list"
              icon={<RefreshCw size={13} className={loading ? 'animate-spin' : ''} />}
            />
          </div>
        </div>
      </div>

      {/* ── TABLE CONTAINER ── */}
      <div
        className="table-wrapper"
        style={{
          flex: 1,
          overflow: 'auto',
          display: 'flex',
          flexDirection: 'column',
          minHeight: 0,
          position: 'relative',
        }}
      >
        <WatermarkLogo />
        <table className="data-table" style={{ flexShrink: 0, width: '100%' }}>
          <thead>
            <tr>
              <th style={{ width: '40px', textAlign: 'center' }}>
                <input
                  type="checkbox"
                  checked={items.length > 0 && selectedIds.size === items.length}
                  onChange={handleSelectAll}
                />
              </th>
              <th style={{ width: '45px', textAlign: 'center' }}>S. No.</th>
              <th>Student / Card Information</th>

              {currentStep === 'reprint_list' && (
                <>
                  <th style={{ width: '150px', textAlign: 'center' }}>Reprint Status</th>
                  <th style={{ width: '130px', textAlign: 'center' }}>Reprint History</th>
                  <th style={{ width: '160px', textAlign: 'center' }}>Actions</th>
                </>
              )}

              {currentStep === 'request_list' && (
                <>
                  <th style={{ width: '180px' }}>Reprint Reason</th>
                  <th style={{ width: '120px', textAlign: 'center' }}>Edits Staged</th>
                  <th style={{ width: '140px' }}>Requested By</th>
                  <th style={{ width: '140px', textAlign: 'center' }}>Requested Date</th>
                </>
              )}

              {currentStep === 'confirmed' && (
                <>
                  <th style={{ width: '130px', textAlign: 'center' }}>Reprint Badge</th>
                  <th style={{ width: '180px' }}>Reason</th>
                  <th style={{ width: '140px' }}>Confirmed By</th>
                  <th style={{ width: '140px', textAlign: 'center' }}>Confirmed Date</th>
                </>
              )}
            </tr>
          </thead>
          <tbody>
            {loading
              ? Array.from({ length: 10 }).map((_, i) => (
                  <tr key={i} className="skeleton-row">
                    <td><div className="skeleton" style={{ width: '16px', height: '16px', margin: '0 auto' }} /></td>
                    <td><div className="skeleton" style={{ width: '20px', height: '12px', margin: '0 auto' }} /></td>
                    <td><div className="skeleton" style={{ height: '14px', width: `${60 + (i % 4) * 8}%` }} /></td>
                    <td><div className="skeleton" style={{ height: '20px', width: '100px', margin: '0 auto' }} /></td>
                    <td><div className="skeleton" style={{ height: '14px', width: '80px', margin: '0 auto' }} /></td>
                    <td><div className="skeleton" style={{ height: '24px', width: '120px', margin: '0 auto' }} /></td>
                  </tr>
                ))
              : items.map((item, idx) => {
                  const idKey = currentStep === 'reprint_list' ? item.card_id : item.rr_id;
                  const isChecked = selectedIds.has(idKey);
                  const orderedFields = item.ordered_fields || [];
                  const studentName =
                    orderedFields.find((f) => f.name.toUpperCase().includes('NAME'))?.value ||
                    item.field_data?.NAME ||
                    item.field_data?.Student_Name ||
                    `Card #${item.card_id}`;
                  const rollNo =
                    orderedFields.find((f) => f.name.toUpperCase().includes('ROLL'))?.value ||
                    item.field_data?.ROLL_NO ||
                    '';
                  const className =
                    orderedFields.find((f) => f.name.toUpperCase().includes('CLASS'))?.value ||
                    item.field_data?.CLASS ||
                    '';

                  return (
                    <tr
                      key={idKey || idx}
                      className={isChecked ? 'selected' : ''}
                      style={{
                        background: isChecked ? '#eff6ff' : idx % 2 === 0 ? '#ffffff' : '#fcfcfd',
                        transition: 'background 0.1s',
                      }}
                    >
                      <td style={{ textAlign: 'center' }}>
                        <input
                          type="checkbox"
                          checked={isChecked}
                          onChange={() => handleToggleSelect(idKey)}
                        />
                      </td>
                      <td style={{ textAlign: 'center', fontWeight: 600, color: '#64748b', fontSize: '11px' }}>
                        {idx + 1}
                      </td>

                      {/* Student details */}
                      <td>
                        <div style={{ display: 'flex', flexDirection: 'column', gap: '2px' }}>
                          <span style={{ fontWeight: 700, color: '#1e293b', fontSize: '13px' }}>
                            {studentName}
                          </span>
                          <div style={{ display: 'flex', gap: '8px', fontSize: '11px', color: '#64748b' }}>
                            <span>Card ID: #{item.card_id}</span>
                            {className && <span>• Class: <strong>{className}</strong></span>}
                            {rollNo && <span>• Roll: <strong>{rollNo}</strong></span>}
                          </div>
                        </div>
                      </td>

                      {/* Step 1: Reprint List columns */}
                      {currentStep === 'reprint_list' && (
                        <>
                          <td style={{ textAlign: 'center' }}>
                            {item.is_in_request_queue ? (
                              <span
                                style={{
                                  display: 'inline-block',
                                  padding: '3px 8px',
                                  borderRadius: '12px',
                                  background: '#fef3c7',
                                  color: '#b45309',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                }}
                              >
                                In Request Queue
                              </span>
                            ) : (
                              <span
                                style={{
                                  display: 'inline-block',
                                  padding: '3px 8px',
                                  borderRadius: '12px',
                                  background: '#ecfeff',
                                  color: '#0e7490',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                }}
                              >
                                Downloaded
                              </span>
                            )}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {item.reprint_count > 0 ? (
                              <span
                                style={{
                                  padding: '3px 8px',
                                  borderRadius: '12px',
                                  background: '#ecfdf5',
                                  color: '#059669',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                }}
                              >
                                {item.reprint_count}x Reprinted
                              </span>
                            ) : (
                              <span style={{ color: '#94a3b8', fontSize: '11px' }}>Original</span>
                            )}
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            <div style={{ display: 'flex', justifyContent: 'center', gap: '6px' }}>
                              <button
                                onClick={() => openEditModal(item)}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '4px',
                                  padding: '4px 10px',
                                  borderRadius: '6px',
                                  border: '1px solid #cbd5e1',
                                  background: '#ffffff',
                                  color: '#2563eb',
                                  fontSize: '11px',
                                  fontWeight: 600,
                                  cursor: 'pointer',
                                }}
                                title="Edit student info and request reprint"
                              >
                                <Pencil size={11} /> Edit & Request
                              </button>
                            </div>
                          </td>
                        </>
                      )}

                      {/* Step 2: Requested List columns */}
                      {currentStep === 'request_list' && (
                        <>
                          <td>
                            <span
                              style={{
                                display: 'inline-block',
                                padding: '3px 8px',
                                borderRadius: '6px',
                                background: '#fef3c7',
                                color: '#92400e',
                                fontSize: '11px',
                                fontWeight: 600,
                              }}
                            >
                              {item.reason}
                            </span>
                          </td>
                          <td style={{ textAlign: 'center' }}>
                            {item.has_changes ? (
                              <button
                                onClick={() => setChangesPreviewItem(item)}
                                style={{
                                  display: 'inline-flex',
                                  alignItems: 'center',
                                  gap: '4px',
                                  padding: '2px 8px',
                                  borderRadius: '12px',
                                  background: '#ede9fe',
                                  color: '#6d28d9',
                                  fontSize: '11px',
                                  fontWeight: 700,
                                  border: 'none',
                                  cursor: 'pointer',
                                }}
                              >
                                <Eye size={11} /> View Changes
                              </button>
                            ) : (
                              <span style={{ color: '#94a3b8', fontSize: '11px' }}>No field edits</span>
                            )}
                          </td>
                          <td style={{ fontSize: '12px', color: '#475569' }}>
                            {item.requested_by_name}
                          </td>
                          <td style={{ textAlign: 'center', fontSize: '11px', color: '#64748b' }}>
                            {item.requested_at}
                          </td>
                        </>
                      )}

                      {/* Step 3: Confirmed List columns */}
                      {currentStep === 'confirmed' && (
                        <>
                          <td style={{ textAlign: 'center' }}>
                            <span
                              style={{
                                display: 'inline-block',
                                padding: '3px 10px',
                                borderRadius: '12px',
                                background: '#dcfce7',
                                color: '#15803d',
                                fontSize: '11px',
                                fontWeight: 700,
                              }}
                            >
                              Reprint #{item.reprint_number}
                            </span>
                          </td>
                          <td style={{ fontSize: '12px', color: '#475569' }}>
                            {item.reason}
                          </td>
                          <td style={{ fontSize: '12px', color: '#475569' }}>
                            {item.confirmed_by_name}
                          </td>
                          <td style={{ textAlign: 'center', fontSize: '11px', color: '#64748b' }}>
                            {item.confirmed_at}
                          </td>
                        </>
                      )}
                    </tr>
                  );
                })}
          </tbody>
        </table>

        {/* Empty State */}
        {!loading && items.length === 0 && (
          <div
            style={{
              flex: 1,
              display: 'flex',
              flexDirection: 'column',
              alignItems: 'center',
              justifyContent: 'center',
              padding: '40px 20px',
              textAlign: 'center',
              minHeight: '240px',
            }}
          >
            <div
              style={{
                width: '64px',
                height: '64px',
                borderRadius: '50%',
                background: 'linear-gradient(135deg, #eff6ff 0%, #dbeafe 100%)',
                color: '#2563eb',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                boxShadow: '0 4px 14px rgba(37,99,235,0.12)',
                border: '1px solid #bfdbfe',
                marginBottom: '12px',
              }}
            >
              <Printer size={30} />
            </div>
            <div style={{ maxWidth: '340px' }}>
              <h4 style={{ fontSize: '16px', fontWeight: 700, color: '#0f172a', margin: '0 0 6px 0' }}>
                No Cards in {STEPS.find((s) => s.id === currentStep)?.label}
              </h4>
              <p style={{ fontSize: '12px', color: '#64748b', margin: 0, lineHeight: 1.5 }}>
                {search ? `No cards match "${search}"` : 'Select a table or change tabs to view cards.'}
              </p>
            </div>
          </div>
        )}
      </div>

      {/* ── EDIT & REQUEST MODAL ── */}
      {editModalCard && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#ffffff',
              borderRadius: '12px',
              width: '100%',
              maxWidth: '560px',
              maxHeight: '85vh',
              display: 'flex',
              flexDirection: 'column',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04)',
              overflow: 'hidden',
            }}
          >
            {/* Modal Header */}
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 20px',
                borderBottom: '1px solid #e2e8f0',
                background: '#f8fafc',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Pencil size={18} style={{ color: '#2563eb' }} />
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  Edit Student & Request Reprint
                </h3>
              </div>
              <button
                onClick={() => setEditModalCard(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b' }}
              >
                <X size={18} />
              </button>
            </div>

            {/* Modal Body */}
            <div style={{ padding: '20px', overflowY: 'auto', flex: 1 }}>
              <div style={{ marginBottom: '16px' }}>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#334155', marginBottom: '4px' }}>
                  Reprint Reason <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="text"
                  placeholder="e.g. Lost ID card, Spelling mistake in Name, Photo update"
                  value={editReason}
                  onChange={(e) => setEditReason(e.target.value)}
                  style={{
                    width: '100%',
                    padding: '8px 12px',
                    borderRadius: '6px',
                    border: '1px solid #cbd5e1',
                    fontSize: '13px',
                    outline: 'none',
                  }}
                />
              </div>

              <div style={{ borderTop: '1px solid #e2e8f0', paddingTop: '14px' }}>
                <h4 style={{ margin: '0 0 12px 0', fontSize: '13px', fontWeight: 700, color: '#475569' }}>
                  Student Data Fields (Make changes if required):
                </h4>
                <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
                  {(editModalCard.ordered_fields || []).map((f) => (
                    <div key={f.name}>
                      <label style={{ display: 'block', fontSize: '11px', fontWeight: 600, color: '#64748b', marginBottom: '3px' }}>
                        {f.label || f.name}
                      </label>
                      <input
                        type="text"
                        value={editFormData[f.name] ?? ''}
                        onChange={(e) =>
                          setEditFormData((prev) => ({
                            ...prev,
                            [f.name]: e.target.value,
                          }))
                        }
                        style={{
                          width: '100%',
                          padding: '6px 10px',
                          borderRadius: '6px',
                          border: '1px solid #cbd5e1',
                          fontSize: '12px',
                          outline: 'none',
                        }}
                      />
                    </div>
                  ))}
                </div>
              </div>
            </div>

            {/* Modal Footer */}
            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                alignItems: 'center',
                gap: '10px',
                padding: '12px 20px',
                borderTop: '1px solid #e2e8f0',
                background: '#f8fafc',
              }}
            >
              <button
                onClick={() => setEditModalCard(null)}
                style={{
                  padding: '6px 14px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  background: '#ffffff',
                  color: '#475569',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Cancel
              </button>
              <button
                disabled={submittingRequest}
                onClick={handleSaveAndRequestReprint}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: '6px',
                  padding: '6px 16px',
                  borderRadius: '6px',
                  border: 'none',
                  background: '#2563eb',
                  color: '#ffffff',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                {submittingRequest ? <Loader2 size={14} className="animate-spin" /> : <RotateCcw size={14} />}
                Submit Reprint Request
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ── VIEW CHANGES DIFF MODAL ── */}
      {changesPreviewItem && (
        <div
          style={{
            position: 'fixed',
            inset: 0,
            background: 'rgba(15, 23, 42, 0.6)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            zIndex: 9999,
            padding: '20px',
          }}
        >
          <div
            style={{
              background: '#ffffff',
              borderRadius: '12px',
              width: '100%',
              maxWidth: '500px',
              boxShadow: '0 20px 25px -5px rgba(0, 0, 0, 0.1)',
              overflow: 'hidden',
            }}
          >
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                padding: '14px 20px',
                borderBottom: '1px solid #e2e8f0',
                background: '#f8fafc',
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                <Eye size={18} style={{ color: '#7c3aed' }} />
                <h3 style={{ margin: 0, fontSize: '15px', fontWeight: 700, color: '#0f172a' }}>
                  Staged Field Updates (Card #{changesPreviewItem.card_id})
                </h3>
              </div>
              <button
                onClick={() => setChangesPreviewItem(null)}
                style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#64748b' }}
              >
                <X size={18} />
              </button>
            </div>

            <div style={{ padding: '20px', maxHeight: '60vh', overflowY: 'auto' }}>
              <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: '12px' }}>
                <thead>
                  <tr style={{ background: '#f1f5f9', borderBottom: '1px solid #cbd5e1' }}>
                    <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 700 }}>Field</th>
                    <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 700, color: '#dc2626' }}>Original</th>
                    <th style={{ padding: '8px 10px', textAlign: 'left', fontWeight: 700, color: '#16a34a' }}>New Value</th>
                  </tr>
                </thead>
                <tbody>
                  {Object.entries(changesPreviewItem.changes || {}).map(([key, newVal]) => {
                    const oldVal = changesPreviewItem.field_data?.[key] || '—';
                    return (
                      <tr key={key} style={{ borderBottom: '1px solid #e2e8f0' }}>
                        <td style={{ padding: '8px 10px', fontWeight: 600, color: '#334155' }}>{key}</td>
                        <td style={{ padding: '8px 10px', color: '#dc2626', textDecoration: 'line-through' }}>{String(oldVal)}</td>
                        <td style={{ padding: '8px 10px', color: '#16a34a', fontWeight: 700 }}>{String(newVal)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>

            <div
              style={{
                display: 'flex',
                justifyContent: 'flex-end',
                padding: '12px 20px',
                borderTop: '1px solid #e2e8f0',
                background: '#f8fafc',
              }}
            >
              <button
                onClick={() => setChangesPreviewItem(null)}
                style={{
                  padding: '6px 16px',
                  borderRadius: '6px',
                  border: '1px solid #cbd5e1',
                  background: '#ffffff',
                  color: '#475569',
                  fontSize: '13px',
                  fontWeight: 600,
                  cursor: 'pointer',
                }}
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
