from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMStockEntry(StockEntry):
    def get_gl_entries(self, warehouse_account):
        gl_entries = super().get_gl_entries(warehouse_account)
        return apply_item_group_mapping(self, gl_entries, warehouse_account)
