from erpnext.stock.doctype.delivery_note.delivery_note import DeliveryNote
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMDeliveryNote(DeliveryNote):
    def get_gl_entries(self, warehouse_account=None, default_expense_account=None, default_cost_center=None):
        gl_entries = super().get_gl_entries(
            warehouse_account=warehouse_account,
            default_expense_account=default_expense_account,
            default_cost_center=default_cost_center,
        )
        return apply_item_group_mapping(self, gl_entries, warehouse_account)
