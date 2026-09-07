# Agent Operating Guide — CardFlow

This guide defines the permanent operating contract for AI coding agents in this repository.
Goal: **High Context Quality + Low Unnecessary Token Consumption**.

---

## 1. Context Usage Rules
- **Do not read every `.agent/` file on every task**:
  - Read [`.agent/CONTEXT.md`](.agent/CONTEXT.md) when you need current system state, stack versions, or architectural conventions.
  - Read [`.agent/DECISIONS.md`](.agent/DECISIONS.md) only before proposing architectural or data-model changes.
  - Read [`.agent/CHANGELOG.md`](.agent/CHANGELOG.md) only when investigating regressions or historical feature evolution.
- **Inspect surgically**: Read only the files directly involved in the task. Never dump entire directories into context.
- **Update context sparingly**: Modify `.agent/` documents only when project architecture, critical conventions, or meaningful milestones change.

---

## 2. Core Engineering Directives
1. **Understand First, Modify Second**: Form an accurate diagnosis before writing code.
2. **Smallest Correct Change**: Prefer minimal, localized changes over broad refactorings.
3. **Do Not Modify Unrelated Code**: Never touch working tree edits or unrelated features. Keep git diffs strictly scoped.
4. **Preserve Existing Behavior**: Do not remove or alter existing functionality without explicit user requirement.
5. **No Speculative Dependencies**: Use existing utilities and libraries (e.g. `services/api.js`, `PermissionService`, `MediaNameService`). Do not introduce new packages without clear justification.
6. **Zero Secrets Policy**: Never commit, create, or expose `.env` variables, API keys, passwords, or tokens in files or messages.
7. **Review Final Diff**: Always inspect `git diff` before reporting completion to ensure zero unintended mutations.
8. **Dedicated Feature/Fix Branch Workflow**:
   - Every fix or feature must be created and developed on its own dedicated branch (e.g. `feat/<short-name>` or `fix/<short-name>`). Never commit or modify code directly on `main`.
   - Never push to remote or merge into `main` autonomously. Once implementation and verification are complete, wait for explicit user approval before pushing and merging.

---

## 3. Architecture & Repository Conventions
- **Backend (Django REST API)**:
  - The backend is a pure headless REST API. Never render server-side HTML templates for web application views.
  - Return consistent JSON responses with appropriate HTTP status codes (`401`/`403` for auth failures).
  - Business logic belongs in service layers (`core/services/`, app service modules), not in fat views.
  - Respect Two-Domain isolation: Platform Domain vs Organisation Domain. Super Managers **cannot** create tables (`403 Forbidden`).
  - Card reprints in `backend/reprint/` mutate `IDCard.field_data` in-place and increment reprint count badges; **never** create duplicate card records.
- **Frontend (React 19 SPA)**:
  - All UI routes are handled client-side via React SPA in `frontend/`.
  - Design system uses pure Vanilla CSS with HSL variables in `frontend/src/index.css`. **Do not use Tailwind CSS**.
  - Use TanStack Virtual (`@tanstack/react-virtual`) for high-volume tabular rendering.
- **Mobile App (Expo / React Native)**:
  - In `android_app/`, always use native SVG paths (`DynamicIcon.js`) for iconography. Do not introduce icon font packages (causes Android startup crashes).
- **Media & Ingestion**:
  - Follow `MediaNameService` naming formats: `O<OrgCode>_<ImageCode>V<Version>.<ext>`.
  - Ingestion supports embedded cell photos from `.xlsx` (`ws._images`) and `.docx` (`w:drawing`, `a:blip`).

---

## 4. Verification & Testing Standards
- **Use Targeted Checks**: Verify changes with the smallest relevant tests.
- **Fast Test Loop (Default)**:
  ```bash
  python -m pytest -m "not slow and not very_slow" --reuse-db -q
  ```
- **Business-Critical Regressions**:
  ```bash
  python -m pytest -m "important and not very_slow" --reuse-db -q
  ```
- **Avoid Expensive Runs**: The full test suite exceeds 800 tests (~61 minutes). Do not run full test suites or visual regression lanes for routine edits.
- **Frontend Linting**:
  ```bash
  cd frontend && npm run lint
  ```

---

## 5. Communication & Output
- Keep status updates and completion reports concise, factual, and scannable.
- Do not repeat file contents or duplicate documentation already present in the workspace.
