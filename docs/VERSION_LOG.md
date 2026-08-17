# Adarsh / CardFlow Platform Version Log

| Date | Platform Version | Mobile Version | Mobile Build | Key Changes |
| :--- | :--- | :--- | :--- | :--- |
| **2026-08-17** | **v5.7.0** | **1.1.00** | **100** | **Column Dropdown Presets & Soft Unique Duplicate Engine**: Standard presets catalog for `class`, `section`, `course`, `branch` with `FormatPresetConfigModal`. Soft `is_unique` constraint with backend `find_duplicate_cards()`, amber `REPEAT` badges, gentle cell highlights, and toolbar `Duplicates (count)` filter. Code quality & dead code purge across backend and frontend. |
| **2026-08-17** | **v5.6.0** | **1.1.00** | **100** | **Ultra-Fast Reupload Matcher Engine**: In-memory pre-indexed streaming matcher processing 10,000+ photos in <400ms with strict multi-image column matching (`PHOTO`, `SIGNATURE`, `REL_PHOTO`) and fallback stem heuristics. |
| **2026-08-16** | **v5.5.0** | **1.1.00** | **100** | **Reversible Operations & Undo/Redo Engine**: Multi-level transaction audit history with forward/inverse mutation logs (`OperationHistory`, `BulkTransaction`). Single-card and mass batch rollback without rewriting audit trails. |
| **2026-08-16** | **v5.4.0** | **1.1.00** | **100** | **TanStack Virtual High-Density Virtualized Grid**: Integrated row virtualization for instantaneous rendering of 10,000+ cards with 0 DOM lag, multi-column search, and floating status pills. |
| **2026-08-15** | **v5.3.0** | **1.1.00** | **100** | **Enterprise Auth & Role Hierarchy Redesign**: Implemented Two-Domain Model (Platform Domain vs Organisation Domain), Autonomous Super Managers (independent credentials, quota caps, cannot create tables), Table Delegation (`TableAccess` model & API), Scoped Assistants, Auto-Generated 8–10 char PIN passwords, Dual Email/Username login, and Pro Features Manage Passwords view. |
| **2026-08-12** | **v5.2.0** | **1.1.00** | **100** | **Backend Optimization**: Total purge of legacy HTML page views, dead backup files, and unrouted page handlers across all 9 Django apps. Pure REST API backend complete. |
| **2026-08-12** | **v5.1.1** | **1.1.00** | **100** | **Security Hardening**: CORS_ALLOW_ALL_ORIGINS defaulted to False. Added security headers to all API responses. Tightened rate limiting and PermissionValidationMiddleware. |
| **2026-08-12** | **v5.1.0** | **1.1.00** | **100** | **Architecture**: Backend converted to pure REST API (no HTML rendering). All UI pages now exclusively on React SPA. Removed /panel/ route prefix, cleaned all HTML page views. Middleware returns JSON 401/403. CSRF prefetch on SPA boot. |
| **2026-08-11** | **v5.0.0** | **1.1.00** | **100** | **Major Architecture Milestone**: Complete migration to React 19 SPA frontend + Django REST API backend. Total purge of legacy HTML templates, build-css.bat, build_bundles.py, and unneeded static assets. |

---

## Current Stable Release (v5.7.0)

### Backend & Core Schema Engine (v5.7.0)
- **Column Dropdown Presets & Options Normalization**: Dynamic column schema supporting `format_preset` and `options: list[str]` for standard and custom dropdown fields.
- **Soft Unique Constraint Scanner (`find_duplicate_cards`)**: Real-time non-destructive duplicate scanner across any unique fields without altering cards.
- **Ultra-Fast Reupload Matcher**: 10,000+ image matching in <400ms across multiple image columns.
- **Reversible Operations Engine**: Full undo/redo capability with inverse payload execution.

### Frontend Web SPA (v5.7.0)
- **Interactive Preset Lab (`FormatPresetConfigModal`)**: Configures Roman, Ordinal, Numeric, Word, Alphabetical, House, Course, Branch, or custom options with live chip preview.
- **Duplicate Visual Highlighting**: Amber `REPEAT` pills, cell highlights, and instant `Duplicates (count)` toolbar filter.
- **TanStack Virtualized ID Card Grid**: High-density 60fps rendering of multi-thousand card tables.
- **Cleaned Codebase**: Dead code, unused legacy modals, and obsolete states eliminated.
