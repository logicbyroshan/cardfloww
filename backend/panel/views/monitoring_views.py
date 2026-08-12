"""
Monitoring views  (panel app)
==============================
Client-side error reporting and monitoring dashboard API.
Moved from core/views/monitoring_api.py.
"""

import json
import logging
import os
import platform
import re
import secrets
import shutil
import socket
import string
import subprocess
from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.conf import settings
from django.core.cache import cache
from django.core.serializers.json import DjangoJSONEncoder
from django.db import connection
from django.db.models import Count, Q
from django.http import JsonResponse
from django.views.decorators.http import require_http_methods, require_POST
from django.views.decorators.csrf import csrf_protect
from django.contrib.auth.decorators import login_required
from core.services.permission_service import api_require_any_authenticated

logger = logging.getLogger('core.views')

_MAX_REPORTS_PER_MIN = 10
_MAX_LOG_FIELD_LEN = 500
_SERVER_INFO_CACHE_KEY = 'panel:server-info:snapshot:v3'
_SERVER_INFO_CACHE_TTL = 86400
_LOG_CLEAR_GUARD_STATE_KEY = 'activity_log_clear_guard_state_v1'
_LOG_CLEAR_CODE_TTL_SECONDS = 600
_LOG_CLEAR_MAX_ATTEMPTS = 5


def _archive_activity_logs_before_clear(*, actor_username, rows_iterable, row_count):
    """Persist an archive snapshot before destructive log clear."""
    archive_root = Path(settings.MEDIA_ROOT) / 'audit_log_archives'
    archive_root.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now(dt_timezone.utc).strftime('%Y%m%d_%H%M%S')
    archive_filename = f'activity_logs_before_clear_{timestamp}.jsonl'
    archive_path = archive_root / archive_filename

    metadata = {
        'type': 'activity_log_archive',
        'archived_at': datetime.now(dt_timezone.utc),
        'archived_by': actor_username,
        'row_count': int(row_count or 0),
    }

    with archive_path.open('w', encoding='utf-8') as handle:
        handle.write(json.dumps({'meta': metadata}, cls=DjangoJSONEncoder) + '\n')
        for row in rows_iterable:
            handle.write(json.dumps(row, cls=DjangoJSONEncoder) + '\n')

    return archive_path


def _generate_ten_digit_code() -> str:
    return ''.join(secrets.choice(string.digits) for _ in range(10))


def _log_clear_code_session_key(user_id) -> str:
    return f'activity_log_clear_code_{user_id}'


def _log_clear_attempts_session_key(user_id) -> str:
    return f'activity_log_clear_attempts_{user_id}'


def _read_log_clear_attempts(request) -> int:
    try:
        return int(request.session.get(_log_clear_attempts_session_key(request.user.pk), 0) or 0)
    except (TypeError, ValueError):
        return 0


def _set_log_clear_attempts(request, attempts: int) -> None:
    request.session[_log_clear_attempts_session_key(request.user.pk)] = max(int(attempts or 0), 0)
    request.session.modified = True


def _reset_log_clear_attempts(request) -> None:
    key = _log_clear_attempts_session_key(request.user.pk)
    if key in request.session:
        del request.session[key]
        request.session.modified = True


def _increment_log_clear_attempts(request) -> int:
    attempts = _read_log_clear_attempts(request) + 1
    _set_log_clear_attempts(request, attempts)
    return attempts


def _store_log_clear_code(request, code: str) -> None:
    request.session[_log_clear_code_session_key(request.user.pk)] = {
        'code': str(code or ''),
        'generated_at': datetime.now(dt_timezone.utc).isoformat(),
    }
    _reset_log_clear_attempts(request)
    request.session.modified = True


def _consume_log_clear_code_if_valid(request, provided_code: str):
    key = _log_clear_code_session_key(request.user.pk)
    payload = request.session.get(key)
    now = datetime.now(dt_timezone.utc)

    if not isinstance(payload, dict):
        _increment_log_clear_attempts(request)
        return False, 'missing'

    generated_raw = str(payload.get('generated_at') or '').strip()
    generated_at = None
    if generated_raw:
        try:
            generated_at = datetime.fromisoformat(generated_raw.replace('Z', '+00:00'))
            if generated_at.tzinfo is None:
                generated_at = generated_at.replace(tzinfo=dt_timezone.utc)
        except Exception:
            generated_at = None

    if not generated_at or (now - generated_at).total_seconds() > _LOG_CLEAR_CODE_TTL_SECONDS:
        try:
            del request.session[key]
        except KeyError:
            pass
        _increment_log_clear_attempts(request)
        request.session.modified = True
        return False, 'expired'

    valid = str(payload.get('code') or '') == str(provided_code or '')
    if not valid:
        _increment_log_clear_attempts(request)
        return False, 'invalid'

    try:
        del request.session[key]
    except KeyError:
        pass
    _reset_log_clear_attempts(request)
    request.session.modified = True
    return True, 'ok'


def _is_log_clear_actor(user) -> bool:
    role = str(getattr(user, 'role', '') or '').strip().lower()
    return role in {'super_admin', 'pro_user'}


def _is_manual_log_clear_enabled() -> bool:
    return bool(getattr(settings, 'ACTIVITY_LOG_MANUAL_CLEAR_ENABLED', False))


def _normalize_log_clear_guard_state(payload):
    if not isinstance(payload, dict):
        return {
            'status': 'idle',
            'requested_by_username': '',
            'requested_by_role': '',
            'requested_by_user_id': None,
            'requested_at': '',
            'last_completed_by': '',
            'last_completed_at': '',
            'last_deleted_count': 0,
        }

    state = {
        'status': str(payload.get('status') or 'idle').strip().lower() or 'idle',
        'requested_by_username': str(payload.get('requested_by_username') or '').strip(),
        'requested_by_role': str(payload.get('requested_by_role') or '').strip().lower(),
        'requested_by_user_id': payload.get('requested_by_user_id'),
        'requested_at': str(payload.get('requested_at') or '').strip(),
        'last_completed_by': str(payload.get('last_completed_by') or '').strip(),
        'last_completed_at': str(payload.get('last_completed_at') or '').strip(),
        'last_deleted_count': int(payload.get('last_deleted_count') or 0),
    }
    if state['status'] != 'pending_pro_user_confirmation':
        state['status'] = 'idle'
    return state


def _load_log_clear_guard_state():
    from core.models import SystemSettings

    raw_value = SystemSettings.get_value(_LOG_CLEAR_GUARD_STATE_KEY, default='')
    if not raw_value:
        return _normalize_log_clear_guard_state(None)
    try:
        parsed = json.loads(raw_value)
    except Exception:
        parsed = None
    return _normalize_log_clear_guard_state(parsed)


def _save_log_clear_guard_state(state):
    from core.models import SystemSettings

    normalized = _normalize_log_clear_guard_state(state)
    SystemSettings.set_value(
        _LOG_CLEAR_GUARD_STATE_KEY,
        json.dumps(normalized, cls=DjangoJSONEncoder),
        description='Guard state for two-step activity-log deletion approvals.',
    )
    return normalized


def _extract_confirmation_code(request):
    payload = {}
    if request.body:
        try:
            payload = json.loads(request.body.decode('utf-8') or '{}')
        except Exception:
            payload = {}

    code = str(payload.get('confirmation_code') or request.POST.get('confirmation_code') or '').strip()
    if len(code) != 10 or not code.isdigit():
        return ''
    return code


def _clear_activity_logs_with_archive(*, actor):
    from core.models import ActivityLog

    archive_fields = [
        'id', 'user_id', 'action', 'description', 'target_model', 'target_id',
        'target_name', 'ip_address', 'created_at',
    ]
    archive_qs = ActivityLog.objects.order_by('id').values(*archive_fields)
    archive_count = ActivityLog.objects.count()
    archive_path = _archive_activity_logs_before_clear(
        actor_username=(actor.username or '').strip() or f'user:{actor.pk}',
        rows_iterable=archive_qs.iterator(chunk_size=1000),
        row_count=archive_count,
    )
    deleted_count, _ = ActivityLog.objects.all().delete()
    archive_rel = str(archive_path.relative_to(Path(settings.MEDIA_ROOT))).replace('\\', '/')
    return int(deleted_count or 0), archive_rel


def _parse_feed_int(value, default, min_value=None, max_value=None):
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if min_value is not None:
        parsed = max(min_value, parsed)
    if max_value is not None:
        parsed = min(max_value, parsed)
    return parsed


def _parse_iso_datetime(value):
    raw_value = str(value or '').strip()
    if not raw_value:
        return None

    try:
        parsed = datetime.fromisoformat(raw_value.replace('Z', '+00:00'))
    except Exception:
        return None

    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=dt_timezone.utc)
    return parsed


def _matches_activity_search(entry, token):
    if not token:
        return True

    haystack = ' '.join([
        str(entry.get('display_text') or ''),
        str(entry.get('description') or ''),
        str(entry.get('target_model') or ''),
        str(entry.get('target_name') or ''),
        str(entry.get('actor') or ''),
        str(entry.get('action') or ''),
    ]).lower()
    return token in haystack


def _build_activity_log_feed_rows(*, user, now, fetch_cap, search='', user_role='', action='', offset=0, limit=None, paginated=False):
    from django.db.models import Q
    from django.utils.timesince import timesince as django_timesince
    from core.models import ActivityLog
    from core.services.activity_service import ActivityService

    action_display_map = dict(ActivityLog.ACTION_CHOICES)
    rows = []

    queryset = ActivityLog.objects.select_related(
        'user',
        'user__client_profile',
    ).order_by('-created_at')

    if user and user.is_authenticated:
        queryset = ActivityService._apply_role_filter(queryset, user)

    if action:
        queryset = queryset.filter(action=action)
    if user_role:
        queryset = queryset.filter(user__role=user_role)
    if search:
        queryset = queryset.filter(
            Q(description__icontains=search)
            | Q(target_name__icontains=search)
            | Q(target_model__icontains=search)
            | Q(user__username__icontains=search)
            | Q(user__first_name__icontains=search)
            | Q(user__last_name__icontains=search)
        )

    total_count = queryset.count()
    if paginated:
        safe_offset = max(int(offset or 0), 0)
        safe_limit = max(int(limit or 1), 1)
        entries = queryset[safe_offset:safe_offset + safe_limit]
    else:
        entries = queryset[:fetch_cap]

    for entry in entries:
        entry_action = str(entry.action or '').strip()
        description = str(entry.description or '').strip() or 'Activity update'
        created_at_dt = entry.created_at or now
        created_at_display = created_at_dt.strftime('%d-%m-%Y %H:%M')
        time_ago = django_timesince(created_at_dt, now) + ' ago'
        actor = ActivityService._get_actor_display(entry, user, hide_admin_names=False)

        device_meta = _device_surface_meta(_infer_device_surface(entry_action, description))
        event_title = action_display_map.get(entry_action, entry_action.replace('_', ' ').title() or 'Activity')

        rows.append({
            'source_type': 'activity_log',
            'source_label': 'Activity Log',
            'event_title': event_title,
            'event_subtitle': str(entry.target_model or ''),
            'task_id': None,
            'status': '',
            'status_display': '',
            'action': entry_action,
            'action_display': event_title,
            'can_cancel': False,
            'description': description,
            'target_name': str(entry.target_name or ''),
            'user': actor or 'System',
            'ip_address': str(entry.ip_address or ''),
            'progress_text': '',
            'error': '',
            'icon_class': str(entry.icon_class or 'fa-circle-info'),
            'icon_color': str(entry.icon_color or 'edit'),
            'created_at': created_at_display,
            'time_ago': time_ago,
            'created_at_dt': created_at_dt,
            **device_meta,
        })

    return rows, total_count


def _infer_device_surface(action, description):
    text = f"{action or ''} {description or ''}".lower()
    mobile_tokens = ('mobile app', 'android', 'iphone', 'ipad', 'ipod', ' ios ', 'mobile')
    desktop_tokens = ('desktop web', 'desktop', 'browser', 'windows', 'mac', 'linux', 'web app', 'web')

    if any(token in text for token in mobile_tokens):
        return 'mobile'
    if any(token in text for token in desktop_tokens):
        return 'desktop'
    return 'unknown'


def _device_surface_meta(surface):
    normalized = str(surface or '').strip().lower()
    if normalized == 'mobile':
        return {
            'device_surface': 'mobile',
            'device_surface_label': 'Mobile',
            'device_surface_icon': 'fa-mobile-screen-button',
        }
    if normalized == 'desktop':
        return {
            'device_surface': 'desktop',
            'device_surface_label': 'Desktop',
            'device_surface_icon': 'fa-desktop',
        }
    return {
        'device_surface': 'unknown',
        'device_surface_label': 'Unknown',
        'device_surface_icon': 'fa-circle-question',
    }


def _sanitize_log_value(val, max_len=_MAX_LOG_FIELD_LEN):
    if not isinstance(val, str):
        val = str(val) if val is not None else ''
    val = re.sub(r'[\r\n\x00-\x1f\x7f]', ' ', val)
    return val[:max_len]


def _format_bytes(size_bytes):
    size = float(max(size_bytes or 0, 0))
    units = ['B', 'KB', 'MB', 'GB', 'TB', 'PB']
    idx = 0
    while size >= 1024 and idx < len(units) - 1:
        size /= 1024.0
        idx += 1
    return f"{size:.1f} {units[idx]}"


def _dir_size_bytes(root_path):
    total = 0
    stack = [root_path]
    while stack:
        current = stack.pop()
        try:
            with os.scandir(current) as entries:
                for entry in entries:
                    try:
                        if entry.is_symlink():
                            continue
                        if entry.is_file(follow_symlinks=False):
                            total += entry.stat(follow_symlinks=False).st_size
                        elif entry.is_dir(follow_symlinks=False):
                            stack.append(entry.path)
                    except (FileNotFoundError, PermissionError, OSError):
                        continue
        except (FileNotFoundError, PermissionError, OSError):
            continue
    return total


def _memory_snapshot():
    # Keep this dependency-free for quick deployment.
    if platform.system().lower().startswith('win'):
        import ctypes

        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ('dwLength', ctypes.c_ulong),
                ('dwMemoryLoad', ctypes.c_ulong),
                ('ullTotalPhys', ctypes.c_ulonglong),
                ('ullAvailPhys', ctypes.c_ulonglong),
                ('ullTotalPageFile', ctypes.c_ulonglong),
                ('ullAvailPageFile', ctypes.c_ulonglong),
                ('ullTotalVirtual', ctypes.c_ulonglong),
                ('ullAvailVirtual', ctypes.c_ulonglong),
                ('sullAvailExtendedVirtual', ctypes.c_ulonglong),
            ]

        stat = MEMORYSTATUSEX()
        stat.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(stat)):
            total = int(stat.ullTotalPhys)
            free = int(stat.ullAvailPhys)
            used = max(total - free, 0)
            pct = round((used / total) * 100, 1) if total > 0 else 0
            return {
                'total_bytes': total,
                'used_bytes': used,
                'free_bytes': free,
                'used_pct': pct,
                'total_human': _format_bytes(total),
                'used_human': _format_bytes(used),
                'free_human': _format_bytes(free),
            }

    try:
        page_size = os.sysconf('SC_PAGE_SIZE')
        total_pages = os.sysconf('SC_PHYS_PAGES')
        avail_pages = os.sysconf('SC_AVPHYS_PAGES')
        total = int(page_size * total_pages)
        free = int(page_size * avail_pages)
        used = max(total - free, 0)
        pct = round((used / total) * 100, 1) if total > 0 else 0
        return {
            'total_bytes': total,
            'used_bytes': used,
            'free_bytes': free,
            'used_pct': pct,
            'total_human': _format_bytes(total),
            'used_human': _format_bytes(used),
            'free_human': _format_bytes(free),
        }
    except Exception:
        return {
            'total_bytes': 0,
            'used_bytes': 0,
            'free_bytes': 0,
            'used_pct': 0,
            'total_human': '0 B',
            'used_human': '0 B',
            'free_human': '0 B',
        }


def _dir_size_fast(path_obj):
    """Prefer fast native 'du' on Unix; fallback to Python walker."""
    path_str = str(path_obj)
    if os.name != 'nt' and shutil.which('du'):
        try:
            proc = subprocess.run(
                ['du', '-sb', path_str],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
            if proc.returncode == 0 and proc.stdout:
                first_token = proc.stdout.split()[0]
                return int(first_token)
        except Exception as exc:
            logger.debug('Native du scan failed for %s: %s', path_str, exc)
    return _dir_size_bytes(path_str)


def _safe_rel_contains(parent: Path, child: Path) -> bool:
    try:
        child.resolve().relative_to(parent.resolve())
        return True
    except Exception:
        return False


def _other_usage_breakdown(base_dir: Path, other_total_bytes: int, project_total_bytes: int):
    """
    Estimate where 'other system usage' is consumed on the same machine.
    We only expose labels, never absolute paths.
    """
    candidates = [
        ('System Packages', Path('/usr')),
        ('System Data', Path('/var')),
        ('Other Home Data', Path('/home')),
        ('Optional Software', Path('/opt')),
        ('Snap Packages', Path('/snap')),
        ('Temp Data', Path('/tmp')),
        ('Root Home', Path('/root')),
    ]

    if os.name == 'nt':
        # Windows fallback labels (only if paths exist)
        system_drive = Path(os.environ.get('SystemDrive', 'C:') + '\\')
        candidates = [
            ('Windows OS', system_drive / 'Windows'),
            ('Program Files', system_drive / 'Program Files'),
            ('Program Files x86', system_drive / 'Program Files (x86)'),
            ('ProgramData', system_drive / 'ProgramData'),
            ('Users Data', system_drive / 'Users'),
            ('Temp Data', Path(os.environ.get('TEMP', str(system_drive / 'Temp')))),
        ]

    parts = []
    measured_sum = 0
    for label, dir_path in candidates:
        if not dir_path.exists() or not dir_path.is_dir():
            continue

        try:
            size_bytes = _dir_size_fast(dir_path)
        except Exception:
            continue

        # If this bucket contains project root, remove project to avoid double counting.
        if _safe_rel_contains(dir_path, base_dir):
            size_bytes = max(size_bytes - project_total_bytes, 0)

        if size_bytes <= 0:
            continue

        measured_sum += size_bytes
        parts.append({
            'name': label,
            'size_bytes': int(size_bytes),
            'size_human': _format_bytes(size_bytes),
        })

    unattributed = max(other_total_bytes - measured_sum, 0)
    if unattributed > 0:
        parts.append({
            'name': 'Unattributed / Restricted',
            'size_bytes': int(unattributed),
            'size_human': _format_bytes(unattributed),
        })

    for item in parts:
        item['pct_of_other'] = round((item['size_bytes'] / other_total_bytes) * 100, 1) if other_total_bytes > 0 else 0
        item['pct_of_used_disk'] = round((item['size_bytes'] / max(other_total_bytes, 1)) * 100, 1) if other_total_bytes > 0 else 0

    parts.sort(key=lambda x: x['size_bytes'], reverse=True)
    return parts


def _size_for_label(path_usage_raw, label):
    for item in path_usage_raw:
        if item.get('name') == label:
            return int(item.get('size_bytes') or 0)
    return 0


def _sum_existing_dirs(paths):
    total = 0
    seen = set()
    for path_obj in paths:
        try:
            resolved = path_obj.resolve()
        except Exception:
            resolved = path_obj

        key = str(resolved)
        if key in seen:
            continue
        seen.add(key)

        if not path_obj.exists() or not path_obj.is_dir():
            continue
        try:
            total += _dir_size_fast(path_obj)
        except Exception:
            continue
    return int(total)


def _media_video_usage_bytes(media_roots):
    video_exts = {
        '.mp4', '.mov', '.avi', '.mkv', '.webm', '.m4v', '.wmv',
        '.mpeg', '.mpg', '.3gp', '.flv', '.ts', '.m2ts',
    }
    total = 0

    for root in media_roots:
        if not root.exists() or not root.is_dir():
            continue

        stack = [str(root)]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as entries:
                    for entry in entries:
                        try:
                            if entry.is_symlink():
                                continue
                            if entry.is_dir(follow_symlinks=False):
                                stack.append(entry.path)
                                continue
                            if not entry.is_file(follow_symlinks=False):
                                continue
                            if Path(entry.name).suffix.lower() in video_exts:
                                total += int(entry.stat(follow_symlinks=False).st_size)
                        except (FileNotFoundError, PermissionError, OSError):
                            continue
            except (FileNotFoundError, PermissionError, OSError):
                continue

    return int(total)


def _database_storage_snapshot(base_dir):
    backend = settings.DATABASES.get('default', {}).get('ENGINE', '')
    db_name = settings.DATABASES.get('default', {}).get('NAME', '')

    db_info = {
        'backend': backend.split('.')[-1] if backend else 'unknown',
        'name': str(db_name) if db_name else '-',
        'size_bytes': 0,
        'size_human': '0 B',
        'status': 'unknown',
        'error': '',
    }

    try:
        if 'sqlite' in backend:
            db_file = Path(db_name) if db_name else (base_dir / 'db.sqlite3')
            if db_file.exists() and db_file.is_file():
                size_bytes = db_file.stat().st_size
                db_info.update({
                    'size_bytes': int(size_bytes),
                    'size_human': _format_bytes(size_bytes),
                    'status': 'ok',
                    'name': db_file.name,
                })
            else:
                db_info.update({'status': 'missing', 'error': 'SQLite file not found'})

        elif 'postgresql' in backend or 'postgres' in backend:
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_database_size(current_database())')
                row = cursor.fetchone()
            size_bytes = int(row[0]) if row and row[0] is not None else 0
            db_info.update({
                'size_bytes': size_bytes,
                'size_human': _format_bytes(size_bytes),
                'status': 'ok',
            })

        else:
            db_info.update({'status': 'unsupported', 'error': 'Database engine not supported for size metrics'})

    except Exception as exc:
        logger.exception("Database storage snapshot failed")
        db_info.update({
            'status': 'error',
            'error': 'Database size metrics unavailable',
        })

    return db_info


@api_require_any_authenticated
@require_POST
@csrf_protect
def api_client_errors(request):
    """Receive client-side JS errors and log them server-side."""
    rate_key = f'panel:client-errors:{request.user.pk}'
    report_count = int(cache.get(rate_key, 0) or 0)
    if report_count >= _MAX_REPORTS_PER_MIN:
        return JsonResponse({'status': 'rate_limited'}, status=429)
    if report_count <= 0:
        cache.set(rate_key, 1, 60)
    else:
        try:
            cache.incr(rate_key)
        except ValueError:
            cache.set(rate_key, 1, 60)

    try:
        body = json.loads(request.body)
        errors = body.get('errors', [])
    except (json.JSONDecodeError, AttributeError):
        return JsonResponse({'status': 'bad_request'}, status=400)

    if not isinstance(errors, list) or len(errors) == 0:
        return JsonResponse({'status': 'empty'}, status=200)

    errors = errors[:50]
    username = getattr(request.user, 'username', 'unknown')

    for err in errors:
        err_type = _sanitize_log_value(err.get('type', 'unknown'), 30)
        message = _sanitize_log_value(err.get('message', ''))
        source = _sanitize_log_value(err.get('source', ''), 200)
        line = err.get('line', 0)
        if not isinstance(line, (int, float)):
            line = 0
        page_url = _sanitize_log_value(err.get('url', ''), 200)
        status_code = _sanitize_log_value(err.get('status', ''), 10)

        if err_type in ('error', 'rejection'):
            logger.warning(
                "CLIENT_JS_ERROR type=%s user=%s page=%s message=%s source=%s line=%s",
                err_type, username, page_url, message, source, line
            )
        elif err_type in ('htmx', 'htmx-network'):
            logger.warning(
                "CLIENT_HTMX_ERROR type=%s user=%s page=%s status=%s path=%s",
                err_type, username, page_url, status_code,
                _sanitize_log_value(err.get('path', ''), 200)
            )
        elif err_type == 'resource':
            logger.info(
                "CLIENT_RESOURCE_ERROR user=%s page=%s tag=%s src=%s",
                username, page_url,
                _sanitize_log_value(err.get('tag', ''), 30),
                _sanitize_log_value(err.get('src', ''), 200)
            )

    return JsonResponse({'status': 'ok', 'received': len(errors)})


@require_http_methods(["GET"])
@login_required
def api_monitoring_data(request):
    """
    Return monitoring data for the Manage Panel → Monitoring tab.
    GET /panel/api/monitoring/
    """
    from core.services.permission_service import PermissionService

    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Super admin only'}, status=403)

    from django.utils import timezone
    from datetime import timedelta
    from core.models import BackgroundTask, BackupTask, ActivityLog

    now = timezone.now()
    since_24h = now - timedelta(hours=24)

    task_stats = BackgroundTask.objects.aggregate(
        active_tasks=Count('id', filter=Q(status__in=['pending', 'processing'])),
        pending_tasks=Count('id', filter=Q(status='pending')),
        completed_24h=Count('id', filter=Q(status='completed', completed_at__gte=since_24h)),
        failed_24h=Count('id', filter=Q(status='failed', completed_at__gte=since_24h)),
    )

    recent_qs = (
        BackgroundTask.objects
        .select_related('user')
        .order_by('-created_at')[:20]
    )

    STATUS_COLOR = {
        'pending': 'warning',
        'processing': 'info',
        'completed': 'success',
        'failed': 'danger',
        'cancelled': 'secondary',
    }

    recent_items = []
    for t in recent_qs:
        recent_items.append({
            'id': t.id,
            'task_type': t.get_task_type_display(),
            'status': t.status,
            'status_display': t.get_status_display(),
            'status_color': STATUS_COLOR.get(t.status, 'secondary'),
            'progress_pct': t.progress_percentage,
            'user': t.user.get_full_name() or t.user.username if t.user else '—',
            'created_at': t.created_at,
            'completed_at': t.completed_at,
            'error': (t.error_message or '')[:120] if t.status == 'failed' else '',
        })

    export_fail_logs = (
        ActivityLog.objects
        .filter(target_model='Export', description__startswith='Export failed (sync)')
        .select_related('user')
        .order_by('-created_at')[:10]
    )
    for log in export_fail_logs:
        recent_items.append({
            'id': f'log-{log.id}',
            'task_type': 'Export (sync)',
            'status': 'failed',
            'status_display': 'Failed',
            'status_color': STATUS_COLOR.get('failed', 'danger'),
            'progress_pct': 0,
            'user': log.user.get_full_name() or log.user.username if log.user else '—',
            'created_at': log.created_at,
            'completed_at': log.created_at,
            'error': (log.description or '')[:120],
        })

    recent_items.sort(key=lambda item: item.get('created_at') or now, reverse=True)
    recent_tasks = []
    for item in recent_items[:20]:
        created_at = item.get('created_at')
        completed_at = item.get('completed_at')
        item['created_at'] = created_at.strftime('%d-%m-%Y %H:%M') if created_at else ''
        item['completed_at'] = completed_at.strftime('%d-%m-%Y %H:%M') if completed_at else None
        recent_tasks.append(item)

    backup_qs = (
        BackupTask.objects
        .filter(status__in=['pending', 'processing'])
        .order_by('-created_at')[:10]
    )

    backup_tasks = []
    for b in backup_qs:
        backup_tasks.append({
            'id': b.id,
            'status': b.status,
            'status_display': b.get_status_display(),
            'progress': b.progress,
            'total': b.total,
            'progress_pct': round((b.progress / b.total) * 100) if b.total > 0 else 0,
            'current_client': b.current_client or '',
            'created_at': b.created_at.strftime('%d-%m-%Y %H:%M'),
        })

    return JsonResponse({
        'success': True,
        'stats': {
            'active_tasks': task_stats['active_tasks'],
            'pending_tasks': task_stats['pending_tasks'],
            'completed_24h': task_stats['completed_24h'],
            'failed_24h': task_stats['failed_24h'],
        },
        'recent_tasks': recent_tasks,
        'backup_tasks': backup_tasks,
    })


@require_http_methods(["GET"])
@login_required
def api_operations_feed(request):
    """
    Unified operations feed for Manage Panel.
    Combines background tasks, backup tasks and activity logs with filters.

    GET /panel/api/operations-feed/
    """
    from datetime import timedelta
    from django.db.models import Q
    from django.utils import timezone
    from django.utils.timesince import timesince as django_timesince
    from core.models import BackgroundTask, BackupTask
    from core.services.permission_service import PermissionService

    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Super admin only'}, status=403)

    now = timezone.now()
    since_24h = now - timedelta(hours=24)

    limit = _parse_feed_int(request.GET.get('limit', 180), 180, min_value=20, max_value=300)
    offset = _parse_feed_int(request.GET.get('offset', 0), 0, min_value=0)
    fetch_cap = min(max(offset + limit + 400, 300), 2000)

    source = (request.GET.get('source', 'logs') or 'logs').strip().lower()
    allowed_sources = {'all', 'tasks', 'task', 'background', 'background_tasks', 'backups', 'backup', 'logs', 'log', 'activity'}
    if source not in allowed_sources:
        return JsonResponse({'success': False, 'message': 'Invalid source filter'}, status=400)
    search = (request.GET.get('search', '') or '').strip()
    user_role = (request.GET.get('user_role', '') or '').strip()
    task_status = (request.GET.get('task_status', '') or '').strip()
    action = (request.GET.get('action', '') or '').strip()

    include_background = source in ('all', 'tasks', 'task', 'background', 'background_tasks')
    include_backups = source in ('all', 'tasks', 'task', 'backups', 'backup')
    include_logs = source in ('all', 'logs', 'log', 'activity')

    allow_latest_cancel = PermissionService.can_manage_pro_features(request.user)
    latest_active_background_task_id = None
    if allow_latest_cancel:
        latest_active_background_task_id = (
            BackgroundTask.objects
            .filter(status__in=['pending', 'processing'])
            .order_by('-created_at', '-id')
            .values_list('id', flat=True)
            .first()
        )

    active_tasks = BackgroundTask.objects.filter(status__in=['pending', 'processing']).count()
    pending_tasks = BackgroundTask.objects.filter(status='pending').count()
    completed_24h = BackgroundTask.objects.filter(
        status='completed', completed_at__gte=since_24h
    ).count()
    failed_24h = BackgroundTask.objects.filter(
        status='failed', completed_at__gte=since_24h
    ).count()

    items = []

    if include_background:
        bg_qs = BackgroundTask.objects.select_related('user').order_by('-created_at')
        if user_role:
            bg_qs = bg_qs.filter(user__role=user_role)
        if task_status:
            bg_qs = bg_qs.filter(status=task_status)
        if search:
            bg_qs = bg_qs.filter(
                Q(task_type__icontains=search)
                | Q(error_message__icontains=search)
                | Q(user__username__icontains=search)
                | Q(user__first_name__icontains=search)
                | Q(user__last_name__icontains=search)
            )

        for task in bg_qs[:fetch_cap]:
            user_name = task.user.get_full_name() or task.user.username if task.user else 'System'
            progress_text = ''
            if task.total and task.total > 0:
                progress_text = f'Progress {task.progress}/{task.total} ({task.progress_percentage}%)'
            can_cancel = (
                allow_latest_cancel
                and latest_active_background_task_id is not None
                and task.status in ('pending', 'processing')
                and task.id == latest_active_background_task_id
            )

            items.append({
                'source_type': 'background_task',
                'source_label': 'Background Task',
                'event_title': task.get_task_type_display(),
                'event_subtitle': f'Task #{task.id}',
                'task_id': task.id,
                'status': task.status,
                'status_display': task.get_status_display(),
                'action': '',
                'action_display': '',
                'can_cancel': can_cancel,
                'description': task.error_message or 'Background task event',
                'target_name': '',
                'user': user_name,
                'ip_address': '',
                'progress_text': progress_text,
                'error': (task.error_message or '')[:180],
                'icon_class': 'fa-gears',
                'icon_color': 'edit',
                'created_at': task.created_at.strftime('%d-%m-%Y %H:%M'),
                'time_ago': django_timesince(task.created_at, now) + ' ago',
                'created_at_dt': task.created_at,
            })

    if include_backups:
        backup_qs = BackupTask.objects.select_related('created_by').order_by('-created_at')
        if user_role:
            backup_qs = backup_qs.filter(created_by__role=user_role)
        if task_status:
            backup_qs = backup_qs.filter(status=task_status)
        if search:
            backup_qs = backup_qs.filter(
                Q(current_client__icontains=search)
                | Q(error_message__icontains=search)
                | Q(created_by__username__icontains=search)
                | Q(created_by__first_name__icontains=search)
                | Q(created_by__last_name__icontains=search)
            )

        for task in backup_qs[:fetch_cap]:
            user_name = task.created_by.get_full_name() or task.created_by.username if task.created_by else 'System'
            progress_text = ''
            if task.total and task.total > 0:
                progress_pct = round((task.progress / task.total) * 100)
                progress_text = f'Progress {task.progress}/{task.total} ({progress_pct}%)'

            items.append({
                'source_type': 'backup_task',
                'source_label': 'Backup Task',
                'event_title': 'Client Backup',
                'event_subtitle': f'Backup #{task.id}',
                'task_id': None,
                'status': task.status,
                'status_display': task.get_status_display(),
                'action': '',
                'action_display': '',
                'can_cancel': False,
                'description': task.current_client or 'Backup pipeline event',
                'target_name': '',
                'user': user_name,
                'ip_address': '',
                'progress_text': progress_text,
                'error': (task.error_message or '')[:180],
                'icon_class': 'fa-database',
                'icon_color': 'approve',
                'created_at': task.created_at.strftime('%d-%m-%Y %H:%M'),
                'time_ago': django_timesince(task.created_at, now) + ' ago',
                'created_at_dt': task.created_at,
            })

    log_total = 0
    logs_only_mode = include_logs and not include_background and not include_backups

    if include_logs:
        log_items, log_total = _build_activity_log_feed_rows(
            user=request.user,
            now=now,
            fetch_cap=fetch_cap,
            search=search,
            user_role=user_role,
            action=action,
            offset=offset if logs_only_mode else 0,
            limit=limit if logs_only_mode else None,
            paginated=logs_only_mode,
        )
        items.extend(log_items)

    items.sort(key=lambda row: row.get('created_at_dt') or now, reverse=True)
    if logs_only_mode:
        total = log_total
        source_counts = {
            'background_task': 0,
            'backup_task': 0,
            'activity_log': log_total,
        }
        paged_items = items
    else:
        total = len(items)
        source_counts = {
            'background_task': sum(1 for row in items if row.get('source_type') == 'background_task'),
            'backup_task': sum(1 for row in items if row.get('source_type') == 'backup_task'),
            'activity_log': sum(1 for row in items if row.get('source_type') == 'activity_log'),
        }
        paged_items = items[offset:offset + limit]

    for row in paged_items:
        row.pop('created_at_dt', None)

    return JsonResponse({
        'success': True,
        'total': total,
        'items': paged_items,
        'source_counts': source_counts,
        'stats': {
            'active_tasks': active_tasks,
            'pending_tasks': pending_tasks,
            'completed_24h': completed_24h,
            'failed_24h': failed_24h,
        },
    })


@require_POST
@login_required
@csrf_protect
def api_clear_activity_logs(request):
    """
    Manually clear all activity log entries from Logs & Updates.

    POST /panel/api/activity-logs/clear/
    """
    if not _is_log_clear_actor(request.user):
        return JsonResponse({'success': False, 'message': 'Only Super Admin or Pro User can manage log deletion.'}, status=403)

    if not _is_manual_log_clear_enabled():
        return JsonResponse(
            {
                'success': False,
                'message': 'Log deletion guard is disabled by server policy.',
                'code': 'log_clear_disabled',
            },
            status=403,
        )

    confirmation_code = _extract_confirmation_code(request)
    if not confirmation_code:
        return JsonResponse(
            {
                'success': False,
                'message': 'Please enter a valid 10-digit confirmation code.',
                'code': 'confirmation_required',
            },
            status=400,
        )

    attempts = _read_log_clear_attempts(request)
    if attempts >= _LOG_CLEAR_MAX_ATTEMPTS:
        return JsonResponse(
            {
                'success': False,
                'message': 'Too many failed confirmation attempts. Generate a fresh 10-digit code and retry.',
                'code': 'too_many_attempts',
            },
            status=429,
        )

    code_valid, code_reason = _consume_log_clear_code_if_valid(request, confirmation_code)
    if not code_valid:
        message = 'Invalid confirmation code. Generate a fresh 10-digit code and retry.'
        error_code = 'invalid_confirmation_code'
        if code_reason == 'expired':
            message = 'Confirmation code expired. Generate a fresh 10-digit code and retry.'
            error_code = 'expired_confirmation_code'
        return JsonResponse(
            {
                'success': False,
                'message': message,
                'code': error_code,
            },
            status=400,
        )

    role = str(getattr(request.user, 'role', '') or '').strip().lower()
    now_iso = datetime.now(dt_timezone.utc).isoformat()
    guard_state = _load_log_clear_guard_state()

    if role == 'super_admin':
        next_state = {
            'status': 'pending_pro_user_confirmation',
            'requested_by_username': request.user.username or f'user:{request.user.pk}',
            'requested_by_role': 'super_admin',
            'requested_by_user_id': request.user.pk,
            'requested_at': now_iso,
            'last_completed_by': guard_state.get('last_completed_by', ''),
            'last_completed_at': guard_state.get('last_completed_at', ''),
            'last_deleted_count': guard_state.get('last_deleted_count', 0),
        }
        _save_log_clear_guard_state(next_state)
        return JsonResponse({
            'success': True,
            'pending_pro_user_confirmation': True,
            'message': 'Deletion request saved. Logs will be deleted only after Pro User confirms.',
            'state': next_state,
        })

    if role != 'pro_user':
        return JsonResponse({'success': False, 'message': 'Only Pro User can finalize log deletion.'}, status=403)

    if guard_state.get('status') != 'pending_pro_user_confirmation':
        return JsonResponse(
            {
                'success': False,
                'message': 'No pending admin request found. Ask Super Admin to initiate first.',
                'code': 'no_pending_request',
            },
            status=409,
        )

    try:
        deleted_count, archive_rel = _clear_activity_logs_with_archive(actor=request.user)
        completion_state = {
            'status': 'idle',
            'requested_by_username': '',
            'requested_by_role': '',
            'requested_by_user_id': None,
            'requested_at': '',
            'last_completed_by': request.user.username or f'user:{request.user.pk}',
            'last_completed_at': now_iso,
            'last_deleted_count': deleted_count,
        }
        _save_log_clear_guard_state(completion_state)
        logger.warning(
            'Activity logs cleared by pro_user=%s (id=%s), deleted=%s, archive=%s',
            request.user.username,
            request.user.pk,
            deleted_count,
            archive_rel,
        )
        return JsonResponse({
            'success': True,
            'deleted_count': deleted_count,
            'archive_relative_path': archive_rel,
            'message': f'Cleared {deleted_count} log entries. Archive saved to media/{archive_rel}.',
        })
    except Exception:
        logger.exception('Failed to clear activity logs via guarded flow')
        return JsonResponse({'success': False, 'message': 'Failed to clear logs.'}, status=500)


@require_http_methods(["GET"])
@login_required
def api_activity_log_clear_state(request):
    from core.services.permission_service import PermissionService

    if not _is_log_clear_actor(request.user):
        return JsonResponse({'success': False, 'message': 'Only Super Admin or Pro User can view this state.'}, status=403)

    if not _is_manual_log_clear_enabled():
        return JsonResponse(
            {
                'success': False,
                'message': 'Log deletion guard is disabled by server policy.',
                'code': 'log_clear_disabled',
            },
            status=403,
        )

    role = str(getattr(request.user, 'role', '') or '').strip().lower()
    state = _load_log_clear_guard_state()
    can_confirm = role == 'pro_user' and state.get('status') == 'pending_pro_user_confirmation'
    can_request = role in {'super_admin', 'pro_user'}
    return JsonResponse({
        'success': True,
        'state': state,
        'can_request': can_request,
        'can_confirm': can_confirm,
        'is_pro_user': role == 'pro_user',
        'is_super_admin': PermissionService.is_super_admin(request.user) and role != 'pro_user',
    })


@require_http_methods(["GET"])
@login_required
def api_activity_log_clear_generate_code(request):
    if not _is_log_clear_actor(request.user):
        return JsonResponse({'success': False, 'message': 'Only Super Admin or Pro User can generate code.'}, status=403)
    if not _is_manual_log_clear_enabled():
        return JsonResponse(
            {
                'success': False,
                'message': 'Log deletion guard is disabled by server policy.',
                'code': 'log_clear_disabled',
            },
            status=403,
        )
    code = _generate_ten_digit_code()
    _store_log_clear_code(request, code)
    return JsonResponse({'success': True, 'code': code})


@require_http_methods(["GET"])
@login_required
def api_server_info_snapshot(request):
    """
    Return a server snapshot for Manage Panel -> Server Info tab.
    Uses short-lived cache by default and recomputes when force_refresh=1.
    """
    from core.services.permission_service import PermissionService

    if not PermissionService.is_super_admin(request.user):
        return JsonResponse({'success': False, 'message': 'Super admin / pro user only'}, status=403)

    force_refresh = request.GET.get('force_refresh') == '1'
    if not force_refresh:
        cached = cache.get(_SERVER_INFO_CACHE_KEY)
        if not cached:
            from core.models import SystemSettings
            db_cached_raw = SystemSettings.get_value('panel_server_info_snapshot_persistent', default='')
            if db_cached_raw:
                try:
                    cached = json.loads(db_cached_raw)
                    cache.set(_SERVER_INFO_CACHE_KEY, cached, _SERVER_INFO_CACHE_TTL)
                except Exception:
                    cached = None
        if cached:
            return JsonResponse({
                'success': True,
                'cached': True,
                'cache_ttl_seconds': _SERVER_INFO_CACHE_TTL,
                'snapshot': cached,
            })

    base_dir = Path(settings.BASE_DIR)
    disk = shutil.disk_usage(str(base_dir))
    disk_used_pct = round((disk.used / disk.total) * 100, 1) if disk.total > 0 else 0

    tracked_labels = [
        ('Project Root', base_dir),
        ('venv', base_dir / 'venv'),
        ('.git', base_dir / '.git'),
        ('media', base_dir / 'media'),
        ('mediafiles', base_dir / 'mediafiles'),
        ('static', base_dir / 'static'),
        ('staticfiles', base_dir / 'staticfiles'),
        ('logs', base_dir / 'logs'),
        ('Face Cropper', base_dir / 'Face Cropper'),
        ('Face Cropper/build', base_dir / 'Face Cropper' / 'build'),
        ('Face Cropper/installer', base_dir / 'Face Cropper' / 'installer'),
        ('Face Cropper/logs', base_dir / 'Face Cropper' / 'logs'),
    ]

    path_usage_raw = []
    for label, path_obj in tracked_labels:
        if not path_obj.exists() or not path_obj.is_dir():
            continue
        size_bytes = _dir_size_fast(path_obj)
        path_usage_raw.append({
            'name': label,
            'size_bytes': size_bytes,
            'size_human': _format_bytes(size_bytes),
        })

    path_usage_raw.sort(key=lambda x: x['size_bytes'], reverse=True)
    path_usage = [p for p in path_usage_raw if p['name'] != 'Project Root']
    project_root_size = next((p['size_bytes'] for p in path_usage_raw if p['name'] == 'Project Root'), 0)

    db_info = _database_storage_snapshot(base_dir)
    db_size_bytes = int(db_info.get('size_bytes') or 0)
    db_backend = str(settings.DATABASES.get('default', {}).get('ENGINE', '')).lower()

    disk_used_nonfree = int(disk.used)
    known_used_bytes = max(project_root_size + db_size_bytes, 0)
    other_system_used = max(disk_used_nonfree - known_used_bytes, 0)

    usage_breakdown = [
        {
            'name': 'Project Files',
            'size_bytes': project_root_size,
            'size_human': _format_bytes(project_root_size),
        },
        {
            'name': 'Database',
            'size_bytes': db_size_bytes,
            'size_human': _format_bytes(db_size_bytes),
        },
        {
            'name': 'Other System Usage',
            'size_bytes': other_system_used,
            'size_human': _format_bytes(other_system_used),
        },
    ]

    tracked_total = sum(p['size_bytes'] for p in path_usage)
    for item in path_usage:
        item['pct_of_tracked'] = round((item['size_bytes'] / tracked_total) * 100, 1) if tracked_total > 0 else 0
        item['pct_of_disk'] = round((item['size_bytes'] / disk.total) * 100, 3) if disk.total > 0 else 0

    for item in usage_breakdown:
        item['pct_of_used_disk'] = round((item['size_bytes'] / disk_used_nonfree) * 100, 1) if disk_used_nonfree > 0 else 0
        item['pct_of_total_disk'] = round((item['size_bytes'] / disk.total) * 100, 2) if disk.total > 0 else 0

    usage_breakdown.sort(key=lambda x: x['size_bytes'], reverse=True)

    media_size_bytes = _size_for_label(path_usage_raw, 'media') + _size_for_label(path_usage_raw, 'mediafiles')
    logs_size_bytes = _size_for_label(path_usage_raw, 'logs') + _size_for_label(path_usage_raw, 'Face Cropper/logs')
    support_explicit_bytes = (
        _size_for_label(path_usage_raw, '.git')
        + _size_for_label(path_usage_raw, 'logs')
        + _size_for_label(path_usage_raw, 'Face Cropper/build')
        + _size_for_label(path_usage_raw, 'Face Cropper/installer')
        + _size_for_label(path_usage_raw, 'Face Cropper/logs')
    )

    dependency_bytes = _sum_existing_dirs([
        base_dir / 'venv',
        base_dir / '.venv',
        base_dir / 'env',
        base_dir / 'node_modules',
        base_dir / 'Face Cropper' / 'venv',
        base_dir / 'Face Cropper' / '.venv',
        base_dir / 'Face Cropper' / 'node_modules',
    ])

    core_project_bytes = max(project_root_size - media_size_bytes - dependency_bytes, 0)
    support_bytes = min(max(support_explicit_bytes, 0), core_project_bytes)
    project_files_without_media_bytes = max(core_project_bytes - support_bytes, 0)
    system_usage_details = [
        {
            'name': 'OS Usage',
            'size_bytes': int(other_system_used),
            'size_human': _format_bytes(other_system_used),
            'pct_of_used_disk': round((other_system_used / disk_used_nonfree) * 100, 1) if disk_used_nonfree > 0 else 0,
            'meta': 'Machine storage outside this project',
        },
        {
            'name': 'Project Dependencies Usage',
            'size_bytes': int(dependency_bytes),
            'size_human': _format_bytes(dependency_bytes),
            'pct_of_used_disk': round((dependency_bytes / disk_used_nonfree) * 100, 1) if disk_used_nonfree > 0 else 0,
            'meta': 'venv and installed dependency folders',
        },
        {
            'name': 'Project Files Usage',
            'size_bytes': int(project_files_without_media_bytes),
            'size_human': _format_bytes(project_files_without_media_bytes),
            'pct_of_used_disk': round((project_files_without_media_bytes / disk_used_nonfree) * 100, 1) if disk_used_nonfree > 0 else 0,
            'meta': 'Project files excluding images and videos',
        },
        {
            'name': 'Project Support Usage',
            'size_bytes': int(support_bytes),
            'size_human': _format_bytes(support_bytes),
            'pct_of_used_disk': round((support_bytes / disk_used_nonfree) * 100, 1) if disk_used_nonfree > 0 else 0,
            'meta': 'Git, logs, build and installer support files',
        },
    ]

    panel_usage_details = [
        {
            'name': 'Images Usage',
            'size_bytes': int(media_size_bytes),
            'size_human': _format_bytes(media_size_bytes),
            'pct_of_project': round((media_size_bytes / project_root_size) * 100, 1) if project_root_size > 0 else 0,
            'meta': 'Media and mediafiles storage',
        },
        {
            'name': 'Database Usage',
            'size_bytes': int(db_size_bytes),
            'size_human': _format_bytes(db_size_bytes),
            'pct_of_project': round((db_size_bytes / project_root_size) * 100, 1) if project_root_size > 0 else 0,
            'meta': 'Overall database size (Postgres/SQLite)',
        },
        {
            'name': 'Logs Usage',
            'size_bytes': int(logs_size_bytes),
            'size_human': _format_bytes(logs_size_bytes),
            'pct_of_project': round((logs_size_bytes / project_root_size) * 100, 1) if project_root_size > 0 else 0,
            'meta': 'Application and service logs',
        },
    ]

    other_breakdown = _other_usage_breakdown(
        base_dir=base_dir,
        other_total_bytes=other_system_used,
        project_total_bytes=project_root_size,
    )

    now = datetime.now(dt_timezone.utc)
    snapshot = {
        'fetched_at': now.isoformat(),
        'fetched_at_human': now.strftime('%d-%m-%Y %H:%M:%S UTC'),
        'host': socket.gethostname(),
        'platform': platform.platform(),
        'python_version': platform.python_version(),
        'cpu': {
            'logical_cores': os.cpu_count() or 0,
        },
        'memory': _memory_snapshot(),
        'storage': {
            'total_bytes': disk.total,
            'used_bytes': disk.used,
            'free_bytes': disk.free,
            'used_pct': disk_used_pct,
            'total_human': _format_bytes(disk.total),
            'used_human': _format_bytes(disk.used),
            'free_human': _format_bytes(disk.free),
            'tracked_total_bytes': tracked_total,
            'tracked_total_human': _format_bytes(tracked_total),
            'project_total_bytes': project_root_size,
            'project_total_human': _format_bytes(project_root_size),
            'database_total_bytes': db_size_bytes,
            'database_total_human': _format_bytes(db_size_bytes),
            'other_system_used_bytes': other_system_used,
            'other_system_used_human': _format_bytes(other_system_used),
        },
        'database': db_info,
        'usage_breakdown': usage_breakdown,
        'other_usage_breakdown': other_breakdown,
        'system_usage_details': system_usage_details,
        'panel_usage_details': panel_usage_details,
        'path_usage': path_usage,
    }

    cache.set(_SERVER_INFO_CACHE_KEY, snapshot, _SERVER_INFO_CACHE_TTL)

    # Save snapshot persistently to SystemSettings
    from core.models import SystemSettings
    try:
        SystemSettings.set_value(
            'panel_server_info_snapshot_persistent',
            json.dumps(snapshot, cls=DjangoJSONEncoder),
            description='Persistent cache of the last calculated server info snapshot.'
        )
    except Exception as exc:
        logger.exception("Failed to save server info snapshot to SystemSettings persistent cache")

    return JsonResponse({
        'success': True,
        'cached': False,
        'cache_ttl_seconds': _SERVER_INFO_CACHE_TTL,
        'snapshot': snapshot,
    })
