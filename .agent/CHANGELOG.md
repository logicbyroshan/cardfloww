# CardFlow Project Milestone Changelog

This changelog summarizes the major milestones, architectural evolutions, and significant features reliably documented in the repository releases and Git history.

---

## [Post-v5.7.0 Incremental Iterations] — 2026-08 to 2026-09
- **Dedicated Reprint App Refactoring**: Completed migration to `backend/reprint/` with a 3-step lifecycle (`reprint_list`, `request_list`, `confirmed`), staged diff modals, and in-place `IDCard` mutations.
- **Client Reprint Permissions**: Added bypass logic and modal support for client accounts requesting reprints directly from downloaded card pools.
- **Ad Banner System**: Implemented `/api/banners/` endpoint and tall vertical skyscraper carousel with VidyaMaxx rotation.
- **Dev Server Port Stability**: Switched backend default development port references to 8008 to prevent common localhost port collisions.
- **UI Ergonomics**: Normalized toolbar padding across views, added instant clear buttons to search inputs, and pinned tutorial actions.

---

## [v5.7.0] — 2026-08-17
- **Column Dropdown Presets**: Added standardized preset catalogs for `class`, `section`, `course`, and `branch` schemas via `FormatPresetConfigModal`.
- **Soft Unique Duplicate Engine**: Introduced `find_duplicate_cards()` real-time scanner, amber `REPEAT` badges, and toolbar duplicate filter.
- **Codebase Cleanup**: Purged dead code, obsolete modal states, and legacy imports across backend and frontend.

---

## [v5.6.0] — 2026-08-17
- **Ultra-Fast Reupload Matcher Engine**: In-memory pre-indexed streaming matcher processing 10,000+ photos in <400ms across multiple image columns (`PHOTO`, `SIGNATURE`, `REL_PHOTO`) with fallback stem heuristics.

---

## [v5.5.0] — 2026-08-16
- **Reversible Operations Engine**: Multi-level transaction audit history with forward/inverse mutation logs (`OperationHistory`, `BulkTransaction`).
- **Batch Undo/Redo**: Enabled single-card and batch operation rollback without corrupting audit trails.

---

## [v5.4.0] — 2026-08-16
- **TanStack Virtualized Grid**: Integrated `@tanstack/react-virtual` for ID card tabular grids, maintaining steady 60 FPS rendering on 10,000+ card datasets with zero DOM lag.

---

## [v5.3.0] — 2026-08-15
- **Two-Domain Role Hierarchy**: Strict separation between Platform Domain and Organisation Domain.
- **Autonomous Super Managers**: Independent accounts with configurable quota caps (`max_super_managers`); restricted from table creation (`403 Forbidden`).
- **Table Delegation**: Introduced `TableAccess` relational model and sharing APIs for granular table assignment.
- **Automated PIN Credentials**: Added `AutoPasswordService` generating 8–10 character PINs with dual Email/Username login support.

---

## [v5.2.0] — 2026-08-12
- **Backend Optimization**: Total purge of legacy HTML page views, obsolete backup files, and unrouted page handlers across all 9 Django apps.

---

## [v5.1.1] — 2026-08-12
- **Security Hardening**: Enforced `CORS_ALLOW_ALL_ORIGINS = False` default, added strict security headers, and tightened `PermissionValidationMiddleware`.

---

## [v5.1.0] — 2026-08-12
- **Pure REST API Conversion**: Backend finalized as headless REST API provider. All UI pages migrated exclusively to React SPA. Middleware converted to return JSON 401/403 responses.

---

## [v5.0.0] — 2026-08-11
- **Full Architecture Milestone**: Migration to React 19 SPA frontend + Django REST API backend. Removal of legacy Django HTML templates and legacy build scripts (`build-css.bat`, `build_bundles.py`).
