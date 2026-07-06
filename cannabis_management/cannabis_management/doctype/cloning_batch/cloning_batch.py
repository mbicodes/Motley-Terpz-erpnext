# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, cint, today

from cannabis_management.cannabis_management.doctype.farm_production_batch.farm_production_batch import (
    update_linked_harvest,
)


class CloningBatch(Document):

    def validate(self):
        self.calculate_totals()
        self.validate_warehouse_company()

    def validate_warehouse_company(self):
        """Ensure target warehouse belongs to the selected company."""
        if self.company and self.target_warehouse:
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

    def calculate_totals(self):
        """Calculate totals from Clone Details only."""

        total_clone_quantity = 0

        for row in self.clone_details or []:
            total_clone_quantity += flt(row.quantity)

        self.total_clone_quantity = total_clone_quantity
        self.total_quantity = total_clone_quantity
        self.total_clones_produced = cint(total_clone_quantity)

        # Labour Cost
        self.total_labor_cost = flt(self.labour_hours) * flt(self.labour_rate)

        # Session Cost
        self.total_session_cost = flt(self.total_labor_cost)

        # Cost Per Clone
        if self.total_clones_produced:
            self.cost_per_clone = (
                self.total_session_cost / self.total_clones_produced
            )
        else:
            self.cost_per_clone = 0

    def on_submit(self):
        self.create_stock_entry()
        update_linked_harvest(self)

    def get_labor_expense_account(self):
        """Labor expense account (fixed)."""
        account_name = "Harvest Labor - TSBC"

        if not frappe.db.exists("Account", account_name):
            frappe.throw(
                _("Expense Account {0} not found. Please create it first.").format(
                    frappe.bold(account_name)
                )
            )

        return account_name

    def create_stock_entry(self):

        if not self.target_warehouse:
            frappe.throw(_("Target Warehouse is required."))

        if not self.company:
            frappe.throw(_("Company is required."))

        stock_entry = frappe.new_doc("Stock Entry")

        stock_entry.stock_entry_type = "Material Receipt"
        stock_entry.company = self.company
        stock_entry.posting_date = self.session_date or today()

        if self.batchproject:
            stock_entry.project = self.batchproject

        has_items = False

        # Clone Details table se items map karna
        for row in self.clone_details or []:

            if not row.clone_item:
                continue

            qty = flt(row.quantity)

            if qty <= 0:
                continue

            stock_entry.append(
                "items",
                {
                    "item_code": row.clone_item,
                    "qty": qty,
                    "t_warehouse": self.target_warehouse,
                },
            )

            has_items = True

        if not has_items:
            frappe.throw(_("Please add at least one Clone Detail."))

        # Labor cost ko Additional Costs table mein add karna
        if flt(self.total_labor_cost) > 0:
            stock_entry.append(
                "additional_costs",
                {
                    "expense_account": self.get_labor_expense_account(),
                    "description": "Labor Cost - Cloning Batch {0}".format(self.name),
                    "amount": flt(self.total_labor_cost),
                },
            )

        stock_entry.insert(ignore_permissions=True)
        stock_entry.submit()

        self.db_set("stock_entry", stock_entry.name)

        frappe.msgprint(
            _("Stock Entry <b>{0}</b> created successfully.").format(
                stock_entry.name
            ),
            alert=True,
        )