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

        if self.task_type == "Bucking":
            self.calculate_bucking_assembly_totals()

    def calculate_bucking_assembly_totals(self):
        """Distru-style Assembly rollup: cost from Ingredients + Additional
        Costs + labor, and Yield / Moisture Loss derived from Ingredient vs
        Output quantities."""

        total_ingredient_cost = sum(flt(row.cost) for row in self.ingredients)
        total_additional_cost = sum(flt(row.amount) for row in self.additional_costs)

        self.total_ingredient_cost = total_ingredient_cost
        self.total_additional_cost = total_additional_cost
        self.total_assembly_cost = (
            total_ingredient_cost + total_additional_cost + flt(self.hours) * flt(self.labor_rate)
        )

        qty_used = sum(flt(row.qty_used) for row in self.ingredients)
        qty_produced = sum(flt(row.qty_produced) for row in self.outputs)

        self.yield_pct = (qty_produced / qty_used * 100) if qty_used else 0
        self.moisture_loss_pct = ((qty_used - qty_produced) / qty_used * 100) if qty_used else 0

    def validate_warehouse_company(self):
        """Ensure every Ingredient/Output warehouse belongs to the selected
        company (Bucking only)."""
        if self.task_type != "Bucking" or not self.company:
            return

        for row in self.ingredients:
            self._check_warehouse_company(row.source_warehouse, "Source Warehouse")

        for row in self.outputs:
            self._check_warehouse_company(row.target_warehouse, "Target Warehouse")

    def _check_warehouse_company(self, warehouse, label):
        if not warehouse:
            return
        warehouse_company = frappe.db.get_value("Warehouse", warehouse, "company")
        if warehouse_company and warehouse_company != self.company:
            frappe.throw(
                _("{0} {1} does not belong to Company {2}.").format(
                    label,
                    frappe.bold(warehouse),
                    frappe.bold(self.company),
                )
            )

    def on_submit(self):
        if self.task_type == "Bucking":
            self.create_bucking_stock_entry()
        update_linked_harvest(self)

    def get_additional_cost_account(self, cost_type):
        """Resolve an expense account for a Bucking Additional Cost row.
        Prefers the Company's own 'Farm {cost_type} - ABBR' account (matches
        the farm companies' chart of accounts, e.g. 'Farm Equipment - TSBC');
        falls back to the Company's Stock Adjustment account when no such
        dedicated account exists (e.g. Packaging, Other)."""
        abbr = frappe.db.get_value("Company", self.company, "abbr")
        candidate = f"Farm {cost_type} - {abbr}" if abbr else None
        if candidate and frappe.db.exists("Account", candidate):
            return candidate
        return frappe.db.get_value("Company", self.company, "stock_adjustment_account")

    def create_bucking_stock_entry(self):
        """Bucking is the Assembly-style task: multiple harvested Ingredients
        consumed, multiple packaged Outputs produced. Planting and Deleaf
        never reach this code path."""

        if not self.ingredients:
            frappe.throw(_("At least one Ingredient row is required for Bucking sessions."))

        if not self.outputs:
            frappe.throw(_("At least one Output row is required for Bucking sessions."))

        if not self.company:
            frappe.throw(_("Company is required."))

        stock_entry = frappe.new_doc("Stock Entry")
        # Repack (not Manufacture) — per client instruction, this Assembly
        # is treated as a repack of harvested material into packaged
        # output, not a BOM/Work Order-backed manufacture.
        stock_entry.stock_entry_type = "Repack"
        stock_entry.company = self.company
        stock_entry.posting_date = self.session_date or today()

        for ing in self.ingredients:
            if flt(ing.qty_used) <= 0:
                frappe.throw(_("Qty Used must be greater than zero for every Ingredient row."))
            if not ing.source_warehouse:
                frappe.throw(_("Source Warehouse is required for every Ingredient row."))

            stock_entry.append(
                "items",
                {
                    "item_code": ing.source_item,
                    "qty": flt(ing.qty_used),
                    "uom": ing.uom,
                    "s_warehouse": ing.source_warehouse,
                    "is_finished_item": 0,
                },
            )

        for out in self.outputs:
            if flt(out.qty_produced) <= 0:
                frappe.throw(_("Qty Produced must be greater than zero for every Output row."))
            if not out.target_warehouse:
                frappe.throw(_("Target Warehouse is required for every Output row."))

            stock_entry.append(
                "items",
                {
                    "item_code": out.output_item,
                    "qty": flt(out.qty_produced),
                    "uom": out.uom,
                    "t_warehouse": out.target_warehouse,
                    "is_finished_item": 1,
                },
            )

        # Additional Costs (Bucking Additional Cost table) → Stock Entry's
        # own Additional Costs table, so Packaging/Equipment/Other charges
        # actually land on the finished-good valuation instead of being
        # calculated on the session but dropped on the floor.
        missing_account = False
        for cost in self.additional_costs:
            amount = flt(cost.amount)
            if amount <= 0:
                continue

            expense_account = self.get_additional_cost_account(cost.cost_type or "Other")
            if not expense_account:
                missing_account = True

            stock_entry.append(
                "additional_costs",
                {
                    "expense_account": expense_account,
                    "description": cost.description or cost.cost_type or _("Additional Cost"),
                    "amount": amount,
                },
            )

        stock_entry.insert(ignore_permissions=True)
        # Left in draft — same pattern as before, not auto-submitted. The
        # harvested plant is METRC-tracked, not an ERPNext stock item, so
        # there is no matching source-side transaction to submit against yet.

        if missing_account:
            frappe.msgprint(
                _(
                    "Could not find an expense account for one or more Additional Cost rows. "
                    "Please set an Expense Account on Stock Entry {0} before submitting it, "
                    "or set a Stock Adjustment Account on Company {1}."
                ).format(frappe.bold(stock_entry.name), frappe.bold(self.company)),
                alert=True,
                indicator="orange",
            )

        self.db_set("stock_entry", stock_entry.name)

        frappe.msgprint(
            _("Stock Entry <b>{0}</b> created in draft.").format(stock_entry.name),
            alert=True,
        )
