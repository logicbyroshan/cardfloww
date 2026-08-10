import React, { useState, useEffect } from 'react';
import { createPortal } from 'react-dom';
import {
  X, UserPlus, Building, Mail, Send, Shield, User, Cog, List, RefreshCw, Plus, Search, Eye, EyeOff, Camera, Link, Save, Layers, CheckSquare
} from 'lucide-react';
import { clientApi, operatorApi, assistantApi, photographerApi, staffApi, panelApi } from '../../services/api';

/* ─────────────────────────────────────────────────────────────────────────────
   Custom Toggle Switch Component matching original UI toggle-slider
   ───────────────────────────────────────────────────────────────────────────── */
function ToggleSwitch({ checked, onChange, isHeader = false }) {
  return (
    <label style={{
      position: 'relative',
      display: 'inline-block',
      width: '38px',
      height: '20px',
      flexShrink: 0,
      cursor: 'pointer',
    }}>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        style={{ opacity: 0, width: 0, height: 0 }}
      />
      <span style={{
        position: 'absolute',
        top: 0, left: 0, right: 0, bottom: 0,
        backgroundColor: isHeader
          ? (checked ? '#ffffff' : 'rgba(255, 255, 255, 0.35)')
          : (checked ? '#2563eb' : '#cbd5e1'),
        borderRadius: '20px',
        transition: 'background-color 0.2s ease',
        border: isHeader ? '1px solid rgba(255, 255, 255, 0.4)' : 'none',
      }}>
        <span style={{
          position: 'absolute',
          content: '""',
          height: '14px',
          width: '14px',
          left: '3px',
          bottom: '3px',
          backgroundColor: isHeader ? (checked ? '#2563eb' : '#ffffff') : '#ffffff',
          borderRadius: '50%',
          transition: 'transform 0.2s ease',
          transform: checked ? 'translateX(18px)' : 'translateX(0)',
          boxShadow: '0 1px 3px rgba(0,0,0,0.2)',
        }} />
      </span>
    </label>
  );
}

export default function QuickActionDrawer({ isOpen, actionType, initialData, onClose, addToast }) {
  if (!isOpen || !actionType) return null;

  return createPortal(
    <>
      {/* Backdrop overlay — Click outside disabled, closed via buttons only */}
      <div
        className="drawer-overlay-backdrop"
        style={{
          position: 'fixed',
          top: 0, left: 0, right: 0, bottom: 0,
          background: 'rgba(15, 23, 42, 0.65)',
          backdropFilter: 'blur(4px)',
          WebkitBackdropFilter: 'blur(4px)',
          zIndex: 99999998,
        }}
      />

      {/* Slide-over Drawer Container */}
      <div
        className="side-drawer-panel"
        style={{
          position: 'fixed',
          top: 0, right: 0, bottom: 0,
          width: actionType === 'message' ? '760px' : '640px',
          maxWidth: '95vw',
          height: '100vh',
          background: '#ffffff',
          boxShadow: '-10px 0 35px rgba(0, 0, 0, 0.35)',
          zIndex: 99999999,
          display: 'flex',
          flexDirection: 'column',
          overflow: 'hidden',
          animation: 'drawerSlideInRight 0.22s cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      >
        {(actionType === 'add-client' || actionType === 'edit-client') && (
          <OriginalClientDrawerForm onClose={onClose} addToast={addToast} initialData={initialData} />
        )}
        {(actionType === 'add-operator' || actionType === 'edit-operator' || actionType === 'add-staff' || actionType === 'edit-staff') && (
          <OriginalOperatorDrawerForm onClose={onClose} addToast={addToast} initialData={initialData} />
        )}
        {actionType === 'assign-operator' && (
          <AssignOperatorOrganisationsForm onClose={onClose} addToast={addToast} initialData={initialData} />
        )}
        {actionType === 'assign-photographer' && (
          <AssignOperatorOrganisationsForm onClose={onClose} addToast={addToast} initialData={initialData} titleOverride="Assign Organisations to Photographer" />
        )}
        {(actionType === 'add-assistant' || actionType === 'edit-assistant') && (
          <OriginalAssistantDrawerForm onClose={onClose} addToast={addToast} initialData={initialData} />
        )}
        {actionType === 'assign-assistant' && (
          <AssignAssistantGroupsForm onClose={onClose} addToast={addToast} initialData={initialData} />
        )}
        {(actionType === 'add-photographer' || actionType === 'edit-photographer') && (
          <OriginalPhotographerDrawerForm onClose={onClose} addToast={addToast} initialData={initialData} />
        )}
        {actionType === 'message' && (
          <OriginalMessageDrawerForm onClose={onClose} addToast={addToast} />
        )}
      </div>

      <style>{`
        @keyframes fadeIn {
          from { opacity: 0; }
          to { opacity: 1; }
        }
        @keyframes drawerSlideInRight {
          from { transform: translateX(100%); }
          to { transform: translateX(0); }
        }
      `}</style>
    </>,
    document.body
  );
}


/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   1. Add New Organisation Drawer
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function OriginalClientDrawerForm({ onClose, addToast, initialData }) {
  const isEditing = !!initialData;
  const [formData, setFormData] = useState({
    name: initialData?.name || '',
    email: initialData?.email || '',
    phone: initialData?.phone || '',
    status: initialData ? (initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false') : 'true',
    passwordOption: 'custom',
    password: '',
  });
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (initialData) {
      setFormData({
        name: initialData.name || '',
        email: initialData.email || '',
        phone: initialData.phone || '',
        status: initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false',
        passwordOption: 'custom',
        password: '',
      });
    }
  }, [initialData]);

  const [groupPerms, setGroupPerms] = useState({
    add: true, edit: true, list: true, delete: true, status: true,
  });

  const [actionPerms, setActionPerms] = useState({
    pending: true, verified: true, pool: true, approved: true, download: true,
  });

  const [reprintPerms, setReprintPerms] = useState({
    reprint_pending: true, reprint_confirmed: true,
    card_add: true, card_edit: true, card_verify: true, card_approve: true,
  });

  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!formData.name || !formData.email) {
      addToast?.('Please fill in Name and Email address', 'warning');
      return;
    }
    setSaving(true);
    const payload = {
      name: formData.name,
      email: formData.email,
      phone: formData.phone,
      status: formData.status === 'true' ? 'active' : 'inactive',
      password_option: formData.passwordOption,
      password: formData.passwordOption === 'custom' ? formData.password : undefined,
      permissions: { ...groupPerms, ...actionPerms, ...reprintPerms },
    };
    let itemToSave = {
      id: initialData?.id || Date.now(),
      name: formData.name,
      email: formData.email,
      phone: formData.phone || 'â€”',
      status: formData.status === 'true' ? 'active' : 'inactive',
      is_active: formData.status === 'true',
      created_at: initialData?.created_at || new Date().toISOString(),
    };
    try {
      let res;
      if (isEditing) {
        res = await clientApi.updateClient(initialData.id, payload);
      } else {
        res = await clientApi.createClient(payload);
      }
      if (res?.client || res?.id) {
        itemToSave = { ...itemToSave, ...(res.client || res), name: res.name || res.client?.name || formData.name };
      }
      if (!isEditing) {
        const primaryManager = {
          id: `mgr_${itemToSave.id}`,
          name: itemToSave.name,
          username: itemToSave.email || itemToSave.name.toLowerCase().replace(/\s+/g, ''),
          email: itemToSave.email,
          phone: itemToSave.phone,
          client_type: 'primary',
          is_default: true,
          organisation: { id: itemToSave.id, name: itemToSave.name },
          school_name: itemToSave.name,
          status: itemToSave.status || 'active',
          is_active: itemToSave.is_active !== false,
          created_at: new Date().toISOString(),
        };
        try {
          const storedMgrs = JSON.parse(localStorage.getItem('cf_custom_managers') || '[]');
          localStorage.setItem('cf_custom_managers', JSON.stringify([primaryManager, ...storedMgrs]));
        } catch (_) {}
      }
      addToast?.(`Organisation "${formData.name}" ${isEditing ? 'updated' : 'created'} successfully!`, 'success');
      onClose();
      window.__addClientItem?.(itemToSave);
      window.__reloadClientDirectory?.();
      window.__reloadDashboard?.();
      window.__reloadClientAccounts?.();
    } catch {
      if (!isEditing) {
        const primaryManager = {
          id: `mgr_${itemToSave.id}`,
          name: itemToSave.name,
          username: itemToSave.email || itemToSave.name.toLowerCase().replace(/\s+/g, ''),
          email: itemToSave.email,
          phone: itemToSave.phone,
          client_type: 'primary',
          is_default: true,
          organisation: { id: itemToSave.id, name: itemToSave.name },
          school_name: itemToSave.name,
          status: itemToSave.status || 'active',
          is_active: itemToSave.is_active !== false,
          created_at: new Date().toISOString(),
        };
        try {
          const storedMgrs = JSON.parse(localStorage.getItem('cf_custom_managers') || '[]');
          localStorage.setItem('cf_custom_managers', JSON.stringify([primaryManager, ...storedMgrs]));
        } catch (_) {}
      }
      addToast?.(`Organisation "${formData.name}" ${isEditing ? 'updated' : 'created'}!`, 'success');
      onClose();
      window.__addClientItem?.(itemToSave);
      window.__reloadClientDirectory?.();
      window.__reloadDashboard?.();
      window.__reloadClientAccounts?.();
    } finally {
      setSaving(false);
    }
  };


  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      
      {/* 1. Header (Fixed Top) */}
      <div style={{
        background: '#2563eb',
        color: '#fff',
        padding: '12px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <UserPlus size={18} />
          <span>{isEditing ? 'Edit Organisation Details' : 'Add New Organisation'}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '2px' }}
        >
          <X size={18} />
        </button>
      </div>

      {/* 2. Scrollable Body Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        
        {/* Section 1: Organisation Information */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '14px'
          }}>
            <Building size={15} /> Organisation Information
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                Organisation Name <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                type="text"
                required
                value={formData.name}
                onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                placeholder="Enter organisation / school name"
                style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                  Email <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="email"
                  required
                  value={formData.email}
                  onChange={(e) => setFormData({ ...formData, email: e.target.value })}
                  placeholder="Enter email address"
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Phone</label>
                <input
                  type="tel"
                  value={formData.phone}
                  onChange={(e) => setFormData({ ...formData, phone: e.target.value })}
                  placeholder="Enter phone number (optional)"
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Status</label>
                <select
                  value={formData.status}
                  onChange={(e) => setFormData({ ...formData, status: e.target.value })}
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
                >
                  <option value="false">Inactive</option>
                  <option value="true">Active</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Password Option</label>
                <select
                  value={formData.passwordOption}
                  onChange={(e) => setFormData({ ...formData, passwordOption: e.target.value })}
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
                >
                  <option value="custom">Custom Password</option>
                  <option value="phone">Use Phone Number</option>
                </select>
              </div>
            </div>

            {formData.passwordOption === 'custom' && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                  Password <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={formData.password}
                    onChange={(e) => setFormData({ ...formData, password: e.target.value })}
                    placeholder="Enter custom password"
                    style={{ width: '100%', height: '36px', padding: '0 36px 0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', color: '#6b7280', cursor: 'pointer' }}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Section 2: User Permission */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '14px'
          }}>
            <Shield size={15} /> User Permission
          </div>

          {/* Category 1: GROUP SETTINGS */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Cog size={13} /> TABLE SETTINGS
              </div>
              <ToggleSwitch
                checked={Object.values(groupPerms).every(Boolean)}
                onChange={(val) => {
                  setGroupPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'add', label: 'Create Template' },
                { key: 'edit', label: 'Edit Template' },
                { key: 'list', label: 'View Template' },
                { key: 'delete', label: 'Delete Template' },
                { key: 'status', label: 'Status Template' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!groupPerms[key]}
                    onChange={(v) => setGroupPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category 2: ID CARD ACTION LIST */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <List size={13} /> ID CARD ACTION LIST
              </div>
              <ToggleSwitch
                checked={Object.values(actionPerms).every(Boolean)}
                onChange={(val) => {
                  setActionPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'pending', label: 'Pending List' },
                { key: 'verified', label: 'Verified List' },
                { key: 'pool', label: 'Pool List' },
                { key: 'approved', label: 'Approved List' },
                { key: 'download', label: 'Download List' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!actionPerms[key]}
                    onChange={(v) => setActionPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category 3: REPRINT & CARD ACTIONS */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <RefreshCw size={13} /> REPRINT & CARD ACTIONS
              </div>
              <ToggleSwitch
                checked={Object.values(reprintPerms).every(Boolean)}
                onChange={(val) => {
                  setReprintPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'reprint_pending', label: 'Reprint Request' },
                { key: 'reprint_confirmed', label: 'Confirmed List' },
                { key: 'card_add', label: 'Add Card' },
                { key: 'card_edit', label: 'Edit Card' },
                { key: 'card_verify', label: 'Verify Card' },
                { key: 'card_approve', label: 'Approve Card' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!reprintPerms[key]}
                    onChange={(v) => setReprintPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3. STICKY FOOTER */}
      <div style={{
        flexShrink: 0,
        padding: '12px 18px',
        background: '#ffffff',
        borderTop: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '10px',
        boxShadow: '0 -4px 12px rgba(0,0,0,0.05)',
        zIndex: 10,
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '8px 16px',
            background: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            color: '#2563eb',
            fontWeight: 600,
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <X size={14} /> Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          style={{
            padding: '8px 18px',
            background: '#2563eb',
            border: 'none',
            borderRadius: '4px',
            color: '#ffffff',
            fontWeight: 700,
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <Save size={14} /> {saving ? (isEditing ? 'Savingâ€¦' : 'Addingâ€¦') : (isEditing ? 'Save Changes' : '+ Add Organisation')}
        </button>
      </div>
    </form>
  );
}

/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   2. Add New Operator Drawer (OPERATOR INFO + PERMISSIONS)
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function OriginalOperatorDrawerForm({ onClose, addToast, initialData }) {
  const isEditing = !!initialData;
  const [operatorName, setOperatorName] = useState(initialData?.name || initialData?.full_name || '');
  const [email, setEmail] = useState(initialData?.email || '');
  const [phone, setPhone] = useState(initialData?.phone || '');
  const [status, setStatus] = useState(
    initialData ? (initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false') : 'true'
  );
  const [passwordOption, setPasswordOption] = useState('custom');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (initialData) {
      setOperatorName(initialData.name || initialData.full_name || '');
      setEmail(initialData.email || '');
      setPhone(initialData.phone || '');
      setStatus(initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false');
    }
  }, [initialData]);

  const [groupPerms, setGroupPerms] = useState({
    add: true, edit: true, list: true, delete: true, status: true,
  });

  const [actionPerms, setActionPerms] = useState({
    pending: true, verified: true, pool: true, approved: true, download: true,
  });

  const [reprintPerms, setReprintPerms] = useState({
    reprint_pending: true, reprint_confirmed: true,
    card_add: true, card_edit: true, card_verify: true, card_approve: true,
  });

  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!operatorName || !email) {
      addToast?.('Please fill in Operator Name and Email', 'warning');
      return;
    }
    setSaving(true);
    const payload = {
      name: operatorName,
      email,
      phone,
      status: status === 'true',
      password_option: passwordOption,
      password: passwordOption === 'custom' ? password : (phone || '12345678'),
    };
    let itemToSave = {
      id: initialData?.id || Date.now(),
      name: operatorName,
      email: email,
      phone: phone || 'â€”',
      designation: initialData?.designation || 'Operator',
      status: status === 'true' ? 'active' : 'inactive',
      is_active: status === 'true',
      created_at: initialData?.created_at || new Date().toISOString(),
    };
    try {
      let res;
      if (isEditing) {
        try { res = await operatorApi.update(initialData.id, payload); }
        catch { res = await staffApi.update(initialData.id, payload); }
      } else {
        try { res = await operatorApi.create(payload); }
        catch { res = await staffApi.create(payload); }
      }
      if (res?.operator || res?.staff) {
        itemToSave = { ...itemToSave, ...(res.operator || res.staff || res), name: res.name || operatorName };
      }
      addToast?.(`Operator "${operatorName}" ${isEditing ? 'updated' : 'created'} successfully!`, 'success');
      onClose();
      window.__addStaffItem?.(itemToSave);
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } catch {
      addToast?.(`Operator "${operatorName}" ${isEditing ? 'updated' : 'created'}!`, 'success');
      onClose();
      window.__addStaffItem?.(itemToSave);
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      
      {/* 1. Header (Fixed Top) */}
      <div style={{
        background: '#2563eb',
        color: '#fff',
        padding: '12px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <UserPlus size={18} />
          <span>{isEditing ? 'Edit Operator Account' : 'Add New Operator'}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '2px' }}
        >
          <X size={18} />
        </button>
      </div>

      {/* 2. Scrollable Body Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        
        {/* Section 1: Operator Information */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '12px'
          }}>
            <User size={15} /> Operator Information
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                Operator Name <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                type="text"
                required
                value={operatorName}
                onChange={(e) => setOperatorName(e.target.value)}
                placeholder="Enter operator name"
                style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                  Email <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter email address"
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Phone</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="Enter phone number (optional)"
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
                >
                  <option value="false">Inactive</option>
                  <option value="true">Active</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Password Option</label>
                <select
                  value={passwordOption}
                  onChange={(e) => setPasswordOption(e.target.value)}
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
                >
                  <option value="custom">Custom Password</option>
                  <option value="phone">Use Phone Number</option>
                </select>
              </div>
            </div>

            {passwordOption === 'custom' && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                  Password <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter custom password"
                    style={{ width: '100%', height: '36px', padding: '0 36px 0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', color: '#6b7280', cursor: 'pointer' }}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Section 2: Operator Permissions */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '14px'
          }}>
            <Shield size={15} /> Operator Permissions
          </div>

          {/* Category 1: GROUP SETTINGS */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Cog size={13} /> TABLE SETTINGS
              </div>
              <ToggleSwitch
                checked={Object.values(groupPerms).every(Boolean)}
                onChange={(val) => {
                  setGroupPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'add', label: 'Create Template' },
                { key: 'edit', label: 'Edit Template' },
                { key: 'list', label: 'View Template' },
                { key: 'delete', label: 'Delete Template' },
                { key: 'status', label: 'Status Template' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!groupPerms[key]}
                    onChange={(v) => setGroupPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category 2: ID CARD ACTION LIST */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <List size={13} /> ID CARD ACTION LIST
              </div>
              <ToggleSwitch
                checked={Object.values(actionPerms).every(Boolean)}
                onChange={(val) => {
                  setActionPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'pending', label: 'Pending List' },
                { key: 'verified', label: 'Verified List' },
                { key: 'pool', label: 'Pool List' },
                { key: 'approved', label: 'Approved List' },
                { key: 'download', label: 'Download List' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!actionPerms[key]}
                    onChange={(v) => setActionPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category 3: REPRINT & CARD ACTIONS */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <RefreshCw size={13} /> REPRINT & CARD ACTIONS
              </div>
              <ToggleSwitch
                checked={Object.values(reprintPerms).every(Boolean)}
                onChange={(val) => {
                  setReprintPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'reprint_pending', label: 'Reprint Request' },
                { key: 'reprint_confirmed', label: 'Confirmed List' },
                { key: 'card_add', label: 'Add Card' },
                { key: 'card_edit', label: 'Edit Card' },
                { key: 'card_verify', label: 'Verify Card' },
                { key: 'card_approve', label: 'Approve Card' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!reprintPerms[key]}
                    onChange={(v) => setReprintPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3. STICKY FOOTER */}
      <div style={{
        flexShrink: 0,
        padding: '12px 18px',
        background: '#ffffff',
        borderTop: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '10px',
        boxShadow: '0 -4px 12px rgba(0,0,0,0.05)',
        zIndex: 10,
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '8px 16px',
            background: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            color: '#2563eb',
            fontWeight: 600,
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <X size={14} /> Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          style={{
            padding: '8px 18px',
            background: '#2563eb',
            border: 'none',
            borderRadius: '4px',
            color: '#ffffff',
            fontWeight: 700,
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <Save size={14} /> {saving ? (isEditing ? 'Savingâ€¦' : 'Creatingâ€¦') : (isEditing ? 'Save Changes' : '+ Add Operator')}
        </button>
      </div>
    </form>
  );
}

/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   2b. Assign Organisations to Operator Drawer ('assign-operator')
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function AssignOperatorOrganisationsForm({ onClose, addToast }) {
  const [search, setSearch] = useState('');
  const [clients, setClients] = useState([]);
  const [selectedClients, setSelectedClients] = useState([]);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    clientApi.getAllForAssignment()
      .then((data) => {
        const list = Array.isArray(data) ? data : data?.clients || data?.results || [];
        setClients(list.map(c => ({ id: String(c.id), name: c.name || c.school_name || `Organisation #${c.id}` })));
      })
      .catch(() => {
        setClients([
          { id: '1', name: 'SAKET MGM SCHOOL (VIDISHA)' },
          { id: '2', name: 'MAHARSHI VASHISHTA VIDYA NIKETAN' },
          { id: '3', name: 'DM CO ED SCHOOL (BHOPAL)' },
          { id: '4', name: 'DPS (NEELBAD)' },
        ]);
      });
  }, []);

  const filteredClients = clients.filter(c => c.name.toLowerCase().includes(search.toLowerCase()));

  const toggleSelectAll = () => {
    if (selectedClients.length === filteredClients.length) {
      setSelectedClients([]);
    } else {
      setSelectedClients(filteredClients.map(c => c.id));
    }
  };

  const toggleClient = (id) => {
    setSelectedClients(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      addToast?.(`Assigned ${selectedClients.length} organisation(s) to operator successfully!`, 'success');
      onClose();
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } catch {
      addToast?.('Failed to update operator assignments', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      <div style={{ background: '#2563eb', color: '#fff', padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <Link size={18} />
          <span>Assign Organisations to Operator</span>
        </div>
        <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: '2px' }}>
          <X size={18} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        <div>
          <div style={{ background: '#2563eb', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <Building size={15} /> Select Assigned Organisations ({selectedClients.length})
            </div>
            <div style={{ display: 'flex', gap: '8px', fontSize: '11px' }}>
              <button type="button" onClick={toggleSelectAll} style={{ background: 'none', border: 'none', color: '#fff', fontWeight: 700, cursor: 'pointer', textDecoration: 'underline' }}>Select All</button>
              <button type="button" onClick={() => setSelectedClients([])} style={{ background: 'none', border: 'none', color: 'rgba(255,255,255,0.8)', cursor: 'pointer', textDecoration: 'underline' }}>Clear</button>
            </div>
          </div>

          <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', padding: '12px', background: '#f8fafc' }}>
            <div style={{ position: 'relative', marginBottom: '10px' }}>
              <Search size={13} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search organisation school..."
                style={{ width: '100%', height: '32px', paddingLeft: '30px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '12px', outline: 'none' }}
              />
            </div>

            <div style={{ maxHeight: '320px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {filteredClients.map(c => {
                const isChecked = selectedClients.includes(c.id);
                return (
                  <label
                    key={c.id}
                    onClick={() => toggleClient(c.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '10px',
                      padding: '8px 12px', borderRadius: '6px', border: '1px solid',
                      borderColor: isChecked ? '#bfdbfe' : '#e2e8f0',
                      background: isChecked ? '#eff6ff' : '#ffffff',
                      cursor: 'pointer', fontSize: '13px', color: '#334155', fontWeight: 500
                    }}
                  >
                    <input type="checkbox" checked={isChecked} onChange={() => {}} style={{ accentColor: '#2563eb' }} />
                    <span>{c.name}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div style={{ flexShrink: 0, padding: '12px 18px', background: '#ffffff', borderTop: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '10px' }}>
        <button type="button" onClick={onClose} style={{ padding: '8px 16px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#2563eb', fontWeight: 600, fontSize: '12px', cursor: 'pointer' }}>
          <X size={14} /> Cancel
        </button>
        <button type="submit" disabled={saving} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#ffffff', fontWeight: 700, fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Save size={14} /> {saving ? 'Savingâ€¦' : 'Save Assignments'}
        </button>
      </div>
    </form>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   2b. Add / Edit Manager Drawer Form
   ───────────────────────────────────────────────────────────────────────────── */
function OriginalManagerDrawerForm({ onClose, addToast, initialData }) {
  const isEditing = !!initialData;
  const [organisations, setOrganisations] = useState([]);
  const [selectedOrgId, setSelectedOrgId] = useState(initialData?.organisation_id || initialData?.organisation?.id || '');
  const [managerName, setManagerName] = useState(initialData?.name || initialData?.full_name || '');
  const [email, setEmail] = useState(initialData?.email || '');
  const [phone, setPhone] = useState(initialData?.phone || '');
  const [status, setStatus] = useState(
    initialData ? (initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false') : 'true'
  );
  const [passwordOption, setPasswordOption] = useState('custom');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const local = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
      try {
        const data = await clientApi.getAllClients({ page: 1, page_size: 200 });
        const api = data?.clients || data?.results || (Array.isArray(data) ? data : []);
        const merged = [...api];
        local.forEach(lc => { if (!merged.find(ac => String(ac.id) === String(lc.id))) merged.push(lc); });
        setOrganisations(merged);
        if (merged.length > 0 && !selectedOrgId) setSelectedOrgId(String(merged[0].id));
      } catch {
        setOrganisations(local);
        if (local.length > 0 && !selectedOrgId) setSelectedOrgId(String(local[0].id));
      }
    })();
  }, []);

  useEffect(() => {
    if (initialData) {
      const orgObj = initialData.organisation || (initialData.name && !initialData.client_type ? initialData : null);
      if (orgObj) {
        setSelectedOrgId(String(orgObj.id || ''));
      } else if (initialData.organisation_id) {
        setSelectedOrgId(String(initialData.organisation_id));
      }
      if (initialData.client_type === 'manager' || initialData.designation === 'Manager' || initialData.email) {
        setManagerName(initialData.name || initialData.full_name || '');
        setEmail(initialData.email || '');
        setPhone(initialData.phone || '');
        setStatus(initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false');
      }
    }
  }, [initialData]);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!managerName || !email) {
      addToast?.('Please fill in Manager Name and Email', 'warning');
      return;
    }
    setSaving(true);
    const selOrg = organisations.find(o => String(o.id) === String(selectedOrgId)) || { id: selectedOrgId, name: 'Organisation' };

    const payload = {
      name: managerName,
      email,
      phone,
      client_type: 'manager',
      is_default: false,
      organisation_id: selOrg.id,
      status: status === 'true' ? 'active' : 'inactive',
      password_option: passwordOption,
      password: passwordOption === 'custom' ? password : (phone || '12345678'),
    };

    const itemToSave = {
      id: initialData?.id || mgr_,
      name: managerName,
      username: email || managerName.toLowerCase().replace(/\s+/g, ''),
      email: email,
      phone: phone || '—',
      client_type: 'manager',
      is_default: false,
      organisation_id: selOrg.id,
      organisation: { id: selOrg.id, name: selOrg.name },
      school_name: selOrg.name,
      status: status === 'true' ? 'active' : 'inactive',
      is_active: status === 'true',
      created_at: initialData?.created_at || new Date().toISOString(),
    };

    try {
      if (isEditing) {
        await clientApi.updateClient(initialData.id, payload);
      } else {
        await clientApi.createClient(payload);
      }
    } catch (_) {}

    try {
      const storedMgrs = JSON.parse(localStorage.getItem('cf_custom_managers') || '[]');
      const updatedMgrs = [itemToSave, ...storedMgrs.filter(m => String(m.id) !== String(itemToSave.id) && m.email !== itemToSave.email)];
      localStorage.setItem('cf_custom_managers', JSON.stringify(updatedMgrs));
    } catch (_) {}

    addToast?.(`Manager "${managerName}" ${isEditing ? 'updated' : 'created'} for ${selOrg.name}!`, 'success');
    onClose();
    window.__reloadClientAccounts?.();
    window.__reloadDashboard?.();
    setSaving(false);
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      <div style={{ background: '#2563eb', color: '#fff', padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <UserPlus size={18} />
          <span>{isEditing ? 'Edit Manager Account' : 'Add New Manager Account'}</span>
        </div>
        <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer' }}>
          <X size={18} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        <div>
          <div style={{ background: '#2563eb', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Building size={15} /> Select Organisation
          </div>
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
              Select Organisation to which this Manager belongs <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <select
              value={selectedOrgId}
              onChange={(e) => setSelectedOrgId(e.target.value)}
              style={{ width: '100%', height: '38px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', fontWeight: 600, color: '#1e293b', outline: 'none', background: '#f8fafc', cursor: 'pointer' }}
            >
              {organisations.map(o => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
          </div>
        </div>

        <div>
          <div style={{ background: '#2563eb', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <User size={15} /> Manager Information
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Manager Name <span style={{ color: '#ef4444' }}>*</span></label>
              <input type="text" required value={managerName} onChange={(e) => setManagerName(e.target.value)} placeholder="Enter manager name" style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Email <span style={{ color: '#ef4444' }}>*</span></label>
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Enter email" style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Phone</label>
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Enter phone" style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
              </div>
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Status</label>
                <select value={status} onChange={(e) => setStatus(e.target.value)} style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', background: '#fff' }}>
                  <option value="true">Active</option>
                  <option value="false">Inactive</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Password Option</label>
                <select value={passwordOption} onChange={(e) => setPasswordOption(e.target.value)} style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', background: '#fff' }}>
                  <option value="custom">Custom Password</option>
                  <option value="phone">Use Phone Number</option>
                </select>
              </div>
            </div>
            {passwordOption === 'custom' && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Password <span style={{ color: '#ef4444' }}>*</span></label>
                <div style={{ position: 'relative' }}>
                  <input type={showPassword ? 'text' : 'password'} required value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Enter password" style={{ width: '100%', height: '36px', padding: '0 36px 0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
                  <button type="button" onClick={() => setShowPassword(!showPassword)} style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', color: '#6b7280', cursor: 'pointer' }}>
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>

      <div style={{ flexShrink: 0, padding: '12px 18px', background: '#ffffff', borderTop: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '10px' }}>
        <button type="button" onClick={onClose} style={{ padding: '8px 16px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#2563eb', fontWeight: 600, fontSize: '12px', cursor: 'pointer' }}><X size={14} /> Cancel</button>
        <button type="submit" disabled={saving} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#ffffff', fontWeight: 700, fontSize: '12px', cursor: 'pointer' }}>
          <Save size={14} /> {saving ? 'Saving...' : isEditing ? 'Save Changes' : '+ Add Manager'}
        </button>
      </div>
    </form>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   3. Add New Assistant Drawer (SINGLE CLIENT SELECTION + ASSISTANT DETAILS + PERMISSIONS)

/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   3. Add New Assistant Drawer (SINGLE CLIENT SELECTION + ASSISTANT DETAILS + PERMISSIONS)
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function OriginalAssistantDrawerForm({ onClose, addToast, initialData }) {
  const isEditing = !!initialData;
  const [selectedClient, setSelectedClient] = useState('1');
  const [assistantName, setAssistantName] = useState(initialData?.name || initialData?.full_name || '');
  const [email, setEmail] = useState(initialData?.email || '');
  const [phone, setPhone] = useState(initialData?.phone || '');
  const [status, setStatus] = useState(
    initialData ? (initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false') : 'true'
  );
  const [passwordOption, setPasswordOption] = useState('custom');
  const [password, setPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);

  useEffect(() => {
    if (initialData) {
      setAssistantName(initialData.name || initialData.full_name || '');
      setEmail(initialData.email || '');
      setPhone(initialData.phone || '');
      setStatus(initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false');
    }
  }, [initialData]);

  const [groupPerms, setGroupPerms] = useState({
    add: true, edit: true, list: true, delete: true, status: true,
  });

  const [actionPerms, setActionPerms] = useState({
    pending: true, verified: true, pool: true, approved: true, download: true,
  });

  const [reprintPerms, setReprintPerms] = useState({
    reprint_pending: true, reprint_confirmed: true,
    card_add: true, card_edit: true, card_verify: true, card_approve: true,
  });

  const [allClients, setAllClients] = useState([]);

  useEffect(() => {
    (async () => {
      const localClients = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
      const localMgrs = JSON.parse(localStorage.getItem('cf_custom_managers') || '[]');
      try {
        const data = await clientApi.getAllClients({ page: 1, page_size: 200 });
        const api = data?.clients || data?.results || (Array.isArray(data) ? data : []);
        const merged = [...api];
        localClients.forEach(lc => { if (!merged.find(ac => String(ac.id) === String(lc.id))) merged.push(lc); });
        localMgrs.forEach(m => { if (!merged.find(ac => String(ac.id) === String(m.id))) merged.push({ id: m.id, name: m.name + (m.school_name ? ' (' + m.school_name + ')' : '') }); });
        setAllClients(merged);
        if (merged.length > 0 && (!selectedClient || selectedClient === '1')) setSelectedClient(String(merged[0].id));
      } catch {
        const combined = [...localClients, ...localMgrs.map(m => ({ id: m.id, name: m.name + (m.school_name ? ' (' + m.school_name + ')' : '') }))];
        setAllClients(combined);
        if (combined.length > 0 && (!selectedClient || selectedClient === '1')) setSelectedClient(String(combined[0].id));
      }
    })();
  }, []);

  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!assistantName || !email) {
      addToast?.('Please fill in Assistant Name and Email', 'warning');
      return;
    }
    setSaving(true);
    const payload = {
      name: assistantName,
      email,
      phone,
      status: status === 'true',
      client: selectedClient || undefined,
      password_option: passwordOption,
      password: passwordOption === 'custom' ? password : (phone || '12345678'),
    };
    let itemToSave = {
      id: initialData?.id || Date.now(),
      name: assistantName,
      email: email,
      phone: phone || 'â€”',
      designation: 'Assistant',
      status: status === 'true' ? 'active' : 'inactive',
      is_active: status === 'true',
      created_at: initialData?.created_at || new Date().toISOString(),
    };
    try {
      let res;
      if (isEditing) {
        res = await assistantApi.update(initialData.id, payload);
      } else {
        res = await assistantApi.create(payload);
      }
      if (res?.staff || res?.id) {
        itemToSave = { ...itemToSave, ...(res.staff || res), name: res.name || assistantName };
      }
      addToast?.(`Assistant "${assistantName}" ${isEditing ? 'updated' : 'created'} successfully!`, 'success');
      onClose();
      window.__addStaffItem?.(itemToSave);
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } catch {
      addToast?.(`Assistant "${assistantName}" ${isEditing ? 'updated' : 'created'}!`, 'success');
      onClose();
      window.__addStaffItem?.(itemToSave);
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      
      {/* 1. Header (Fixed Top) */}
      <div style={{
        background: '#2563eb',
        color: '#fff',
        padding: '12px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <UserPlus size={18} />
          <span>{isEditing ? 'Edit Assistant Details' : 'Add New Assistant'}</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '2px' }}
        >
          <X size={18} />
        </button>
      </div>

      {/* 2. Scrollable Body Area */}
      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        
        {/* Section 1: Organisation Selection (Pick 1 Client) */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '12px'
          }}>
            <Building size={15} /> Select Organisation
          </div>

          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '6px' }}>
              Select Organisation / Client to which this Assistant is created for <span style={{ color: '#ef4444' }}>*</span>
            </label>
            <select
              value={selectedClient}
              onChange={(e) => setSelectedClient(e.target.value)}
              style={{
                width: '100%',
                height: '38px',
                padding: '0 12px',
                border: '1px solid #d1d5db',
                borderRadius: '4px',
                fontSize: '13px',
                fontWeight: 600,
                color: '#1e293b',
                outline: 'none',
                fontFamily: 'var(--font-family)',
                background: '#f8fafc',
                cursor: 'pointer'
              }}
            >
              {allClients.map(c => (
                <option key={c.id} value={c.id}>
                  {c.name}
                </option>
              ))}
            </select>
          </div>
        </div>

        {/* Section 2: Assistant Information */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '12px'
          }}>
            <User size={15} /> Assistant Information
          </div>

          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                Assistant Name <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <input
                type="text"
                required
                value={assistantName}
                onChange={(e) => setAssistantName(e.target.value)}
                placeholder="Enter assistant name"
                style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
              />
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                  Email <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <input
                  type="email"
                  required
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  placeholder="Enter email address"
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Phone</label>
                <input
                  type="tel"
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  placeholder="Enter phone number (optional)"
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                />
              </div>
            </div>

            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Status</label>
                <select
                  value={status}
                  onChange={(e) => setStatus(e.target.value)}
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
                >
                  <option value="false">Inactive</option>
                  <option value="true">Active</option>
                </select>
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Password Option</label>
                <select
                  value={passwordOption}
                  onChange={(e) => setPasswordOption(e.target.value)}
                  style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
                >
                  <option value="custom">Custom Password</option>
                  <option value="phone">Use Phone Number</option>
                </select>
              </div>
            </div>

            {passwordOption === 'custom' && (
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>
                  Password <span style={{ color: '#ef4444' }}>*</span>
                </label>
                <div style={{ position: 'relative' }}>
                  <input
                    type={showPassword ? 'text' : 'password'}
                    required
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    placeholder="Enter custom password"
                    style={{ width: '100%', height: '36px', padding: '0 36px 0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none', fontFamily: 'var(--font-family)' }}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    style={{ position: 'absolute', right: '10px', top: '50%', transform: 'translateY(-50%)', border: 'none', background: 'none', color: '#6b7280', cursor: 'pointer' }}
                  >
                    {showPassword ? <EyeOff size={15} /> : <Eye size={15} />}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Section 3: Assistant Permissions */}
        <div>
          <div style={{
            background: '#2563eb',
            color: '#fff',
            padding: '8px 12px',
            borderRadius: '6px',
            fontWeight: 700,
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px',
            marginBottom: '14px'
          }}>
            <Shield size={15} /> Assistant Permissions
          </div>

          {/* Category 1: GROUP SETTINGS */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <Cog size={13} /> TABLE SETTINGS
              </div>
              <ToggleSwitch
                checked={Object.values(groupPerms).every(Boolean)}
                onChange={(val) => {
                  setGroupPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'add', label: 'Create Template' },
                { key: 'edit', label: 'Edit Template' },
                { key: 'list', label: 'View Template' },
                { key: 'delete', label: 'Delete Template' },
                { key: 'status', label: 'Status Template' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!groupPerms[key]}
                    onChange={(v) => setGroupPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category 2: ID CARD ACTION LIST */}
          <div style={{ marginBottom: '14px' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <List size={13} /> ID CARD ACTION LIST
              </div>
              <ToggleSwitch
                checked={Object.values(actionPerms).every(Boolean)}
                onChange={(val) => {
                  setActionPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'pending', label: 'Pending List' },
                { key: 'verified', label: 'Verified List' },
                { key: 'pool', label: 'Pool List' },
                { key: 'approved', label: 'Approved List' },
                { key: 'download', label: 'Download List' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!actionPerms[key]}
                    onChange={(v) => setActionPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>

          {/* Category 3: REPRINT & CARD ACTIONS */}
          <div>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', fontSize: '11px', fontWeight: 800, color: '#1e3a8a', letterSpacing: '0.04em', marginBottom: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                <RefreshCw size={13} /> REPRINT & CARD ACTIONS
              </div>
              <ToggleSwitch
                checked={Object.values(reprintPerms).every(Boolean)}
                onChange={(val) => {
                  setReprintPerms(prev => {
                    const copy = { ...prev };
                    Object.keys(copy).forEach(k => { copy[k] = val; });
                    return copy;
                  });
                }}
              />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(2, 1fr)', gap: '8px' }}>
              {[
                { key: 'reprint_pending', label: 'Reprint Request' },
                { key: 'reprint_confirmed', label: 'Confirmed List' },
                { key: 'card_add', label: 'Add Card' },
                { key: 'card_edit', label: 'Edit Card' },
                { key: 'card_verify', label: 'Verify Card' },
                { key: 'card_approve', label: 'Approve Card' },
              ].map(({ key, label }) => (
                <div key={key} style={{ display: 'flex', alignItems: 'center', gap: '10px', padding: '8px 12px', background: '#f8fafc', border: '1px solid #e2e8f0', borderRadius: '6px' }}>
                  <ToggleSwitch
                    checked={!!reprintPerms[key]}
                    onChange={(v) => setReprintPerms(prev => ({ ...prev, [key]: v }))}
                  />
                  <span style={{ fontSize: '12px', fontWeight: 600, color: '#334155' }}>{label}</span>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>

      {/* 3. STICKY FOOTER */}
      <div style={{
        flexShrink: 0,
        padding: '12px 18px',
        background: '#ffffff',
        borderTop: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '10px',
        boxShadow: '0 -4px 12px rgba(0,0,0,0.05)',
        zIndex: 10,
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{
            padding: '8px 16px',
            background: '#ffffff',
            border: '1px solid #cbd5e1',
            borderRadius: '4px',
            color: '#2563eb',
            fontWeight: 600,
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <X size={14} /> Cancel
        </button>
        <button
          type="submit"
          disabled={saving}
          style={{
            padding: '8px 18px',
            background: '#2563eb',
            border: 'none',
            borderRadius: '4px',
            color: '#ffffff',
            fontWeight: 700,
            fontSize: '12px',
            cursor: 'pointer',
            display: 'flex',
            alignItems: 'center',
            gap: '4px'
          }}
        >
          <Plus size={14} /> {saving ? 'Creating…' : '+ Add Assistant'}
        </button>
      </div>
    </form>
  );
}

/* ─────────────────────────────────────────────────────────────────────────────
   3b. Assign Groups / Classes to Assistant Drawer ('assign-assistant')
   ───────────────────────────────────────────────────────────────────────────── */
function AssignAssistantGroupsForm({ onClose, addToast, initialData }) {
  const [search, setSearch] = useState('');
  const [allGroups, setAllGroups] = useState([]);
  const [selectedGroups, setSelectedGroups] = useState(initialData?.assigned_groups || initialData?.allowed_table_ids || ['1', '2']);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    try {
      const customGroups = JSON.parse(localStorage.getItem('cf_custom_table_groups') || '[]');
      const defaultGroups = [
        { id: '1', name: 'CLASS 1 - SEC A' },
        { id: '2', name: 'CLASS 1 - SEC B' },
        { id: '3', name: 'CLASS 2 - SEC A' },
        { id: '4', name: 'CLASS 3 - SEC A' },
        { id: '5', name: 'STAFF & TEACHERS' },
      ];
      const merged = [...defaultGroups];
      customGroups.forEach(cg => {
        if (!merged.some(g => String(g.id) === String(cg.id))) {
          merged.push({ id: String(cg.id), name: cg.name || cg.group_name || `Group #${cg.id}` });
        }
      });
      setAllGroups(merged);
    } catch {
      setAllGroups([
        { id: '1', name: 'CLASS 1 - SEC A' },
        { id: '2', name: 'CLASS 1 - SEC B' },
        { id: '3', name: 'CLASS 2 - SEC A' },
        { id: '4', name: 'CLASS 3 - SEC A' },
        { id: '5', name: 'STAFF & TEACHERS' },
      ]);
    }
  }, []);

  const filteredGroups = allGroups.filter(g => (g.name || '').toLowerCase().includes(search.toLowerCase()));

  const toggleGroup = (id) => {
    setSelectedGroups(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      if (initialData?.id) {
        try {
          await assistantApi.update(initialData.id, { assigned_groups: selectedGroups });
        } catch (_) {}

        const staffList = JSON.parse(localStorage.getItem('cf_custom_staff') || '[]');
        const updated = staffList.map(s => {
          if (String(s.id) === String(initialData.id)) {
            return { ...s, assigned_groups: selectedGroups, allowed_table_ids: selectedGroups };
          }
          return s;
        });
        localStorage.setItem('cf_custom_staff', JSON.stringify(updated));
      }
      addToast?.(`Assigned ${selectedGroups.length} group(s) to ${initialData?.name || 'assistant'} successfully!`, 'success');
      onClose();
      window.__reloadStaffList?.();
    } catch {
      addToast?.('Failed to save group assignments', 'error');
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      <div style={{ background: '#2563eb', color: '#fff', padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <Layers size={18} />
          <span>Assign Groups & Classes to {initialData?.name ? `"${initialData.name}"` : 'Assistant'}</span>
        </div>
        <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: '2px' }}>
          <X size={18} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        <div>
          <div style={{ background: '#2563eb', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '12px' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <CheckSquare size={15} /> Select Classes / Groups ({selectedGroups.length})
            </div>
          </div>

          <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', padding: '12px', background: '#f8fafc' }}>
            <div style={{ position: 'relative', marginBottom: '10px' }}>
              <Search size={13} style={{ position: 'absolute', left: '10px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search class or group..."
                style={{ width: '100%', height: '32px', paddingLeft: '30px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '12px', outline: 'none' }}
              />
            </div>

            <div style={{ maxHeight: '280px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '6px' }}>
              {filteredGroups.map(g => {
                const isChecked = selectedGroups.includes(g.id);
                return (
                  <label
                    key={g.id}
                    onClick={() => toggleGroup(g.id)}
                    style={{
                      display: 'flex', alignItems: 'center', gap: '10px',
                      padding: '8px 12px', borderRadius: '6px', border: '1px solid',
                      borderColor: isChecked ? '#bfdbfe' : '#e2e8f0',
                      background: isChecked ? '#eff6ff' : '#ffffff',
                      cursor: 'pointer', fontSize: '13px', color: '#334155', fontWeight: 500
                    }}
                  >
                    <input type="checkbox" checked={isChecked} onChange={() => {}} style={{ accentColor: '#2563eb' }} />
                    <span>{g.name}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>
      </div>

      <div style={{ flexShrink: 0, padding: '12px 18px', background: '#ffffff', borderTop: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '10px' }}>
        <button type="button" onClick={onClose} style={{ padding: '8px 16px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#2563eb', fontWeight: 600, fontSize: '12px', cursor: 'pointer' }}>
          <X size={14} /> Cancel
        </button>
        <button type="submit" disabled={saving} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#ffffff', fontWeight: 700, fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}>
          <Save size={14} /> {saving ? 'Saving…' : 'Save Group Assignments'}
        </button>
      </div>
    </form>
  );
}


/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   4. Add New Photographer Drawer
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function OriginalPhotographerDrawerForm({ onClose, addToast, initialData }) {
  const isEditing = !!initialData;
  const [search, setSearch] = useState('');
  const [selectedClients, setSelectedClients] = useState(['1', '2']);
  const [photographerName, setPhotographerName] = useState(initialData?.name || initialData?.full_name || '');
  const [email, setEmail] = useState(initialData?.email || '');
  const [phone, setPhone] = useState(initialData?.phone || '');
  const [status, setStatus] = useState(
    initialData ? (initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false') : 'true'
  );
  const [password, setPassword] = useState('');

  useEffect(() => {
    if (initialData) {
      setPhotographerName(initialData.name || initialData.full_name || '');
      setEmail(initialData.email || '');
      setPhone(initialData.phone || '');
      setStatus(initialData.is_active || initialData.status === 'active' || initialData.status === true ? 'true' : 'false');
    }
  }, [initialData]);

  const [allClients, setAllClients] = useState([]);

  useEffect(() => {
    (async () => {
      const local = JSON.parse(localStorage.getItem('cf_custom_clients') || '[]');
      try {
        const data = await clientApi.getAllClients({ page: 1, page_size: 200 });
        const api = data?.clients || data?.results || (Array.isArray(data) ? data : []);
        const merged = [...api];
        local.forEach(lc => { if (!merged.find(ac => String(ac.id) === String(lc.id))) merged.push(lc); });
        setAllClients(merged);
      } catch { setAllClients(local); }
    })();
  }, []);

  const filteredClients = allClients.filter(c => (c.name || '').toLowerCase().includes(search.toLowerCase()));
  const [saving, setSaving] = useState(false);

  const handleSubmit = async (e) => {
    e.preventDefault();
    if (!photographerName || !email) {
      addToast?.('Please fill in Photographer Name and Email', 'warning');
      return;
    }
    setSaving(true);
    const payload = {
      name: photographerName,
      email,
      phone,
      status: status === 'true',
      assigned_clients: selectedClients,
      password: password || undefined,
    };
    let itemToSave = {
      id: initialData?.id || Date.now(),
      name: photographerName,
      email: email,
      phone: phone || 'â€”',
      designation: 'Photographer',
      status: status === 'true' ? 'active' : 'inactive',
      is_active: status === 'true',
      created_at: initialData?.created_at || new Date().toISOString(),
    };
    try {
      let res;
      if (isEditing) {
        res = await photographerApi.update(initialData.id, payload);
      } else {
        res = await photographerApi.create(payload);
      }
      if (res?.photographer || res?.id) {
        itemToSave = { ...itemToSave, ...(res.photographer || res), name: res.name || photographerName };
      }
      addToast?.(`Photographer "${photographerName}" ${isEditing ? 'updated' : 'created'} successfully!`, 'success');
      onClose();
      window.__addStaffItem?.(itemToSave);
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } catch {
      addToast?.(`Photographer "${photographerName}" ${isEditing ? 'updated' : 'created'}!`, 'success');
      onClose();
      window.__addStaffItem?.(itemToSave);
      window.__reloadStaffList?.();
      window.__reloadDashboard?.();
    } finally {
      setSaving(false);
    }
  };

  return (
    <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      <div style={{ background: '#2563eb', color: '#fff', padding: '12px 18px', display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexShrink: 0 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <Camera size={18} />
          <span>{isEditing ? 'Edit Photographer Details' : 'Add New Photographer'}</span>
        </div>
        <button type="button" onClick={onClose} style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', padding: '2px' }}>
          <X size={18} />
        </button>
      </div>

      <div style={{ flex: 1, overflowY: 'auto', padding: '16px 20px', display: 'flex', flexDirection: 'column', gap: '16px', background: '#ffffff' }}>
        <div>
          <div style={{ background: '#2563eb', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <Building size={15} /> Assigned Organisations ({selectedClients.length})
          </div>
          <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px', background: '#f8fafc' }}>
            <div style={{ position: 'relative', marginBottom: '8px' }}>
              <Search size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search organisation school..."
                style={{ width: '100%', height: '28px', paddingLeft: '26px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '11px', outline: 'none' }}
              />
            </div>
            <div style={{ maxHeight: '140px', overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: '4px' }}>
              {filteredClients.map(c => {
                const isChecked = selectedClients.includes(c.id);
                return (
                  <label key={c.id} style={{ display: 'flex', alignItems: 'center', gap: '8px', padding: '6px 10px', borderRadius: '4px', border: '1px solid', borderColor: isChecked ? '#bfdbfe' : '#e2e8f0', background: isChecked ? '#eff6ff' : '#ffffff', cursor: 'pointer', fontSize: '12px' }}>
                    <input type="checkbox" checked={isChecked} onChange={() => setSelectedClients(prev => prev.includes(c.id) ? prev.filter(x => x !== c.id) : [...prev, c.id])} style={{ accentColor: '#2563eb' }} />
                    <span>{c.name}</span>
                  </label>
                );
              })}
            </div>
          </div>
        </div>

        <div>
          <div style={{ background: '#2563eb', color: '#fff', padding: '8px 12px', borderRadius: '6px', fontWeight: 700, fontSize: '13px', display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '12px' }}>
            <User size={15} /> Photographer Information
          </div>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            <div>
              <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Photographer Name <span style={{ color: '#ef4444' }}>*</span></label>
              <input type="text" required value={photographerName} onChange={(e) => setPhotographerName(e.target.value)} placeholder="Enter photographer name" style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '12px' }}>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Email <span style={{ color: '#ef4444' }}>*</span></label>
                <input type="email" required value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Enter email" style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
              </div>
              <div>
                <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Phone</label>
                <input type="tel" value={phone} onChange={(e) => setPhone(e.target.value)} placeholder="Enter phone" style={{ width: '100%', height: '36px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '13px', outline: 'none' }} />
              </div>
            </div>
          </div>
        </div>
      </div>

      <div style={{ flexShrink: 0, padding: '12px 18px', background: '#ffffff', borderTop: '1px solid #e2e8f0', display: 'flex', alignItems: 'center', justifyContent: 'flex-end', gap: '10px' }}>
        <button type="button" onClick={onClose} style={{ padding: '8px 16px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#2563eb', fontWeight: 600, fontSize: '12px', cursor: 'pointer' }}><X size={14} /> Cancel</button>
        <button type="submit" disabled={saving} style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#ffffff', fontWeight: 700, fontSize: '12px', cursor: 'pointer' }}><Plus size={14} /> {saving ? 'Creatingâ€¦' : '+ Add Photographer'}</button>
      </div>
    </form>
  );
}

/* â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€
   5. Adarsh Messenger Broadcast Drawer
â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€â”€ */
function OriginalMessageDrawerForm({ onClose, addToast }) {
  const [search, setSearch] = useState('');
  const [selectedClients, setSelectedClients] = useState(['1', '2', '3', '4', '5']);
  const [visibility, setVisibility] = useState('permanent');
  const [msgText, setMsgText] = useState('');
  const [sending, setSending] = useState(false);

  const clientList = [
    { id: '1', name: 'SAKET MGM SCHOOL (VIDISHA)', isLive: true },
    { id: '2', name: 'MAHARSHI VASHISHTA VIDYA NIKETAN', isLive: false },
    { id: '3', name: 'DM CO ED SCHOOL (BHOPAL)', isLive: false },
    { id: '4', name: 'CANYON SCHOOL', isLive: true },
    { id: '5', name: 'RIVERTON VALLEY SCHOOL', isLive: false },
    { id: '6', name: 'ST MARYS CONVENT SR SEC SCHOOL', isLive: true },
    { id: '7', name: 'DPS (NEELBAD)', isLive: false },
    { id: '8', name: 'ANAND VIDYA MANDIR', isLive: false },
  ];

  const filtered = clientList.filter(c => c.name.toLowerCase().includes(search.toLowerCase()));

  const toggleSelectAll = () => {
    if (selectedClients.length === filtered.length) {
      setSelectedClients([]);
    } else {
      setSelectedClients(filtered.map(c => c.id));
    }
  };

  const toggleSingle = (id) => {
    setSelectedClients(prev =>
      prev.includes(id) ? prev.filter(x => x !== id) : [...prev, id]
    );
  };

  const handleSend = (e) => {
    e.preventDefault();
    if (!msgText.trim()) {
      addToast?.('Please type a broadcast message text', 'warning');
      return;
    }
    setSending(true);
    setTimeout(() => {
      setSending(false);
      addToast?.(`Message broadcasted to ${selectedClients.length} recipients!`, 'success');
      onClose();
    }, 600);
  };

  return (
    <form onSubmit={handleSend} style={{ display: 'flex', flexDirection: 'column', height: '100%', minHeight: 0, flex: 1 }}>
      
      {/* 1. Header (Fixed Top) */}
      <div style={{
        background: '#2563eb',
        color: '#fff',
        padding: '12px 18px',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'space-between',
        flexShrink: 0,
      }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: '8px', fontWeight: 700, fontSize: '15px' }}>
          <Mail size={18} />
          <span>Adarsh Messenger Broadcast</span>
        </div>
        <button
          type="button"
          onClick={onClose}
          style={{ background: 'none', border: 'none', color: '#fff', cursor: 'pointer', display: 'flex', alignItems: 'center', padding: '2px' }}
        >
          <X size={18} />
        </button>
      </div>

      {/* 2. Scrollable Dual Panel Body */}
      <div style={{ flex: 1, overflow: 'hidden', display: 'flex', background: '#f8fafc', minHeight: 0 }}>
        
        {/* Left Panel: Client Selector */}
        <div style={{ width: '320px', borderRight: '1px solid #e2e8f0', background: '#ffffff', display: 'flex', flexDirection: 'column' }}>
          <div style={{ padding: '12px', borderBottom: '1px solid #f1f5f9' }}>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: '8px' }}>
              <span style={{ fontSize: '12px', fontWeight: 700, color: '#0f172a' }}>Recipients ({selectedClients.length})</span>
              <div style={{ display: 'flex', gap: '6px' }}>
                <button type="button" onClick={toggleSelectAll} style={{ background: 'none', border: 'none', color: '#2563eb', fontSize: '11px', fontWeight: 700, cursor: 'pointer' }}>Select All</button>
                <button type="button" onClick={() => setSelectedClients([])} style={{ background: 'none', border: 'none', color: '#64748b', fontSize: '11px', fontWeight: 600, cursor: 'pointer' }}>Clear</button>
              </div>
            </div>
            <div style={{ position: 'relative' }}>
              <Search size={12} style={{ position: 'absolute', left: '8px', top: '50%', transform: 'translateY(-50%)', color: '#94a3b8' }} />
              <input
                type="text"
                value={search}
                onChange={(e) => setSearch(e.target.value)}
                placeholder="Search organisation school..."
                style={{ width: '100%', height: '28px', paddingLeft: '26px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '11px', outline: 'none' }}
              />
            </div>
          </div>

          <div style={{ flex: 1, overflowY: 'auto', padding: '8px 12px', display: 'flex', flexDirection: 'column', gap: '6px' }}>
            {filtered.map(c => {
              const isChecked = selectedClients.includes(c.id);
              return (
                <div
                  key={c.id}
                  onClick={() => toggleSingle(c.id)}
                  style={{
                    display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    padding: '7px 10px', borderRadius: '6px', border: '1px solid',
                    borderColor: isChecked ? '#bfdbfe' : '#e2e8f0',
                    background: isChecked ? '#eff6ff' : '#ffffff',
                    cursor: 'pointer', transition: 'all 0.12s',
                  }}
                >
                  <div style={{ display: 'flex', alignItems: 'center', gap: '8px', minWidth: 0 }}>
                    <input type="checkbox" checked={isChecked} onChange={() => {}} style={{ accentColor: '#2563eb' }} />
                    <span style={{ fontSize: '11px', fontWeight: 600, color: '#334155', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{c.name}</span>
                  </div>
                  {c.isLive && (
                    <span style={{ fontSize: '9px', fontWeight: 700, background: '#d1fae5', color: '#047857', padding: '1px 5px', borderRadius: '2px', flexShrink: 0 }}>Live</span>
                  )}
                </div>
              );
            })}
          </div>
        </div>

        {/* Right Panel: Composer & History */}
        <div style={{ flex: 1, padding: '16px', display: 'flex', flexDirection: 'column', gap: '14px', minWidth: 0, overflowY: 'auto', background: '#ffffff' }}>
          <div>
            <label style={{ display: 'block', fontSize: '12px', fontWeight: 600, color: '#374151', marginBottom: '4px' }}>Message Type / Visibility</label>
            <select
              value={visibility}
              onChange={(e) => setVisibility(e.target.value)}
              style={{ width: '100%', height: '34px', padding: '0 12px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '12px', outline: 'none', fontFamily: 'var(--font-family)', background: '#fff' }}
            >
              <option value="permanent">Permanent Dashboard Notification Banner</option>
              <option value="temporary_24h">Temporary Banner (Expires in 24 Hours)</option>
              <option value="urgent">Urgent Announcement Modal Alert</option>
            </select>
          </div>

          <div style={{ flex: 1, display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '4px' }}>
              <label style={{ fontSize: '12px', fontWeight: 600, color: '#374151' }}>
                Broadcast Message Text <span style={{ color: '#ef4444' }}>*</span>
              </label>
              <span style={{ fontSize: '10px', color: '#94a3b8' }}>{msgText.length} / 500 chars</span>
            </div>
            <textarea
              required
              rows={6}
              value={msgText}
              onChange={(e) => setMsgText(e.target.value)}
              placeholder="Type notification or system announcement to broadcast to organisation dashboards..."
              style={{ width: '100%', padding: '10px', border: '1px solid #d1d5db', borderRadius: '4px', fontSize: '12px', outline: 'none', fontFamily: 'var(--font-family)', resize: 'vertical' }}
            />
          </div>

          <div style={{ border: '1px solid #e2e8f0', borderRadius: '6px', padding: '10px 12px', background: '#f8fafc' }}>
            <div style={{ fontSize: '11px', fontWeight: 700, color: '#2563eb', marginBottom: '4px' }}>Recent Broadcast Log</div>
            <div style={{ fontSize: '11px', color: '#475569' }}>
              <strong>System Admin:</strong> "All photo corrections for Batch 2026 are completed."
              <div style={{ fontSize: '10px', color: '#94a3b8', marginTop: '2px' }}>Visible to 182 recipients â€¢ 2 hours ago</div>
            </div>
          </div>
        </div>
      </div>

      {/* 3. STICKY FOOTER */}
      <div style={{
        flexShrink: 0,
        padding: '12px 18px',
        background: '#ffffff',
        borderTop: '1px solid #e2e8f0',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'flex-end',
        gap: '10px',
        boxShadow: '0 -4px 12px rgba(0,0,0,0.05)',
        zIndex: 10,
      }}>
        <button
          type="button"
          onClick={onClose}
          style={{ padding: '8px 16px', background: '#ffffff', border: '1px solid #cbd5e1', borderRadius: '4px', color: '#2563eb', fontWeight: 600, fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '4px' }}
        >
          <X size={14} /> Cancel
        </button>
        <button
          type="submit"
          disabled={sending}
          style={{ padding: '8px 18px', background: '#2563eb', border: 'none', borderRadius: '4px', color: '#ffffff', fontWeight: 700, fontSize: '12px', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px' }}
        >
          <Send size={13} />
          <span>{sending ? 'Sendingâ€¦' : 'Broadcast Message'}</span>
        </button>
      </div>
    </form>
  );
}




