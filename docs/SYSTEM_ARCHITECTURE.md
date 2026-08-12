# System Architecture & Technical Topology Deep Dive

This document provides a comprehensive technical breakdown of the **CardFlow Platform** architecture, system topology, service layer abstractions, security middleware, and execution flow.

---

## 1. High-Level Architectural Topology

CardFlow is architected as a hybrid enterprise platform combining a robust **Django REST/Service backend**, a modern **React 19 SPA web control panel**, an **ASGI WebSocket real-time communication layer**, and an **Expo / React Native companion mobile app**.

```text
                               ┌────────────────────────────────────────┐
                               │           Client Interfaces            │
                               │  - React 19 SPA Web Control Panel       │
                               │  - Android / iOS Mobile Companion App  │
                               └───────────────────┬────────────────────┘
                                                   │ HTTPS / WSS
                                                   ▼
                               ┌────────────────────────────────────────┐
                               │         Nginx Reverse Proxy            │
                               │   - TLS termination & SSL redirect     │
                               │   - Static file caching (WhiteNoise)   │
                               └─────────┬────────────────────┬─────────┘
                                         │                    │
                          HTTP / REST    │                    │ WSS / WebSockets
                                         ▼                    ▼
                        ┌────────────────────────┐  ┌───────────────────┐
                        │ Gunicorn (Django WSGI) │  │ Daphne (ASGI)     │
                        │ - Service Controllers  │  │ - WebSocket Layer │
                        │ - Security Middleware  │  │ - Real-Time Push  │
                        └───────────┬────────────┘  └─────────┬─────────┘
                                    │                         │
                                    └────────────┬────────────┘
                                                 │
                                                 ▼
                 ┌───────────────────────────────────────────────────────────────┐
                 │                       Core Subsystems                         │
                 ├───────────────────────┬───────────────────────┬───────────────┤
                 │   PostgreSQL / SQLite │     Redis Cache       │  Celery Task  │
                 │   - Relational Data   │  - Rate Limiting      │  - Worker     │
                 │   - Card Schemas      │  - Field Value Cache  │  - Bulk Jobs  │
                 └───────────────────────┴───────────────────────┴───────────────┘
```

---

## 2. Core Subsystem Responsibilities

### 2.1 Backend Core (`backend/`)
- **Django 5.2.12**: Core ORM, user management, REST APIs, and service controllers encapsulated inside `backend/` (`backend/core/`, `backend/config/`, `backend/accounts/`, `backend/organisation/`, etc.).
- **Service Layer Abstraction**: Encapsulates all business logic inside dedicated service modules (e.g. `CardService`, `BulkUploadService`, `ExportService`). Views remain thin, delegating all operations to services.
- **Domain Split Routing**: Supports subdomain isolation between the public web landing page and administrative control panel.

### 2.2 Modern React Web SPA (`frontend/`)
- **React 19 & Vite**: High-performance SPA frontend located inside `frontend/` built for high-density tabular data editing, interactive status pipelines, and real-time dashboard analytics.
- **Smooth Scrolling & Notifications**: Lenis smooth scrolling engine (`@studio-freight/lenis`) and Sonner toast notification pipeline (`sonner`).
- **Iconography & Styling**: Uses Lucide icons (`lucide-react`) and Vanilla CSS design tokens with custom HSL palette rules.

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
