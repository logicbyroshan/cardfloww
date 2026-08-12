import axios from 'axios';

// ─── CSRF Token Helper ──────────────────────────────────────────────────────
function getCsrfToken() {
  const cookieMatch = document.cookie.match(/csrftoken=([^;]+)/);
  if (cookieMatch) return cookieMatch[1];
  const metaCsrf = document.querySelector('meta[name="csrf-token"]');
  if (metaCsrf) return metaCsrf.getAttribute('content');
  return '';
}

// ─── Axios Client ───────────────────────────────────────────────────────────
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
    'X-Requested-With': 'XMLHttpRequest',
  },
  withCredentials: true,
});

// Attach CSRF token to all mutating requests automatically
apiClient.interceptors.request.use((config) => {
  const method = (config.method || '').toLowerCase();
  if (['post', 'put', 'patch', 'delete'].includes(method)) {
    const token = getCsrfToken();
    if (token) config.headers['X-CSRFToken'] = token;
  }
  return config;
});

// Suppress infinite 401 error loops when unauthenticated
let isRedirectingToLogin = false;
apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response && error.response.status === 401) {
      const isLoginPage = window.location.pathname === '/auth/login' || window.location.pathname === '/login';
      if (!isRedirectingToLogin && !isLoginPage) {
        isRedirectingToLogin = true;
        // Reset flag after 2s so future navigation works if user logs back in
        setTimeout(() => { isRedirectingToLogin = false; }, 2000);
        window.location.href = '/auth/login';
      }
    }
    return Promise.reject(error);
  }
);

// ─── Group 1: Authentication & Session ─────────────────────────────────────
export const authApi = {
  /** POST /api/auth/login/ — returns { success, user, role, … } */
  login: async (email, password) => {
    const res = await apiClient.post('/api/auth/login/', { email, password });
    return res.data;
  },

  /** GET /api/auth/me/ — returns { authenticated, user } */
  getCurrentUser: async () => {
    const res = await apiClient.get('/api/auth/me/');
    return res.data;
  },

  /** POST /api/auth/logout/ — Django session logout via JSON API */
  logout: async () => {
    try {
      const res = await apiClient.post('/api/auth/logout/');
      return res.data;
    } catch {
      // Silently succeed — session is cleared server-side regardless
      return { success: true };
    }
  },
};

// ─── Group 1b: Impersonation ────────────────────────────────────────────────
export const impersonateApi = {
  /** GET list of users available for impersonation */
  getUsers: async () => {
    try {
      const res = await apiClient.get('/api/auth/impersonate/users/');
      return res.data;
    } catch {
      const res = await apiClient.get('/panel/api/auth/impersonate/users/');
      return res.data;
    }
  },

  /** POST start impersonating user_id */
  start: async (userId) => {
    try {
      const res = await apiClient.post('/api/auth/impersonate/start/', { user_id: userId });
      return res.data;
    } catch {
      const res = await apiClient.post('/panel/api/auth/impersonate/start/', { user_id: userId });
      return res.data;
    }
  },

  /** POST stop impersonation */
  stop: async () => {
    try {
      const res = await apiClient.post('/api/auth/impersonate/stop/');
      return res.data;
    } catch {
      const res = await apiClient.post('/panel/api/auth/impersonate/stop/');
      return res.data;
    }
  },
};

// ─── Group 2: Dashboard Analytics ──────────────────────────────────────────
export const dashboardApi = {
  /** GET /api/dashboard-card-stats/ — role-scoped card statistics */
  getStats: async () => {
    const res = await apiClient.get('/api/dashboard-card-stats/');
    return res.data;
  },

  /** GET /api/recent-activity/ — paginated audit event stream */
  getRecentActivity: async (limit = 50) => {
    const res = await apiClient.get('/api/recent-activity/', { params: { limit } });
    return res.data;
  },

  /** GET /api/reprint-overview/ — reprint queue overview */
  getReprintOverview: async () => {
    const res = await apiClient.get('/api/reprint-overview/');
    return res.data;
  },

  /** GET /api/notifications/unread-count/ */
  getUnreadCount: async () => {
    const res = await apiClient.get('/api/notifications/unread-count/');
    return res.data;
  },

  /** GET /api/notifications/list/ */
  getNotifications: async () => {
    const res = await apiClient.get('/api/notifications/list/');
    return res.data;
  },

  /** POST /api/notifications/mark-all-read/ */
  markAllRead: async () => {
    const res = await apiClient.post('/api/notifications/mark-all-read/');
    return res.data;
  },

  /** GET /api/recent-client-updates/ */
  getRecentClientUpdates: async () => {
    const res = await apiClient.get('/api/recent-client-updates/');
    return res.data;
  },
};

// ─── Group 3: ID Cards Data Grid & Image Versioning ────────────────────────
export const cardApi = {
  /** GET /api/table/<table_id>/cards/ — paginated card list */
  getCards: async (tableId, params = {}) => {
    try {
      const res = await apiClient.get(`/api/table/${tableId}/cards-json/`, { params });
      return res.data;
    } catch {
      const res = await apiClient.get(`/api/table/${tableId}/cards/`, { params });
      return res.data;
    }
  },

  /** GET /api/table/<table_id>/status-counts/ */
  getStatusCounts: async (tableId) => {
    const res = await apiClient.get(`/api/table/${tableId}/status-counts/`);
    return res.data;
  },

  /** GET /api/card/<card_id>/ */
  getCard: async (cardId) => {
    const res = await apiClient.get(`/api/card/${cardId}/`);
    return res.data;
  },

  /** POST /api/card/<card_id>/update-field/ */
  updateField: async (cardId, fieldName, value) => {
    const res = await apiClient.post(`/api/card/${cardId}/update-field/`, { field_name: fieldName, value });
    return res.data;
  },

  /** POST /api/card/<card_id>/undo-image/ — restores previous photo version */
  undoImage: async (cardId, fieldName = 'PHOTO') => {
    const res = await apiClient.post(`/api/card/${cardId}/undo-image/`, { field_name: fieldName });
    return res.data;
  },

  /** POST /api/card/<card_id>/redo-image/ — restores next photo version */
  redoImage: async (cardId, fieldName = 'PHOTO') => {
    const res = await apiClient.post(`/api/card/${cardId}/redo-image/`, { field_name: fieldName });
    return res.data;
  },

  /** POST /api/card/<card_id>/status/ */
  changeStatus: async (cardId, status) => {
    const res = await apiClient.post(`/api/card/${cardId}/status/`, { status });
    return res.data;
  },

  /** POST /api/card/<card_id>/delete/ */
  deleteCard: async (cardId) => {
    const res = await apiClient.post(`/api/card/${cardId}/delete/`);
    return res.data;
  },

  /** GET /api/card/<card_id>/history/ */
  getHistory: async (cardId) => {
    const res = await apiClient.get(`/api/card/${cardId}/history/`);
    return res.data;
  },

  // Backwards-compat aliases
  getDashboardStats: async () => dashboardApi.getStats(),
  getRecentActivity: async () => dashboardApi.getRecentActivity(),
  getActiveClients: async () => clientApi.getActive(),
  getStaffList: async () => operatorApi.list(),
  getBackups: async () => panelApi.getBackups(),
};

// ─── Group 4: Client Management ────────────────────────────────────────────
export const clientApi = {
  /** GET /api/clients/active/ — paginated list with search/status/page filters */
  getActive: async (params = {}) => {
    const res = await apiClient.get('/api/clients/active/', { params });
    return res.data;
  },

  /** GET /api/clients/for-staff-assignment/ — all clients (no pagination) */
  getAllForAssignment: async () => {
    const res = await apiClient.get('/api/clients/for-staff-assignment/');
    return res.data;
  },

  /** POST /client/api/staff/ (client-staff create) — creates a new client/organisation */
  createClient: async (data) => {
    const res = await apiClient.post('/api/clients/create/', data);
    return res.data;
  },

  /** POST /api/clients/<id>/update/ */
  updateClient: async (clientId, data) => {
    const res = await apiClient.post(`/api/clients/${clientId}/update/`, data);
    return res.data;
  },

  /** POST /api/clients/<id>/delete/ */
  deleteClient: async (clientId) => {
    const res = await apiClient.post(`/api/clients/${clientId}/delete/`);
    return res.data;
  },

  /** POST /api/clients/<id>/toggle-status/ */
  toggleStatus: async (clientId) => {
    const res = await apiClient.post(`/api/clients/${clientId}/toggle-status/`);
    return res.data;
  },

  /** GET /api/client/<id>/ — get single client detail (includes group_id) */
  getClient: async (clientId) => {
    const res = await apiClient.get(`/api/client/${clientId}/`);
    return res.data;
  },

  /** GET /api/group/<group_id>/tables/ — ID card tables for a client group */
  getClientTables: async (groupId) => {
    const res = await apiClient.get(`/api/group/${groupId}/tables/`);
    return res.data;
  },

  /** GET /api/clients/active/ with all clients for table management */
  getAllClients: async (params = {}) => {
    try {
      const res = await apiClient.get('/api/clients/active/', { params });
      return res.data;
    } catch {
      const res = await apiClient.get('/api/clients/for-staff-assignment/', { params });
      return res.data;
    }
  },
};

// ─── Group 5: Operator Management ──────────────────────────────────────────
export const operatorApi = {
  /** GET /operators/api/operator/ — list all operators */
  list: async (params = {}) => {
    try {
      const res = await apiClient.get('/operators/api/operator/', { params });
      return res.data;
    } catch {
      try {
        const res = await apiClient.get('/panel/operators/api/operator/', { params });
        return res.data;
      } catch {
        const res = await apiClient.get('/api/staff/', { params });
        return res.data;
      }
    }
  },

  /** POST /operators/api/operator/ — create operator */
  create: async (data) => {
    try {
      const res = await apiClient.post('/operators/api/operator/', data);
      return res.data;
    } catch {
      try {
        const res = await apiClient.post('/panel/operators/api/operator/', data);
        return res.data;
      } catch {
        const res = await apiClient.post('/api/staff/create/', data);
        return res.data;
      }
    }
  },

  /** GET /operators/api/operator/<id>/ — get single operator */
  get: async (operatorId) => {
    try {
      const res = await apiClient.get(`/operators/api/operator/${operatorId}/`);
      return res.data;
    } catch {
      const res = await apiClient.get(`/api/staff/${operatorId}/`);
      return res.data;
    }
  },

  /** PATCH /operators/api/operator/<id>/ — update operator */
  update: async (operatorId, data) => {
    try {
      const res = await apiClient.patch(`/operators/api/operator/${operatorId}/`, data);
      return res.data;
    } catch {
      const res = await apiClient.post(`/api/staff/${operatorId}/update/`, data);
      return res.data;
    }
  },

  /** POST /operators/api/operator/<id>/delete/ */
  delete: async (operatorId) => {
    try {
      const res = await apiClient.post(`/operators/api/operator/${operatorId}/delete/`);
      return res.data;
    } catch {
      const res = await apiClient.post(`/api/staff/${operatorId}/delete/`);
      return res.data;
    }
  },

  /** POST /operators/api/operator/<id>/toggle-status/ */
  toggleStatus: async (operatorId) => {
    try {
      const res = await apiClient.post(`/operators/api/operator/${operatorId}/toggle-status/`);
      return res.data;
    } catch {
      const res = await apiClient.post(`/api/staff/${operatorId}/toggle-status/`);
      return res.data;
    }
  },

  /** POST /operators/api/operator/<id>/reset-password/ */
  resetPassword: async (operatorId, data) => {
    const res = await apiClient.post(`/operators/api/operator/${operatorId}/reset-password/`, data);
    return res.data;
  },

  /** GET /operators/api/permissions/available/ — list all available permissions */
  getAvailablePermissions: async () => {
    const res = await apiClient.get('/operators/api/permissions/available/');
    return res.data;
  },

  /** GET /operators/api/clients/available/ — list clients that can be assigned */
  getAvailableClients: async () => {
    const res = await apiClient.get('/operators/api/clients/available/');
    return res.data;
  },
};

// ─── Group 6: Assistant Management ─────────────────────────────────────────
export const assistantApi = {
  /** GET /assistants/api/staff/ — list assistants */
  list: async (params = {}) => {
    const res = await apiClient.get('/assistants/api/staff/', { params });
    return res.data;
  },

  /** POST /assistants/api/staff/ — create assistant */
  create: async (data) => {
    const res = await apiClient.post('/assistants/api/staff/', data);
    return res.data;
  },

  /** GET /assistants/api/staff/<id>/ */
  get: async (staffId) => {
    const res = await apiClient.get(`/assistants/api/staff/${staffId}/`);
    return res.data;
  },

  /** PATCH /assistants/api/staff/<id>/ — update */
  update: async (staffId, data) => {
    const res = await apiClient.patch(`/assistants/api/staff/${staffId}/`, data);
    return res.data;
  },

  /** DELETE /assistants/api/staff/<id>/ — delete */
  delete: async (staffId) => {
    const res = await apiClient.delete(`/assistants/api/staff/${staffId}/`);
    return res.data;
  },

  /** POST /assistants/api/staff/<id>/toggle-status/ */
  toggleStatus: async (staffId) => {
    const res = await apiClient.post(`/assistants/api/staff/${staffId}/toggle-status/`);
    return res.data;
  },

  /** POST /assistants/api/staff/<id>/set-temp-password/ */
  setTempPassword: async (staffId, data) => {
    const res = await apiClient.post(`/assistants/api/staff/${staffId}/set-temp-password/`, data);
    return res.data;
  },

  /** GET /assistants/api/groups/active/ — active client groups for assignment */
  getClientGroups: async () => {
    const res = await apiClient.get('/assistants/api/groups/active/');
    return res.data;
  },

  /** POST /assistants/api/staff/bulk-delete/ */
  bulkDelete: async (staffIds) => {
    const res = await apiClient.post('/assistants/api/staff/bulk-delete/', { staff_ids: staffIds });
    return res.data;
  },
};

// ─── Group 7: Photographer Management ──────────────────────────────────────
export const photographerApi = {
  /** GET /api/photographer/<id>/ */
  get: async (staffId) => {
    const res = await apiClient.get(`/api/photographer/${staffId}/`);
    return res.data;
  },

  /** POST /api/photographer/create/ */
  create: async (data) => {
    const res = await apiClient.post('/api/photographer/create/', data);
    return res.data;
  },

  /** POST /api/photographer/<id>/update/ */
  update: async (staffId, data) => {
    const res = await apiClient.post(`/api/photographer/${staffId}/update/`, data);
    return res.data;
  },

  /** POST /api/photographer/<id>/delete/ */
  delete: async (staffId) => {
    const res = await apiClient.post(`/api/photographer/${staffId}/delete/`);
    return res.data;
  },

  /** POST /api/photographer/<id>/toggle-status/ */
  toggleStatus: async (staffId) => {
    const res = await apiClient.post(`/api/photographer/${staffId}/toggle-status/`);
    return res.data;
  },

  /** POST /api/photographer/<id>/assign-clients/ */
  assignClients: async (staffId, clientIds) => {
    const res = await apiClient.post(`/api/photographer/${staffId}/assign-clients/`, { client_ids: clientIds });
    return res.data;
  },

  /** POST /api/photographer/<id>/set-temp-password/ */
  setTempPassword: async (staffId, data) => {
    const res = await apiClient.post(`/api/photographer/${staffId}/set-temp-password/`, data);
    return res.data;
  },
};

// ─── Group 8: Admin Staff (core /api/staff/) ────────────────────────────────
export const staffApi = {
  /** POST /api/staff/create/ */
  create: async (data) => {
    const res = await apiClient.post('/api/staff/create/', data);
    return res.data;
  },

  /** POST /api/staff/<id>/update/ */
  update: async (staffId, data) => {
    const res = await apiClient.post(`/api/staff/${staffId}/update/`, data);
    return res.data;
  },

  /** POST /api/staff/<id>/delete/ */
  delete: async (staffId) => {
    const res = await apiClient.post(`/api/staff/${staffId}/delete/`);
    return res.data;
  },

  /** POST /api/staff/<id>/toggle-status/ */
  toggleStatus: async (staffId) => {
    const res = await apiClient.post(`/api/staff/${staffId}/toggle-status/`);
    return res.data;
  },

  /** POST /api/staff/<id>/set-temp-password/ */
  setTempPassword: async (staffId, data) => {
    const res = await apiClient.post(`/api/staff/${staffId}/set-temp-password/`, data);
    return res.data;
  },

  // backwards compat
  createStaff: async (data) => staffApi.create(data),
  updateStaff: async (staffId, data) => staffApi.update(staffId, data),
  deleteStaff: async (staffId) => staffApi.delete(staffId),
  createPhotographer: async (data) => photographerApi.create(data),
  deletePhotographer: async (staffId) => photographerApi.delete(staffId),
  getStaffForAssignment: async () => clientApi.getAllForAssignment(),
};

// ─── Group 9: Control Panel, Backups, Logs & Settings ───────────────────────
export const panelApi = {
  // ── Backups ──────────────────────────────────────────────────────────────
  /** GET /api/backup/list/ */
  getBackups: async (params = {}) => {
    const res = await apiClient.get('/api/backup/list/', { params });
    return res.data;
  },

  /** POST /api/backup/initiate/ */
  initiateBackup: async (payload = {}) => {
    const res = await apiClient.post('/api/backup/initiate/', payload);
    return res.data;
  },

  /** POST /api/backup/start/ */
  startBackup: async (payload = {}) => {
    const res = await apiClient.post('/api/backup/start/', payload);
    return res.data;
  },

  /** GET /api/backup/status/<task_id>/ */
  getBackupStatus: async (taskId) => {
    const res = await apiClient.get(`/api/backup/status/${taskId}/`);
    return res.data;
  },

  /** POST /api/backup/<task_id>/delete-now/ */
  deleteBackup: async (taskId) => {
    const res = await apiClient.post(`/api/backup/${taskId}/delete-now/`);
    return res.data;
  },

  /** GET /api/backup/download/<task_id>/ — returns a redirect/file URL */
  getBackupDownloadUrl: (taskId) => `/api/backup/download/${taskId}/`,

  // ── Email Logs ───────────────────────────────────────────────────────────
  /** GET /api/email-logs/ */
  getEmailLogs: async (params = {}) => {
    const res = await apiClient.get('/api/email-logs/', { params });
    return res.data;
  },

  /** POST /api/email-resend/<log_id>/ */
  resendEmail: async (logId) => {
    const res = await apiClient.post(`/api/email-resend/${logId}/`);
    return res.data;
  },

  /** POST /api/email-send/ */
  sendEmail: async (data) => {
    const res = await apiClient.post('/api/email-send/', data);
    return res.data;
  },

  /** GET /api/email-compose-defaults/ */
  getEmailDefaults: async () => {
    const res = await apiClient.get('/api/email-compose-defaults/');
    return res.data;
  },

  // ── Activity Logs ────────────────────────────────────────────────────────
  /** GET /api/activity-logs/ */
  getLogs: async (params = {}) => {
    const res = await apiClient.get('/api/activity-logs/', { params });
    return res.data;
  },

  /** GET /api/activity-logs/clear/state/ */
  getLogClearState: async () => {
    const res = await apiClient.get('/api/activity-logs/clear/state/');
    return res.data;
  },

  /** POST /api/activity-logs/clear/ */
  clearLogs: async (data) => {
    const res = await apiClient.post('/api/activity-logs/clear/', data);
    return res.data;
  },

  // ── Admin Notifications ──────────────────────────────────────────────────
  /** GET /api/notifications/admin/list/ */
  getAdminNotifications: async (params = {}) => {
    const res = await apiClient.get('/api/notifications/admin/list/', { params });
    return res.data;
  },

  /** POST /api/notifications/admin/create/ */
  createNotification: async (data) => {
    const res = await apiClient.post('/api/notifications/admin/create/', data);
    return res.data;
  },

  /** POST /api/notifications/admin/<id>/delete/ */
  deleteNotification: async (notifId) => {
    const res = await apiClient.post(`/api/notifications/admin/${notifId}/delete/`);
    return res.data;
  },

  /** GET /api/notifications/admin/target-users/ */
  getNotificationTargetUsers: async (params = {}) => {
    const res = await apiClient.get('/api/notifications/admin/target-users/', { params });
    return res.data;
  },

  // ── Monitoring & System ──────────────────────────────────────────────────
  /** GET /api/monitoring/ */
  getMonitoring: async () => {
    const res = await apiClient.get('/api/monitoring/');
    return res.data;
  },

  /** GET /api/server-info/ */
  getServerInfo: async () => {
    const res = await apiClient.get('/api/server-info/');
    return res.data;
  },

  /** GET /api/health/ */
  getHealth: async () => {
    const res = await apiClient.get('/api/health/');
    return res.data;
  },

  /** GET /api/operations-feed/ */
  getOperationsFeed: async () => {
    const res = await apiClient.get('/api/operations-feed/');
    return res.data;
  },

  // ── Maintenance ──────────────────────────────────────────────────────────
  /** GET /api/maintenance/status/ */
  getMaintenanceStatus: async () => {
    const res = await apiClient.get('/api/maintenance/status/');
    return res.data;
  },

  /** POST /api/maintenance/toggle/ */
  toggleMaintenance: async () => {
    const res = await apiClient.post('/api/maintenance/toggle/');
    return res.data;
  },

  // Legacy aliases
  listBackups: async () => panelApi.getBackups(),
  getActivityLogs: async (params) => panelApi.getLogs(params),
  getNotifications: async (params) => panelApi.getAdminNotifications(params),
};

// ─── Group 10: Schema & Table Settings ─────────────────────────────────────
export const schemaApi = {
  /** GET /api/schemas/ */
  getSchemas: async (params = {}) => {
    const res = await apiClient.get('/api/schemas/', { params });
    return res.data;
  },

  /** POST /api/schemas/create/ */
  createSchema: async (data) => {
    const res = await apiClient.post('/api/schemas/create/', data);
    return res.data;
  },

  /** GET /api/group/<group_id>/tables/ — list tables for a group */
  getGroupTables: async (groupId) => {
    const res = await apiClient.get(`/api/group/${groupId}/tables/`);
    return res.data;
  },

  /** POST /api/group/<group_id>/table/create/ — create a new table in a group */
  createTable: async (groupId, data) => {
    const res = await apiClient.post(`/api/group/${groupId}/table/create/`, data);
    return res.data;
  },

  /** GET /api/table/<id>/ */
  getTable: async (tableId) => {
    const res = await apiClient.get(`/api/table/${tableId}/`);
    return res.data;
  },

  /** POST /api/table/<id>/update/ */
  updateTable: async (tableId, data) => {
    const res = await apiClient.post(`/api/table/${tableId}/update/`, data);
    return res.data;
  },

  /** POST /api/table/<id>/delete/ */
  deleteTable: async (tableId) => {
    const res = await apiClient.post(`/api/table/${tableId}/delete/`);
    return res.data;
  },

  /** POST /api/table/<id>/toggle-status/ */
  toggleTableStatus: async (tableId) => {
    const res = await apiClient.post(`/api/table/${tableId}/toggle-status/`);
    return res.data;
  },

  /** GET /api/table/<id>/status-counts/ — card counts per status */
  getTableStatusCounts: async (tableId) => {
    const res = await apiClient.get(`/api/table/${tableId}/status-counts/`);
    return res.data;
  },

  /** POST /api/group/<group_id>/table/create-from-xlsx/ — create table from uploaded XLSX */
  createTableFromXlsx: async (groupId, formData) => {
    const res = await apiClient.post(`/api/group/${groupId}/table/create-from-xlsx/`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /** GET /client/<client_id>/groups/ — HTML page that contains group_id;
   *  Instead use the client list API to get group_id from client data */
  getClientGroups: async (clientId) => {
    try {
      const res = await apiClient.get(`/api/client/${clientId}/`);
      return res.data;
    } catch {
      return null;
    }
  },
};

// ─── Group 11: Profile & Account Settings ──────────────────────────────────
export const profileApi = {
  /** GET /api/profile/ */
  getProfile: async () => {
    const res = await apiClient.get('/api/profile/');
    return res.data;
  },

  /** POST /api/profile/update/ */
  updateProfile: async (data) => {
    const res = await apiClient.post('/api/profile/update/', data);
    return res.data;
  },

  /** POST /api/profile/change-password/ */
  changePassword: async (data) => {
    const res = await apiClient.post('/api/profile/change-password/', data);
    return res.data;
  },

  /** POST /api/profile/upload-image/ */
  uploadImage: async (formData) => {
    const res = await apiClient.post('/api/profile/upload-image/', formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
    });
    return res.data;
  },

  /** POST /api/profile/remove-image/ */
  removeImage: async () => {
    const res = await apiClient.post('/api/profile/remove-image/');
    return res.data;
  },
};

// ─── Group 12: Reprint Cards ────────────────────────────────────────────────
export const reprintApi = {
  /** GET /reprint/api/queue/ or similar */
  getQueue: async (params = {}) => {
    const res = await apiClient.get('/reprint/api/queue/', { params });
    return res.data;
  },

  /** POST /reprint/api/<id>/approve/ */
  approve: async (reprintId) => {
    const res = await apiClient.post(`/reprint/api/${reprintId}/approve/`);
    return res.data;
  },

  /** POST /reprint/api/<id>/reject/ */
  reject: async (reprintId, reason = '') => {
    const res = await apiClient.post(`/reprint/api/${reprintId}/reject/`, { reason });
    return res.data;
  },
};

// ─── Domain Renaming Aliases ───────────────────────────────────────────────
export const organisationApi = clientApi;
export const managerApi = clientApi;
export const tableGroupApi = schemaApi;

export { apiClient };
export default apiClient;
