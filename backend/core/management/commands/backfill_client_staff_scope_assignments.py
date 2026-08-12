from __future__ import annotations

from collections import defaultdict
from typing import Dict, Iterable, List, Set, Tuple

from django.core.management.base import BaseCommand
from django.db import transaction

from core.services.cache_version_service import CacheVersionService
from tables.models import IDCard, Table, Table
from staff.models import Staff


class Command(BaseCommand):
    help = (
        "Backfill legacy client_staff scope assignments. "
        "Targets assistants with empty assignment_scopes. "
        "Default mode handles legacy-empty allowed class/section/branch lists; "
        "use --include-flat-legacy to also convert flat legacy allowed_* records."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--apply",
            action="store_true",
            default=False,
            help="Persist changes. Default is dry-run.",
        )
        parser.add_argument(
            "--client-id",
            type=int,
            default=0,
            help="Only process assistants under this client ID.",
        )
        parser.add_argument(
            "--staff-id",
            type=int,
            default=0,
            help="Only process this assistant staff ID.",
        )
        parser.add_argument(
            "--limit",
            type=int,
            default=0,
            help="Process at most N assistants (0 means no limit).",
        )
        parser.add_argument(
            "--include-flat-legacy",
            action="store_true",
            default=False,
            help=(
                "Also convert assistants with empty assignment_scopes but non-empty "
                "allowed class/section/branch lists into explicit scopes."
            ),
        )

    def handle(self, *args, **options):
        apply_changes = bool(options.get("apply"))
        client_id = int(options.get("client_id") or 0)
        staff_id = int(options.get("staff_id") or 0)
        limit = max(int(options.get("limit") or 0), 0)
        include_flat_legacy = bool(options.get("include_flat_legacy"))

        mode = "APPLY" if apply_changes else "DRY-RUN"
        self.stdout.write(f"\n=== backfill_client_staff_scope_assignments ({mode}) ===")

        qs = (
            Staff.objects
            .filter(staff_type="assistant", client__isnull=False)
            .select_related("client", "user")
            .prefetch_related("assigned_groups")
            .order_by("id")
        )
        if client_id > 0:
            qs = qs.filter(client_id=client_id)
        if staff_id > 0:
            qs = qs.filter(id=staff_id)

        candidates: List[Tuple[Staff, Dict[str, object]]] = []
        skipped_not_legacy = 0
        skipped_no_values = 0
        skipped_not_legacy_items: List[Staff] = []
        skipped_no_values_items: List[Staff] = []

        for staff in qs:
            if not self._is_legacy_unscoped_staff(staff, include_flat_legacy=include_flat_legacy):
                skipped_not_legacy += 1
                skipped_not_legacy_items.append(staff)
                continue

            plan = self._build_backfill_plan(staff)
            if not plan.get("assignment_scopes"):
                skipped_no_values += 1
                skipped_no_values_items.append(staff)
                continue

            candidates.append((staff, plan))
            if limit and len(candidates) >= limit:
                break

        self.stdout.write(f"Legacy-unscoped staff found: {len(candidates)}")
        self.stdout.write(f"Skipped (already scoped / not legacy-empty): {skipped_not_legacy}")
        self.stdout.write(f"Skipped (no scope values found in card data): {skipped_no_values}")

        # Provide short previews including client names to aid diagnostics
        if skipped_not_legacy_items:
            self.stdout.write("\nPreview (skipped - already scoped / not legacy-empty):")
            for s in skipped_not_legacy_items[:20]:
                cname = getattr(s.client, 'name', '') if getattr(s, 'client', None) else ''
                self.stdout.write(f"  - staff_id={s.id}, client_id={s.client_id}, client_name={cname}")

        if skipped_no_values_items:
            self.stdout.write("\nPreview (skipped - no scope values found):")
            for s in skipped_no_values_items[:20]:
                cname = getattr(s.client, 'name', '') if getattr(s, 'client', None) else ''
                self.stdout.write(f"  - staff_id={s.id}, client_id={s.client_id}, client_name={cname}")

        if not candidates:
            self.stdout.write(self.style.WARNING("No assistants require backfill."))
            return

        self.stdout.write("\nPreview (first 20):")
        for staff, plan in candidates[:20]:
            scopes = plan.get("assignment_scopes") or []
            classes = plan.get("allowed_classes") or []
            sections = plan.get("allowed_sections") or []
            branches = plan.get("allowed_branches") or []
            cname = getattr(staff.client, 'name', '') if getattr(staff, 'client', None) else ''
            self.stdout.write(
                f"  - staff_id={staff.id}, client_id={staff.client_id}, client_name={cname}, "
                f"scopes={len(scopes)}, classes={len(classes)}, "
                f"sections={len(sections)}, branches={len(branches)}"
            )

        if not apply_changes:
            self.stdout.write("\nDry-run only. Re-run with --apply to persist changes.")
            return

        updated = 0
        touched_clients: Set[int] = set()

        for staff, plan in candidates:
            group_ids = list(plan.get("group_ids") or [])
            table_ids = list(plan.get("table_ids") or [])
            scopes = list(plan.get("assignment_scopes") or [])
            allowed_classes = list(plan.get("allowed_classes") or [])
            allowed_sections = list(plan.get("allowed_sections") or [])
            allowed_branches = list(plan.get("allowed_branches") or [])

            with transaction.atomic():
                valid_groups = Table.objects.filter(client_id=staff.client_id, id__in=group_ids)
                staff.assigned_groups.set(valid_groups)
                staff.assigned_table_ids = table_ids
                staff.assignment_scopes = scopes
                staff.allowed_classes = allowed_classes
                staff.allowed_sections = allowed_sections
                staff.allowed_branches = allowed_branches
                staff.save(
                    update_fields=[
                        "assigned_table_ids",
                        "assignment_scopes",
                        "allowed_classes",
                        "allowed_sections",
                        "allowed_branches",
                        "updated_at",
                    ]
                )

            updated += 1
            touched_clients.add(int(staff.client_id))

        for cid in touched_clients:
            CacheVersionService.bump("client_staff", f"client:{cid}")
            CacheVersionService.bump("client_dash_counts", f"client:{cid}")

        self.stdout.write("")
        self.stdout.write(self.style.SUCCESS(f"Updated assistants: {updated}"))
        self.stdout.write(f"Touched clients: {len(touched_clients)}")

    @staticmethod
    def _normalize_positive_int_ids(values: Iterable[object]) -> List[int]:
        out: List[int] = []
        seen: Set[int] = set()
        for value in values or []:
            if isinstance(value, bool):
                continue
            try:
                num = int(str(value).strip())
            except (TypeError, ValueError):
                continue
            if num <= 0 or num in seen:
                continue
            seen.add(num)
            out.append(num)
        return out

    @staticmethod
    def _normalize_value_list(values: Iterable[object]) -> List[str]:
        out: List[str] = []
        seen: Set[str] = set()
        for value in values or []:
            text = str(value or "").strip()
            if not text:
                continue
            key = text.lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(text)
        return out

    @staticmethod
    def _build_class_sections(classes: List[str], sections: List[str]) -> Dict[str, List[str]]:
        classes_norm = [str(v).strip() for v in (classes or []) if str(v).strip()]
        sections_norm = [str(v).strip() for v in (sections or []) if str(v).strip()]
        if not classes_norm or not sections_norm:
            return {}
        # Legacy flat filters effectively behave as class x section combinations.
        return {cls_name: list(sections_norm) for cls_name in classes_norm}

    def _is_legacy_unscoped_staff(self, staff: Staff, include_flat_legacy: bool = False) -> bool:
        scopes = staff.assignment_scopes if isinstance(staff.assignment_scopes, list) else []
        if scopes:
            return False

        if include_flat_legacy:
            return True

        if self._normalize_value_list(staff.allowed_classes or []):
            return False
        if self._normalize_value_list(staff.allowed_sections or []):
            return False
        if self._normalize_value_list(staff.allowed_branches or []):
            return False

        return True

    @staticmethod
    def _resolve_scope_field_names(table: Table) -> Tuple[str, str, str]:
        class_field = ""
        section_field = ""
        branch_field = ""

        for field in (table.fields or []):
            if not isinstance(field, dict):
                continue
            ftype = str(field.get("type", "") or "").strip().lower()
            fname = str(field.get("name", "") or "").strip()
            lower = fname.lower()

            if not class_field and (ftype == "class" or lower == "class"):
                class_field = fname
                continue
            if not section_field and (ftype == "section" or lower == "section"):
                section_field = fname
                continue
            if not branch_field and (
                ftype == "branch"
                or lower == "branch"
                or lower == "stream"
                or lower == "course"
                or "branch" in lower
                or "stream" in lower
                or "course" in lower
            ):
                branch_field = fname

        return class_field, section_field, branch_field

    def _collect_table_scope_values(self, table_rows: List[Table]) -> Dict[int, Dict[str, Set[str]]]:
        by_table: Dict[int, Dict[str, Set[str]]] = {}
        field_map: Dict[int, Tuple[str, str, str]] = {}

        for table in table_rows:
            class_field, section_field, branch_field = self._resolve_scope_field_names(table)
            field_map[int(table.id)] = (class_field, section_field, branch_field)
            by_table[int(table.id)] = {
                "classes": set(),
                "sections": set(),
                "branches": set(),
            }

        table_ids = [int(table.id) for table in table_rows]
        if not table_ids:
            return by_table

        cards = IDCard.objects.filter(table_id__in=table_ids).values_list("table_id", "field_data").iterator(chunk_size=1000)
        for table_id, field_data in cards:
            if not field_data:
                continue
            class_field, section_field, branch_field = field_map.get(int(table_id), ("", "", ""))
            bucket = by_table.get(int(table_id))
            if not bucket:
                continue

            if class_field:
                value = (
                    field_data.get(class_field)
                    or field_data.get(class_field.upper())
                    or field_data.get(class_field.lower())
                    or ""
                )
                text = str(value).strip()
                if text:
                    bucket["classes"].add(text)

            if section_field:
                value = (
                    field_data.get(section_field)
                    or field_data.get(section_field.upper())
                    or field_data.get(section_field.lower())
                    or ""
                )
                text = str(value).strip()
                if text:
                    bucket["sections"].add(text)

            if branch_field:
                value = (
                    field_data.get(branch_field)
                    or field_data.get(branch_field.upper())
                    or field_data.get(branch_field.lower())
                    or ""
                )
                text = str(value).strip()
                if text:
                    bucket["branches"].add(text)

        return by_table

    def _build_backfill_plan(self, staff: Staff) -> Dict[str, object]:
        client = staff.client
        groups = list(Table.objects.filter(client=client).only("id").order_by("id"))
        if not groups:
            return {}

        tables = list(
            Table.objects.filter(group__client=client, deleted_by_client=False)
            .only("id", "group_id", "fields")
            .order_by("id")
        )
        if not tables:
            return {}

        group_ids_all = [int(g.id) for g in groups]
        table_ids_all = [int(t.id) for t in tables]
        table_ids_by_group: Dict[int, List[int]] = defaultdict(list)
        table_group_map: Dict[int, int] = {}
        for table in tables:
            tid = int(table.id)
            gid = int(table.group_id)
            table_ids_by_group[gid].append(tid)
            table_group_map[tid] = gid

        assigned_group_ids = self._normalize_positive_int_ids(staff.assigned_groups.values_list("id", flat=True))
        assigned_group_ids = [gid for gid in assigned_group_ids if gid in group_ids_all]

        assigned_table_ids = self._normalize_positive_int_ids(staff.assigned_table_ids or [])
        assigned_table_ids = [tid for tid in assigned_table_ids if tid in table_ids_all]

        preset_classes = self._normalize_value_list(staff.allowed_classes or [])
        preset_sections = self._normalize_value_list(staff.allowed_sections or [])
        preset_branches = self._normalize_value_list(staff.allowed_branches or [])

        # For flat legacy records with explicit allowed_* values but no assignment IDs,
        # avoid guessing a scope across all client groups/tables.
        if (preset_classes or preset_sections or preset_branches) and not (assigned_group_ids or assigned_table_ids):
            return {}

        use_table_mode = (len(group_ids_all) <= 1) or (bool(assigned_table_ids) and not assigned_group_ids)

        if use_table_mode:
            if assigned_table_ids:
                scope_table_ids = assigned_table_ids
            elif assigned_group_ids:
                scope_table_ids = []
                for gid in assigned_group_ids:
                    scope_table_ids.extend(table_ids_by_group.get(gid, []))
                scope_table_ids = self._normalize_positive_int_ids(scope_table_ids)
            else:
                scope_table_ids = table_ids_all

            scope_group_ids = sorted({table_group_map[tid] for tid in scope_table_ids if tid in table_group_map})
            staff_table_ids = scope_table_ids
            scope_tuples = [("table", tid, table_group_map.get(tid, 0)) for tid in scope_table_ids]
        else:
            scope_group_ids = assigned_group_ids or group_ids_all
            scope_group_ids = [gid for gid in scope_group_ids if gid in group_ids_all]
            staff_table_ids = assigned_table_ids
            scope_tuples = [("group", gid, gid) for gid in scope_group_ids]

        table_values = self._collect_table_scope_values(tables)

        scopes = []
        union_classes: List[str] = []
        union_sections: List[str] = []
        union_branches: List[str] = []

        seen_class: Set[str] = set()
        seen_section: Set[str] = set()
        seen_branch: Set[str] = set()

        for scope_type, scope_id, group_id in scope_tuples:
            if scope_type == "table":
                table_ids = [int(scope_id)]
            else:
                table_ids = table_ids_by_group.get(int(scope_id), [])

            classes: Set[str] = set()
            sections: Set[str] = set()
            branches: Set[str] = set()

            for table_id in table_ids:
                bucket = table_values.get(int(table_id)) or {}
                classes.update(bucket.get("classes") or set())
                sections.update(bucket.get("sections") or set())
                branches.update(bucket.get("branches") or set())

            classes_list = sorted(classes)
            sections_list = sorted(sections)
            branches_list = sorted(branches)

            if preset_classes:
                classes_list = list(preset_classes)
            if preset_sections:
                sections_list = list(preset_sections)
            if preset_branches:
                branches_list = list(preset_branches)

            # Keep only scopes that can enforce at least one row-level dimension.
            if not (classes_list or sections_list or branches_list):
                continue

            class_sections = self._build_class_sections(classes_list, sections_list)

            scopes.append({
                "scope_type": scope_type,
                "scope_id": int(scope_id),
                "group_id": int(group_id),
                "classes": classes_list,
                "sections": sections_list,
                "branches": branches_list,
                "class_sections": class_sections,
            })

            for value in classes_list:
                key = value.lower()
                if key not in seen_class:
                    seen_class.add(key)
                    union_classes.append(value)
            for value in sections_list:
                key = value.lower()
                if key not in seen_section:
                    seen_section.add(key)
                    union_sections.append(value)
            for value in branches_list:
                key = value.lower()
                if key not in seen_branch:
                    seen_branch.add(key)
                    union_branches.append(value)

        return {
            "group_ids": scope_group_ids,
            "table_ids": staff_table_ids,
            "assignment_scopes": scopes,
            "allowed_classes": union_classes,
            "allowed_sections": union_sections,
            "allowed_branches": union_branches,
        }
