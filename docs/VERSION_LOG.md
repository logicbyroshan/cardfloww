# Adarsh Platform Version Log

| Date | Platform Version | Mobile Version | Mobile Build | Key Changes |
| :--- | :--- | :--- | :--- | :--- |
| **2026-08-12** | **v5.2.0** | **1.1.00** | **100** | **Backend Optimization: Total purge of 2,250+ lines of legacy HTML page views, dead backup files (word_images_backup.py, views_pages.py, views_shared_pages.py), and unrouted page handlers across all 9 Django apps (accounts, assistants, organisation, operators, panel, reprintcard, stats, staff, core). Pure REST API backend complete.** |
| **2026-08-12** | **v5.1.1** | **1.1.00** | **100** | **Security Hardening: CORS_ALLOW_ALL_ORIGINS defaulted to False. Added X-Frame-Options: DENY, Cache-Control: no-store, and Cross-Origin-Resource-Policy: same-site to all API responses. Tightened rate limiting and PermissionValidationMiddleware ALWAYS_EXEMPT gate.** |
| **2026-08-12** | **v5.1.0** | **1.1.00** | **100** | **Architecture: Backend converted to pure REST API (no HTML rendering). All UI pages now exclusively on React SPA. Removed /panel/ route prefix, cleaned all HTML page views. Middleware returns JSON 401/403. CSRF prefetch on SPA boot.** |
| **2026-08-11** | **v5.0.0** | **1.1.00** | **100** | **Major Architecture Milestone: Complete migration to React 19 SPA frontend + Django REST API backend. Total purge of legacy HTML templates, build-css.bat, build_bundles.py, and unneeded static assets.** |
| **2026-06-12** | **v4.18.4** | **1.0.99** | **99** | **Fix: Resolve Android touch event conflicts for photo picking menu and column filters; fix backend image path normalization for unchanged URLs.** |
| **2026-06-12** | **v4.18.4** | **1.0.97** | **97** | **Fix: TypeError crash in forms/lists on null fields, safeguard FilterDrawer, ClientGroups, CardList, and GroupSettings against empty fields, and verify backend normalized image matches.** |
| **2026-06-12** | **v4.18.4** | **1.0.96** | **96** | **Fix: Update crash with type error, center logo to prevent cropping on Android, request notification permissions, and sign with correct release key fingerprint.** |
| **2026-06-02** | **v4.18.2** | **1.0.67** | **67** | **Fix search persistence across tabs in reprint and main lists, customize ReprintScreen for clients with 3 workflow badges** |
| **2026-06-02** | **v4.18.2** | **1.0.66** | **66** | **Implement inline background PDF download modal to fix authenticated redirection errors for clients and assistants** |
| **2026-06-01** | **v4.18.2** | **1.0.65** | **65** | **Fix TopBar PDF action button for clients/guests; bump build version** |
| **2026-05-30** | **v4.18.2** | **1.0.56** | **56** | **Phase 2 app bug fixes: designation field layout fix, search query reset on tab switch, in-place client updates, flat list keyboard persistent tap, admin client status tabs pre-selection** |
| **2026-05-22** | **v4.18.2** | **1.0.45** | **45** | **Fix: Reprint download CSRF refresh + retry; Pro Features admin UI fetch fixes; session keepalive URL handling; rebuild dist assets** |
| **2026-05-11** | **v3.20.0** | **1.0.45** | **45** | **Google Play API 35 Requirement Fix** |
| 2026-05-11 | v3.20.0 | 1.0.44 | 44 | SVG Icon Stabilization, Crash Fix, Release Signing |
| 2026-05-08 | v3.19.0 | 1.0.43 | 43 | Role-based UI logic and initial native build |

## Current Stable Release (v4.18.2 / 1.0.56)

### Mobile App (1.0.56)
- **API 35 Target**: Updated `targetSdkVersion` to 35 to meet the latest Google Play Store requirements.
- **Centralized Iconography**: Migrated from `@expo/vector-icons` fonts to native SVG paths in `Icons.js`.
- **Stability**: Fixed Android startup crash (`ReferenceError: fontFamily`).
- **Resilience**: Added 5-second splash timeout and global error boundaries.
- **Signing**: Configured with production `release.keystore` from May 8th.
- **Phase 2 fixes**: Included layout fixes for designation field, keyboard persist on lists, clear search on tab changes, and in-place client/card status updates.

### Backend (v4.18.2)
- **Reprint Workflow**: Confirmed-list retrieve action is wired and visible, with backend transition handling verified.
- **UI/Release**: Rebuilt dist assets and aligned the release log with the 4.18.2 deployment.
- **Approved List Actions**: Restored `Download Images` and `Download Word` on the approved list action bar for bulk-download users.

## Next Steps
- [ ] Complete Google Play Store upload of `app-release.aab` (v56).
- [ ] Verify internal testing track performance on target devices (Vivo V27 Pro).
- [ ] Monitor backend API logs for any version mismatches.
