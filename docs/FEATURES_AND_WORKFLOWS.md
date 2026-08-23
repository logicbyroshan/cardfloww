# Core Features & Operational Workflows Guide

This guide provides a detailed breakdown of the primary business features, card status lifecycles, reprint handling queues, and operational workflows implemented within **CardFlow**.

---

## 1. Dynamic ID Card Schema Engine

CardFlow provides a flexible dynamic schema builder that allows schools, colleges, and organizations to customize card structures without requiring database migrations.

### Schema Mechanics (`IDCardTable`)
- **JSON Field Spec**: Columns are defined in a structured JSON schema (`fields` attribute), supporting types such as `text`, `number`, `date`, `select`, `image`, `signature`, `qr`, and `barcode`.
- **Case Preservation**: Input text casing is strictly preserved across create, update, and bulk upload paths.
- **Dynamic Filter Generation**: Frontend UI automatically constructs tabular filter controls based on configured field types.

---

## 2. Card Status Lifecycle & Transition Pipeline

Cards pass through a strictly enforced, state-machine driven status pipeline:

```text
[ PENDING ] ──────► [ VERIFIED ] ──────► [ POOL ] ──────► [ APPROVED ] ──────► [ DOWNLOAD ]
 (Initial)          (Checked)          (Batch)         (Finalized)         (Exported)
```

| Status | Meaning & Operational Scope |
|---|---|
| `pending` | Card record created (via web portal, mobile app, or bulk CSV). Awaiting initial review. |
| `verified` | Data and student photo verified by client admin or operator. |
| `pool` | Grouped into a print batch pool for physical card production. |
| `approved` | Formally approved by super-admin or institution authority for printing. |
| `download` | Exported into final PDF print grid or Word document bundle. |

---

## 3. Dedicated 3-Step Reprint Lifecycle Architecture (`reprint/`)

When a student or staff member loses an ID card or requires a corrected reprint, CardFlow routes the request through a dedicated 3-stage lifecycle that prevents duplicate card records and preserves data integrity.

```text
[ STEP 1: REPRINT LIST ] ──────► [ STEP 2: REQUESTED LIST ] ──────► [ STEP 3: CONFIRMED LIST ]
(Downloaded Cards Pool)          (Staged Edits & Diff Review)         (In-Place Card Update & Counter)
         ▲                                   │
         └────────── Reject / Cancel ────────┘
```

1. **Step 1: Reprint List (`reprint_list`)**:
   - Source pool consists strictly of previously downloaded cards (`status='download'`).
   - Cards are displayed uniquely (deduplicated by `card.id`).
   - Users can edit student fields directly in the drawer or modal before submitting.
   - Shows active status badges and lifetime reprint counts (*e.g., 2x Reprinted*).
2. **Step 2: Requested List (`request_list`)**:
   - Lists active requests with reason (*Lost*, *Damaged*, *Information Update*), requester, and a visual diff comparing original vs staged values.
   - **Admin Reject / Cancel**: Cancels the request and returns the card to available state in the Reprint List without altering the original card.
   - **Admin Confirm**: Approves the reprint and staged changes.
3. **Step 3: Confirmed List (`confirmed`)**:
   - **In-Place Mutation (Zero Duplication)**: Approved edits are applied directly to the original `IDCard.field_data`—**never creating duplicate card rows**.
   - **Sequential Reprint Badges**: Tracks and displays incremental reprint counts (*Reprint #1, Reprint #2, etc.*).
   - Records confirmation timestamp and approving admin for full auditability.

---

## 4. Multi-Tenant Role Operations & Two-Domain Access Matrix

CardFlow implements granular role-based access control across both the **Platform Domain** and **Organisation Domain**:

| Feature / Operation | Prime Admin | Super Admin | Operator / Photographer | Prime Manager (Org Owner) | Super Manager (Autonomous) | Guest Manager | Assistant (Scoped) |
|---|---|---|---|---|---|---|---|
| **Create / Modify Tables & Schemas** | Yes | Yes | No | Yes | No (`403 Forbidden`) | No | No |
| **Delegate Table Access (`TableAccess`)** | Yes | Yes | No | Yes | No | No | No |
| **Add / Edit Cards** | Yes | Yes | Assigned Orgs | All Org Tables | Delegated Tables | Delegated Tables | Scoped Tables |
| **Delete Single Card** | Yes | Yes | No | Yes | Delegated (if edit enabled) | No | No |
| **Delete All Cards (Bulk)** | Yes | No | No | No | No | No | No |
| **Approve Print Batches** | Yes | Yes | No | Yes | If `can_approve_print` | No | No |
| **Manage Organisation Managers** | Yes | Yes | No | Yes (Up to Quota Limit) | No | No | No |
| **Trigger Bulk ZIP Reupload** | Yes | Yes | Assigned Orgs | Yes | Delegated Tables | No | No |
| **Export PDF / Excel / Word** | Yes | Yes | Assigned Orgs | Yes | Delegated Tables | Delegated Tables | Scoped Tables |
| **Manage Temporary Passwords** | Yes | Yes | No | Yes | No | No | No |

---

## 5. Audit Logging & System Telemetry

- **ActivityLog**: Logs every card creation, modification, status transition, and export generation with timestamp, user ID, and client context.
- **Active User Telemetry**: Automatically alerts super-administrators via email and toast notification when working concurrent sessions exceed system thresholds (>50 active users).
- **System Load Snapshots (`stats/`)**: Collects CPU, RAM, database connection pool, and background queue metrics.

---

## 6. High-Performance Data Ingestion & "Create with Data"

CardFlow features a modular data ingestion app (`imports/`) supporting spreadsheets and Word documents:
- **"Create with Data"**: Instantly builds schemas and populates cards from `.xlsx`, `.xls`, `.csv`, or `.docx` Word tables in a 3-step guided wizard.
- **"Upload Data"**: Appends batch records to existing tables with fuzzy header matching.
- **Embedded Cell Photo Extraction**: Automatically scans Excel worksheet drawings (`ws._images`) and Word table drawings (`w:drawing`, `a:blip`), extracting embedded student photos and signatures directly into card records without requiring ZIP files.
- **Multi-Key ZIP Reupload Matching**: Re-matches uploaded photo archives against student records by Pending path, Roll No, Student Name, or Card ID in atomic batch transactions.

---

## 7. High-Performance Export Pipelines & Natural Sorting

- **Natural Hierarchical Sorting (`fast_sort.py`)**: Universal pre-sorting by $Class \to Section \to Roll \to Full Name$ with LRU memoization evaluating 50,000 keys in < 5ms.
- **Compact 300 DPI PDF Generation**: Pillow C-bindings downsample raw camera photos to exact print dimensions (`280×360px` @ `quality=82`), shrinking PDF sizes by 15x–20x (from ~200MB down to ~10MB) and accelerating generation by 500%–1000%.
- **Zero-CPU Lossless ZIP Streaming**: Streams full original quality photos using `ZIP_STORED` mode, eliminating 100% CPU overhead.
- **Word (.docx) Exporter**: Generates structured tables with embedded full-resolution photos scaled to physical XML dimensions (`1.9cm × 2.5cm`).

