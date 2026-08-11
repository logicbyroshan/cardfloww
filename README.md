# 🎴 CardFlow ID Cards — Enterprise Management Platform

A high-performance, production-grade ID card operations platform designed for schools, colleges, institutions, and enterprise organizations.

> **Live Production Panel**: [https://panel.adarshbhopal.in](https://panel.adarshbhopal.in) | **Current Build Version**: `v4.19.01`

---

## 🌟 Feature Showcase & Visual Modules

CardFlow brings together web management, real-time biometrics, dynamic template engines, and automated export pipelines. Below is an interactive overview of each core platform module:

---

### 🏛️ 1. Control Panel & Organization Schema Management

**Overview & Key Capabilities:**
- **Multi-Tenant Administration**: Manage multiple schools, colleges, and enterprise clients from a unified control panel with isolated scope boundaries.
- **Dynamic Schema Design Lab**: Create custom ID card schemas (`IDCardTable`) with dynamic field types (text, numbers, dates, dropdowns, photos, signatures, QR codes) without needing database migrations.
- **Real-Time Data Table & Filters**: High-density data grid featuring inline editing, dynamic column sorting, and instant search filter dropdowns powered by Redis caching.

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

- 🏗️ [**System Architecture & Topology Guide**](docs/SYSTEM_ARCHITECTURE.md): Deep dive into Django 5.2, React 18 SPA, Daphne WebSockets, Celery task workers, Redis caching, and zero-trust security middleware.
- ⚙️ [**Core Features & Workflows Guide**](docs/FEATURES_AND_WORKFLOWS.md): Detailed workflows covering dynamic schema design, card status transitions (`pending ➔ verified ➔ pool ➔ approved`), reprint queues, and multi-tenant roles.
- ⚡ [**Bulk Ingestion, Face Cropper & Export Engine Guide**](docs/BULK_INGESTION_AND_EXPORTS.md): Complete guide to semantic image matching, standalone PyInstaller OpenCV Face Cropper, PDF grid printing, and Word `.docx` section page breaks.
- 📱 [**Mobile Companion App Guide**](docs/MOBILE_APP_COMPANION.md): Technical overview of the Expo React Native app, native SVG iconography, real-time optical biometric scanner, and Android build specs.

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


- Mobile upload timeout hardening for 3-image updates.
- Dashboard caching/runtime optimization improvements.
- Mobile action overlay and image upload regression fixes.

```bash
git log --oneline
```

---

## License

Proprietary. All rights reserved.

Unauthorized copying, distribution, or modification is prohibited.
