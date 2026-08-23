# 🎨 CardFlow Frontend Architecture Specification

> **Platform Version**: `v5.3.0` | **Core Engine**: React 19 Single Page Application (SPA) | **Bundler**: Vite 8 | **Styling**: Pure Vanilla CSS HSL Design System

---

## 📋 Table of Contents
1. [Architecture Overview](#1-architecture-overview)
2. [Component & View Hierarchy Topology](#2-component--view-hierarchy-topology)
3. [Two-Domain UI Layout & Role Rendering](#3-two-domain-ui-layout--role-rendering)
4. [Design System & Vanilla CSS Engine](#4-design-system--vanilla-css-engine)
5. [State Management & Navigation Architecture](#5-state-management--navigation-architecture)
6. [API Service Layer & Axios Client](#6-api-service-layer--axios-client)
7. [Table Delegation & Dynamic Schema UI](#7-table-delegation--dynamic-schema-ui)
8. [Pro Tools & Interactive Components](#8-pro-tools--interactive-components)
9. [Performance Optimizations](#9-performance-optimizations)
10. [Frontend Directory Structure](#10-frontend-directory-structure)

---

## 1. Architecture Overview

The **CardFlow Frontend** is a modern, high-performance React 19 Single Page Application (SPA) designed to deliver a high-density, desktop-grade user interface for managing ID card operations, multi-tenant schemas, real-time data grids, dynamic exports, and interactive image processing.

### Key Architectural Principles
* **Decoupled SPA Architecture**: 100% decoupled from server-side Django templates. Communicates exclusively via JSON REST APIs over HTTP/HTTPS and WebSockets.
* **Two-Domain Navigation**: Clean visual separation between Platform Management and Tenant Organisation views.
* **Autonomous Super Manager Interface**: Dedicated Manager Accounts view with live quota pills (`Super Managers: X / Y max`), role badges, and delegated table counts.
* **Interactive Table Delegation (`TableShareModal`)**: Dedicated modal in Table View allowing Prime Managers to delegate or revoke table permissions in real time.
* **Pure Vanilla CSS HSL Token System**: Employs CSS custom properties with HSL color math, custom dark mode elevation layers, glassmorphism backdrop filters, and responsive micro-animations.
* **Edge-Ready Deployment**: Configurable `VITE_API_BASE_URL` supporting independent deployment to static CDNs (Vercel, Netlify, Cloudflare Pages, S3/CloudFront).

---

## 2. Component & View Hierarchy Topology

```mermaid
graph TD
    AppEntry["src/main.jsx (React 19 Root & Lenis Scroll Setup)"]
    AppCore["src/App.jsx (Central State, Auth Provider & View Router)"]
    
    subgraph Global Services & Modals
        AxiosClient["src/services/api.js (Axios Client, CSRF, Sonner Toasts)"]
        GlobalSearchModal["GlobalSearchModal (Ctrl + K Command Palette)"]
        ConfirmDeleteModal["ConfirmDeleteModal (Destructive Actions Guard)"]
        TableShareModal["TableShareModal (Table Delegation & Sharing)"]
        SonnerToaster["Sonner Toaster (Toast Notifications Container)"]
    end

    subgraph App Shell Layout ("src/components/layout/")
        Shell["Shell Component (Main Shell Container)"]
        Sidebar["Sidebar Component (Collapsible Two-Domain Navigation)"]
        Header["Header Component (Tenant Selector, User Profile, Theme Toggle)"]
        Breadcrumbs["Breadcrumbs Component (Contextual Navigation Path)"]
        Footer["Footer Component (Telemetry & Count Dispatcher)"]
    end

    subgraph Core View Modules
        DashView["dashboard/ (Operational Telemetry KPI Cards, Recharts Analytics)"]
        CardGridModule["idcard/ (TanStack Data Grid, Inline Edit, Status Pipelines, Table Delegation)"]
        TenantModule["client/ (Manager Accounts View, Quota Counters, Super Manager Cards)"]
        ReprintQueueModule["reprint/ (Dedicated Reprint Request Queue & Pool Manager)"]
        ProToolsModule["pro/ (Manage Passwords, OpenCV Cropper, 3D Lanyard Engine)"]
        PanelControlModule["panel/ (Task Progress Tracker, Audit Logs, Settings)"]
        AuthModule["auth/ (Dual Email/Username Login Form, Role-Based Route Locks)"]
    end

    AppEntry --> AppCore
    AppCore --> AxiosClient
    AppCore --> GlobalSearchModal
    AppCore --> ConfirmDeleteModal
    AppCore --> TableShareModal
    AppCore --> SonnerToaster
    
    AppCore --> Shell
    Shell --> Sidebar
    Shell --> Header
    Shell --> Breadcrumbs
    Shell --> Footer

    Shell --> DashView
    Shell --> CardGridModule
    Shell --> TenantModule
    Shell --> ReprintQueueModule
    Shell --> ProToolsModule
    Shell --> PanelControlModule
    Shell --> AuthModule
```

---

## 3. Two-Domain UI Layout & Role Rendering

### 3.1 Manager Accounts View (`src/components/client/ClientAccountsView.jsx`)
* **Live Quota Pill**: Renders real-time badge `Super Managers: {super_manager_count} / {max_super_managers} max` (flashes red when full).
* **Manager Type Badges**:
  * `Prime Manager`: Blue badge (`#1d4ed8`) indicating full organisation ownership.
  * `Super Manager`: Purple badge (`#6b21a8`) indicating autonomous manager with delegated tables.
  * `Guest Manager`: Amber badge (`#b45309`) indicating temporary reviewer.
* **Delegated Tables Column**: Shows number of delegated tables with quick status pills.

### 3.2 Add / Edit Manager Drawer (`src/components/dashboard/QuickActionDrawer.jsx`)
* Integrated with `organisationManagerApi` for direct creation of Super and Guest managers.
* **Initial Table Delegation**: Checkbox list allowing Prime Managers to assign specific tables during creation.
* **Auto-PIN Notice**: Informative card explaining automated credential dispatch.

### 3.3 Manage Passwords View (`src/components/pro/ManageFeaturesView.jsx`)
* Dedicated tab in Pro Features for reviewing active temporary PINs, resetting passwords, and triggering credential emails.

---

## 4. Design System & Vanilla CSS Engine

The design system is located in `src/index.css` and built entirely on native CSS custom properties:
* **Glassmorphism Backdrop Filters**: Uses `backdrop-filter: blur(12px)` for headers, sidebars, command palettes, and floating action bars.
* **Micro-Animations & Keyframes**: Native CSS `@keyframes` handle shimmer loading skeletons, pulse badges, modal scale transitions, and table row highlight fades.

---

## 5. State Management & Navigation Architecture

* **View Context**: Managed via `activeView` in `App.jsx` (`'dashboard'`, `'tables'`, `'client_accounts'`, `'reprint'`, `'pro_features'`).
* **Role-Based Locks**:
  * Super Managers: Hide `+ Add Table` and `Create with XLSX` buttons. Table view displays only delegated tables.
  * Prime Managers: Unlocks table creation and the **Share** delegation button.

---

## 6. API Service Layer & Axios Client

The unified Axios instance in `src/services/api.js` provides organized domain namespaces:
* `authAPI`: `login()`, `logout()`, `getProfile()`, `verifyOTP()`
* `organisationManagerApi` / `managerApi`: `list()`, `create()`, `get()`, `update()`, `delete()`
* `schemaApi`: `getTables()`, `createTable()`, `createTableFromData()`, `getSharedManagers()`, `shareManagers()`
* `reprintApi`: `getStepCounts()`, `getReprintList()`, `requestReprint()`, `getRequestList()`, `confirmReprint()`, `rejectReprint()`, `getConfirmedList()`, `getCardHistory()`
* `bulkApi` / `exportApi`: `bulkUpload()`, `reuploadImages()`, `exportPdf()`, `exportXlsx()`, `exportDocx()`, `exportImages()`, `downloadAll()`
* `tempPasswordApi`: `list()`, `reset()`, `resendEmail()`

---

## 7. Table Delegation & Dynamic Ingestion UI

### 7.1 "Create with Data" Wizard (`CreateXlsxModal`)
* 3-step creation wizard accepting `.xlsx`, `.xls`, `.csv`, and `.docx` Word documents.
* Automatically queries `/api/imports/preview/` to detect schema, column types, and embedded cell photos (with live badge: `📷 {N} Embedded Photos Detected`).
* Allows customizing column types (`Text`, `Number`, `Date`, `Photo`, `Father Photo`, `Mother Photo`, `Signature`) before committing.

### 7.2 "Upload Data" Modal (`IDCardActionsView`)
* Ingests `.xlsx`, `.xls`, `.csv`, and `.docx` data into existing tables.
* Auto-maps document headers to table fields and extracts embedded photos.

### 7.3 Interactive Table Delegation Modal (`TableShareModal`)
* Prime Managers can click **Share** on any table row to open `TableShareModal`.
* Fetches Super Managers via `GET /api/table/<id>/shared-managers/`.
* Allows toggling table permissions (`can_edit_cards`, `can_approve_print`) with one-click saving via `POST /api/table/<id>/share-managers/`.

### 7.4 Dedicated 3-Stage Reprint Manager View (`ReprintCardsManagerView.jsx`)
* Interactive 3-tab layout: **Reprint List** (source downloaded cards with inline edit modal) $\to$ **Requested List** (staged changes diff modal, cancel/reject, confirm) $\to$ **Confirmed List** (in-place non-duplicating card updates & sequential `#1`, `#2` badges).
* Dynamic live badge counters fetching metrics via `GET /reprint/api/table/<id>/step-counts/`.

---

## 8. Performance Optimizations

1. **Virtualization**: Uses `@tanstack/react-virtual` for datasets exceeding 1,000+ records to maintain 60 FPS scrolling.
2. **Lazy Loading & Code Splitting**: Heavy modules (Recharts, 3D Mockup Engine, OpenCV Cropper) load on demand.
3. **Smooth Scroll Isolation**: Lenis scroll engine runs on a RAF loop, eliminating scroll stutter.

---

## 9. Frontend Directory Structure

```
frontend/
├── index.html               # SPA Entry HTML Container
├── vite.config.js           # Vite configuration & proxy settings
├── package.json             # React 19 dependencies & scripts
└── src/
    ├── main.jsx             # React 19 Root entrypoint & Lenis scroll setup
    ├── App.jsx              # Central router, state provider & view manager
    ├── index.css            # Pure Vanilla CSS Design System (Tokens, HSL, Utilities)
    ├── App.css              # Structural layout & animation styles
    ├── services/
    │   └── api.js           # Unified Axios client with CSRF & Sonner error handling
    ├── utils/
    │   ├── constants.js     # System constants & status codes
    │   └── formatters.js    # Date, badge & byte formatters
    └── components/
        ├── auth/            # Dual Email/Username login form & OTP modals
        ├── client/          # Manager Accounts View, Quota Counters, Directory
        ├── common/          # Reusable UI primitives (CreateXlsxModal, CustomSelect, Skeleton, ConfirmModal)
        ├── dashboard/       # Operational Telemetry KPI cards & QuickActionDrawer
        ├── idcard/          # TanStack Data Grid, CardTableView, CardDownloadsModal & TableShareModal
        ├── layout/          # Shell, Sidebar, Header, Breadcrumbs & Footer
        ├── panel/           # Control Panel settings, Task Progress & Audit Logs
        ├── pro/             # Manage Passwords Tab, Face Cropper, 3D Mockup
        ├── reprint/         # Reprint Queue manager & approval workflows
        ├── settings/        # System & user settings panels
        └── staff/           # Staff directory & role permissions UI
```

---
*Documentation updated for CardFlow Frontend Architecture (`v5.4.0`).*
