# CardFlow Architectural Decisions Log

This document records the foundational architectural and design decisions established in the CardFlow codebase. Only decisions supported by repository commits and documentation are documented here.

---

### Decision 1: Full Decoupling of Frontend (React 19 SPA) and Pure Django REST API Backend
- **Date**: 2026-08-11 to 2026-08-12 (`v5.0.0` - `v5.1.0`)
- **Decision**: Completely removed server-rendered Django HTML templates and associated static bundle scripts (`build-css.bat`, `build_bundles.py`). Replaced with a standalone React 19 Single Page Application (Vite 8) communicating exclusively via JSON REST APIs.
- **Reason**: Enable high-density interactive UI rendering (virtualized tables, dynamic modals, live telemetry) without server-side page reloads, cleanly isolating backend business logic from presentation.
- **Impact**: All web UI routes are handled client-side. The backend strictly issues JSON responses (returning HTTP `401`/`403` instead of redirects for unauthorized API requests). Django CSRF cookie is pre-fetched by the SPA at boot.

---

### Decision 2: Two-Domain Role Hierarchy with Autonomous Super Managers & Table Delegation
- **Date**: 2026-08-15 (`v5.3.0`)
- **Decision**: Restructured RBAC into two discrete domains: Platform Domain (`prime_admin`, `super_admin`, `operator`, `photographer`) and Organisation Domain (`prime_manager`, `super_manager`, `guest_manager`, `assistant`). Created relational `TableAccess` delegation and introduced autonomous Super Managers capped per organisation (`Organisation.max_super_managers`).
- **Reason**: Tenant organisations (e.g. schools with multiple department heads) required delegating management of specific classes/tables without exposing global organisation settings or granting table creation privileges.
- **Impact**: Super Managers possess independent login credentials but are strictly forbidden from creating tables (`403 Forbidden`). Table and schema APIs filter dynamically based on `TableAccess` grants. Scoped assistants are restricted to their creating manager's delegated tables.

---

### Decision 3: High-Density Row Virtualization via TanStack Virtual
- **Date**: 2026-08-16 (`v5.4.0`)
- **Decision**: Integrated `@tanstack/react-virtual` for ID card tabular grids.
- **Reason**: Commercial printing batches involve tables with 5,000 to 10,000+ student cards. Full DOM rendering caused severe browser frame-rate drops and memory spikes.
- **Impact**: Real-time 60 FPS scrolling with zero DOM lag across multi-thousand card tables.

---

### Decision 4: Reversible Operations Engine with Inverse Payloads (Undo/Redo)
- **Date**: 2026-08-16 (`v5.5.0`)
- **Decision**: Built a dual-layer audit and undo engine backed by `OperationHistory` and `BulkTransaction` models storing forward and inverse mutation states.
- **Reason**: Bulk data entry and status changes in high-throughput printing labs risk accidental overwrites; operators required non-destructive rollback capabilities without wiping audit trails.
- **Impact**: Single-card and batch modifications can be reversed or re-applied instantly via UI shortcuts without mutating underlying historical audit logs.

---

### Decision 5: Dedicated Standalone Reprint App with In-Place Mutation
- **Date**: 2026-08-17 (Post-`v5.7.0` refactor)
- **Decision**: Refactored reprint functionality out of generic card operations into a dedicated `backend/reprint/` Django application operating a 3-stage lifecycle (`reprint_list` $\rightarrow$ `request_list` $\rightarrow$ `confirmed`). Confirmed reprints update existing `IDCard.field_data` records in-place rather than cloning rows.
- **Reason**: Previous implementations risked duplicate student records, broken foreign key associations, and ambiguous lifetime reprint tracking.
- **Impact**: Zero duplicate card records generated during reprint workflows. Incremental reprint badges (`#1`, `#2`) are tracked sequentially on the original record with complete audit accountability.

---

### Decision 6: Soft Unique Constraint Detection via Real-Time Scanner
- **Date**: 2026-08-17 (`v5.7.0`)
- **Decision**: Implemented `find_duplicate_cards()` backend scanner and UI `REPEAT` pill alerts instead of hard database unique constraints on dynamic schema fields.
- **Reason**: Hard database-level unique constraints cause hard 500 crashes or total import rejections when importing external school spreadsheets containing duplicates (e.g. twins, shared phone numbers).
- **Impact**: Imports succeed without data loss; duplicate entries are non-destructively flagged with amber badges and filterable via the toolbar.

---

### Decision 7: Native SVG Iconography for Mobile Companion
- **Date**: Date not explicitly recorded in version log (documented in `docs/MOBILE_APP_COMPANION.md`)
- **Decision**: Replaced vector icon font packages in the Expo mobile app with pure native SVG path components rendered via `DynamicIcon.js`.
- **Reason**: Custom icon font library initialization triggered cold boot crashes on certain Android versions (`ReferenceError: Property 'fontFamily' doesn't exist`).
- **Impact**: Cold startup times improved by ~40% and font initialization crashes were completely eliminated.

---

### Decision 8: Memory Pre-scaling of Media for High-Precision PDF Grid Generation
- **Date**: Date not explicitly recorded in version log (documented in `docs/BACKEND_ARCHITECTURE.md`)
- **Decision**: Downscaled raw high-resolution card photos to exact 300 DPI card dimensions (`280x360px` @ `quality=82`) using C-accelerated Pillow operations before embedding in ReportLab PDF grids.
- **Reason**: Embedding raw multi-megabyte photos caused ReportLab PDF export memory blowouts and generated unmanageably large files (hundreds of MBs per sheet).
- **Impact**: Reduced PDF export sizes by 15x–20x and accelerated generation speed by 500%–1000%.

---

### Decision 9: Ephemeral SQLite Routing for Guest Sandbox Sessions
- **Date**: Date not explicitly recorded in version log (documented in `docs/BACKEND_ARCHITECTURE.md` & `backend/core/db_router.py`)
- **Decision**: Implemented `GuestSandboxMiddleware` and `GuestSandboxRouter` to direct demo/guest sessions to per-session isolated SQLite databases while normal sessions hit PostgreSQL.
- **Reason**: Enable live demonstrations and evaluation by prospective clients without risking pollution or data corruption of production multi-tenant databases.
- **Impact**: Guest activity is fully isolated and discarded without overhead on the main database.
