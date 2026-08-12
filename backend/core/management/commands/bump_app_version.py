"""
Management command: bump_app_version
===================================

Version format:
    v<major>.<minor:02d>.<patch:02d>

Rules:
    small   -> increment patch (00..09), then carry to minor (e.g. 2.18.09 -> 2.19.00)
    major   -> increment minor and reset patch (e.g. 2.18.04 -> 2.19.00)
    feature -> increment major and reset minor/patch (e.g. 2.18.04 -> 3.00.00)

Usage:
    python manage.py bump_app_version --level small
    python manage.py bump_app_version --level major
    python manage.py bump_app_version --level feature
    python manage.py bump_app_version --set 2.19.00
    python manage.py bump_app_version --level small --dry-run
"""

from __future__ import annotations

import re
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError


VERSION_RE = re.compile(r"^\s*v?(\d+)\.(\d{1,2})\.(\d{1,2})\s*$", re.IGNORECASE)
README_VERSION_LINE_RE = re.compile(r"(?m)^- VERSION\.txt:\s*v?\d+\.\d+\.\d+\s*$")


class Command(BaseCommand):
    help = "Bump app version using Adarsh rules and sync VERSION.txt + README.md."

    def add_arguments(self, parser):
        parser.add_argument(
            "--level",
            choices=["small", "major", "feature"],
            default="small",
            help="Version bump level. Default: small",
        )
        parser.add_argument(
            "--set",
            dest="set_version",
            default="",
            help="Set explicit version (examples: 2.19.00 or v2.19.00).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Preview new version without writing files.",
        )

    def handle(self, *args, **options):
        base_dir = Path(__file__).resolve().parents[3]
        version_file = base_dir / "VERSION.txt"
        readme_file = base_dir / "README.md"

        if not version_file.exists():
            raise CommandError(f"Missing version file: {version_file}")

        raw_current = version_file.read_text(encoding="utf-8").strip()
        major, minor, patch = self._parse_version(raw_current)
        current = self._format_version(major, minor, patch)

        set_version_raw = str(options.get("set_version") or "").strip()
        if set_version_raw:
            new_major, new_minor, new_patch = self._parse_version(set_version_raw)
        else:
            level = options["level"]
            new_major, new_minor, new_patch = self._bump(major, minor, patch, level)

        new_version = self._format_version(new_major, new_minor, new_patch)

        self.stdout.write(f"Current version: {current}")
        self.stdout.write(f"New version:     {new_version}")

        if options.get("dry_run"):
            self.stdout.write(self.style.WARNING("Dry run only. No files were changed."))
            return

        # 1) Canonical source of truth.
        version_file.write_text(new_version + "\n", encoding="utf-8")

        # 2) README headline mirror (best effort; does not fail command).
        if readme_file.exists():
            readme_text = readme_file.read_text(encoding="utf-8")
            replacement_line = f"- VERSION.txt: {new_version}"
            updated_readme, count = README_VERSION_LINE_RE.subn(replacement_line, readme_text, count=1)
            if count == 1 and updated_readme != readme_text:
                readme_file.write_text(updated_readme, encoding="utf-8")
                self.stdout.write("Updated README.md version line.")
            else:
                self.stdout.write(self.style.WARNING("README.md version line not found or unchanged."))

        self.stdout.write(self.style.SUCCESS(f"Version updated to {new_version}"))

    def _parse_version(self, raw: str) -> tuple[int, int, int]:
        m = VERSION_RE.match(str(raw or ""))
        if not m:
            raise CommandError(
                f"Invalid version format: '{raw}'. Expected v<major>.<minor>.<patch>, e.g. v2.18.09"
            )

        major = int(m.group(1))
        minor = int(m.group(2))
        patch = int(m.group(3))

        if major < 0:
            raise CommandError("Major version cannot be negative.")
        if minor < 0 or minor > 99:
            raise CommandError("Minor version must be between 00 and 99.")
        if patch < 0 or patch > 99:
            raise CommandError("Patch version must be between 00 and 99.")

        return major, minor, patch

    def _format_version(self, major: int, minor: int, patch: int) -> str:
        return f"v{major}.{minor:02d}.{patch:02d}"

    def _bump(self, major: int, minor: int, patch: int, level: str) -> tuple[int, int, int]:
        if level == "small":
            patch += 1
            if patch >= 10:
                patch = 0
                minor += 1
        elif level == "major":
            minor += 1
            patch = 0
        elif level == "feature":
            major += 1
            minor = 0
            patch = 0
        else:
            raise CommandError(f"Unsupported level: {level}")

        if minor >= 100:
            major += minor // 100
            minor = minor % 100

        return major, minor, patch
