import frappe
from frappe import _
from frappe.utils import flt
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry, FinishedGoodError
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMStockEntry(StockEntry):
    def get_gl_entries(self, warehouse_account):
        gl_entries = super().get_gl_entries(warehouse_account)
        return apply_item_group_mapping(self, gl_entries, warehouse_account)

    def set_total_incoming_outgoing_value(self):
        """
        Total Incoming Value = sum of basic_amount for items going INTO a warehouse.
        Operating costs (additional_costs) are posted to GL separately and intentionally
        excluded from the stock-valuation incoming total.
        """
        self.total_incoming_value = self.total_outgoing_value = 0.0
        for d in self.get("items"):
            if d.t_warehouse:
                self.total_incoming_value += flt(d.basic_amount)
            if d.s_warehouse:
                self.total_outgoing_value += flt(d.amount)
        self.value_difference = self.total_incoming_value - self.total_outgoing_value

    def validate_finished_goods(self):
        # If no work order, or all FG items match the WO production item, use standard validation
        if not self.work_order:
            return super().validate_finished_goods()

        production_item = frappe.db.get_value("Work Order", self.work_order, "production_item")
        fg_items = [d for d in self.get("items") if d.is_finished_item]

        if all(d.item_code == production_item for d in fg_items):
            return super().validate_finished_goods()

        # Micron-based SE: FG items were substituted by populate_micron_finished_goods.
        # Skip item-code mismatch and multi-FG checks; only enforce that at least one FG exists.
        if not fg_items:
            frappe.throw(
                msg=_("There must be atleast 1 Finished Good in this Stock Entry"),
                title=_("Missing Finished Good"),
                exc=FinishedGoodError,
            )
