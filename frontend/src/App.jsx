import React, { useState, useEffect, useCallback } from 'react';
import PageTransition from './components/common/PageTransition';
import Sidebar from './components/layout/Sidebar';
import Header from './components/layout/Header';
import DashboardView from './components/dashboard/DashboardView';
import Footer from './components/layout/Footer';

import OrganisationDirectoryView from './components/client/ClientDirectoryView';
import OperatorManagementView, {
  AssistantManagementView,
  PhotographerManagementView,
} from './components/staff/StaffManagementView';
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

function parsePathToRoute(pathname) {
  const path = pathname || (typeof window !== 'undefined' ? window.location.pathname : '/');

  // Match /table/:tableId/:status or /tables/:tableId/:status or /cards/:tableId/:status or /table/:tableId
  const tableMatch = path.match(/^\/(?:table|tables|cards)\/([^/]+)(?:\/([^/]+))?\/?$/);
  if (tableMatch) {
    const rawTid = tableMatch[1];
    const tableId = (rawTid && rawTid !== '??' && !isNaN(Number(rawTid))) ? Number(rawTid) : 1;
    const status = tableMatch[2] || 'pending';
    return {
      tab: 'idcard-actions',
      idcardActionsState: { tableId, status },
    };
  }

  const map = {
    '/': { tab: 'dashboard', idcardActionsState: null },
    '/dashboard': { tab: 'dashboard', idcardActionsState: null },
    '/tables': { tab: 'cards', idcardActionsState: null },
    '/cards': { tab: 'cards', idcardActionsState: null },
    '/reprints': { tab: 'reprints', idcardActionsState: null },
    '/organisations': { tab: 'organisations', idcardActionsState: null },
    '/organisation': { tab: 'organisations', idcardActionsState: null },
    '/managers': { tab: 'organisations', idcardActionsState: null },
    '/accounts': { tab: 'organisations', idcardActionsState: null },
    '/client-accounts': { tab: 'organisations', idcardActionsState: null },
    '/clients': { tab: 'organisations', idcardActionsState: null },
    '/operators': { tab: 'operators', idcardActionsState: null },
    '/operator': { tab: 'operators', idcardActionsState: null },
    '/staff': { tab: 'operators', idcardActionsState: null },
    '/assistants': { tab: 'assistants', idcardActionsState: null },
    '/assistant': { tab: 'assistants', idcardActionsState: null },
    '/photographers': { tab: 'photographers', idcardActionsState: null },
    '/photographer': { tab: 'photographers', idcardActionsState: null },
    '/panel': { tab: 'panel', idcardActionsState: null },
    '/tutorial': { tab: 'tutorial', idcardActionsState: null },
    '/settings': { tab: 'settings', idcardActionsState: null },
    '/pro': { tab: 'pro', idcardActionsState: null },
    '/profile': { tab: 'profile', idcardActionsState: null },
  };

  return map[path] || { tab: 'dashboard', idcardActionsState: null };
}

export default function App() {
  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const cached = localStorage.getItem('cf_auth_user') || sessionStorage.getItem('cf_auth_user');
      return cached ? JSON.parse(cached) : null;
    } catch (_) {
      return null;
    }
  });
  const [userRole, setUserRole] = useState(() => {
    try {
      const cached = localStorage.getItem('cf_auth_user') || sessionStorage.getItem('cf_auth_user');
      if (cached) {
        const u = JSON.parse(cached);
        return u.role || 'super_admin';
      }
    } catch (_) {}
    return 'super_admin';
  });
  const [bootState, setBootState] = useState(() => {
    try {
      const cached = localStorage.getItem('cf_auth_user') || sessionStorage.getItem('cf_auth_user');
      return cached ? BOOT.AUTH : BOOT.LOADING;
    } catch (_) {
      return BOOT.LOADING;
    }
  });
  const [impersonatedUser, setImpersonatedUser] = useState(null);
  const [activeTab, setActiveTab] = useState(() => parsePathToRoute().tab);
  const [activeTableId, setActiveTableId] = useState(null); // set when navigating from cardflow → cards
  const [idcardActionsState, setIdcardActionsState] = useState(() => parsePathToRoute().idcardActionsState); // { tableId, status }
  const [searchQuery, setSearchQuery] = useState('');
  const [selectedClient, setSelectedClient] = useState('all');
  const [scopedClientId, setScopedClientId] = useState(null);
  const [scopedClientOrg, setScopedClientOrg] = useState(null);
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
      } else if (activeTab === 'idcard-actions' && idcardActionsState?.tableId) {
        const targetRoute = `/table/${idcardActionsState.tableId}/${idcardActionsState.status || 'pending'}`;
        if (path !== targetRoute) {
          window.history.pushState({}, document.title, targetRoute);
        }
      } else {
        const routeMap = {
          dashboard: '/',
          cards: '/tables',
          tables: '/tables',
          reprints: '/reprints',
          organisations: '/organisations',
          clients: '/managers',
          operators: '/operators',
          staff: '/operators',
          assistants: '/assistants',
          photographers: '/photographers',
          panel: '/panel',
          tutorial: '/tutorial',
          settings: '/settings',
          pro: '/pro',
          profile: '/profile',
        };
        const targetRoute = routeMap[activeTab] || '/';
        if (path !== targetRoute && path !== '/dashboard') {
          window.history.pushState({}, document.title, targetRoute);
        }
      }
    }
  }, [bootState, activeTab, idcardActionsState]);

  // Handle browser back/forward buttons (popstate)
  useEffect(() => {
    const handlePopState = () => {
      const parsed = parsePathToRoute(window.location.pathname);
      setActiveTab(parsed.tab);
      setIdcardActionsState(parsed.idcardActionsState || null);
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

  const handleStatusChange = useCallback((newStatus) => {
    setIdcardActionsState((prev) => {
      if (!prev) return prev;
      if (prev.status === newStatus) return prev;
      return { ...prev, status: newStatus };
    });
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
        // Only set UNAUTH if server definitively responded that user is not authenticated
        try {
          localStorage.removeItem('cf_auth_user');
          sessionStorage.removeItem('cf_auth_user');
        } catch (_) {}
        setCurrentUser(null);
        setImpersonatedUser(null);
        setBootState(BOOT.UNAUTH);
      }
    } catch (err) {
      console.warn('Auth refresh error:', err);
      // If network error, don't immediately kick user out if they have a cached user
      const hasCached = localStorage.getItem('cf_auth_user') || sessionStorage.getItem('cf_auth_user');
      if (!hasCached) {
        setCurrentUser(null);
        setImpersonatedUser(null);
        setBootState(BOOT.UNAUTH);
      }
    }
  }, []);

  useEffect(() => {
    const handleUnauthorized = () => {
      try {
        localStorage.removeItem('cf_auth_user');
        sessionStorage.removeItem('cf_auth_user');
      } catch (_) {}
      setCurrentUser(null);
      setBootState(BOOT.UNAUTH);
    };
    window.addEventListener('cardflow:auth-unauthorized', handleUnauthorized);
    return () => window.removeEventListener('cardflow:auth-unauthorized', handleUnauthorized);
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

    // Safe 8s fallback timeout so app never gets stuck indefinitely
    const timer = setTimeout(() => {
      setBootState((prev) => {
        if (prev === BOOT.LOADING) {
          const hasCached = localStorage.getItem('cf_auth_user') || sessionStorage.getItem('cf_auth_user');
          return hasCached ? BOOT.AUTH : BOOT.UNAUTH;
        }
        return prev;
      });
    }, 8000);

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
    try {
      localStorage.removeItem('cf_auth_user');
      localStorage.removeItem('cf_remember_me');
      sessionStorage.removeItem('cf_auth_user');
    } catch (_) {}
    setBootState(BOOT.UNAUTH);
    setCurrentUser(null);
    setImpersonatedUser(null);
    setUserRole('super_admin');
    setActiveTab('dashboard');
  };

  // ── Loading splash ──────────────────────────────────────────────────────────
  if (bootState === BOOT.LOADING) {
    return <Preloader onFinished={() => {}} />;
  }

  // ── Mobile Screen Boundary Gate (< 1000px) ──────────────────────────────
  if (windowWidth < 1000 && !forceDesktop) {
    return <MobileAppFallback onForceDesktop={() => setForceDesktop(true)} />;
  }

  // ── Auth Flow ─────────────────────────────────────────────────────────────────
  if (bootState === BOOT.UNAUTH) {
    return (
      <AuthFlowContainer
        onLoginSuccess={async (user) => {
          if (user) {
            setCurrentUser(user);
            setUserRole(user.role || 'super_admin');
          }
          await refreshUser();
          setBootState(BOOT.AUTH);
          addToast('Welcome back!', 'success');
        }}
      />
    );
  }

  const normRole = String(userRole || '').toLowerCase();
  const isAdminRole = normRole === 'prime_admin' || normRole === 'super_admin' || normRole === 'pro_user' || normRole === 'admin';
  const isOrgRole = normRole === 'prime_manager' || normRole === 'super_manager' || normRole === 'manager' || normRole === 'client';
  const isOperatorRole = normRole === 'operator';

  return (
    <div className="app-container">
      {/* Dark sidebar */}
      <Sidebar
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        userRole={userRole}
        currentUser={currentUser}
        onLogout={handleLogout}
        impersonatedUser={impersonatedUser}
        onExitImpersonation={handleExitImpersonation}
      />

      {/* Right: topbar + page content */}
      <div className="main-content">

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
            onOpenActionDrawer={handleOpenActionDrawer}
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
                  onOpenActionDrawer={handleOpenActionDrawer}
                />
              )}

              {/* ── ID Cards / Tables ── */}
              {activeTab === 'cards' && (
                <CardTableView
                  addToast={addToast}
                  currentUser={currentUser}
                  userRole={userRole}
                  selectedClientId={scopedClientId}
                  selectedClientOrg={scopedClientOrg}
                  onClearSelectedClient={() => {
                    setScopedClientId(null);
                    setScopedClientOrg(null);
                  }}
                  onNavigate={(tabOrObj, params) => {
                    if (typeof tabOrObj === 'string' && tabOrObj === 'idcard-actions' && params) {
                      setIdcardActionsState({ tableId: params.tableId, status: params.status || 'pending' });
                      setActiveTab('idcard-actions');
                    } else if (typeof tabOrObj === 'string') {
                      if (tabOrObj !== 'cards') {
                        setScopedClientId(null);
                        setScopedClientOrg(null);
                      }
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
                  onStatusChange={handleStatusChange}
                  addToast={addToast}
                  currentUser={currentUser}
                  userRole={userRole}
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
              {activeTab === 'organisations' && ((isAdminRole || isOperatorRole) ? (
                <OrganisationDirectoryView
                  addToast={addToast}
                  onOpenActionDrawer={handleOpenActionDrawer}
                  onNavigate={(tab, params) => {
                    if (tab === 'cards' && params?.clientId) {
                      setScopedClientId(params.clientId);
                      setScopedClientOrg(params.org || { id: params.clientId, name: params.clientName });
                      setActiveTab('cards');
                    } else {
                      setScopedClientId(null);
                      setScopedClientOrg(null);
                      setActiveTab(tab);
                    }
                  }}
                  onOpenDeleteModal={(cfg) =>
                    setDeleteModalConfig(cfg || { title: 'Confirm Permanent Delete', itemDescription: 'this item' })
                  }
                />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}


              {/* ── Manage Operator ── */}
              {(activeTab === 'operators' || activeTab === 'staff') && (isAdminRole ? (
                <OperatorManagementView
                  addToast={addToast}
                  staffType="operator"
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
                <AssistantManagementView
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
              {activeTab === 'photographers' && ((isAdminRole || isOperatorRole) ? (
                <PhotographerManagementView
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
              {activeTab === 'panel' && ((isAdminRole || isOperatorRole) ? (
                <ManagePanelView addToast={addToast} />
              ) : (
                <DashboardView currentUser={currentUser} onNavigate={(d) => setActiveTab(d)} />
              ))}

              {/* ── Tutorial ── */}
              {activeTab === 'tutorial' && <TutorialGuideView />}

              {/* ── Settings / Profile ── */}
              {(activeTab === 'settings' || activeTab === 'profile') && (
                <ProfileSettingsView addToast={addToast} currentUser={currentUser} onLogout={handleLogout} />
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
        <Footer
          activeTab={activeTab}
          onNavigate={(dest) => {
            if (dest === 'organisations') {
              setScopedClientId(null);
              setScopedClientOrg(null);
            }
            setActiveTab(dest);
          }}
          idcardActionsState={idcardActionsState}
          scopedOrgName={scopedClientOrg?.name || null}
        />
      </div>

      {/* ── Global Modals & Drawers ── */}
      <ErrorBoundary>
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
      </ErrorBoundary>
      <CardDownloadsModal
        isOpen={showDownloadsModal}
        onClose={() => setShowDownloadsModal(false)}
        addToast={addToast}
      />

      <GlobalSearchModal
        isOpen={showSearchModal}
        onClose={() => setShowSearchModal(false)}
        onNavigate={(tab, params) => {
          if (tab === 'idcard-actions' && params) {
            setIdcardActionsState({ tableId: params.tableId, status: params.status || 'pending' });
            setActiveTab('idcard-actions');
          } else if (tab === 'cards' && params?.clientId) {
            setScopedClientId(params.clientId);
            setScopedClientOrg(params.org || { id: params.clientId, name: params.clientName });
            setActiveTab('cards');
          } else if (tab) {
            setActiveTab(tab);
          }
        }}
      />
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
