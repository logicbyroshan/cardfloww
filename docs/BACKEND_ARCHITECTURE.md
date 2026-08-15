# 🛠️ CardFlow Backend Architecture Specification

> **Platform Version**: `v5.1.0` | **Engine**: Django 5.2.12 (Python 3.11+) | **Architecture**: Decoupled REST & Async Worker Architecture

---

## 📋 Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [High-Level System Topology](#2-high-level-system-topology)
3. [Two-Domain Roles & Access Control Model](#3-two-domain-roles--access-control-model)
4. [Django App & Modular Breakdown](#4-django-app--modular-breakdown)
5. [Database & Multi-Tenancy Engine](#5-database--multi-tenancy-engine)
6. [Security, Middleware & Authentication](#6-security-middleware--authentication)
7. [Media Storage & Protected Access Control](#7-media-storage--protected-access-control)
8. [Async Workers, Task Queue & Real-time Layer](#8-async-workers-task-queue--real-time-layer)
9. [Export Pipelines & Image Processing Engine](#9-export-pipelines--image-processing-engine)
10. [API Route Map & Directory Structure](#10-api-route-map--directory-structure)

---

## 1. Architecture Overview

The **CardFlow Backend** is a production-grade, multi-tenant enterprise REST API and real-time backend engineered for high-volume ID card design, batch data ingestion, automated image processing, and precision PDF/Word printing pipelines.

### Core Architectural Principles
* **Decoupled RESTful Design**: Operates purely as a headless JSON API provider for the React 19 SPA, Expo Mobile Companion, and Desktop sync app. Zero Django template rendering for web views.
* **Two-Domain Multi-Tenancy**: Strict separation between the **Platform Domain** (Platform Owner, Super Admin, Operators, Photographers) and the **Organisation Domain** (Organisations, Prime Managers, Autonomous Super Managers, Guest Managers, and Scoped Assistants).
* **Table Delegation Engine (`TableAccess`)**: Relational table sharing mechanism enabling Prime Managers to delegate specific tables to Super Managers without granting table creation privileges.
* **Automated Password Lifecycle**: Auto-generated 8–10 character PINs based on phone/entity name, dual login authentication (Email/Username), and automated credential dispatch.
* **Zero-Trust Media Protection**: Direct filesystem and Nginx `X-Accel-Redirect` protection ensuring raw card images, client photos, signatures, and export documents are strictly verified per-user and per-tenant before serving.

---

## 2. High-Level System Topology

```mermaid
graph TD
    ClientSPA["React 19 Web SPA (Vite / Port 5173)"]
    MobileApp["React Native Expo Mobile Companion"]
    DesktopApp["Desktop Sync App Client"]
    
    Nginx["Nginx Reverse Proxy / Load Balancer"]
    WSGI["WSGI Server (Gunicorn / Daphne)"]
    ASGI["ASGI Server (Django Channels / WebSockets)"]
    
    subgraph Django Core Engine ["Django 5.2.12 Backend Core"]
        MiddlewareStack["Middleware Pipeline (Security, Auth, CSRF, Sandbox, Session, Audit)"]
        APIRouter["URL Dispatcher & REST API Views (/api/* & /panel/*)"]
        
        subgraph Modular Apps
            AppAccounts["accounts (Auth, Roles, Dual Login, Devices)"]
            AppOrganisation["organisation (Organisations, OrganisationManagers, Quotas)"]
            AppTables["tables (Table Models, TableAccess Relational Delegation)"]
            AppCards["idcards (Card Data & State Machine)"]
            AppAssistants["assistants (Scoped Assistants, Manager Workloads)"]
            AppReprint["reprintcard (Reprint Queue & Pool)"]
            AppExports["exports (ReportLab PDF, Word, ZIP)"]
            AppMedia["mediafiles (OpenCV, Protected Media)"]
            AppMobile["mobile_api (Biometrics, Camera API)"]
            AppCore["core (Background Workers, AutoPasswordService, Audit Logs)"]
        end
    end
    
    subgraph Data & Execution Layer
        PostgresDB[("PostgreSQL Database (Primary Data Store)")]
        SQLiteDev[("SQLite Sandbox DB (Guest / Local Dev)")]
        RedisCache[("Redis Cache & Channel Layer (OTP, Sessions, Rates)")]
        CeleryWorker["Background Workers (ThreadPool / Celery)"]
        Filesystem["Protected File Storage (/media/adarshimg, /exports)"]
    end

    ClientSPA -->|HTTP REST / JSON| Nginx
    MobileApp -->|HTTP REST / JSON| Nginx
    DesktopApp -->|HTTP REST / Sync| Nginx
    ClientSPA -->|WebSockets| ASGI

    Nginx -->|WSGI Pass| WSGI
    Nginx -->|ASGI Pass| ASGI
    WSGI --> MiddlewareStack
    MiddlewareStack --> APIRouter
    APIRouter --> AppAccounts
    APIRouter --> AppOrganisation
    APIRouter --> AppTables
    APIRouter --> AppCards
    APIRouter --> AppAssistants
    APIRouter --> AppReprint
    APIRouter --> AppExports
    APIRouter --> AppMedia
    APIRouter --> AppMobile
    APIRouter --> AppCore

    AppCore --> CeleryWorker
    Django Core Engine --> PostgresDB
    Django Core Engine --> SQLiteDev
    Django Core Engine --> RedisCache
    AppExports --> Filesystem
    AppMedia --> Filesystem
    CeleryWorker --> Filesystem
```

---

## 3. Two-Domain Roles & Access Control Model

CardFlow enforces a clean separation of responsibilities across two discrete operational domains:

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

### Role Capabilities & Boundaries:
* **Prime Manager**: Owns the organisation. Can create tables, configure fields, add/edit Super Managers, and assign table access.
* **Super Manager**: Independent manager with separate login credentials. **Cannot create tables** (`403 Forbidden`). Only accesses and edits card records for tables delegated via `TableAccess`.
* **Assistant**: Scoped directly to their creating Manager (`assistant.manager_id == request.user.id`).

---

## 4. Django App & Modular Breakdown

| Application | Primary Responsibility & Key Models |
|---|---|
| **`core`** | System infrastructure, middleware stack, global error handling, `BackgroundTask` model, `ActivityLog` model, `AutoPasswordService`, and database routers. |
| **`accounts`** | Custom User Model (`core.User`), dual username/email authentication, session security, device tracking (`DeviceSessionMiddleware`), OTP generation, and RBAC role definitions. |
| **`organisation`** | Tenant management (`Organisation`), `OrganisationManager` models, quota limit enforcement (`max_super_managers`), and manager CRUD views. |
| **`tables`** | Core schema model (`Table`), `TableAccess` relational delegation model, field definition configuration, and status counters. |
| **`assistants`** | Assistant user profiles (`Assistant`), manager workload scoping, and table assignment. |
| **`idcards`** | Primary student/staff card data records (`IDCard`), state-machine transition pipeline (`pending` ➔ `verified` ➔ `pool` ➔ `approved` ➔ `download`). |
| **`reprintcard`** | Dedicated replacement/lost card request queue (`ReprintRequest`, `ReprintCardData`), print pool batching, and isolated confirmation workflows. |
| **`exports`** | High-precision PDF grid generation engine (ReportLab, WeasyPrint), Word `.docx` section exporter, Excel/CSV bulk export services. |
| **`mediafiles`** | Protected media delivery (`_protected_media_serve`), zero-trust authorization checks, OpenCV face auto-cropping, thumbnail generation. |
| **`mobile_api`** | Specialized endpoints for the React Native companion app: real-time optical camera biometric checks, directory search, and field photo capture. |

---

## 5. Database & Multi-Tenancy Engine

### 5.1 Relational Models for Delegation & Quotas
* **`Organisation.max_super_managers`**: Configurable maximum active Super Managers per organisation (default: 4).
* **`OrganisationManager` (`organisation_manager`)**: Links `User` to `Organisation` with `manager_type` (`'prime_manager' | 'super_manager' | 'guest_manager'`) and boolean capabilities (`can_view_tables`, `can_manage_assistants`, etc.).
* **`TableAccess` (`tables_tableaccess`)**: Unique `(table, manager)` pair defining access grants (`can_view`, `can_edit_cards`, `can_approve_print`).

---

## 6. Security, Middleware & Authentication

* **Dual Login Authentication**: Users can authenticate using either their **Email** or **Username** (or normalized phone number).
* **Automated PIN Generator (`AutoPasswordService`)**: Securely generates 8–10 character PINs (e.g. `MATH@5080`) based on organization name or phone number.
* **Per-Request Permission Guard**: `PermissionValidationMiddleware` re-evaluates user permissions against database roles every `PERMISSION_REVALIDATION_INTERVAL` requests to instantly revoke compromised access.

---

## 7. Media Storage & Protected Access Control

All sensitive images and documents (`/media/adarshimg/`, `/media/exports/`, `/media/clients_imgs/`, `/media/staff_imgs/`, `/media/temp/`) are denied direct public access and served via `_protected_media_serve` and Nginx `X-Accel-Redirect`.

---

## 8. Async Workers, Task Queue & Real-time Layer

Heavy tasks (ReportLab PDF compilation, Word document generation, ZIP archive packing, OpenCV batch cropping) are offloaded asynchronously via `BackgroundTask` workers and monitored in real time via Django Channels WebSockets.

---

## 9. Export Pipelines & Image Processing Engine

* **PDF Engine**: Renders millimeter-accurate CR80 card grids (85.6mm × 53.98mm) for dual-sided PVC card printers.
* **Word Exporter**: Generates `.docx` sheets structured with automatic page breaks per Class/Section.
* **OpenCV Face Cropper**: Automatically detects face boundaries, aligns eye levels, and crops portraits to 3:4 aspect ratios.

---

## 10. API Route Map & Directory Structure

### 10.1 Key Endpoints Overview
* `/api/auth/login/` — Dual Email/Username login endpoint.
* `/api/organisation-managers/` — List and create organisation managers with quota limit enforcement.
* `/api/organisation-managers/<id>/` — Retrieve, update, or delete organisation managers.
* `/api/schemas/` — Scoped table schema listing (filters by `TableAccess` for Super Managers).
* `/api/schemas/create/` — Table creation (strictly restricted to Prime Managers & Admins).
* `/api/table/<id>/shared-managers/` — List Super Managers and their table delegation status.
* `/api/table/<id>/share-managers/` — Update table delegation grants for Super Managers.
* `/api/panel/temp-passwords/` — Pro Features temporary credentials management.

---
*Documentation updated for CardFlow Engine Architecture (`v5.1.0`).*
