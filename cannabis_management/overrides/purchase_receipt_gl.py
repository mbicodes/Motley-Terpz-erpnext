from erpnext.stock.doctype.purchase_receipt.purchase_receipt import PurchaseReceipt
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMPurchaseReceipt(PurchaseReceipt):
    def get_gl_entries(self, warehouse_account=None, via_landed_cost_voucher=False):
        gl_entries = super().get_gl_entries(
            warehouse_account=warehouse_account,
            via_landed_cost_voucher=via_landed_cost_voucher,
        )
        return apply_item_group_mapping(self, gl_entries, warehouse_account)
