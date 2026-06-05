import frappe
from frappe.model.document import Document
from frappe.utils import flt


class OperatingComponent(Document):
    def validate(self):
        # Ensure expense_account belongs to the selected company
        if self.expense_account and self.company:
            account_company = frappe.db.get_value("Account", self.expense_account, "company")
            if account_company and account_company != self.company:
                frappe.throw(
                    f"Expense Head <b>{self.expense_account}</b> does not belong to company "
                    f"<b>{self.company}</b>."
                )


# ── Workstation hook ──────────────────────────────────────────────────────────

def validate_workstation(doc, method=None):
    """
    Called on Workstation validate.
    1. Validates every Operating Component belongs to the same company as the Workstation.
    2. Sums all operating costs and writes to custom_total_operating_cost.
    """
    if not hasattr(doc, "custom_operating_costs"):
        return

    total = 0.0
    for row in (doc.custom_operating_costs or []):
        if not row.operating_component:
            continue

        comp_company = frappe.db.get_value(
            "Operating Component", row.operating_component, "company"
        )
        if comp_company and comp_company != doc.company:
            frappe.throw(
                f"Row {row.idx} — Operating Component <b>{row.operating_component}</b> "
                f"belongs to company <b>{comp_company}</b> but this Workstation "
                f"is under <b>{doc.company}</b>.",
                title="Company Mismatch"
            )

        total += flt(row.operating_cost)

    doc.custom_total_operating_cost = total
