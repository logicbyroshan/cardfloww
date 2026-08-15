# Adarsh / CardFlow Platform Version Log

| Date | Platform Version | Mobile Version | Mobile Build | Key Changes |
| :--- | :--- | :--- | :--- | :--- |
| **2026-08-15** | **v5.3.0** | **1.1.00** | **100** | **Enterprise Auth & Role Hierarchy Redesign**: Implemented Two-Domain Model (Platform Domain vs Organisation Domain), Autonomous Super Managers (independent credentials, quota caps, cannot create tables), Table Delegation (`TableAccess` model & API), Scoped Assistants, Auto-Generated 8–10 char PIN passwords, Dual Email/Username login, and Pro Features Manage Passwords view. |
| **2026-08-12** | **v5.2.0** | **1.1.00** | **100** | **Backend Optimization**: Total purge of legacy HTML page views, dead backup files, and unrouted page handlers across all 9 Django apps. Pure REST API backend complete. |
| **2026-08-12** | **v5.1.1** | **1.1.00** | **100** | **Security Hardening**: CORS_ALLOW_ALL_ORIGINS defaulted to False. Added security headers to all API responses. Tightened rate limiting and PermissionValidationMiddleware. |
| **2026-08-12** | **v5.1.0** | **1.1.00** | **100** | **Architecture**: Backend converted to pure REST API (no HTML rendering). All UI pages now exclusively on React SPA. Removed /panel/ route prefix, cleaned all HTML page views. Middleware returns JSON 401/403. CSRF prefetch on SPA boot. |
| **2026-08-11** | **v5.0.0** | **1.1.00** | **100** | **Major Architecture Milestone**: Complete migration to React 19 SPA frontend + Django REST API backend. Total purge of legacy HTML templates, build-css.bat, build_bundles.py, and unneeded static assets. |

---

## Current Stable Release (v5.3.0)

### Backend & Domain Hierarchy (v5.3.0)
- **Two-Domain Architecture**:
  - **Platform Domain**: `Prime Admin` $\rightarrow$ `Super Admin` $\rightarrow$ `Operator` / `Photographer`.
  - **Organisation Domain**: `Organisation` $\rightarrow$ `Prime Manager` (1, Org Owner) + `Super Managers` (0..N, max configurable, default 4) + `Guest Manager` + `Assistants`.
- **Autonomous Super Managers**: Independent user accounts with separate credentials; strictly forbidden from creating tables (`403 Forbidden`).
- **Table Delegation (`TableAccess`)**: Relational model enabling Prime Managers to delegate specific table access (`can_view`, `can_edit_cards`, `can_approve_print`) via `/api/table/<id>/share-managers/`.
- **Assistant Scoping**: Assistants linked directly to their creating Prime/Super Manager (`assistant.manager_id = user.id`) and restricted to that Manager's delegated tables.
- **Auto-Generated Temporary Passwords (`AutoPasswordService`)**: Automatic 8–10 char PIN generation, dual Email/Username login, and credential management APIs (`/api/panel/temp-passwords/`).

### Frontend Web SPA (v5.3.0)
- **Manager Accounts View** (`ClientAccountsView.jsx`): Real-time quota pills (`Super Managers: X / Y max`), role badges, and delegated table count column.
- **Quick Action Drawer** (`QuickActionDrawer.jsx`): Direct creation of Super/Guest managers with dynamic initial table delegation checkboxes and Auto-PIN notice cards.
- **Card Table Management** (`CardTableView.jsx`): Added `Share` button and `TableShareModal` for Prime Managers; restricted table creation buttons for Super Managers.
- **Manage Passwords View** (`ManageFeaturesView.jsx`): Dedicated tab in Pro Features with eye toggle, quick copy, and credential resend buttons.
