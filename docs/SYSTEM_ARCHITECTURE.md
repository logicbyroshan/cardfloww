# System Architecture & Technical Topology Deep Dive

This document provides a comprehensive technical breakdown of the **CardFlow Platform** architecture, system topology, service layer abstractions, security middleware, and execution flow.

---

## 1. High-Level Architectural Topology

CardFlow is architected as a **fully decoupled** enterprise platform:

- **Backend** (`backend/`): Pure REST API hub. **Never serves any HTML pages.** All business logic, authentication, and data processing.
- **Frontend** (`frontend/`): React 19 SPA. Handles **100% of all UI pages** including login, dashboard, and all admin views.
- **Mobile App** (`mobile_api/`): React Native companion app; communicates via `/api/mobile/*`.

```text
             ┌───────────────────────────────────────────────────────┐
             │                  Client Interfaces                     │
             │  • React 19 SPA — cardflow.in     (all UI pages)      │
             │  • Android / iOS Mobile App        (native app)        │
             └────────────────────┬─────────────────┬────────────────┘
                                  │                 │
                   HTTPS (port 443/80)              │ HTTPS (port 443/80)
                                  │                 │
            ┌─────────────────────▼──┐  ┌───────────▼──────────────┐
            │   Nginx → React Build  │  │ Nginx → Django Gunicorn  │
            │   cardflow.in          │  │ privatexyz.cardflow.in   │
            │   /static (Vite dist)  │  │ /api/* (REST API only)   │
            └────────────────────────┘  │ /media/* (uploads)       │
                                        │ /app/* (mobile download) │
                                        └──────────────────────────┘
```

### Deployment URLs
| Layer | Dev URL | Production URL |
|:------|:--------|:---------------|
| React SPA (Frontend) | `http://localhost:5173` | `https://cardflow.in` |
| Django REST API (Backend) | `http://localhost:8000` | `https://privatexyz.cardflow.in` |
| Media Files | `http://localhost:8000/media/` | `https://privatexyz.cardflow.in/media/` |

---

## 2. Core Subsystem Responsibilities

### 2.1 Backend Core (`backend/`) — **Pure REST API**
- **Django 5.2.12**: Core ORM, user management, JSON REST APIs, and service controllers.
- **API-Only Policy**: The backend **never renders HTML pages** (except `/app/*` mobile download and Django debug mode). Every response is JSON.
- **Service Layer Abstraction**: Encapsulates all business logic inside dedicated service modules (e.g. `CardService`, `BulkUploadService`, `ExportService`, `OrganisationManagerService`, `AutoPasswordService`). Views remain thin.
- **Dual Login Authentication**: Supports both **Email** and **Username** (or Phone) credentials with automated temporary PIN password lifecycle.
- **Auth via CSRF+Session**: Browser SPA uses Django session cookies + CSRF tokens. Mobile app uses token-based auth (`/api/mobile/`).

### 2.2 Modern React Web SPA (`frontend/`) — **All UI Pages**
- **React 19 & Vite**: High-performance SPA. Handles **all routes** including auth (login, forgot password), dashboard, client management, ID card actions.
- **CSRF Boot**: On app load, fetches `GET /api/auth/csrf/` to obtain the CSRF cookie before any POST request.
- **API Communication**: All backend calls use `/api/*` endpoints proxied by Vite dev server. In production, the SPA is served from a CDN/Nginx and calls `https://privatexyz.cardflow.in/api/*` directly.
- **401 Handling**: On any 401 response from the API, the SPA automatically redirects to `/auth/login` (handled in `api.js`).

### 2.3 ASGI WebSocket & Real-Time Layer (`desktop_app/`, `channels`)
- **Django Channels (ASGI)**: Handles bi-directional WebSockets for real-time print status pushes, desktop PWA tokens, and active session telemetries.
- **Redis Channel Layer**: Acts as the message broker forwarding events across Gunicorn worker threads and ASGI Daphne processes.

### 2.4 Redis Caching & Lock Infrastructure
- **Dynamic Filter Option Cache**: Caches `SELECT DISTINCT` queries for card search dropdowns (`class_name`, `section`, `blood_group`) in Redis with a 600-second TTL.
- **Distributed Lock Guard**: Prevents concurrent duplicate upload tasks or conflicting batch card transitions per user session.

---

## 3. Security & Middleware Stack

CardFlow enforces a zero-trust multi-tier security pipeline on every incoming request:

1. **Subdomain URL Routing (`SubdomainURLRoutingMiddleware`)**: Dynamically resolves request host headers to isolate Panel and Public API routes.
2. **Session Idle & Lifetime Control (`SessionIdleTimeoutMiddleware`)**: Enforces absolute maximum session age and idle session invalidation.
3. **Session Fingerprinting (`SessionFingerprintMiddleware`)**: Validates client browser user-agent and IP hash fingerprints against active session tokens.
4. **Permission Revalidation (`PermissionRevalidationMiddleware`)**: Re-evaluates user role permissions against database state on critical endpoints.
5. **Slow Query & Telemetry Monitoring (`RequestTimingMiddleware`)**: Records SQL query count thresholds and flags requests exceeding execution bounds.

---

## 4. Multi-Tenant Role & Domain Permission Hierarchy

CardFlow features a strictly separated **Two-Domain Architecture** that isolates Platform Administration from Tenant Organisations:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. PLATFORM DOMAIN (Multi-Tenant Administration)                             │
│                                                                             │
│                        [ Prime Admin (Platform Owner) ]                     │
│                                       │                                     │
│                                       ▼                                     │
│                         [ Super Admin (Global Admin) ]                      │
│                                       │                                     │
│                         ┌─────────────┴─────────────┐                       │
│                         ▼                           ▼                       │
│                    [ Operator ]              [ Photographer ]               │
│                (Assigned Orgs Only)        (Field Photo Capture)            │
└───────────────────────────────────────┬─────────────────────────────────────┘
                                        │ (Supervises / Onboards)
┌───────────────────────────────────────▼─────────────────────────────────────┐
│ 2. ORGANISATION DOMAIN (Tenant Schools, Colleges, Offices)                  │
│                                                                             │
│                         [ Organisation (Tenant Entity) ]                    │
│                                       │                                     │
│                         [ Prime Manager (Org Owner) ]                       │
│                                       │                                     │
│               ┌───────────────────────┼───────────────────────┐             │
│               │ (Delegates Tables)    │ (Delegates Tables)    │             │
│               ▼                       ▼                       ▼             │
│       [ Super Manager 1 ]     [ Super Manager 2 ]     [ Guest Manager ]     │
│       (Max limit: 4 default)  (Max limit: 4 default)  (Temporary Reviewer)  │
│       • Autonomous Account    • Autonomous Account    • Cannot add tables   │
│       • Cannot create tables  • Cannot create tables  • Delegated tables    │
│               │                       │                       │             │
│               ▼                       ▼                       ▼             │
│          [ Assistant ]           [ Assistant ]           [ Assistant ]      │
│       (Scoped to SM1 Tables)  (Scoped to SM2 Tables)  (Scoped to GM Tables) │
└─────────────────────────────────────────────────────────────────────────────┘
```

### Domain & Role Breakdown:

1. **Platform Domain**:
   - **Prime Admin (`prime_admin`)**: Ultimate platform owner; creates and manages Super Admins, Pro Features, and system backups.
   - **Super Admin (`super_admin`)**: Global operations manager; manages organisations, operators, and platform analytics.
   - **Operator (`operator`)**: Production and print manager; restricted strictly to organisations assigned by Super Admin.
   - **Photographer (`photographer`)**: Field agent capturing ID card photos via Mobile App; scoped to assigned organisations.

2. **Organisation Domain**:
   - **Prime Manager (`prime_manager`)**: Primary owner and administrator of the Organisation. Full authority to create tables, configure schemas, manage organisation staff, and delegate tables to Super Managers.
   - **Super Manager (`super_manager`)**: Autonomous manager with independent credentials. Created by Prime Manager (capped at `Organisation.max_super_managers`, default=4). **Strictly forbidden from creating tables** (`403 Forbidden`). Can only view and edit cards for tables delegated to them via `TableAccess`.
   - **Guest Manager (`guest_manager`)**: Temporary or guest reviewer with read/delegated edit permissions on specific tables.
   - **Assistant (`assistant`)**: Subordinate data entry / verification assistant owned by their specific creating Manager (`assistant.manager_id = user.id`), restricted strictly to that Manager's delegated tables.

---

## 5. Table Delegation Architecture (`TableAccess`)

The `TableAccess` relational model enables granular table delegation within an Organisation:

```text
[ Table (e.g. Class 10 Students) ] ──◄ (TableAccess) ►── [ Super Manager ]
                                             │
                                   • can_view: True
                                   • can_edit_cards: True
                                   • can_approve_print: False
```

- **Prime Manager Access**: Retains implicit full access to all tables in the organisation and controls delegation via `/api/table/<id>/share-managers/`.
- **Super Manager Scoping**: `GET /api/schemas/` dynamically filters table schemas to only return tables with an active `TableAccess` grant for `request.user`.

---

## 6. Storage & Deployment Architecture

- **Media Normalization (`mediafiles/`)**: Protected media paths validate user access authorization before serving uploaded card photos, signatures, or generated card thumbnails.
- **Production Server Handoff**: Supports Nginx `X-Accel-Redirect` (`MEDIA_USE_XACCEL=True`) to offload file serving from Python worker threads to Nginx.
- **WhiteNoise Static Engine**: Serves compressed, hashed production assets directly from Gunicorn with zero performance penalty.
