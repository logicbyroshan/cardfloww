# CardFlow — Security Policy & Architecture Guide

This document outlines the security architecture, controls, and vulnerability reporting procedures for the **CardFlow Enterprise Platform**.

---

## 🛡️ 1. Reporting Security Vulnerabilities

We take platform and student identity data security seriously. If you discover a potential security vulnerability within CardFlow, please report it immediately to our security operations team:

- **Security Contact**: `security@cardfloww.com`
- **Responsible Disclosure**: Please provide sufficient detail to reproduce the vulnerability. Do not disclose the issue publicly until a fix has been released.
- **Response Timeline**: Initial response within 24 hours; severity assessment and triage within 48 hours.

---

## 🏛️ 2. Two-Domain Isolation Model

CardFlow enforces a strict **Two-Domain Isolation Architecture**:

```
+-----------------------------------------------------------+
|                    PLATFORM DOMAIN                        |
|  - Prime Admin (Global Root)                              |
|  - Super Admin (Multi-Org Operations)                     |
|  - Operator (Data Ingestion & Production)                 |
|  - Photographer (Media Ingestion Only)                    |
+-----------------------------------------------------------+
                             |
                             v
+-----------------------------------------------------------+
|                  ORGANISATION DOMAIN                      |
|  - Prime Manager (Organisation Owner)                     |
|  - Super Managers (Delegated Table Workload, NO Table Creation) |
|  - Assistants (Manager-Scoped Field Operators)            |
|  - Guest Manager (Read-Only Reviewer)                     |
+-----------------------------------------------------------+
```

### Key Security Invariants:
1. **No Cross-Organisation Access**: All Organisation Domain users can strictly view/modify data within their assigned Organisation (`organisation_id`).
2. **Super Manager Restriction**: Super Managers are explicitly forbidden from creating tables (`403 Forbidden`). They can only access tables explicitly delegated to them via `TableAccess` relational permissions.
3. **Assistant Scoping**: Assistants are bound to their creating manager (`manager_id`) and inherit access only to tables granted to that manager.
4. **Platform Domain Isolation**: Platform operators cannot alter organization ownership without Prime Admin elevation.

---

## 🔐 3. Authentication & Password Security

### Password Storage
- Passwords are encrypted using Django's **PBKDF2 with SHA-256** algorithm with 720,000 iterations.
- Password hashes are salted uniquely per user.
- Direct password comparison (`==`) is prohibited across the codebase; all checks use constant-time `check_password()`.

### Password Validation
- Minimum password length: **8 characters** in production.
- Common password similarity and common password dictionary checks are enforced by `django.contrib.auth.password_validation`.

### Multi-Tenant Credentials Lifecycle
- Auto-generated temporary PINs for newly invited managers follow strong entropy patterns (e.g. `NAME@4DigitRandom`).
- Upon first login, users are prompted to set a permanent, private password.

---

## 🍪 4. Session & Cookie Security

| Security Attribute | Development (`DEBUG=True`) | Production (`DEBUG=False`) |
|---|---|---|
| `SESSION_COOKIE_SECURE` | `False` (allows HTTP) | `True` (HTTPS only) |
| `CSRF_COOKIE_SECURE` | `False` (allows HTTP) | `True` (HTTPS only) |
| `SESSION_COOKIE_HTTPONLY` | `True` | `True` (mitigates XSS cookie theft) |
| `CSRF_COOKIE_HTTPONLY` | `False` (accessible by frontend for header) | `False` (CSRF token passed in header) |
| `SESSION_COOKIE_SAMESITE` | `'Lax'` | `'Lax'` (or `'Strict'` for hardened API) |
| `CSRF_COOKIE_SAMESITE` | `'Lax'` | `'Lax'` |
| `SESSION_COOKIE_AGE` | 86,400s (24h) | 86,400s (24h) |

---

## 🌐 5. Network, CORS & CSRF Protections

### CORS Configuration
- **Development**: Localhost ports (`5173`, `3000`, `8000`, `8008`) are permitted ONLY when `DEBUG=True`.
- **Production**: Localhost origins are **completely stripped**. Production only accepts origins explicitly configured via the `CORS_ALLOWED_ORIGINS` environment variable.
- `CORS_ALLOW_ALL_ORIGINS` defaults to `False` and should never be enabled in production.

### CSRF Protection
- All mutating endpoints (`POST`, `PUT`, `PATCH`, `DELETE`) require a valid CSRF token passed via the `X-CSRFToken` header.
- `CSRF_TRUSTED_ORIGINS` requires explicit HTTPS origins in production.

---

## 🔑 6. API Key & Service-to-Service Security

### Landing Website Public Integration (`WEB_APP_API_KEY`)
- Authenticates server-to-server contact form and directory sync between the public marketing site and CardFlow API.
- The key is supplied via `X-API-KEY` or `Authorization: Bearer <key>` header.
- **Production Guard**: If `DEBUG=False` and `WEB_APP_API_KEY` is not set in `.env`, the Django server raises `ImproperlyConfigured` at startup, preventing insecure default states.

---

## 📷 7. Media & Biometric Data Protection

- **Student Photos & Signatures**: Media files are organized by organisation code and hashed version numbers (`O<OrgCode>_<ImageCode>V<Version>.<ext>`).
- **Nginx Protected Downloads**: Media routes are protected behind Django authentication middleware using internal redirects (`X-Accel-Redirect`) to prevent unauthenticated enumeration of student portraits.
- **No PII in Error Telemetry**: Sentry error tracking has `SENTRY_SEND_PII=False` to ensure sensitive student and staff data is never logged to external monitoring tools.

---

## 📜 8. Dual-Layer Audit Engine

CardFlow tracks all state changes with a reversible, non-destructive audit engine:
- `OperationHistory`: Records user, timestamp, table, card ID, previous state, and new state.
- `BulkTransaction`: Groups batch operations into single reversible units with inverse undo/redo capabilities.

---

## 🛡️ 9. Security Hardening Checklist

Before launching to production:
1. Verify `DEBUG=False` in backend `.env`.
2. Generate a new `SECRET_KEY` (minimum 50 chars).
3. Set a unique `WEB_APP_API_KEY` and update the landing site configuration.
4. Enforce HTTPS across all domains (`SECURE_SSL_REDIRECT=True`).
5. Run `python -m pytest` test suite to verify permission tests pass.
6. Verify no development convenience scripts (`scripts/create_admin.py`, `scripts/setup_clean_environment.py`) are executed in production.
