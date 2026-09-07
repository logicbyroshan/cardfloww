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
8. **Mandatory Branch → Push → PR → Merge Workflow** *(enforced on every task without exception)*:
   - **Step 1 — Branch**: Before writing any code, create and switch to a dedicated branch:
     - Features: `git checkout -b feat/<short-name>`
     - Bug fixes: `git checkout -b fix/<short-name>`
     - Docs/config: `git checkout -b chore/<short-name>`
     - **Never** commit directly to `main`. This rule has no exceptions.
   - **Step 2 — Commit**: Make all commits on that branch. Keep commits scoped and descriptive (e.g. `feat(auth): add PIN login`).
   - **Step 3 — Review diff**: Run `git diff main` before pushing. Ensure zero unintended mutations.
   - **Step 4 — Push**: Push the branch to remote: `git push origin <branch-name>`.
   - **Step 5 — Create PR**: Use `gh pr create --base main` with a clear title and description.
   - **Step 6 — Wait for approval**: Stop and report the PR URL to the user. **Do not merge autonomously.** Wait for explicit user confirmation.
   - **Step 7 — Merge**: Once user approves, merge via `gh pr merge --squash --delete-branch`.
   - **Step 8 — Sync**: After merge, switch back to `main` and confirm it is up to date.

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
