from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMStockReconciliation(StockReconciliation):
    def get_gl_entries(self, warehouse_account=None):
        gl_entries = super().get_gl_entries(warehouse_account=warehouse_account)
        return apply_item_group_mapping(self, gl_entries, warehouse_account)
