# 🛠️ CardFlow Backend Architecture Specification

> **Platform Version**: `v5.3.0` | **Engine**: Django 5.2.12 (Python 3.11+) | **Architecture**: Decoupled REST & Async Worker Architecture

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
| **`exports`** | High-precision PDF grid generation engine with Pillow C-bindings 300 DPI pre-scaling, zero-CPU lossless ZIP streaming, Word `.docx` section exporter, and fast natural hierarchical sorting (`fast_sort.py`). |
| **`imports`** | High-speed data ingestion engine for `.xlsx`, `.xls`, `.csv`, and `.docx` Word tables, embedded cell photo extraction (`ws._images`, `w:drawing`), schema auto-detection, and multi-key photo reupload matching. |
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

## 7. Media Storage & CardFlow Media Engine

CardFlow incorporates a high-throughput, version-aware media engine designed for large batch processing (100,000+ files) with zero N+1 queries and memory-safe streaming extraction.

### 7.1. Compact Deterministic Naming Scheme (`MediaNameService`)
- **Format**: `O<OrgCode>_<ImageCode>V<Version>.<ext>` (e.g. `O73F_A8XZV1.jpg`, `O73F_A8XZV2.jpg`).
- **OrgCode**: 3–5 uppercase alphanumeric characters derived from `Organisation.image_folder_code` or Base36 PK.
- **ImageCode**: Deterministic 4-character Base36 encoding of `(card_id << 4 | field_type_idx)` ensuring absolute logical identity across edits.
- **Version**: Incrementing integer (`V1` on initial assignment, `V2`, `V3` upon re-upload/editing).
- **Backward Compatibility**: Fully parses legacy patterns (`c0_14325101234501.jpg`, `a1_...`).

### 7.2. Dual-Path Classification & Reupload Engine (`ReuploadMatcher`)
When a ZIP archive containing mixed files (foreign orgs, existing managed re-uploads, unmanaged raw camera photos) is uploaded:
1. **Classification Pipeline**:
   - **Path A (Managed Files)**: Fast regex stem parse. If `OrgCode != current_org_code`, rejected in $O(1)$ time with zero DB queries and zero disk I/O. If `OrgCode == current_org_code`, resolved against in-memory `managed_map` and version-incremented ($V1 \to V2$).
   - **Path B (Unmanaged Files)**: Raw camera files (`0001.jpg`, `IMG_1234.jpg`, `student_name.jpg`) are matched against pre-indexed table import maps (Pending paths, Roll No, Adm No, Student Name, Card ID) in $O(1)$ time, guaranteeing **0 missed new images**.
2. **Streaming Extraction**:
   - Scans `zipfile.ZipFile.infolist()` in memory.
   - Extracts **only** matched entries directly to storage. Unmatched/rejected entries are never decompressed.
3. **Zero N+1 DB Updates**:
   - Commits all modified card records via `IDCard.objects.bulk_update(['field_data'])` in atomic batches.

---

## 8. Async Workers, Task Queue & Real-time Layer

Heavy tasks (ReportLab PDF compilation, Word document generation, ZIP archive packing, OpenCV batch cropping) are offloaded asynchronously via `BackgroundTask` workers and monitored in real time via Django Channels WebSockets.

---

## 9. Export & Ingestion Engines

* **PDF Engine**: Pre-scales raw photos to exact 300 DPI card dimensions (`280×360px` @ `quality=82`) using C-accelerated Pillow downsampling, shrinking PDF size by 15x–20x and accelerating rendering by 500%–1000%.
* **Zero-CPU Lossless ZIP Exporter**: Streams full original quality photos using `ZIP_STORED` mode, eliminating 100% CPU overhead.
* **Fast Natural Sorting Engine (`fast_sort.py`)**: Hierarchical sorting ($Class \to Section \to Roll \to Name$) with LRU memoization evaluating 50,000 keys in < 5ms.
* **Embedded Photo Extraction**: Scans Excel worksheet drawings (`ws._images`) and Word table drawings (`w:drawing`, `a:blip`) to extract student photos directly from document cells into student records without requiring a ZIP file.
* **High-Speed Reupload Matcher**: Matches ZIP photo filenames against student cards by Pending path, Roll No, Student Name, or Card ID using batch database transactions.

---

## 10. API Route Map & Directory Structure

### 10.1 Key Endpoints Overview
* `/api/auth/login/` — Dual Email/Username login endpoint.
* `/api/group/<id>/table/create-with-data/` — Create new table from XLSX, CSV, or DOCX with embedded photo extraction.
* `/api/table/<id>/cards/bulk-upload/` — Bulk data import with embedded photo extraction.
* `/api/table/<id>/cards/reupload-images/` — High-speed ZIP photo reupload matching.
* `/api/imports/preview/` — Fast document preview and embedded photo count detection.
* `/api/organisation-managers/` — List and create organisation managers with quota limit enforcement.
* `/api/organisation-managers/<id>/` — Retrieve, update, or delete organisation managers.
* `/api/schemas/` — Scoped table schema listing (filters by `TableAccess` for Super Managers).
* `/api/schemas/create/` — Table creation (strictly restricted to Prime Managers & Admins).
* `/api/table/<id>/shared-managers/` — List Super Managers and their table delegation status.
* `/api/table/<id>/share-managers/` — Update table delegation grants for Super Managers.
* `/api/panel/temp-passwords/` — Pro Features temporary credentials management.

---

## 11. Reversible Operations & Undo/Redo Engine (`operations`)

CardFlow includes a multi-user, conflict-aware **Reversible Operations Engine** (`operations`) designed for high-concurrency ID card data management:

### 11.1. Delta-Based Operation Model
* **$O(\Delta)$ Field Deltas**: Instead of storing expensive full-table snapshots, changes are recorded as granular `before_value` and `after_value` tuples on `OperationChange`.
* **Dynamic Field & Type Fidelity**: Preserves exact native types (numbers, dates, booleans) and explicitly distinguishes `null` (absent) from empty strings `""`.
* **Media & Crop Reversibility**: Reverses photo replacement and crop box adjustments without deleting underlying media files.

### 11.2. Multi-User Conflict Detection
* **Safe Reversals**: When User A triggers Undo, the engine verifies that `current_value == change.after_value`.
* **Non-Destructive Rollback**: If User B modified the field after User A, the engine detects the conflict, preserves User B's change, and transitions the operation to `PARTIALLY_UNDONE` or `CONFLICTED`.
* **Redo Invalidation (Invariant 11)**: Performing any new mutation after an Undo immediately clears the forward Redo stack for that user/table context.
* **Immutable Audit Log**: Undo and Redo create new `UNDO_OPERATION` / `REDO_OPERATION` events and log to `ActivityLog`, preserving a permanent append-only audit trail.

### 11.3. Endpoints
* `POST /api/operations/undo/` — Undoes the latest (or specific) operation on a table.
* `POST /api/operations/redo/` — Redoes the latest undone operation on a table.
* `GET /api/operations/stack/` — Live status query returning `can_undo`, `can_redo`, and descriptive button tooltips.
* `GET /api/operations/history/` — Paginated operation audit history with field delta breakdown.

---

## 12. Audit Log, Activity History & Bulk Transaction Engine

CardFlow features a complete, immutable **Audit Log, Activity History, and Bulk Transaction Subsystem**:

### 12.1. "Record First, Restrict Later" Architecture
* **Always Recorded**: Every data mutation (single-cell edits, drawer saves, status moves, deletes, restores, media replacements, and crop updates) is permanently written to the append-only `AuditEvent` store.
* **Query-Time Role Scoping (`AuditVisibilityService`)**:
  - `ORGANISATION`: Scoped strictly to the actor's tenant (`organisation_id`), visible to Organization Managers, Assistants, and Client Staff.
  - `INTERNAL_ADMIN`: Scoped to CardFlow internal operators and administrators.
  - `PRIME_ADMIN`: Scoped to Prime Admins and Super Admins.
  - `SUPER_ADMIN` / `SYSTEM`: Scoped exclusively to Super Admins.
  - **Zero Tenant Leakage**: The database query strictly enforces tenant boundaries at the SQL level.

### 12.2. First-Class Bulk Transactions (`BulkTransaction`)
* **Mass Batch Grouping**: Operations affecting 100 to 2,000+ cards create a discrete `BulkTransaction` entity (e.g. `BT-20260817-001`).
* **Bidirectional Linkage**: High-level feeds show clean summaries (e.g. *"Assistant A moved 2,000 cards Pending → Verified"*), while individual cards link directly to their parent bulk transaction.
* **Safe Historical Reversals**: Reversing a historical transaction checks the current state of each affected card. Non-conflicted cards are reverted, cards modified subsequently are safely skipped as conflicts, and a **NEW** transaction is created without erasing past history.

### 12.3. Endpoints
* `GET /api/operations/audit/cards/<card_id>/timeline/` — Per-card chronological history with before/after field changes.
* `GET /api/operations/audit/tables/<table_id>/activity/` — Table activity feed.
* `GET /api/operations/audit/transactions/` — Paginated bulk transaction history.
* `GET /api/operations/audit/transactions/<id>/` — Bulk transaction details and affected cards.
* `POST /api/operations/audit/transactions/<id>/reverse/` — Conflict-aware safe transaction reversal.
* `GET /api/operations/audit/export/` — Export audit trail to CSV with auditable export logging.

---
*Documentation updated for CardFlow Engine Architecture (`v5.7.0`).*


