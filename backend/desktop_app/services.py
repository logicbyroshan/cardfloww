import hashlib
import json
import os
import re
import tempfile
import zipfile
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Dict, Iterable, List, Optional, Tuple

from django.conf import settings
from django.core.files.storage import default_storage
from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from organisation.models import Organisation
from core.services.base import BaseService
from tables.models import IDCard, Table, Table
from mediafiles.constants import IMAGE_FIELD_TYPES
from mediafiles.models import CardMedia
from mediafiles.services import ImageService

from .models import DesktopAppDevice

SAFE_MEDIA_PREFIXES = (
    'adarshimg/',
    'card_media/',
    'clients_imgs/',
    'staff_imgs/',
    'id_photos/',
    'temp/',
)


def _safe_text(value: Any, fallback: str = '') -> str:
    text = str(value or '').strip()
    return text if text else fallback


def _safe_segment(value: Any, fallback: str = 'item') -> str:
    text = _safe_text(value, fallback)
    text = re.sub(r'[^A-Za-z0-9._-]+', '_', text)
    text = re.sub(r'_+', '_', text).strip('._-')
    return text[:80] or fallback


def _normalize_media_path(raw_path: str) -> str:
    parts = []
    for part in str(raw_path or '').replace('\\', '/').split('/'):
        part = part.strip()
        if not part or part == '.':
            continue
        if part == '..':
            return ''
        parts.append(part)
    return '/'.join(parts)


@dataclass
class DesktopAuthResult:
    success: bool
    message: str = ''
    device: Optional[DesktopAppDevice] = None
    token: str = ''
    status_code: int = 200


class DesktopAppService:
    @staticmethod
    def _bootstrap_token() -> str:
        return _safe_text(getattr(settings, 'DESKTOP_APP_BOOTSTRAP_TOKEN', ''))

    @staticmethod
    def _max_connections() -> int:
        return int(getattr(settings, 'DESKTOP_APP_MAX_CONNECTIONS', 5) or 5)

    @staticmethod
    def _token_lifetime_seconds() -> int:
        return int(getattr(settings, 'DESKTOP_APP_TOKEN_MAX_AGE_SECONDS', 60 * 60 * 24 * 30) or 0)

    @classmethod
    def _token_expires_at(cls):
        seconds = cls._token_lifetime_seconds()
        if seconds <= 0:
            return None
        return timezone.now() + timedelta(seconds=seconds)

    @staticmethod
    def _hash_token(token: str) -> str:
        return hashlib.sha256(str(token or '').encode('utf-8')).hexdigest()

    @staticmethod
    def is_allowed_media_path(path: str) -> bool:
        normalized = _normalize_media_path(path)
        if not normalized:
            return False
        return normalized.startswith(SAFE_MEDIA_PREFIXES)

    @classmethod
    def register_device(
        cls,
        *,
        device_name: str,
        installation_id: str,
        bootstrap_token: str = '',
        allow_admin: bool = False,
        ip_address: str = '',
    ) -> DesktopAuthResult:
        if not getattr(settings, 'DESKTOP_APP_ENABLED', True):
            return DesktopAuthResult(False, 'Desktop API is disabled.', status_code=503)

        device_name = _safe_text(device_name, 'Desktop Device')
        installation_id = _safe_text(installation_id)
        if not installation_id:
            return DesktopAuthResult(False, 'installation_id is required.', status_code=400)

        expected_bootstrap = cls._bootstrap_token()
        if not expected_bootstrap:
            return DesktopAuthResult(False, 'Desktop bootstrap token is not configured.', status_code=503)
        if not allow_admin and bootstrap_token != expected_bootstrap:
            return DesktopAuthResult(False, 'Invalid desktop bootstrap token.', status_code=403)

        with transaction.atomic():
            existing = DesktopAppDevice.objects.select_for_update().filter(installation_id=installation_id).first()
            if existing and existing.is_active:
                raw_token = DesktopAppDevice.make_token()
                existing.device_name = device_name
                existing.token_hash = DesktopAppDevice.hash_token(raw_token)
                existing.token_prefix = raw_token[:12]
                existing.token_expires_at = cls._token_expires_at()
                existing.revoked_at = None
                if ip_address:
                    existing.last_ip_address = ip_address
                existing.save(update_fields=['device_name', 'token_hash', 'token_prefix', 'token_expires_at', 'revoked_at', 'last_ip_address', 'updated_at'])
                return DesktopAuthResult(True, 'Device token rotated.', device=existing, token=raw_token)

            active_count = DesktopAppDevice.objects.filter(is_active=True, revoked_at__isnull=True).count()
            if active_count >= cls._max_connections() and not existing:
                return DesktopAuthResult(False, 'Desktop connection limit reached.', status_code=403)

            raw_token = DesktopAppDevice.make_token()
            device = existing or DesktopAppDevice(installation_id=installation_id)
            device.device_name = device_name
            device.token_hash = DesktopAppDevice.hash_token(raw_token)
            device.token_prefix = raw_token[:12]
            device.is_active = True
            device.revoked_at = None
            device.last_ip_address = ip_address or None
            device.token_expires_at = cls._token_expires_at()
            device.save()
            return DesktopAuthResult(True, 'Device registered.', device=device, token=raw_token)

    @classmethod
    def authenticate_token(cls, token: str, *, installation_id: str = '', ip_address: str = '') -> DesktopAuthResult:
        if not getattr(settings, 'DESKTOP_APP_ENABLED', True):
            return DesktopAuthResult(False, 'Desktop API is disabled.', status_code=503)

        token = _safe_text(token)
        if not token:
            return DesktopAuthResult(False, 'Desktop token is required.', status_code=401)

        token_hash = cls._hash_token(token)
        device = DesktopAppDevice.objects.filter(token_hash=token_hash, is_active=True).first()
        if not device:
            return DesktopAuthResult(False, 'Invalid desktop token.', status_code=401)
        if installation_id and device.installation_id != installation_id:
            return DesktopAuthResult(False, 'Desktop installation mismatch.', status_code=403)
        if device.token_expires_at and device.token_expires_at <= timezone.now():
            device.revoke()
            return DesktopAuthResult(False, 'Desktop token expired.', status_code=401)

        device.touch(ip_address=ip_address)
        return DesktopAuthResult(True, 'Authenticated.', device=device)

    @classmethod
    def revoke_device(cls, *, installation_id: str = '', token: str = '') -> DesktopAuthResult:
        if installation_id:
            device = DesktopAppDevice.objects.filter(installation_id=installation_id).first()
        else:
            device = DesktopAppDevice.objects.filter(token_hash=cls._hash_token(token)).first()
        if not device:
            return DesktopAuthResult(False, 'Device not found.', status_code=404)
        device.revoke()
        return DesktopAuthResult(True, 'Device revoked.', device=device)

    @classmethod
    def _scope_objects(cls, *, client_id: Optional[int] = None, table_id: Optional[int] = None, search_query: Optional[str] = None, include_data: bool = True):
        if table_id:
            table = Table.objects.select_related('group', 'group__client').filter(id=table_id).first()
            if not table:
                return None
            client_id = table.group.client_id
            clients = Organisation.objects.filter(id=client_id).order_by('id')
            groups = Table.objects.select_related('client').filter(client_id=client_id).order_by('id')
            tables = Table.objects.select_related('group', 'group__client').filter(group__client_id=client_id).order_by('id')
            cards = IDCard.objects.select_related('table', 'table__group', 'table__group__client').filter(table_id=table.id, status__in=['approved', 'download']).order_by('-id') if include_data else IDCard.objects.none()
            return clients, groups, tables, cards

        clients = Organisation.objects.all().order_by('id')
        if search_query:
            clients = clients.filter(name__icontains=search_query)
        if client_id:
            clients = clients.filter(id=client_id)
            if not clients.exists():
                return None
        
        if not include_data:
            return clients, Table.objects.none(), Table.objects.none(), IDCard.objects.none()

        client_ids = list(clients.values_list('id', flat=True))
        groups = Table.objects.select_related('client').filter(client_id__in=client_ids).order_by('id')
        tables = Table.objects.select_related('group', 'group__client').filter(group__client_id__in=client_ids).order_by('id')
        table_ids = list(tables.values_list('id', flat=True))
        cards = IDCard.objects.select_related('table', 'table__group', 'table__group__client').filter(table_id__in=table_ids, status__in=['approved', 'download']).order_by('-id')
        return clients, groups, tables, cards

    @staticmethod
    def _serialize_client(organisation: Organisation) -> Dict[str, Any]:
        return {
            'id': Organisation.id,
            'name': Organisation.name,
            'status': Organisation.status,
            'is_guest': Organisation.is_guest,
            'image_folder_code': Organisation.image_folder_code,
            'image_folder_uuid': str(client.image_folder_uuid),
            'city': Organisation.city,
            'state': Organisation.state,
            'pincode': Organisation.pincode,
            'address': '',
            'created_at': Organisation.created_at.isoformat() if client.created_at else None,
            'updated_at': Organisation.updated_at.isoformat() if client.updated_at else None,
        }

    @staticmethod
    def _serialize_group(group: Table) -> Dict[str, Any]:
        return {
            'id': group.id,
            'client_id': group.client_id,
            'name': group.name,
            'description': group.description,
            'is_active': group.is_active,
            'created_at': group.created_at.isoformat() if group.created_at else None,
            'updated_at': group.updated_at.isoformat() if group.updated_at else None,
        }

    @staticmethod
    def _serialize_table(table: Table) -> Dict[str, Any]:
        image_fields = [field for field in (table.fields or []) if field.get('type') in IMAGE_FIELD_TYPES]
        return {
            'id': table.id,
            'group_id': table.group_id,
            'client_id': table.group.client_id if table.group_id else None,
            'name': table.name,
            'fields': table.fields,
            'image_fields': image_fields,
            'is_active': table.is_active,
            'deleted_by_client': table.deleted_by_client,
            'created_at': table.created_at.isoformat() if table.created_at else None,
            'updated_at': table.updated_at.isoformat() if table.updated_at else None,
        }

    @staticmethod
    def _image_paths_for_card(card: IDCard) -> List[Tuple[str, str]]:
        results: List[Tuple[str, str]] = []
        for field in card.table.fields or []:
            field_name = _safe_text(field.get('name'))
            if not field_name or field.get('type') not in IMAGE_FIELD_TYPES:
                continue
            path = ImageService.get_image_path_for_card(card, field_name, fallback_to_field_data=True)
            if path:
                results.append((field_name, path))
        return results

    @staticmethod
    def _serialize_card(card: IDCard) -> Dict[str, Any]:
        image_paths = {}
        for field_name, path in DesktopAppService._image_paths_for_card(card):
            image_paths[field_name] = path
        return {
            'id': card.id,
            'table_id': card.table_id,
            'group_id': card.table.group_id if card.table_id else None,
            'client_id': card.table.group.client_id if card.table_id else None,
            'status': card.status,
            'field_data': card.field_data,
            'image_paths': image_paths,
            'created_at': card.created_at.isoformat() if card.created_at else None,
            'updated_at': card.updated_at.isoformat() if card.updated_at else None,
        }

    @staticmethod
    def _download_url(request, file_path: str) -> str:
        return request.build_absolute_uri(
            reverse('desktop_app:download_original_file', kwargs={'file_path': file_path})
        ) if request else reverse('desktop_app:download_original_file', kwargs={'file_path': file_path})

    @staticmethod
    def _archive_path(client_id: Any, card_id: Any, field_name: Any, file_name: Any, *, legacy: bool = False) -> str:
        segments = ['original_images']
        if legacy:
            segments.append('legacy')
        segments.extend([
            f'client_{_safe_segment(client_id, "client")}',
            f'card_{_safe_segment(card_id, "card")}',
            _safe_segment(field_name, 'field'),
            _safe_segment(file_name, 'image'),
        ])
        return '/'.join(segments)

    @classmethod
    def _collect_media_entries(cls, cards: Iterable[IDCard], request=None) -> List[Dict[str, Any]]:
        card_list = list(cards)
        media_entries: List[Dict[str, Any]] = []
        seen_paths = set()
        card_ids = [card.id for card in card_list]
        media_qs = CardMedia.objects.select_related('card', 'group', 'client').filter(card_id__in=card_ids).order_by('id')
        for media in media_qs:
            path = _normalize_media_path(media.file.name if media.file else '')
            if not path or path in seen_paths:
                continue
            seen_paths.add(path)
            media_entries.append({
                'source': 'cardmedia',
                'id': media.id,
                'client_id': media.client_id,
                'group_id': media.group_id,
                'card_id': media.card_id,
                'table_id': media.card.table_id if media.card_id else None,
                'media_type': media.media_type,
                'field_name': media.field_name,
                'original_filename': media.original_filename,
                'file_path': path,
                'archive_path': cls._archive_path(media.client_id, media.card_id, media.field_name, media.original_filename or os.path.basename(path)),
                'download_url': cls._download_url(request, path),
                'exists': default_storage.exists(path),
            })

        for card in card_list:
            for field_name, path in cls._image_paths_for_card(card):
                normalized = _normalize_media_path(path)
                if not normalized or normalized in seen_paths:
                    continue
                seen_paths.add(normalized)
                media_entries.append({
                    'source': 'legacy-field',
                    'id': None,
                    'client_id': card.table.group.client_id,
                    'group_id': card.table.group_id,
                    'card_id': card.id,
                    'table_id': card.table_id,
                    'media_type': 'legacy',
                    'field_name': field_name,
                    'original_filename': os.path.basename(normalized),
                    'file_path': normalized,
                    'archive_path': cls._archive_path(card.table.group.client_id, card.id, field_name, os.path.basename(normalized), legacy=True),
                    'download_url': cls._download_url(request, normalized),
                    'exists': default_storage.exists(normalized),
                })
        return media_entries

    @classmethod
    def build_manifest(cls, *, client_id: Optional[int] = None, table_id: Optional[int] = None, search_query: Optional[str] = None, request=None, include_data: bool = True) -> Dict[str, Any]:
        scope = cls._scope_objects(client_id=client_id, table_id=table_id, search_query=search_query, include_data=include_data)
        if not scope:
            if table_id:
                return {'success': False, 'message': 'Table not found.'}
            if client_id:
                return {'success': False, 'message': 'Client not found.'}
            return {'success': False, 'message': 'No data found.'}

        clients, groups, tables, cards = scope
        
        if not include_data:
            cards = cards.none()
            
        media_entries = cls._collect_media_entries(cards, request=request)
        manifest = {
            'success': True,
            'generated_at': timezone.now().isoformat(),
            'scope': {'client_id': client_id, 'table_id': table_id},
            'summary': {
                'clients': clients.count(),
                'groups': groups.count(),
                'tables': tables.count(),
                'cards': cards.count(),
                'media_files': len(media_entries),
            },
            'clients': [cls._serialize_client(item) for item in clients],
            'groups': [cls._serialize_group(item) for item in groups],
            'tables': [cls._serialize_table(item) for item in tables],
            'cards': [cls._serialize_card(item) for item in cards],
            'media': media_entries,
        }
        return manifest

    @classmethod
    def build_archive(cls, *, client_id: Optional[int] = None, table_id: Optional[int] = None, request=None) -> Dict[str, Any]:
        manifest = cls.build_manifest(client_id=client_id, table_id=table_id, request=request)
        if not manifest.get('success'):
            return manifest

        temp_file = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode='w+b')
        archive_name = f'desktop_export_{timezone.now().strftime("%Y%m%d_%H%M%S")}.zip'

        with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('manifest.json', json.dumps(manifest, ensure_ascii=False, indent=2, default=str).encode('utf-8'))
            zip_file.writestr('clients.json', json.dumps(manifest['clients'], ensure_ascii=False, indent=2, default=str).encode('utf-8'))
            zip_file.writestr('groups.json', json.dumps(manifest['groups'], ensure_ascii=False, indent=2, default=str).encode('utf-8'))
            zip_file.writestr('tables.json', json.dumps(manifest['tables'], ensure_ascii=False, indent=2, default=str).encode('utf-8'))
            zip_file.writestr('cards.json', json.dumps(manifest['cards'], ensure_ascii=False, indent=2, default=str).encode('utf-8'))
            zip_file.writestr('media.json', json.dumps(manifest['media'], ensure_ascii=False, indent=2, default=str).encode('utf-8'))

            chunk_size = int(getattr(settings, 'DESKTOP_APP_DOWNLOAD_CHUNK_SIZE', 1024 * 1024) or 1024 * 1024)
            for item in manifest['media']:
                if not item.get('exists'):
                    continue
                file_path = item['file_path']
                if not cls.is_allowed_media_path(file_path):
                    continue
                try:
                    with default_storage.open(file_path, 'rb') as source:
                        with zip_file.open(item['archive_path'], 'w') as destination:
                            while True:
                                chunk = source.read(chunk_size)
                                if not chunk:
                                    break
                                destination.write(chunk)
                except Exception:
                    continue

        temp_file.seek(0)
        return {'success': True, 'archive': temp_file, 'filename': archive_name, 'manifest': manifest}

    @classmethod
    def build_images_zip(
        cls,
        *,
        client_id: Optional[int] = None,
        group_id: Optional[int] = None,
        table_id: Optional[int] = None,
        status: Optional[str] = None,
        request=None
    ) -> Dict[str, Any]:
        status = str(status or '').strip().lower()
        if status == 'approved':
            status_list = ['approved']
        elif status == 'download':
            status_list = ['download']
        else:
            status_list = ['approved', 'download']

        cards = IDCard.objects.select_related('table', 'table__group', 'table__group__client')
        
        if client_id:
            cards = cards.filter(table__group__client_id=client_id)
        if group_id:
            cards = cards.filter(table__group_id=group_id)
        if table_id:
            cards = cards.filter(table_id=table_id)
            
        cards = cards.filter(status__in=status_list).order_by('-id')
        
        media_entries = cls._collect_media_entries(cards, request=request)
        if not media_entries:
            return {'success': False, 'message': 'No images found for the specified filters.'}

        temp_file = tempfile.SpooledTemporaryFile(max_size=32 * 1024 * 1024, mode='w+b')
        archive_name = f'desktop_images_{timezone.now().strftime("%Y%m%d_%H%M%S")}.zip'

        with zipfile.ZipFile(temp_file, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            chunk_size = int(getattr(settings, 'DESKTOP_APP_DOWNLOAD_CHUNK_SIZE', 1024 * 1024) or 1024 * 1024)
            for item in media_entries:
                if not item.get('exists'):
                    continue
                file_path = item['file_path']
                if not cls.is_allowed_media_path(file_path):
                    continue
                try:
                    with default_storage.open(file_path, 'rb') as source:
                        with zip_file.open(item['archive_path'], 'w') as destination:
                            while True:
                                chunk = source.read(chunk_size)
                                if not chunk:
                                    break
                                destination.write(chunk)
                except Exception:
                    continue

        temp_file.seek(0)
        return {
            'success': True,
            'archive': temp_file,
            'filename': archive_name,
            'media_count': len(media_entries)
        }

    @classmethod
    def resolve_download_path(cls, file_path: str):
        normalized = _normalize_media_path(file_path)
        if not cls.is_allowed_media_path(normalized):
            return None
        if not default_storage.exists(normalized):
            return None
        return normalized
