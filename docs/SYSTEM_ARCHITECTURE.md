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
- **Service Layer Abstraction**: Encapsulates all business logic inside dedicated service modules (e.g. `CardService`, `BulkUploadService`, `ExportService`). Views remain thin.
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

## 4. Multi-Tenant Role Permission Hierarchy

```text
                           [ Super Administrator ]
                           (Full Bypass Authority)
                                      │
                                      ▼
                             [ Pro Administrator ]
                          (Guarded Feature Access)
                                      │
                                      ▼
                            [ Admin Staff User ]
                        (Assigned Client Scope Only)
                                      │
                                      ▼
                        ┌─────────────┴─────────────┐
                        ▼                           ▼
                 [ Client Admin ]           [ Client Staff ]
               (Tenant Scope Only)     (Double-Gated Delegated)
```

- **Super Administrator (`super_admin`)**: Full system access, database operations, and user creation.
- **Client Admin (`client`)**: Restricted to their own institution’s students, staff, templates, and exports.
- **Client Staff (`client_staff`)**: Double-gated by both staff feature flags and parent client organization active state.

---

## 5. Storage & Deployment Architecture

- **Media Normalization (`mediafiles/`)**: Protected media paths validate user access authorization before serving uploaded card photos, signatures, or generated card thumbnails.
- **Production Server Handoff**: Supports Nginx `X-Accel-Redirect` (`MEDIA_USE_XACCEL=True`) to offload file serving from Python worker threads to Nginx.
- **WhiteNoise Static Engine**: Serves compressed, hashed production assets directly from Gunicorn with zero performance penalty.
