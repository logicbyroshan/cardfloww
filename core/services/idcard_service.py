"""
IDCardService -- barrel re-export.

SINGLE AUTHORITY for IDCard / Table mutations.
Combines table, card, and bulk sub-services via MRO into one class
so all existing callers (IDCardService.method()) keep working.

Sub-modules:
  idcard_table_service.py  -- IDCardTableService (table CRUD, default group)
  idcard_card_service.py   -- IDCardCardService  (card CRUD, status, helpers)
  idcard_bulk_service.py   -- IDCardBulkService   (bulk ops, search, upgrade)
"""
from .idcard_table_service import IDCardTableService
from .idcard_card_service import IDCardCardService
from .idcard_bulk_service import IDCardBulkService


class IDCardService(IDCardTableService, IDCardCardService, IDCardBulkService):
    """Unified ID Card service -- combines table, card, and bulk operations via MRO."""
    pass
