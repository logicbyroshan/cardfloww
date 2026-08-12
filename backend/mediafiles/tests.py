"""
Tests for mediafiles app.
Covers: CardMedia model, ImageService basics.
"""
from types import SimpleNamespace
from unittest import mock

from django.test import TestCase
from django.contrib.auth import get_user_model

User = get_user_model()


def _create_test_card():
    """Create a client, group, table, and card for mediafiles testing."""
    user = User.objects.create_user(
        username='mfcl@test.com', email='mfcl@test.com',
        password='pass1234', role='client',
    )
    from organisation.models import Organisation
    client = Organisation.objects.create(user=user, name='Media Client')
    from tables.models import Table, IDCard
    group = Table.objects.create(client=client, name='MF Group')
    table = Table.objects.create(
        group=group, name='MF Table',
        fields=[
            {'name': 'NAME', 'type': 'text', 'order': 1},
            {'name': 'PHOTO', 'type': 'photo', 'order': 2},
        ],
    )
    card = IDCard.objects.create(
        table=table, field_data={'NAME': 'MEDIA TEST'}, status='pending',
    )
    return client, group, table, card


class CardMediaModelTests(TestCase):
    """Tests for CardMedia model."""

    def test_create_card_media(self):
        from mediafiles.models import CardMedia
        from django.core.files.uploadedfile import SimpleUploadedFile
        client, group, table, card = _create_test_card()

        # Create a minimal valid PNG
        png_bytes = (
            b'\x89PNG\r\n\x1a\n'
            b'\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01'
            b'\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx'
            b'\x9cc\xf8\x0f\x00\x00\x01\x01\x00\x05\x18\xd8N\x00'
            b'\x00\x00\x00IEND\xaeB`\x82'
        )
        image_file = SimpleUploadedFile('test.png', png_bytes, content_type='image/png')

        media = CardMedia.objects.create(
            card=card,
            client=client,
            file=image_file,
            media_type='photo',
            field_name='PHOTO',
            original_filename='test.png',
        )
        self.assertEqual(media.media_type, 'photo')
        self.assertEqual(media.card.id, card.id)
        self.assertEqual(media.client.id, client.id)
        self.assertTrue(media.file.name)

    def test_card_media_without_card(self):
        """Template images can have null card."""
        from mediafiles.models import CardMedia
        from django.core.files.uploadedfile import SimpleUploadedFile
        client, group, table, card = _create_test_card()

        png_bytes = b'\x89PNG\r\n\x1a\n' + b'\x00' * 50
        image_file = SimpleUploadedFile('template.png', png_bytes, content_type='image/png')

        media = CardMedia.objects.create(
            card=None,
            group=group,
            client=client,
            file=image_file,
            media_type='template_front',
        )
        self.assertIsNone(media.card)
        self.assertEqual(media.group.id, group.id)


class ImageServiceBasicTests(TestCase):
    """Basic tests for ImageService."""

    def test_validate_image_bytes_valid_png(self):
        from core.utils.field_utils import validate_image_bytes
        # Generate a valid PNG using PIL (100x100 to exceed 100-byte minimum)
        from io import BytesIO
        try:
            from PIL import Image
            buf = BytesIO()
            Image.new('RGB', (100, 100), color='red').save(buf, format='PNG')
            png_bytes = buf.getvalue()
            self.assertGreater(len(png_bytes), 100, 'PNG must exceed 100 bytes')
            is_valid, error_msg = validate_image_bytes(png_bytes)
            self.assertTrue(is_valid, f'validate_image_bytes failed: {error_msg}')
        except ImportError:
            self.skipTest('Pillow not installed')

    def test_validate_image_bytes_invalid(self):
        from core.utils.field_utils import validate_image_bytes
        is_valid, error_msg = validate_image_bytes(b'not an image')
        self.assertFalse(is_valid)

    def test_validate_image_bytes_empty(self):
        from core.utils.field_utils import validate_image_bytes
        is_valid, error_msg = validate_image_bytes(b'')
        self.assertFalse(is_valid)

    def test_save_new_image_normalizes_png_to_jpg(self):
        from io import BytesIO
        from PIL import Image
        from mediafiles.services import ImageService

        client_obj, _group, _table, _card = _create_test_card()
        buf = BytesIO()
        Image.new('RGB', (64, 64), color='blue').save(buf, format='PNG')
        png_bytes = buf.getvalue()

        result = ImageService.save_new_image(
            image_bytes=png_bytes,
            client=client_obj,
            field_name='PHOTO',
            original_ext='.png',
            batch_counter=1,
        )
        self.assertTrue(result.success, result.message)
        saved_path = result.data.get('final_value', '')
        self.assertTrue(saved_path.lower().endswith('.jpg'))

        # Keep media folder clean for subsequent tests.
        ImageService.delete_image(saved_path)


class UploadNormalizationTests(TestCase):

    def test_normalize_image_bytes_for_storage_compresses_large_phone_photo(self):
        from io import BytesIO
        from PIL import Image
        from mediafiles.utils import normalize_image_bytes_for_storage

        noise = Image.effect_noise((4200, 3200), 100).convert('RGB')
        buf = BytesIO()
        # Keep source intentionally large to exercise adaptive compression path.
        noise.save(buf, format='PNG', compress_level=0)
        source_bytes = buf.getvalue()

        normalized_bytes, normalized_ext, error = normalize_image_bytes_for_storage(
            source_bytes,
            suggested_ext='.png',
        )

        self.assertIsNone(error)
        self.assertEqual(normalized_ext, '.jpg')
        self.assertLess(len(normalized_bytes), len(source_bytes))

        with Image.open(BytesIO(normalized_bytes)) as out_img:
            self.assertLessEqual(max(out_img.size), 2400)

    def test_normalize_uploaded_image_converts_png_to_jpg(self):
        from io import BytesIO
        from PIL import Image
        from django.core.files.uploadedfile import SimpleUploadedFile
        from mediafiles.utils import normalize_uploaded_image

        buf = BytesIO()
        Image.new('RGB', (48, 48), color='green').save(buf, format='PNG')
        upload = SimpleUploadedFile('student.png', buf.getvalue(), content_type='image/png')

        normalized, error = normalize_uploaded_image(
            upload,
            max_bytes=5 * 1024 * 1024,
            allowed_extensions={'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'},
            allowed_mime_types={
                'image/jpeg', 'image/png', 'image/webp',
                'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
            },
        )

        self.assertIsNone(error)
        self.assertIsNotNone(normalized)
        self.assertEqual(normalized.name.lower(), 'student.jpg')
        self.assertEqual(normalized.content_type, 'image/jpeg')

    def test_normalize_uploaded_image_converts_heic_to_jpg(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from mediafiles.utils import normalize_uploaded_image

        fake_heic_upload = SimpleUploadedFile('iphone.heic', b'fake-heic-bytes', content_type='image/heic')
        converted_jpeg_bytes = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
            b'\xff\xd9'
        )

        with mock.patch(
            'mediafiles.utils.normalize_image_bytes_for_storage',
            return_value=(converted_jpeg_bytes, '.jpg', None),
        ):
            normalized, error = normalize_uploaded_image(
                fake_heic_upload,
                max_bytes=5 * 1024 * 1024,
                allowed_extensions={'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'},
                allowed_mime_types={
                    'image/jpeg', 'image/png', 'image/webp',
                    'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
                },
            )

        self.assertIsNone(error)
        self.assertIsNotNone(normalized)
        self.assertTrue(normalized.name.lower().endswith('.jpg'))
        self.assertEqual(normalized.content_type, 'image/jpeg')

    def test_normalize_uploaded_image_converts_hei_alias_to_jpg(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from mediafiles.utils import normalize_uploaded_image

        fake_hei_upload = SimpleUploadedFile('iphone.hei', b'fake-hei-bytes', content_type='image/heic')
        converted_jpeg_bytes = (
            b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x01\x00H\x00H\x00\x00'
            b'\xff\xd9'
        )

        with mock.patch(
            'mediafiles.utils.normalize_image_bytes_for_storage',
            return_value=(converted_jpeg_bytes, '.jpg', None),
        ):
            normalized, error = normalize_uploaded_image(
                fake_hei_upload,
                max_bytes=5 * 1024 * 1024,
                allowed_extensions={'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif', '.hei'},
                allowed_mime_types={
                    'image/jpeg', 'image/png', 'image/webp',
                    'image/heic', 'image/heif', 'image/heic-sequence', 'image/heif-sequence',
                },
            )

        self.assertIsNone(error)
        self.assertIsNotNone(normalized)
        self.assertTrue(normalized.name.lower().endswith('.jpg'))
        self.assertEqual(normalized.content_type, 'image/jpeg')


class CardMediaModelAdvancedTests(TestCase):
    def test_card_media_upload_path_sanitizes_parts(self):
        from mediafiles.models import card_media_upload_path

        instance = SimpleNamespace(client_id='12/../34', media_type='photo*bad')
        path = card_media_upload_path(instance, '../unsafe path/sample bad?.png')

        self.assertEqual(path, 'card_media/1234/photobad/sample_bad.png')

    def test_card_media_str_for_group_and_filename_property(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from mediafiles.models import CardMedia

        client, group, table, card = _create_test_card()

        image_file = SimpleUploadedFile(
            'template_front.png',
            b'\x89PNG\r\n\x1a\n' + b'\x00' * 200,
            content_type='image/png',
        )
        media = CardMedia.objects.create(
            group=group,
            client=client,
            file=image_file,
            media_type='template_front',
            original_filename='template_front.png',
        )

        self.assertIn('Group:', str(media))
        self.assertTrue(media.filename.startswith('template_front'))
        self.assertTrue(media.filename.endswith('.png'))
        self.assertTrue(media.url)

    def test_cleanup_cardmedia_file_skips_delete_when_path_is_shared(self):
        from mediafiles.models import CardMedia

        client, _group, _table, card = _create_test_card()
        shared_path = 'adarshimg/SHARED/shared.jpg'

        media_one = CardMedia.objects.create(
            card=card,
            client=client,
            file=shared_path,
            media_type='photo',
            field_name='PHOTO',
        )
        media_two = CardMedia.objects.create(
            card=card,
            client=client,
            file=shared_path,
            media_type='photo',
            field_name='MOTHER PHOTO',
        )

        with mock.patch.object(media_one.file.storage, 'exists', return_value=True), \
             mock.patch.object(media_one.file.storage, 'delete') as delete_mock, \
             mock.patch('mediafiles.services.image_thumbnail.ThumbnailService.delete_thumbnail'):
            media_one.delete()

        self.assertFalse(delete_mock.called)
        self.assertTrue(CardMedia.objects.filter(pk=media_two.pk).exists())


class ImageFieldsServiceTests(TestCase):
    def setUp(self):
        self.client_obj, self.group, self.table, self.card = _create_test_card()

    def test_is_image_field_detects_photo_and_not_designation(self):
        from mediafiles.services import ImageService

        self.assertTrue(ImageService.is_image_field({'name': 'Student Photo', 'type': 'text'}))
        self.assertFalse(ImageService.is_image_field({'name': 'Designation', 'type': 'text'}))

    def test_process_image_field_pending_and_unchanged_paths(self):
        from mediafiles.services import ImageService

        pending = ImageService.process_image_field(
            field_name='PHOTO',
            new_value='PENDING:roll_1.jpg',
            existing_value='',
            client=self.client_obj,
            card=self.card,
        )
        self.assertTrue(pending.success)
        self.assertEqual(pending.data['action'], 'pending')
        self.assertEqual(pending.data['final_value'], 'PENDING:roll_1.jpg')

        unchanged = ImageService.process_image_field(
            field_name='PHOTO',
            new_value='adarshimg/CODE/img.jpg',
            existing_value='adarshimg/CODE/img.jpg',
            client=self.client_obj,
            card=self.card,
        )
        self.assertTrue(unchanged.success)
        self.assertEqual(unchanged.data['action'], 'unchanged')

    def test_process_image_field_rewrite_and_missing(self):
        from mediafiles.services import ImageService

        with mock.patch('core.services.base.BaseService.validate_image_path', return_value=True):
            rewrite = ImageService.process_image_field(
                field_name='PHOTO',
                new_value='media/adarshimg/CODE/new.jpg',
                existing_value='adarshimg/CODE/old.jpg',
                client=self.client_obj,
                card=self.card,
            )
        self.assertTrue(rewrite.success)
        self.assertEqual(rewrite.data['action'], 'rewrite')
        self.assertEqual(rewrite.data['final_value'], 'adarshimg/CODE/new.jpg')

        with mock.patch('core.services.base.BaseService.validate_image_path', return_value=False):
            missing = ImageService.process_image_field(
                field_name='PHOTO',
                new_value='adarshimg/CODE/missing.jpg',
                existing_value='adarshimg/CODE/old.jpg',
                client=self.client_obj,
                card=self.card,
            )
        self.assertTrue(missing.success)
        self.assertEqual(missing.data['action'], 'missing')
        self.assertEqual(missing.data['final_value'], 'PENDING:missing.jpg')

    def test_process_image_field_upload_branch_calls_save_or_replace(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        from mediafiles.services import ImageService

        uploaded = SimpleUploadedFile('x.png', b'abc123' * 50, content_type='image/png')

        with mock.patch.object(
            ImageService,
            'save_new_image',
            return_value=ImageService.mark_pending('PHOTO', 'new.jpg'),
        ) as save_new:
            result = ImageService.process_image_field(
                field_name='PHOTO',
                new_value=None,
                existing_value='',
                client=self.client_obj,
                card=self.card,
                uploaded_file=uploaded,
            )
            self.assertTrue(result.success)
            self.assertEqual(save_new.call_count, 1)

        uploaded2 = SimpleUploadedFile('y.png', b'abc123' * 50, content_type='image/png')
        with mock.patch.object(
            ImageService,
            'replace_image',
            return_value=ImageService.mark_pending('PHOTO', 'updated.jpg'),
        ) as replace:
            result2 = ImageService.process_image_field(
                field_name='PHOTO',
                new_value=None,
                existing_value='adarshimg/OLD/path.jpg',
                client=self.client_obj,
                card=self.card,
                uploaded_file=uploaded2,
            )
            self.assertTrue(result2.success)
            self.assertEqual(replace.call_count, 1)

    def test_get_image_path_for_export_prefers_thumbnail_when_available(self):
        from mediafiles.services import ImageService

        self.card.field_data['PHOTO'] = 'adarshimg/CODE/original.jpg'
        self.card.save(update_fields=['field_data'])

        with mock.patch('mediafiles.services.image_fields.ThumbnailService.get_thumbnail_path', return_value='adarshimg/thumbs/CODE/original.webp'):
            with mock.patch('mediafiles.services.image_fields.default_storage.exists', return_value=True):
                got = ImageService.get_image_path_for_export(self.card, 'PHOTO', prefer_thumbnail=True)

        self.assertEqual(got, 'adarshimg/thumbs/CODE/original.webp')

    def test_get_image_path_for_card_blocks_unsafe_paths(self):
        from mediafiles.services import ImageService

        self.card.field_data['PHOTO'] = '../../secret.jpg'
        self.card.save(update_fields=['field_data'])

        got = ImageService.get_image_path_for_card(self.card, 'PHOTO')
        self.assertIsNone(got)


class MediafilesUtilsTests(TestCase):
    def test_generate_folder_code_from_name_variants(self):
        from mediafiles.utils import generate_folder_code_from_name

        self.assertEqual(generate_folder_code_from_name('Alpha Beta'), 'ALPBE')
        self.assertEqual(len(generate_folder_code_from_name('A')), 5)
        self.assertEqual(len(generate_folder_code_from_name('')), 5)

    def test_normalize_image_identifier_and_valid_path(self):
        from mediafiles.utils import normalize_image_identifier, is_valid_image_path

        self.assertEqual(normalize_image_identifier(' 001.0.JPG '), '1')
        self.assertTrue(is_valid_image_path('adarshimg/CODE/x.jpg'))
        self.assertFalse(is_valid_image_path('PENDING:x.jpg'))

    def test_get_card_photo_url_prefers_field_data_over_legacy_photo(self):
        from mediafiles.utils import get_card_photo_url

        class FakePhoto:
            url = '/media/id_photos/legacy.jpg'

        class FakeCard:
            def __init__(self):
                self.field_data = {'PHOTO': 'adarshimg/CODE/new.jpg'}
                self.photo = FakePhoto()

        url = get_card_photo_url(FakeCard())
        self.assertEqual(url, '/media/adarshimg/CODE/new.jpg')

    def test_get_card_photo_url_does_not_fall_back_after_explicit_removal(self):
        from mediafiles.utils import get_card_photo_url

        class FakePhoto:
            url = '/media/id_photos/legacy.jpg'

        class FakeCard:
            def __init__(self):
                self.field_data = {'PHOTO': ''}
                self.photo = FakePhoto()

        self.assertIsNone(get_card_photo_url(FakeCard()))

    def test_get_card_photo_url_handles_legacy_photo_url_errors(self):
        from mediafiles.utils import get_card_photo_url

        class BrokenPhoto:
            @property
            def url(self):
                raise ValueError('broken legacy url')

        class FakeCard:
            def __init__(self):
                self.field_data = {}
                self.photo = BrokenPhoto()

        self.assertIsNone(get_card_photo_url(FakeCard()))


class ThumbnailServiceTests(TestCase):
    def test_thumbnail_path_helpers(self):
        from mediafiles.services.image_thumbnail import ThumbnailService

        original = 'adarshimg/ABC/123.jpg'
        thumb = ThumbnailService.get_thumbnail_path(original)
        self.assertEqual(thumb, 'adarshimg/thumbs/ABC/123.webp')
        self.assertTrue(ThumbnailService.is_thumbnail_path(thumb))

    def test_generate_thumbnail_returns_bytes_for_valid_image(self):
        from io import BytesIO
        from mediafiles.services.image_thumbnail import ThumbnailService

        try:
            from PIL import Image
        except ImportError:
            self.skipTest('Pillow not installed')

        buf = BytesIO()
        Image.new('RGB', (200, 200), color='blue').save(buf, format='PNG')
        image_bytes = buf.getvalue()

        thumb = ThumbnailService.generate_thumbnail(image_bytes, original_size_bytes=len(image_bytes))
        self.assertIsNotNone(thumb)
        self.assertGreater(len(thumb), 50)


class MediafilesPathFallbackTests(TestCase):
    def test_get_image_path_for_card_returns_path_when_storage_check_errors(self):
        from mediafiles.services import ImageService

        _client, _group, _table, card = _create_test_card()
        card.field_data['PHOTO'] = 'adarshimg/CODE/original.jpg'
        card.save(update_fields=['field_data'])

        with mock.patch('mediafiles.services.image_fields.default_storage.exists', side_effect=RuntimeError('storage down')):
            got = ImageService.get_image_path_for_card(card, 'PHOTO')

        self.assertEqual(got, 'adarshimg/CODE/original.jpg')


class ThumbnailExistsCachingTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.client_obj, self.group, self.table, self.card = _create_test_card()
        self.card.field_data['PHOTO'] = 'adarshimg/CODE/original.jpg'
        self.card.save(update_fields=['field_data'])

    def tearDown(self):
        from django.core.cache import cache
        cache.clear()

    def test_get_image_path_for_export_caches_exists_lookup(self):
        from mediafiles.services import ImageService
        from django.core.cache import cache
        
        thumb_path = 'adarshimg/thumbs/CODE/original.webp'
        cache_key = f"thumb_exists:{thumb_path}"

        with mock.patch('mediafiles.services.image_fields.ThumbnailService.get_thumbnail_path', return_value=thumb_path):
            with mock.patch('mediafiles.services.image_fields.default_storage.exists', return_value=True) as mock_exists:
                # First call: cache miss, calls storage.exists
                got = ImageService.get_image_path_for_export(self.card, 'PHOTO', prefer_thumbnail=True)
                self.assertEqual(got, thumb_path)
                self.assertEqual(mock_exists.call_count, 1)
                self.assertTrue(cache.get(cache_key))

                # Second call: cache hit, should NOT call storage.exists
                got2 = ImageService.get_image_path_for_export(self.card, 'PHOTO', prefer_thumbnail=True)
                self.assertEqual(got2, thumb_path)
                self.assertEqual(mock_exists.call_count, 1)

    def test_delete_thumbnail_invalidates_cache(self):
        from mediafiles.services.image_thumbnail import ThumbnailService
        from django.core.cache import cache

        original = 'adarshimg/CODE/original.jpg'
        thumb_path = ThumbnailService.get_thumbnail_path(original)
        cache_key = f"thumb_exists:{thumb_path}"

        # Set in cache manually
        cache.set(cache_key, True, 86400)
        self.assertTrue(cache.get(cache_key))

        # Delete thumbnail
        with mock.patch('django.core.files.storage.default_storage.exists', return_value=True):
            with mock.patch('django.core.files.storage.default_storage.delete') as mock_delete:
                res = ThumbnailService.delete_thumbnail(original)
                self.assertTrue(res)
                self.assertTrue(mock_delete.called)

        # Cache key should be deleted/invalidated
        self.assertIsNone(cache.get(cache_key))


class ImageRenameAndHistoryPipelineTests(TestCase):
    """Tests for Image Rename format, Versioning, Undo/Redo stack, and 36-Hour Cleanup."""

    def test_image_renamer_format_and_parsing(self):
        from mediafiles.services.image_rename import ImageRenamer

        # Test initial filename generation for Admin ('a'), Client ('c'), Operator ('o')
        f_admin = ImageRenamer.generate_filename(upload_prefix='a', edit_count=0)
        f_client = ImageRenamer.generate_filename(upload_prefix='c', edit_count=0)
        f_op = ImageRenamer.generate_filename(upload_prefix='o', edit_count=0)

        self.assertTrue(f_admin.startswith('a0_'))
        self.assertTrue(f_client.startswith('c0_'))
        self.assertTrue(f_op.startswith('o0_'))

        # Parse test
        parsed = ImageRenamer.parse_filename('c0_14325101234501.jpg')
        self.assertIsNotNone(parsed)
        self.assertEqual(parsed['role'], 'c')
        self.assertEqual(parsed['edit_count'], 0)
        self.assertEqual(parsed['root_token'], '14325101234501')
        self.assertEqual(parsed['ext'], '.jpg')

        # Test update filename (increments counter and preserves root token)
        updated = ImageRenamer.generate_updated_filename('c0_14325101234501.jpg', upload_prefix='o')
        self.assertTrue(updated.startswith('o1_14325101234501'))

    def test_undo_redo_and_stale_warning_pipeline(self):
        from mediafiles.services.image_records import ImageRecordsMixin
        from mediafiles.models import CardMedia

        client, group, table, card = _create_test_card()
        field_name = 'PHOTO'

        # 1. Initial save (v0)
        rec0 = CardMedia.objects.create(
            card=card, client=client, file='card_media/c0_14325101234501.jpg',
            media_type='photo', field_name=field_name, root_token='14325101234501',
            version=0, last_edited_by_role='c', status='active'
        )

        # 2. Save new version (v1) -> v0 moves to undo_stack
        rec1 = CardMedia.objects.create(
            card=card, client=client, file='card_media/a1_14325101234501.jpg',
            media_type='photo', field_name=field_name, root_token='14325101234501',
            version=1, last_edited_by_role='a', status='active'
        )
        ImageRecordsMixin.update_history_stack_on_save(card, field_name, rec1)

        rec0.refresh_from_db()
        self.assertEqual(rec0.status, 'undo_stack')
        self.assertEqual(rec1.status, 'active')

        # 3. Test Stale Version Warning on v0 upload attempt
        warning = ImageRecordsMixin.check_old_version_warning(card, field_name, 'c0_14325101234501.jpg')
        self.assertIsNotNone(warning)
        self.assertFalse(warning['success'])
        self.assertEqual(warning['warning_code'], 'OLD_VERSION_DETECTED')

        # 4. Undo action (v1 active -> redo_stack, v0 undo_stack -> active)
        undo_res = ImageRecordsMixin.undo_image_version(card, field_name)
        self.assertTrue(undo_res['success'])
        rec0.refresh_from_db()
        rec1.refresh_from_db()
        self.assertEqual(rec0.status, 'active')
        self.assertEqual(rec1.status, 'redo_stack')

        # 5. Redo action (v0 active -> undo_stack, v1 redo_stack -> active)
        redo_res = ImageRecordsMixin.redo_image_version(card, field_name)
        self.assertTrue(redo_res['success'])
        rec0.refresh_from_db()
        rec1.refresh_from_db()
        self.assertEqual(rec0.status, 'undo_stack')
        self.assertEqual(rec1.status, 'active')

    def test_permanent_history_and_cleanup_command(self):
        from mediafiles.models import CardMedia
        from core.management.commands.cleanup_expired_history_images import cleanup_expired_history_images
        from django.utils import timezone
        from datetime import timedelta

        client, group, table, card = _create_test_card()
        old_time = timezone.now() - timedelta(hours=37)

        # Active record (preserved permanently)
        active_rec = CardMedia.objects.create(
            card=card, client=client, file='card_media/c1_10000000000001.jpg',
            media_type='photo', field_name='PHOTO', status='active'
        )

        # Undo stack record older than 36h (preserved permanently)
        undo_rec = CardMedia.objects.create(
            card=card, client=client, file='card_media/c0_10000000000001.jpg',
            media_type='photo', field_name='PHOTO', status='undo_stack'
        )

        # Expired record (purged by cleanup command)
        expired_rec = CardMedia.objects.create(
            card=card, client=client, file='card_media/c-1_10000000000001.jpg',
            media_type='photo', field_name='PHOTO', status='expired'
        )

        purged_count = cleanup_expired_history_images()
        self.assertEqual(purged_count, 1)

        active_rec.refresh_from_db()
        undo_rec.refresh_from_db()
        self.assertEqual(active_rec.status, 'active')
        self.assertEqual(undo_rec.status, 'undo_stack')

