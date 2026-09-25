import frappe
from frappe import _
from frappe.utils import flt
from erpnext.stock import get_warehouse_account_map
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry, FinishedGoodError
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMStockEntry(StockEntry):
    def get_gl_entries(self, warehouse_account=None):
        # ERPNext's StockEntry.get_gl_entries() declares warehouse_account as a required
        # positional arg, but Repost Accounting Ledger's preview (generate_preview_data)
        # calls doc.get_gl_entries() with no arguments for every voucher type except
        # Purchase Receipt -> TypeError. Default to None and let the map be resolved
        # from the company, exactly as StockController.get_gl_entries() does.
        if not warehouse_account:
            warehouse_account = get_warehouse_account_map(self.company)
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

    def validate_fg_completed_qty(self):
        # ERPNext's version iterates by item_code, so when multiple finished item codes
        # are present (e.g. PR-0037 + SP-0010), process_loss_qty gets set on the first
        # item and incorrectly double-counted on the second. Replace with a single-pass
        # check that sums ALL finished items and handles float rounding.
        if self.purpose != "Manufacture" or not self.work_order:
            return super().validate_fg_completed_qty()

        precision = frappe.get_precision("Stock Entry Detail", "qty")
        self.fg_completed_qty = flt(self.fg_completed_qty, precision)

        total_fg = flt(
            sum(flt(d.qty) for d in self.get("items") if d.is_finished_item),
            precision,
        )
        total = flt(total_fg + flt(self.process_loss_qty), precision)

        # A micron-based entry saved before the fix carries For Quantity equal
        # to the finished goods alone, with the Job Cards' loss on top of it.
        # For Quantity is output plus loss, so correct it rather than refuse.
        if self.process_loss_qty and self.fg_completed_qty == total_fg:
            self.fg_completed_qty = total

        if self.fg_completed_qty and total and self.fg_completed_qty != total:
            frappe.throw(
                _(
                    "Total finished goods quantity {0} plus process loss {1} ({2}) and For Quantity {3} cannot be different"
                ).format(
                    frappe.bold(total_fg),
                    frappe.bold(flt(self.process_loss_qty, precision)),
                    frappe.bold(total),
                    frappe.bold(self.fg_completed_qty),
                )
            )

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
