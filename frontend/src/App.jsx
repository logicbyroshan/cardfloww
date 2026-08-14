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
import { authApi, impersonateApi } from './services/api';

import QuickActionDrawer from './components/dashboard/QuickActionDrawer';

import { UserCog, X, Smartphone, Download } from 'lucide-react';
import Lenis from 'lenis';

const BOOT = { LOADING: 'loading', AUTH: 'auth', UNAUTH: 'unauth' };

function MobileAppFallback({ onForceDesktop }) {
  return (
    <div
      style={{
        minHeight: '100vh',
        width: '100vw',
        background: 'linear-gradient(135deg, #0f172a 0%, #1e1e2e 100%)',
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        padding: '24px',
        color: '#ffffff',
        fontFamily: "'Saira Semi Condensed', sans-serif",
        textAlign: 'center',
        boxSizing: 'border-box',
        position: 'fixed',
        top: 0,
        left: 0,
        zIndex: 999999,
      }}
    >
      <div style={{ marginBottom: '24px' }}>
        <img
          src="/static/cardflow_logo_brand.png"
          onError={(e) => {
            if (!e.target.src.endsWith('/cardflow_logo_brand.png')) {
              e.target.src = '/cardflow_logo_brand.png';
            }
          }}
          alt="CardFlow"
          style={{ height: '44px', objectFit: 'contain' }}
        />
      </div>

      <div
        style={{
          maxWidth: '460px',
          width: '100%',
          background: 'rgba(255, 255, 255, 0.05)',
          border: '1px solid rgba(255, 255, 255, 0.12)',
          borderRadius: '16px',
          padding: '32px 24px',
          backdropFilter: 'blur(16px)',
          WebkitBackdropFilter: 'blur(16px)',
          boxShadow: '0 20px 40px rgba(0, 0, 0, 0.4)',
        }}
      >
        <div
          style={{
            width: '64px',
            height: '64px',
            borderRadius: '16px',
            background: 'linear-gradient(135deg, #0050d2 0%, #00b4ff 100%)',
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            margin: '0 auto 20px',
            boxShadow: '0 8px 24px rgba(0, 180, 255, 0.35)',
          }}
        >
          <Smartphone size={32} color="#ffffff" />
        </div>

        <h2
          style={{
            fontSize: '22px',
            fontWeight: 700,
            marginBottom: '12px',
            color: '#ffffff',
            letterSpacing: '-0.3px',
          }}
        >
          Please Download the CardFlow Mobile App
        </h2>

        <p
          style={{
            fontSize: '14px',
            color: '#94a3b8',
            lineHeight: '1.5',
            marginBottom: '24px',
          }}
        >
          The CardFlow Desktop Portal is optimized for desktop displays (1000px – 2000px). For mobile devices and screens below 1000px, please download the official CardFlow Mobile App.
        </p>

        <div style={{ display: 'flex', flexDirection: 'column', gap: '12px', marginBottom: '20px' }}>
          <a
            href="/static/app/cardflow-mobile-latest.apk"
            download
            style={{
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'center',
              gap: '10px',
              padding: '12px 20px',
              borderRadius: '8px',
              background: 'linear-gradient(135deg, #10b981 0%, #059669 100%)',
              color: '#ffffff',
              fontWeight: 700,
              fontSize: '14px',
              textDecoration: 'none',
              boxShadow: '0 4px 14px rgba(16, 185, 129, 0.3)',
            }}
          >
            <Download size={18} />
            <span>Download Android App (.APK)</span>
          </a>

          <button
            onClick={onForceDesktop}
            style={{
              padding: '10px 16px',
              borderRadius: '8px',
              background: 'transparent',
              border: '1px solid rgba(255, 255, 255, 0.2)',
              color: '#cbd5e1',
              fontSize: '12px',
              fontWeight: 600,
              cursor: 'pointer',
              transition: 'all 0.2s ease',
            }}
            onMouseEnter={(e) => {
              e.currentTarget.style.borderColor = '#ffffff';
              e.currentTarget.style.color = '#ffffff';
            }}
            onMouseLeave={(e) => {
              e.currentTarget.style.borderColor = 'rgba(255, 255, 255, 0.2)';
              e.currentTarget.style.color = '#cbd5e1';
            }}
          >
            Continue to Desktop Web View Anyway (Force Mode)
          </button>
        </div>

        <div style={{ fontSize: '11px', color: '#64748b' }}>
          Desktop Optimization Bounds: 1000px – 2000px Width
        </div>
      </div>
    </div>
  );
}

export default function App() {
  const [bootState, setBootState] = useState(BOOT.LOADING);
  const [currentUser, setCurrentUser] = useState(null);
  const [userRole, setUserRole] = useState('super_admin');
  const [impersonatedUser, setImpersonatedUser] = useState(null);
  const [activeTab, setActiveTab] = useState(() => {
    if (typeof window !== 'undefined') {
      const path = window.location.pathname;
      const pathToTab = {
        '/': 'dashboard',
        '/dashboard': 'dashboard',
        '/cards': 'cards',
        '/reprints': 'reprints',
        '/organisations': 'organisations',
        '/clients': 'clients',
        '/staff': 'staff',
        '/assistants': 'assistants',
        '/photographers': 'photographers',
        '/panel': 'panel',
        '/tutorial': 'tutorial',
        '/settings': 'settings',
        '/pro': 'pro',
        '/profile': 'profile',
      };
      return pathToTab[path] || 'dashboard';
    }
    return 'dashboard';
  });
  const [activeTableId, setActiveTableId] = useState(null); // set when navigating from cardflow → cards
  const [idcardActionsState, setIdcardActionsState] = useState(null); // { tableId, status }
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedClient, setSelectedClient] = useState('all');
  const [windowWidth, setWindowWidth] = useState(typeof window !== 'undefined' ? window.innerWidth : 1200);
  const [forceDesktop, setForceDesktop] = useState(false);

  useEffect(() => {
    const handleResize = () => setWindowWidth(window.innerWidth);
    window.addEventListener('resize', handleResize);
    return () => window.removeEventListener('resize', handleResize);
  }, []);

  // Clean URL query parameters and sync semantic path aliases
  useEffect(() => {
    if (typeof window !== 'undefined' && window.location.search) {
      const urlParams = new URLSearchParams(window.location.search);
      if (urlParams.has('next')) {
        urlParams.delete('next');
        const cleanSearch = urlParams.toString();
        const cleanUrl = window.location.pathname + (cleanSearch ? `?${cleanSearch}` : '');
        window.history.replaceState({}, document.title, cleanUrl);
      }
    }
  }, []);

  // Sync clean, semantic role URLs in browser address bar and sync routes
  useEffect(() => {
    if (bootState === BOOT.UNAUTH) {
      if (window.location.pathname !== '/auth/login' && window.location.pathname !== '/login') {
        window.history.replaceState({}, document.title, '/auth/login');
      }
      return;
    }

    if (bootState === BOOT.AUTH) {
      const path = window.location.pathname;
      if (path === '/auth/login' || path === '/login') {
        window.history.replaceState({}, document.title, '/');
      } else {
        const routeMap = {
          dashboard: '/',
          cards: '/cards',
          reprints: '/reprints',
          organisations: '/organisations',
          clients: '/clients',
          staff: '/staff',
          assistants: '/assistants',
          photographers: '/photographers',
          panel: '/panel',
          tutorial: '/tutorial',
          settings: '/settings',
          pro: '/pro',
          profile: '/profile',
        };
        const targetRoute = routeMap[activeTab] || '/';
        if (path !== targetRoute && path !== '/dashboard' && !path.includes('table/')) {
          window.history.pushState({}, document.title, targetRoute);
        }
      }
    }
  }, [bootState, activeTab]);

  // Handle browser back/forward buttons (popstate)
  useEffect(() => {
    const handlePopState = () => {
      const path = window.location.pathname;
      const pathToTab = {
        '/': 'dashboard',
        '/dashboard': 'dashboard',
        '/cards': 'cards',
        '/reprints': 'reprints',
        '/organisations': 'organisations',
        '/clients': 'clients',
        '/staff': 'staff',
        '/assistants': 'assistants',
        '/photographers': 'photographers',
        '/panel': 'panel',
        '/tutorial': 'tutorial',
        '/settings': 'settings',
        '/pro': 'pro',
        '/profile': 'profile',
      };
      const matchedTab = pathToTab[path];
      if (matchedTab) {
        setActiveTab(matchedTab);
      }
    };
    window.addEventListener('popstate', handlePopState);
    return () => window.removeEventListener('popstate', handlePopState);
  }, []);

  // Native scroll handling for nested scroll containers
  useEffect(() => {
    // Native browser scrolling for nested tables and views
    return () => {};
  }, []);

  // Register global impersonation callback
  useEffect(() => {
    window.__setActiveImpersonation = (user) => {
      setImpersonatedUser(user);
      if (user) {
        setUserRole(user.rawRole || 'prime_manager');
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

  // Toasts — powered by Sonner
  const addToast = useCallback((message, type = 'info') => {
    if (type === 'success') toast.success(message);
    else if (type === 'error') toast.error(message);
    else if (type === 'warning') toast.warning(message);
    else toast.info(message);
  }, []);

  // Auth bootstrap & impersonation re-sync
  const refreshUser = useCallback(async () => {
    try {
      const data = await authApi.getCurrentUser();
      if (data && (data.authenticated || data.user || data.username)) {
        const u = data.user || data;
        setCurrentUser(u);
        const role = u.role || 'super_admin';
        setUserRole(role);

        if (data.is_impersonating && data.impersonator) {
          setImpersonatedUser({
            name: u.full_name || u.username,
            role: role,
            email: u.email,
            impersonator: data.impersonator,
          });
        } else {
          setImpersonatedUser(null);
        }
        setBootState(BOOT.AUTH);
      } else {
        setCurrentUser(null);
        setImpersonatedUser(null);
        setBootState(BOOT.UNAUTH);
      }
    } catch (err) {
      console.warn('Auth refresh error:', err);
      setCurrentUser(null);
      setImpersonatedUser(null);
      setBootState(BOOT.UNAUTH);
    }
  }, []);

  useEffect(() => {
    window.__refreshAuthUser = refreshUser;
    window.__setActiveImpersonation = (user) => {
      if (user) {
        setImpersonatedUser(user);
        setUserRole(user.rawRole || user.role || 'prime_manager');
      } else {
        setImpersonatedUser(null);
        refreshUser();
      }
    };

    // Immediate fallback so app NEVER gets stuck loading
    const timer = setTimeout(() => {
      setBootState((prev) => (prev === BOOT.LOADING ? BOOT.UNAUTH : prev));
    }, 1200);

    // Prefetch CSRF cookie before auth check, then check auth state.
    fetch('/api/auth/csrf/', { credentials: 'include' })
      .catch(() => {})
      .finally(() => {
        refreshUser().finally(() => clearTimeout(timer));
      });
  }, [refreshUser]);

  const handleExitImpersonation = async () => {
    try {
      await impersonateApi.stop();
      addToast('Impersonation session ended. Returned to Super Admin.', 'success');
      await refreshUser();
      setActiveTab('dashboard');
    } catch (err) {
      addToast('Impersonation session ended.', 'info');
      await refreshUser();
      setActiveTab('dashboard');
    }
  };

  const handleLogout = async () => {
    try {
      await authApi.logout();
    } catch (_) {}
    setBootState(BOOT.UNAUTH);
    setCurrentUser(null);
    setImpersonatedUser(null);
    setUserRole('super_admin');
    setActiveTab('dashboard');
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
        onLoginSuccess={async (user) => {
          if (user) {
            setCurrentUser(user);
            if (user.role) setUserRole(user.role);
          }
          await refreshUser();
          setBootState(BOOT.AUTH);
          addToast('Welcome back!', 'success');
        }}
      />
    );
  }

  // ── Mobile Screen Boundary Gate (< 1000px) ──────────────────────────────
  if (windowWidth < 1000 && !forceDesktop) {
    return <MobileAppFallback onForceDesktop={() => setForceDesktop(true)} />;
  }

  const normRole = String(userRole || '').toLowerCase();
  const isAdminRole = normRole === 'super_admin' || normRole === 'pro_user' || normRole === 'admin';
  const isOrgRole = normRole === 'prime_manager' || normRole === 'client' || normRole === 'guest_prime_manager';

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
              onClick={handleExitImpersonation}
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

              {/* ── ID Cards / Tables ── */}
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
              {activeTab === 'organisations' && (isAdminRole ? (
                <ClientDirectoryView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Manage Client ── */}
              {activeTab === 'clients' && (isAdminRole ? (
                <ClientAccountsView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Manage Staff/Operator ── */}
              {activeTab === 'staff' && (isAdminRole ? (
                <StaffManagementView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Manage Assistants ── */}
              {activeTab === 'assistants' && ((isAdminRole || isOrgRole) ? (
                <StaffManagementView
                  addToast={addToast}
                  staffType="assistant"
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Manage Photographers ── */}
              {activeTab === 'photographers' && (isAdminRole ? (
                <StaffManagementView
                  addToast={addToast}
                  staffType="photographer"
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab) => setActiveTab(tab)}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Table Settings (Merged into CardTableView) ── */}
              {activeTab === 'schema' && <CardTableView addToast={addToast} onNavigate={setActiveTab} />}

              {/* ── System/Control Panel ── */}
              {activeTab === 'panel' && (isAdminRole ? (
                <ManagePanelView addToast={addToast} />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Tutorial ── */}
              {activeTab === 'tutorial' && <TutorialGuideView />}

              {/* ── Settings / Profile ── */}
              {(activeTab === 'settings' || activeTab === 'profile') && (
                <ProfileSettingsView addToast={addToast} currentUser={currentUser} />
              )}

              {/* ── Manage Features / Pro Features ── */}
              {activeTab === 'pro' && (isAdminRole ? (
                <ManageFeaturesView addToast={addToast} />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}
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
