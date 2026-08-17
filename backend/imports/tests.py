"""
Test suite for CardFlow Imports App
Tests:
- Schema detection from headers
- Excel (.xlsx, .csv) reader
- Word (.docx) table reader
- Reupload matching engine
- ImportService table creation & bulk upload
"""
import io
import os
import tempfile
import zipfile
from django.test import TestCase
from django.contrib.auth import get_user_model

from tables.models import Table, IDCard
from organisation.models import Organisation
from imports.column_detector import detect_field_type, detect_table_schema_from_headers
from imports.excel_reader import parse_excel_or_csv
from imports.docx_reader import parse_docx_tables
from imports.services import ImportService
from imports.reupload_matcher import ReuploadMatcher, normalize_stem

User = get_user_model()


class ImportsAppTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            username='admin_import_test',
            email='import_test@example.com',
            password='testpassword123',
            role='super_admin',
        )
        self.org = Organisation.objects.create(name='Import Test Org')

    def test_column_detector(self):
        """Test intelligent column type detection."""
        self.assertEqual(detect_field_type('STUDENT PHOTO'), 'photo')
        self.assertEqual(detect_field_type('FATHER PIC'), 'father_photo')
        self.assertEqual(detect_field_type('MOTHER PHOTO'), 'mother_photo')
        self.assertEqual(detect_field_type('STUDENT SIGN'), 'sign')
        self.assertEqual(detect_field_type('DATE OF BIRTH'), 'date')
        self.assertEqual(detect_field_type('ROLL NO'), 'number')
        self.assertEqual(detect_field_type('STUDENT NAME'), 'text')

    def test_schema_generator(self):
        """Test full schema generator from headers."""
        headers = ['ROLL NO', 'FULL NAME', 'CLASS', 'SECTION', 'STUDENT PHOTO', 'DOB']
        schema = detect_table_schema_from_headers(headers)
        self.assertEqual(len(schema), 6)
        self.assertEqual(schema[0]['type'], 'number')
        self.assertEqual(schema[1]['type'], 'text')
        self.assertEqual(schema[4]['type'], 'photo')
        self.assertEqual(schema[5]['type'], 'date')

    def test_csv_parser(self):
        """Test CSV parsing."""
        csv_data = (
            "ROLL NO,NAME,CLASS,SECTION\n"
            "1,Aarav Sharma,10th,A\n"
            "2,Bhavik Patel,10th,B\n"
        ).encode('utf-8')

        parsed = parse_excel_or_csv(csv_data, 'students.csv')
        self.assertEqual(parsed.total_rows, 2)
        self.assertEqual(parsed.headers, ['ROLL NO', 'NAME', 'CLASS', 'SECTION'])
        self.assertEqual(parsed.rows[0][1], 'Aarav Sharma')

    def test_docx_table_parser(self):
        """Test Word .docx table reader."""
        from docx import Document
        doc = Document()
        table = doc.add_table(rows=3, cols=3)
        
        # Header
        table.cell(0, 0).text = "ROLL NO"
        table.cell(0, 1).text = "NAME"
        table.cell(0, 2).text = "CLASS"

        # Row 1
        table.cell(1, 0).text = "101"
        table.cell(1, 1).text = "Rahul Verma"
        table.cell(1, 2).text = "12th"

        # Row 2
        table.cell(2, 0).text = "102"
        table.cell(2, 1).text = "Sneha Roy"
        table.cell(2, 2).text = "12th"

        buf = io.BytesIO()
        doc.save(buf)
        docx_bytes = buf.getvalue()

        parsed = parse_docx_tables(docx_bytes)
        self.assertEqual(parsed.total_rows, 2)
        self.assertEqual(parsed.headers, ['ROLL NO', 'NAME', 'CLASS'])
        self.assertEqual(parsed.rows[0][1], 'Rahul Verma')
        self.assertEqual(parsed.rows[1][0], '102')

    def test_create_table_with_data_service(self):
        """Test table creation and card ingestion in single transaction."""
        csv_data = (
            "ROLL NO,NAME,CLASS,SECTION,MOBILE NO\n"
            "1,Aarav Sharma,10th,A,9876543210\n"
            "2,Bhavik Patel,10th,B,9876543211\n"
            "3,Chetan Gupta,9th,A,9876543212\n"
        ).encode('utf-8')

        result = ImportService.create_table_with_data(
            group_id=self.org.id,
            file_bytes=csv_data,
            filename='Class_10_Students.csv',
            table_name='Class 10 Batch',
            user=self.user,
        )

        self.assertTrue(result.success)
        self.assertEqual(result.cards_created, 3)

        # Verify created Table & Cards
        table = Table.objects.get(id=result.table_id)
        self.assertEqual(table.name, 'Class 10 Batch')
        self.assertEqual(IDCard.objects.filter(table=table).count(), 3)

    def test_reupload_matcher_by_roll_and_name(self):
        """Test ZIP photo matching against roll numbers and names."""
        # Create Table and Card
        table = Table.objects.create(
            organisation=self.org,
            name='Photo Match Table',
            fields=[
                {'name': 'ROLL NO', 'type': 'number'},
                {'name': 'FULL NAME', 'type': 'text'},
                {'name': 'PHOTO', 'type': 'photo'},
            ]
        )
        card1 = IDCard.objects.create(
            table=table,
            field_data={'ROLL NO': '101', 'FULL NAME': 'Rahul Sharma', 'PHOTO': ''},
            status='pending',
        )

        # Create mock ZIP with 101.jpg (1x1 transparent PNG)
        zip_buf = io.BytesIO()
        png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'
        
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            zf.writestr('101.png', png_bytes)
        zip_buf.seek(0)

        matcher = ReuploadMatcher(table)
        match_res = matcher.match_and_update_from_zip(zip_buf, target_field='PHOTO')

        self.assertEqual(match_res.matched_cards, 1)
        self.assertEqual(match_res.updated_photos, 1)

        card1.refresh_from_db()
        self.assertTrue(card1.field_data['PHOTO'].startswith('idcard_photos/'))

    def test_media_name_service_naming_and_parsing(self):
        """Test MediaNameService compact deterministic generation and parsing."""
        from mediafiles.services import MediaNameService

        # 1. Org code generation
        org_code = MediaNameService.get_org_code(self.org)
        self.assertTrue(len(org_code) >= 3)

        # 2. Derive deterministic image code
        code1 = MediaNameService.derive_image_code(card_id=42, field_name='PHOTO')
        code2 = MediaNameService.derive_image_code(card_id=42, field_name='PHOTO')
        code_father = MediaNameService.derive_image_code(card_id=42, field_name='FATHER_PHOTO')

        self.assertEqual(code1, code2)  # Deterministic!
        self.assertNotEqual(code1, code_father)  # Different field type has different code

        # 3. Generate media name
        name_v1 = MediaNameService.generate_media_name(org_code, code1, version=1, ext='.jpg')
        self.assertTrue(name_v1.startswith(f"O{org_code}_{code1}V1"))
        self.assertTrue(name_v1.endswith('.jpg'))

        # 4. Parse managed name
        parsed = MediaNameService.parse_media_name(name_v1)
        self.assertIsNotNone(parsed)
        self.assertTrue(parsed['is_managed'])
        self.assertEqual(parsed['org_code'], org_code)
        self.assertEqual(parsed['image_code'], code1)
        self.assertEqual(parsed['version'], 1)
        self.assertEqual(parsed['ext'], '.jpg')

        # 5. Check next version
        next_ver = MediaNameService.next_version(name_v1)
        self.assertEqual(next_ver, 2)

        name_v2 = MediaNameService.generate_media_name(org_code, code1, version=next_ver, ext='.jpg')
        self.assertTrue(name_v2.startswith(f"O{org_code}_{code1}V2"))

        # 6. Parse unmanaged raw name
        raw_parsed = MediaNameService.parse_media_name('IMG_20260817_123456.jpg')
        self.assertIsNone(raw_parsed)

    def test_dual_path_mixed_batch_reupload(self):
        """
        Benchmark & verify dual-path reupload handling of a mixed ZIP batch:
        - 3 foreign managed images (different org code) -> instantly rejected
        - 1 own managed image (re-upload of existing card) -> incremented to V2
        - 1 unmanaged raw image (matching Roll 202) -> matched and assigned V1
        - 1 random unmatched image -> recorded in unmatched_files
        """
        from mediafiles.services import MediaNameService

        table = Table.objects.create(
            organisation=self.org,
            name='Dual Path Table',
            fields=[
                {'name': 'ROLL NO', 'type': 'number'},
                {'name': 'FULL NAME', 'type': 'text'},
                {'name': 'PHOTO', 'type': 'photo'},
            ]
        )

        org_code = MediaNameService.get_org_code(self.org)
        card1_code = MediaNameService.derive_image_code(card_id=1, field_name='PHOTO')
        card1_v1_path = f"idcard_photos/{table.id}/O{org_code}_{card1_code}V1.jpg"

        # Card 1: Existing card with managed V1 photo
        card1 = IDCard.objects.create(
            table=table,
            field_data={'ROLL NO': '201', 'FULL NAME': 'Alice Smith', 'PHOTO': card1_v1_path},
            status='pending',
        )

        # Card 2: Existing card with no photo yet
        card2 = IDCard.objects.create(
            table=table,
            field_data={'ROLL NO': '202', 'FULL NAME': 'Bob Jones', 'PHOTO': ''},
            status='pending',
        )

        # Create 1x1 PNG bytes
        png_bytes = b'\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\rIDATx\x9cc`\x00\x00\x00\x02\x00\x01H\xaf\xa4q\x00\x00\x00\x00IEND\xaeB`\x82'

        # Build mixed ZIP
        zip_buf = io.BytesIO()
        with zipfile.ZipFile(zip_buf, 'w') as zf:
            # 1. Foreign org managed files (should be skipped cheaply)
            zf.writestr('OOTHER_XXXXV1.png', png_bytes)
            zf.writestr('O9999_YYYYV2.png', png_bytes)
            zf.writestr('OFOREIGN_ZZZZV1.png', png_bytes)

            # 2. Own managed file (re-upload for Card 1)
            zf.writestr(f"O{org_code}_{card1_code}V1.png", png_bytes)

            # 3. Unmanaged raw file matching Card 2 by Roll No
            zf.writestr('202.png', png_bytes)

            # 4. Unrelated random file
            zf.writestr('random_unrelated_photo.png', png_bytes)

        zip_buf.seek(0)

        matcher = ReuploadMatcher(table)
        res = matcher.match_and_update_from_zip(zip_buf, target_field='PHOTO')

        # Assertions
        self.assertEqual(res.matched_cards, 2)  # Card 1 (reupload) and Card 2 (new match)
        self.assertEqual(res.updated_photos, 2)
        self.assertIn('random_unrelated_photo.png', res.unmatched_files)
        # Foreign files should not be in unmatched (they were rejected in O(1) during scan)
        self.assertNotIn('OOTHER_XXXXV1.png', res.unmatched_files)

        # Check Card 1 was updated to V2
        card1.refresh_from_db()
        self.assertIn('V2', card1.field_data['PHOTO'])

        # Check Card 2 received a managed photo
        card2.refresh_from_db()
        self.assertTrue(card2.field_data['PHOTO'].startswith('idcard_photos/'))
        self.assertIn(f"O{org_code}_", card2.field_data['PHOTO'])

