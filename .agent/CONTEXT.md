# CardFlow Platform — Agent Context Snapshot

## 1. Project Purpose & Scope
**CardFlow** (Adarsh ID Cards) is a production-grade, multi-tenant enterprise ID card lifecycle and identity operations platform designed for schools, universities, institutions, and high-volume commercial printing labs. It manages dynamic card schemas, batch data/image ingestion, biometrics, print production queues, and precision multi-format exports.

- **Current Stable Version**: `v5.7.0` (Platform), `1.1.00` / `100` (Mobile Companion)
- **Primary Domain**: Identity operations, card lifecycle state machine, and print production pipelines.

---

## 2. Technology Stack & Key Dependencies

| Subsystem | Technologies & Dependencies | Rationale / Implementation |
|---|---|---|
| **Backend Core** | Python 3.11+, Django 5.2.12 | Pure REST API (`backend/config/settings.py`); never renders web HTML templates. |
| **Realtime & WebSockets**| Django Channels 4.2.2, Daphne, channels-redis 4.2.1 | Bi-directional communication for print queues, task progress, and desktop sync. |
| **Async Task Queue** | Celery 5.4+, Redis 7.2 | Asynchronous ReportLab PDF generation, ZIP compression, and bulk data processing. |
| **Persistence** | PostgreSQL (`psycopg2-binary 2.9.11`), SQLite (Dev/Test/Guest) | Primary relational store in production; SQLite for local dev, pytest, and guest sandboxes. |
| **Frontend Web SPA** | React 19.2.7, Vite 8.1.1 | Decoupled client application (`frontend/`); communicates via JSON REST API. |
| **Frontend Styling** | Pure Vanilla CSS (HSL custom properties) | Custom design system (`frontend/src/index.css`); Tailwind is **not** used. |
| **Frontend UI Primitives**| `@tanstack/react-table` 9.1, `@tanstack/react-virtual` 3.14, `lucide-react`, `sonner`, `lenis` | High-density 60 FPS virtualized grid for 10,000+ cards, smooth scroll, toasts. |
| **Mobile Companion** | React Native 0.79.6, Expo 53.0.27 (`android_app/`) | Field photo capture, directory search, optical camera biometrics; native SVG icons. |
| **Imaging & Biometrics** | OpenCV headless (`opencv-python-headless 4.8+`), Pillow 12.1.1, standalone FastAPI Face Cropper (`127.0.0.1:4765`) | Face/eye detection, aspect-ratio cropping (3:4), optical glasses checking. |
| **Export Engines** | ReportLab 4.4.9, WeasyPrint 68.1, python-docx 1.2.0, openpyxl 3.1.5 | Millimeter-accurate PDF grid printing, Word `.docx` section pagination, Excel sheets. |

---

## 3. Architecture & Topology

```
Clients: [React 19 SPA (Port 5173/Prod)] [Expo Mobile App] [Desktop Sync Client]
                     │                                │                   │
                     ▼                                ▼                   ▼
Gateway:     [Nginx Reverse Proxy / SSL Termination] ──► [WhiteNoise / X-Accel-Redirect (Media)]
                     │
                     ├──────────────► [WSGI / Gunicorn (Port 8000/8008)] ──► Django REST API
                     └──────────────► [ASGI / Daphne]                    ──► Django Channels (WebSockets)
                                              │
Data / Cache: [PostgreSQL / SQLite] ◄─────────┴─────────► [Redis Broker & Cache (TTL 600s)]
                                                                  │
Workers:                                            [Celery / BackgroundTask Workers]
                                                                  │
Auxiliary Services:                                 [OpenCV Face Cropper (Port 4765)]
```

### Core Architectural Rules
1. **Headless REST API**: Backend returns JSON exclusively. Authentication failures return HTTP `401`/`403` JSON payloads (handled by SPA redirect to `/auth/login`).
2. **Two-Domain Multi-Tenancy**:
   - **Platform Domain**: `prime_admin` (Platform Owner), `super_admin` (Global Admin), `operator` (Assigned Orgs), `photographer` (Media Capture Only).
   - **Organisation Domain**: `Organisation` $\rightarrow$ `prime_manager` (Org Owner) $\rightarrow$ `super_manager` (Autonomous, max limit configured via `Organisation.max_super_managers`, default 4) $\rightarrow$ `guest_manager` $\rightarrow$ `assistant` (Scoped to creating manager).
3. **Table Delegation (`TableAccess`)**: Prime Managers delegate table viewing/editing to Super Managers via `TableAccess` grants (`can_view`, `can_edit_cards`, `can_approve_print`). Super Managers are strictly forbidden from creating tables (`403 Forbidden`).
4. **Card Status Lifecycle Pipeline**:
   $$\text{pending} \longrightarrow \text{verified} \longrightarrow \text{pool} \longrightarrow \text{approved} \longrightarrow \text{download}$$
5. **Dedicated 3-Step Reprint Workflow (`backend/reprint/`)**:
   - Step 1: `reprint_list` (Downloaded cards pool, deduplicated by `card.id`, allows pre-request edit).
   - Step 2: `request_list` (Review staged edit diffs, reject/cancel back to pool, or confirm).
   - Step 3: `confirmed` (Applies changes **in-place** to existing `IDCard.field_data` with incremental `#1`, `#2` reprint count badges; **never creates duplicate card records**).
6. **Reversible Operations Engine (`backend/operations/`)**: Forward and inverse mutation tracking (`OperationHistory`, `BulkTransaction`) enabling single-card and batch undo/redo.
7. **Soft Unique Constraint Scanner**: Duplicates detected via real-time backend scanner (`find_duplicate_cards()`) without raising DB exceptions or rejecting batch data.

---

## 4. Repository & App Structure

- **`backend/`**: Django REST backend monorepo package.
  - `config/`: Central settings (`settings.py`, `urls.py`, `asgi.py`, `wsgi.py`).
  - `core/`: Custom `User` model, security middleware, `BackgroundTask`, `ActivityLog`, `AutoPasswordService`.
  - `accounts/`: Auth views, dual Email/Username login, session/device tracking.
  - `organisation/`: `Organisation` model, `OrganisationManager` models, quota enforcement.
  - `tables/`: `Table` (schema definition), `IDCard` (card records), and `TableAccess` (delegation).
  - `assistants/`: Manager-scoped assistant profiles.
  - `reprint/`: 3-stage reprint lifecycle and in-place mutation engine.
  - `operations/`: Undo/redo reversible operations history.
  - `exports/`: ReportLab / WeasyPrint PDF grid, Word `.docx`, and streaming ZIP exports.
  - `imports/`: Excel and Word `.docx` table ingestion with embedded photo extraction (`docx_reader.py`).
  - `mediafiles/`: Protected media serving (`_protected_media_serve`), `MediaNameService`.
  - `mobile_api/`: Endpoints for mobile biometric verification and photo upload.
  - `web_app/`: Server-to-server authenticated public API (`/api/web/clients/`).
- **`frontend/`**: React 19 SPA (`src/` with `components/`, `services/api.js`, `index.css`).
- **`android_app/`**: Expo React Native mobile companion (`src/screens/CameraScreen.js`, `DynamicIcon.js`).
- **`docs/`**: Comprehensive system architecture, backend/frontend specs, workflows, and test documentation. (Note: Mention of `docx/` in legacy context refers to this directory or Word `.docx` ingestion).
- **`scripts/`**: Operational scripts (`create_admin.py`, `verify_env.ps1`, `setup_clean_environment.py`).

---

## 5. Important Development & Operational Conventions

1. **Deterministic Media Naming**: Image files follow `O<OrgCode>_<ImageCode>V<Version>.<ext>` generated by `MediaNameService`.
2. **Embedded Document Photos**: Ingestion reads drawing elements from `.xlsx` (`ws._images`) and `.docx` (`w:drawing`, `a:blip`) to populate photos directly without standalone ZIP files.
3. **Vanilla CSS Design System**: Frontend UI styling is exclusively maintained in `frontend/src/index.css` via custom properties and HSL variables. Do not install or introduce Tailwind utility classes.
4. **Native SVG for Mobile**: To avoid Android startup crashes (`ReferenceError: Property 'fontFamily' doesn't exist`), all mobile icons must use native SVG paths in `android_app/src/components/DynamicIcon.js`.
5. **Database Routing**: `GuestSandboxRouter` automatically directs guest sandbox sessions to isolated ephemeral SQLite databases; default traffic routes to PostgreSQL.
6. **Branching & Merge Approval Workflow**: Every fix or feature must be implemented on its own dedicated branch (`feat/<name>` or `fix/<name>`), never directly on `main`. Once completed and verified, agents must pause and wait for explicit user confirmation before pushing to remote and merging into `main`.

---

## 6. Testing & Quality Assurance

- **Framework**: PyTest with Django test runner (`backend/pytest.ini`, `backend/conftest.py`).
- **Test Lanes**:
  - **Fast Lane (Local Default)**: `python -m pytest -m "not slow and not very_slow" --reuse-db -q`
  - **Important Lane (PR/Blockers)**: `python -m pytest -m "important and not very_slow" --reuse-db -q`
  - **Slow Lane (Exports/Mobile)**: `python -m pytest -m "slow and not very_slow" --reuse-db -q`
  - **Full Suite**: Over 800 tests (~61 min run); avoid running without lane filters during routine tasks.
- **Frontend Lint**: `npm run lint` (`oxlint`) inside `frontend/`.

---

## 7. Current Status & Active Constraints

- **Active State**: Production-stable codebase at `v5.7.0`.
- **Branching Policy**: Every fix or feature must be isolated on a dedicated branch (`feat/*` or `fix/*`) with push/merge awaiting user review and confirmation.
- **Port Strategy**: Local dev uses port 8000 or 8008 for backend, 5173 for frontend Vite dev server. CORS and CSRF trusted origins accommodate both.
