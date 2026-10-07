from erpnext.stock.doctype.stock_reconciliation.stock_reconciliation import StockReconciliation
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMStockReconciliation(StockReconciliation):
    def validate(self):
        from cannabis_management.doc_hooks.stock_reconciliation import clear_superseded_tag_fields

        clear_superseded_tag_fields(self)
        super().validate()

    def validate_inventory_dimension(self):
        # Not a GL concern, but it has to live on the class to run in place of
        # core's own check. See doc_hooks/stock_reconciliation.resolve_tag_direction
        # for why a Source Tag on an upward adjustment is simply in the wrong box.
        from cannabis_management.doc_hooks.stock_reconciliation import resolve_tag_direction

        from cannabis_management.doc_hooks.stock_reconciliation import validate_reconcile_tags

        resolve_tag_direction(self)
        super().validate_inventory_dimension()
        # quantity_difference is set by now (set_total_qty_and_amount).
        validate_reconcile_tags(self)

    def get_gl_entries(self, warehouse_account=None):
        gl_entries = super().get_gl_entries(warehouse_account=warehouse_account)
        return apply_item_group_mapping(self, gl_entries, warehouse_account)
