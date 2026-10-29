import frappe
from frappe import _
from frappe.utils import flt
from erpnext.stock import get_warehouse_account_map
from erpnext.stock.doctype.stock_entry.stock_entry import StockEntry, FinishedGoodError
from cannabis_management.overrides.warehouse_account_utils import apply_item_group_mapping


class CMStockEntry(StockEntry):
    def validate(self):
        self.apply_project_to_items()
        super().validate()

    def apply_project_to_items(self):
        if not self.project:
            return
        for d in self.get("items"):
            d.project = self.project
            d.batch = self.project
            if d.t_warehouse:
                d.to_batch = self.project

    def get_gl_entries(self, warehouse_account=None):
        if not warehouse_account:
            warehouse_account = get_warehouse_account_map(self.company)
        gl_entries = super().get_gl_entries(warehouse_account)
        return apply_item_group_mapping(self, gl_entries, warehouse_account)

    def set_total_incoming_outgoing_value(self):
        self.total_incoming_value = self.total_outgoing_value = 0.0
        for d in self.get("items"):
            if d.t_warehouse:
                self.total_incoming_value += flt(d.basic_amount)
            if d.s_warehouse:
                self.total_outgoing_value += flt(d.amount)
        self.value_difference = self.total_incoming_value - self.total_outgoing_value

    def validate_fg_completed_qty(self):
        if self.purpose != "Manufacture" or not self.work_order:
            return super().validate_fg_completed_qty()

        precision = frappe.get_precision("Stock Entry Detail", "qty")
        self.fg_completed_qty = flt(self.fg_completed_qty, precision)

        total_fg = flt(
            sum(flt(d.qty) for d in self.get("items") if d.is_finished_item),
            precision,
        )
        total = flt(total_fg + flt(self.process_loss_qty), precision)

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
        if not self.work_order:
            return super().validate_finished_goods()

        production_item = frappe.db.get_value("Work Order", self.work_order, "production_item")
        fg_items = [d for d in self.get("items") if d.is_finished_item]

        if all(d.item_code == production_item for d in fg_items):
            return super().validate_finished_goods()

        if not fg_items:
            frappe.throw(
                msg=_("There must be atleast 1 Finished Good in this Stock Entry"),
                title=_("Missing Finished Good"),
                exc=FinishedGoodError,
            )
