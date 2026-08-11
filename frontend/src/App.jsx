import React, { useState, useEffect, useCallback } from 'react';
import PageTransition from './components/common/PageTransition';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import DashboardView from './components/dashboard/DashboardView';
import Footer from './components/layout/Footer';

import ClientDirectoryView from './components/client/ClientDirectoryView';
import ClientAccountsView from './components/client/ClientAccountsView';
import StaffManagementView from './components/staff/StaffManagementView';
import ManagePanelView from './components/panel/ManagePanelView';
import CardActionBar from './components/idcard/CardActionBar';
import CardTableView from './components/idcard/CardTableView';
import IDCardActionsView from './components/idcard/IDCardActionsView';
import CardDownloadsModal from './components/idcard/CardDownloadsModal';
import GlobalSearchModal from './components/common/GlobalSearchModal';
import ConfirmDeleteModal from './components/common/ConfirmDeleteModal';
import { Toaster, toast } from 'sonner';
import ErrorBoundary from './components/common/ErrorBoundary';
import OldVersionWarningModal from './components/idcard/OldVersionWarningModal';
import ReprintCardsManagerView from './components/reprint/ReprintCardsManagerView';
import TableSettingsView from './components/settings/TableSettingsView';
import ProfileSettingsView from './components/settings/ProfileSettingsView';

import TutorialGuideView from './components/tutorial/TutorialGuideView';
import ManageFeaturesView from './components/pro/ManageFeaturesView';
import AuthFlowContainer from './components/auth/AuthFlowContainer';
import Preloader from './components/common/Preloader';
import { authApi } from './services/api';

import QuickActionDrawer from './components/dashboard/QuickActionDrawer';

import { UserCog, X } from 'lucide-react';

const BOOT = { LOADING: 'loading', AUTH: 'auth', UNAUTH: 'unauth' };

export default function App() {
  const [bootState, setBootState] = useState(BOOT.LOADING);
  const [currentUser, setCurrentUser] = useState(null);
  const [userRole, setUserRole] = useState('super_admin');
  const [impersonatedUser, setImpersonatedUser] = useState(null);
  const [activeTab, setActiveTab] = useState('dashboard');
  const [activeTableId, setActiveTableId] = useState(null); // set when navigating from cardflow → cards
  const [idcardActionsState, setIdcardActionsState] = useState(null); // { tableId, status }
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedClient, setSelectedClient] = useState('all');

  // Register global impersonation callback
  useEffect(() => {
    window.__setActiveImpersonation = (user) => {
      setImpersonatedUser(user);
      if (user) {
        setUserRole(user.rawRole || 'client');
      } else {
        setUserRole('super_admin');
      }
    };
  }, []);

  // Modals & Drawers
  const [drawerAction, setDrawerAction] = useState(null);
  const [drawerInitialData, setDrawerInitialData] = useState(null);
  const [showDownloadsModal, setShowDownloadsModal] = useState(false);
  const [showSearchModal, setShowSearchModal] = useState(false);
  const [deleteModalConfig, setDeleteModalConfig] = useState(null);
  const [showWarningModal, setShowWarningModal] = useState(false);
  const [warningData, setWarningData] = useState(null);

  const handleOpenActionDrawer = useCallback((action, initialData = null) => {
    setDrawerAction(action);
    setDrawerInitialData(initialData);
  }, []);

  // Toasts — powered by Sonner (zero call-site changes needed)
  const addToast = useCallback((message, type = 'info') => {
    if (type === 'success') toast.success(message);
    else if (type === 'error') toast.error(message);
    else if (type === 'warning') toast.warning(message);
    else toast.info(message);
  }, []);

  // Auth bootstrap — check session on mount
  useEffect(() => {
    // Immediate fallback so app NEVER gets stuck loading
    const timer = setTimeout(() => {
      setBootState((prev) => (prev === BOOT.LOADING ? BOOT.AUTH : prev));
    }, 400);

    authApi
      .getCurrentUser()
      .then((data) => {
        if (data && (data.authenticated || data.user || data.username)) {
          setCurrentUser(data.user || data);
          setUserRole(data.user?.role || data.role || 'super_admin');
        }
        setBootState(BOOT.AUTH);
      })
      .catch(() => {
        setBootState(BOOT.AUTH);
      })
      .finally(() => clearTimeout(timer));
  }, []);

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (_) {}
    setBootState(BOOT.UNAUTH);
    setCurrentUser(null);
  };

  // ── Loading splash ──────────────────────────────────────────────────────────
  if (bootState === BOOT.LOADING) {
    return (
      <div
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          background: '#f4f4f4',
          flexDirection: 'column',
          gap: '12px',
        }}
      >
        <div
          style={{
            width: '30px',
            height: '30px',
            border: '3px solid #667eea',
            borderTopColor: 'transparent',
            borderRadius: '50%',
            animation: 'spin 0.8s linear infinite',
          }}
        />
        <span style={{ color: '#6b7280', fontSize: '13px', fontFamily: '"Saira Semi Condensed", sans-serif' }}>
          Loading CardFlow…
        </span>
      </div>
    );
  }

  // ── Auth Flow ─────────────────────────────────────────────────────────────────
  if (bootState === BOOT.UNAUTH) {
    return (
      <AuthFlowContainer
        onLoginSuccess={(user) => {
          if (user) {
            setCurrentUser(user);
            setUserRole(user.role || 'super_admin');
          }
          setBootState(BOOT.AUTH);
          addToast('Welcome back!', 'success');
        }}
      />
    );
  }

  // ── App Shell ───────────────────────────────────────────────────────────────
  return (
    <div className="app-container">
      {/* Premium Ambient Preloader */}
      <Preloader currentUser={currentUser} />

      {/* Dark sidebar */}

      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        userRole={userRole}
        currentUser={currentUser}
        onLogout={handleLogout}
      />

      {/* Right: topbar + page content */}
      <div className="main-content">
        {/* Active Impersonation Alert Banner */}
        {impersonatedUser && (
          <div
            style={{
              background: 'linear-gradient(90deg, #dc2626 0%, #b91c1c 100%)',
              color: '#ffffff',
              padding: '8px 16px',
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
              fontSize: '12px',
              fontWeight: 600,
              zIndex: 999,
              boxShadow: '0 2px 10px rgba(220,38,38,0.3)',
            }}
          >
            <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
              <UserCog size={16} />
              <span>
                Active Impersonation Session: <strong>{impersonatedUser.name}</strong> (
                {impersonatedUser.role || impersonatedUser.email})
              </span>
            </div>
            <button
              onClick={() => {
                window.__setActiveImpersonation?.(null);
                addToast('Impersonation session ended. Returned to Super Admin.', 'success');
              }}
              style={{
                background: '#ffffff',
                color: '#dc2626',
                border: 'none',
                borderRadius: '4px',
                padding: '3px 10px',
                fontSize: '11px',
                fontWeight: 700,
                cursor: 'pointer',
                display: 'flex',
                alignItems: 'center',
                gap: '4px',
              }}
            >
              <X size={13} /> Exit Impersonation
            </button>
          </div>
        )}

        {/* Top bar header — Dashboard only */}
        {activeTab === 'dashboard' && (
          <Header
            activeTab={activeTab}
            searchQuery={searchQuery}
            setSearchQuery={(q) => {
              setSearchQuery(q);
              if (q.length > 1) setShowSearchModal(true);
            }}
            selectedClient={selectedClient}
            setSelectedClient={setSelectedClient}
            userRole={userRole}
            currentUser={currentUser}
            onLogout={handleLogout}
          />
        )}

        {/* Page content — scrollable area */}
        <div
          className="page-content"
          style={
            activeTab === 'idcard-actions' ? { padding: 0, margin: 0, height: '100%', overflow: 'hidden' } : undefined
          }
        >
          <ErrorBoundary key={activeTab}>
            <PageTransition pageKey={activeTab} fullHeight={activeTab === 'idcard-actions'}>
              {/* ── Dashboard ── */}
              {activeTab === 'dashboard' && (
                <DashboardView
                  onNavigate={(dest, params) => {
                    if (dest === 'idcard-actions' || (params && (params.tableId || params.table_id))) {
                      const tid = params?.tableId || params?.table_id || 1;
                      const st = params?.status || params?.statusFilter || 'pending';
                      setIdcardActionsState({ tableId: tid, status: st });
                      setActiveTab('idcard-actions');
                    } else if (dest === 'cards') {
                      setActiveTab('cards');
                    } else if (dest) {
                      setActiveTab(dest);
                    }
                  }}
                  currentUser={currentUser}
                  onOpenActionDrawer={(actionType) => setDrawerAction(actionType)}
                />
              )}

              {/* ── ID Cards / Table Group ── */}
              {activeTab === 'cards' && (
                <CardTableView
                  addToast={addToast}
                  onNavigate={(tabOrObj, params) => {
                    if (typeof tabOrObj === 'string' && tabOrObj === 'idcard-actions' && params) {
                      setIdcardActionsState({ tableId: params.tableId, status: params.status || 'pending' });
                      setActiveTab('idcard-actions');
                    } else if (typeof tabOrObj === 'string') {
                      setActiveTab(tabOrObj);
                    }
                  }}
                />
              )}

              {/* ── ID Card Actions (full card list view per table/status) ── */}
              {activeTab === 'idcard-actions' && idcardActionsState && (
                <IDCardActionsView
                  tableId={idcardActionsState.tableId}
                  initialStatus={idcardActionsState.status || 'pending'}
                  addToast={addToast}
                  onBack={() => {
                    setActiveTab('cards');
                    setIdcardActionsState(null);
                  }}
                  onNavigate={(tab, params) => {
                    if (tab === 'table-settings' || tab === 'schema') {
                      if (params?.tableId) setActiveTableId(params.tableId);
                      setActiveTab('schema');
                    } else if (tab === 'cards' || tab === 'idcard-group') {
                      setActiveTab('cards');
                      setIdcardActionsState(null);
                    } else if (typeof tab === 'string') {
                      setActiveTab(tab);
                    }
                  }}
                />
              )}

              {/* ── Reprint Queue ── */}
              {activeTab === 'reprints' && <ReprintCardsManagerView addToast={addToast} />}

              {/* ── Manage Organisation ── */}
              {activeTab === 'organisations' && (
                <ClientDirectoryView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              )}

              {/* ── Manage Client ── */}
              {activeTab === 'clients' && (
                <ClientAccountsView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              )}

              {/* ── Manage Staff/Operator ── */}
              {activeTab === 'staff' && (
                <StaffManagementView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              )}

              {/* ── Manage Assistants ── */}
              {activeTab === 'assistants' && (
                <StaffManagementView
                  addToast={addToast}
                  staffType="assistant"
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              )}

              {/* ── Manage Photographers ── */}
              {activeTab === 'photographers' && (
                <StaffManagementView
                  addToast={addToast}
                  staffType="photographer"
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              )}

              {/* ── Table Settings (Merged into CardTableView) ── */}
              {activeTab === 'schema' && <CardTableView addToast={addToast} onNavigate={setActiveTab} />}

              {/* ── System/Control Panel ── */}
              {activeTab === 'panel' && <ManagePanelView addToast={addToast} />}

              {/* ── Tutorial ── */}
              {activeTab === 'tutorial' && <TutorialGuideView />}

              {/* ── Settings / Profile ── */}
              {(activeTab === 'settings' || activeTab === 'profile') && (
                <ProfileSettingsView addToast={addToast} currentUser={currentUser} />
              )}

              {/* ── Manage Features / Pro Features ── */}
              {activeTab === 'pro' && <ManageFeaturesView addToast={addToast} />}
            </PageTransition>
          </ErrorBoundary>
        </div>

        {/* Global Black Footer */}
        <Footer activeTab={activeTab} onNavigate={setActiveTab} idcardActionsState={idcardActionsState} />
      </div>

      {/* ── Global Modals & Drawers ── */}
      <QuickActionDrawer
        isOpen={!!drawerAction}
        actionType={drawerAction}
        initialData={drawerInitialData}
        onClose={() => {
          setDrawerAction(null);
          setDrawerInitialData(null);
        }}
        addToast={addToast}
      />
      <CardDownloadsModal isOpen={showDownloadsModal} onClose={() => setShowDownloadsModal(false)} />

      <GlobalSearchModal isOpen={showSearchModal} onClose={() => setShowSearchModal(false)} />
      <ConfirmDeleteModal
        isOpen={!!deleteModalConfig}
        onClose={() => setDeleteModalConfig(null)}
        title={deleteModalConfig?.title || 'Confirm Permanent Delete'}
        itemDescription={deleteModalConfig?.itemDescription || 'this item'}
        onConfirm={() => {
          deleteModalConfig?.onConfirm?.();
          setDeleteModalConfig(null);
        }}
      />

      <OldVersionWarningModal
        isOpen={showWarningModal}
        warningData={warningData}
        onClose={() => setShowWarningModal(false)}
        onConfirmOverwrite={() => {
          setShowWarningModal(false);
          addToast('Overwrite confirmed', 'warning');
        }}
      />
      {/* Sonner Toast Container — dark theme to match app */}
      <Toaster
        position="bottom-right"
        theme="dark"
        richColors
        closeButton
        duration={4500}
        toastOptions={{
          style: {
            fontFamily: 'var(--font-family)',
            fontSize: '13px',
            borderRadius: '8px',
          },
        }}
      />
    </div>
  );
}
