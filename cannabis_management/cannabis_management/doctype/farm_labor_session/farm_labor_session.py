# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, today

from cannabis_management.cannabis_management.doctype.farm_production_batch.farm_production_batch import (
    update_linked_harvest,
)


class FarmLaborSession(Document):

    def validate(self):
        self.calculate_totals()
        self.validate_warehouse_company()

    def calculate_totals(self):
        self.total_cost = flt(self.hours) * flt(self.labor_rate)

        if flt(self.hours) > 0:
            self.rate_per_hour = flt(self.units_completed) / flt(self.hours)
        else:
            self.rate_per_hour = 0

    def validate_warehouse_company(self):
        """Ensure target warehouse belongs to the selected company (Bucking only)."""
        if self.task_type == "Bucking" and self.company and self.target_warehouse:
            warehouse_company = frappe.db.get_value(
                "Warehouse", self.target_warehouse, "company"
            )
            if warehouse_company and warehouse_company != self.company:
                frappe.throw(
                    _("Target Warehouse {0} does not belong to Company {1}.").format(
                        frappe.bold(self.target_warehouse),
                        frappe.bold(self.company),
                    )
                )

    def on_submit(self):
        if self.task_type == "Bucking":
            self.create_bucking_stock_entry()
        update_linked_harvest(self)

    def create_bucking_stock_entry(self):
        """Bucking is the only task that produces a sellable stock item
        (packaged fresh-frozen flower). Planting and Deleaf never reach
        this code path."""

        if not self.bucked_item:
            frappe.throw(_("Bucked Item is required for Bucking sessions."))

        if not self.target_warehouse:
            frappe.throw(_("Target Warehouse is required for Bucking sessions."))

        if not self.company:
            frappe.throw(_("Company is required."))

        qty = flt(self.units_completed)
        if qty <= 0:
            frappe.throw(_("Units Completed must be greater than zero for Bucking sessions."))

        stock_entry = frappe.new_doc("Stock Entry")
        stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.company = self.company
        stock_entry.posting_date = self.session_date or today()

        stock_entry.append(
            "items",
            {
                "item_code": self.bucked_item,
                "qty": qty,
                "uom": self.weight_uom,
                "t_warehouse": self.target_warehouse,
            },
        )

        stock_entry.insert(ignore_permissions=True)
        # Left in draft — the harvested plant is METRC-tracked, not an
        # ERPNext stock item, so there is no matching source-side
        # transaction to submit against yet.

        self.db_set("stock_entry", stock_entry.name)

        frappe.msgprint(
            _("Stock Entry <b>{0}</b> created in draft.").format(stock_entry.name),
            alert=True,
        )
