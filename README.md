# 🎴 CardFlow ID Cards — Enterprise Management Platform

A high-performance, production-grade ID card operations platform designed for schools, colleges, institutions, and enterprise organizations.

> **Live Production Panel**: [https://panel.adarshbhopal.in](https://panel.adarshbhopal.in) | **Current Build Version**: `v5.3.0`

---

## 🌟 Feature Showcase & Visual Modules

CardFlow brings together web management, real-time biometrics, dynamic template engines, automated export pipelines, and granular multi-tenant access control. Below is an interactive overview of each core platform module:

---

### 🏛️ 1. Two-Domain Role Architecture & Organisation Manager Management

**Overview & Key Capabilities:**
- **Two-Domain Separation**:
  - **Platform Domain**: `Prime Admin` (Platform Owner) $\rightarrow$ `Super Admin` $\rightarrow$ `Operator` / `Photographer`.
  - **Organisation Domain**: `Organisation` $\rightarrow$ `Prime Manager` (1, Org Owner) + `Super Managers` (0..N, configurable cap, default 4) + `Guest Manager` + `Assistants`.
- **Autonomous Super Managers**: Independent user accounts with separate credentials and login sessions. Super Managers are strictly forbidden from creating tables (`403 Forbidden`) and can only view/edit cards for tables delegated to them.
- **Relational Table Delegation (`TableAccess`)**: Prime Managers delegate table workload to Super Managers via an interactive modal in real time.
- **Scoped Assistants**: Assistants are owned by their specific creating Manager (`assistant.manager_id = user.id`) and restricted to that Manager's delegated tables.
- **Auto-Generated Temporary Passwords (PIN)**: Automatically generates 8–10 character PINs (e.g. `MATH@5080`) based on entity name or phone, supporting dual Email/Username login.

<table width="100%">
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/built-for-schools.webp" alt="Multi-Tenant School Management" width="100%"/>
      <br/><sub><b>Multi-Tenant Institution Management Dashboard</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/customization.webp" alt="Dynamic Card Schema Builder" width="100%"/>
      <br/><sub><b>Dynamic Card Schema & Field Design Lab</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots1.webp" alt="Client Dashboard Analytics" width="100%"/>
      <br/><sub><b>Client Dashboard & Operations Telemetry</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots2.webp" alt="ID Card Data Table & Filters" width="100%"/>
      <br/><sub><b>Card Data Table & Real-Time Search Filters</b></sub>
    </td>
  </tr>
</table>

---

### 📱 2. Mobile Companion App & Real-Time Biometric Scanner

**Overview & Key Capabilities:**
- **Cross-Platform React Native App**: Mobile companion app for field operators, photographers, and school staff with native SVG icon rendering (zero startup crashes).
- **Real-Time Optical Camera Biometrics**: Embedded camera scanner checks face presence, eye alignment, and detects optical glasses or sunglasses in real time with color-coded status feedback (Green / Amber / Red).
- **Directory & Profile Management**: Search student records on the move, capture missing photos, and inspect student card previews directly from mobile devices.

<table width="100%">
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots3.webp" alt="Mobile Companion Home" width="100%"/>
      <br/><sub><b>Mobile Home Screen & Role-Based Actions</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots4.webp" alt="Real-Time Biometric Camera" width="100%"/>
      <br/><sub><b>Real-Time Optical Camera Biometrics Scanner</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots5.webp" alt="Mobile Search & Directory" width="100%"/>
      <br/><sub><b>Mobile Student & Staff Directory</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots6.webp" alt="Student Profile Detail View" width="100%"/>
      <br/><sub><b>Student Profile & Media Detail View</b></sub>
    </td>
  </tr>
</table>

---

### 🖨️ 3. Printing, Reprint Queues & Status Workflows

**Overview & Key Capabilities:**
- **State-Machine Status Pipeline**: Cards transition seamlessly through `pending ➔ verified ➔ pool ➔ approved ➔ download` to guarantee print quality.
- **Dedicated Reprint Workflow**: Isolated reprint request queue (`Requested ➔ Confirmed ➔ Downloaded ➔ Pool`) processes lost or replacement cards without interrupting main production runs.
- **Batch Print Job Tracking**: Group card orders into production print pools with real-time status badges and instant QR code verification.

<table width="100%">
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots7.webp" alt="Reprint Approval Queue" width="100%"/>
      <br/><sub><b>Reprint Request Approval & Status Queue</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots8.webp" alt="Status Transition Pipeline" width="100%"/>
      <br/><sub><b>Status Pipeline (Pending ➔ Approved ➔ Pool)</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots9.webp" alt="Batch Print Job Tracking" width="100%"/>
      <br/><sub><b>Batch Production Print Job Tracking</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots10.webp" alt="Instant QR Verification" width="100%"/>
      <br/><sub><b>Instant QR Code & Digital Verification</b></sub>
    </td>
  </tr>
</table>

---

### ⚡ 4. Bulk Ingestion, OpenCV Face Cropper & Export Engine

**Overview & Key Capabilities:**
- **Automated OpenCV Face Cropper**: Standalone FastAPI + PyInstaller service automatically detects portraits, centers heads, and crops to exact ID card aspect ratios (3:4 portrait).
- **Semantic ZIP & Excel Ingestion**: Bulk upload thousands of student records via Excel/CSV and automatically match multi-field ZIP archives (`PHOTO`, `SIGNATURE`, `FATHER`, `MOTHER`, `QR`).
- **High-Precision PDF & Word Exporters**: Export print-ready PDF grid sheets (ReportLab / WeasyPrint) with millimeter accuracy, or Word (`.docx`) documents with custom Class & Section page breaks.

<table width="100%">
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/AdarshEngine.png" alt="OpenCV Face Cropper Service" width="100%"/>
      <br/><sub><b>Automated OpenCV Face Cropping Engine</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/Adarsh 3dN.png" alt="3D Card Preview Engine" width="100%"/>
      <br/><sub><b>3D Card Lanyard & Physical Mockup Engine</b></sub>
    </td>
  </tr>
  <tr>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots11.webp" alt="Bulk Ingestion & Semantic ZIP" width="100%"/>
      <br/><sub><b>Multi-Image ZIP & Excel Bulk Ingestion</b></sub>
    </td>
    <td width="50%" align="center">
      <img src="docs/assets/screenshots/screenshots12.webp" alt="PDF Grid & Word Export Pipelines" width="100%"/>
      <br/><sub><b>PDF Grid Printing & Word (.docx) Exporters</b></sub>
    </td>
  </tr>
</table>

---

## 📚 In-Depth Technical Documentation

For complete technical specifications, architecture diagrams, and operational guides, explore our dedicated documentation in [`docs/`](docs/):

- 🏗️ [**System Architecture & Topology Guide**](docs/SYSTEM_ARCHITECTURE.md): Deep dive into Django 5.2, React 19 SPA, Two-Domain Hierarchy, Super Manager delegation, Daphne WebSockets, Celery task workers, and security middleware.
- 🛠️ [**Backend Architecture Specification**](docs/BACKEND_ARCHITECTURE.md): Database models (`OrganisationManager`, `TableAccess`), service layer abstractions, automated password lifecycle, and REST API route map.
- 🎨 [**Frontend Architecture Specification**](docs/FRONTEND_ARCHITECTURE.md): React 19 SPA, Vanilla CSS token engine, Manager Accounts view, `TableShareModal`, and Pro Features Manage Passwords tab.
- ⚙️ [**Core Features & Workflows Guide**](docs/FEATURES_AND_WORKFLOWS.md): Detailed workflows covering dynamic schema design, card status transitions (`pending ➔ verified ➔ pool ➔ approved`), reprint queues, and multi-tenant roles.
- ⚡ [**Bulk Ingestion, Face Cropper & Export Engine Guide**](docs/BULK_INGESTION_AND_EXPORTS.md): Complete guide to semantic image matching, standalone PyInstaller OpenCV Face Cropper, PDF grid printing, and Word `.docx` section page breaks.
- 📱 [**Mobile Companion App Guide**](docs/MOBILE_APP_COMPANION.md): Technical overview of the Expo React Native app, native SVG iconography, real-time optical biometric scanner, and Android build specs.
- 📝 [**Platform Version Log**](docs/VERSION_LOG.md): Complete chronological release history and changelog.

---

## 🛠️ Tech Stack Summary

| Layer | Primary Technology |
|---|---|
| **Backend Framework** | Django 5.2.12 (Python 3.11+) + Django REST API |
| **Frontend Web SPA** | React 19, Vite, Lenis Smooth Scroll, Sonner Toasts, Lucide React Icons |
| **Styling & Aesthetics** | Pure Vanilla CSS Design System + HSL CSS Custom Tokens |
| **Mobile App** | React Native / Expo (Native SVG Icons & Optical Biometric Scanner) |
| **Database & Cache** | PostgreSQL (Prod) / SQLite (Dev) + Redis Cache |
| **Task Queue & Async** | Celery + Channels WebSockets (ASGI) |
| **Media Processing** | OpenCV, Pillow, PyInstaller Face Cropper |
| **Exports Engine** | ReportLab, WeasyPrint, openpyxl, python-docx |

---

## 🚀 Quick Start Setup

### Backend (Django REST Server)
```bash
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend Web SPA (React 19 + Vite)
```bash
cd frontend
npm install
npm run dev
# Production build:
npm run build
```

---

## 📄 License & Intellectual Property

All rights reserved. Property of **CardFlow Platform / Adarsh ID Cards**.
