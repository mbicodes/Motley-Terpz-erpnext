import frappe
from frappe.model.document import Document
from frappe.utils import flt


class OperatingComponent(Document):
    def validate(self):
        seen = set()
        for row in (self.accounts or []):
            if row.company in seen:
                frappe.throw(
                    f"Company <b>{row.company}</b> appears more than once in the Accounts table."
                )
            seen.add(row.company)


def validate_workstation(doc, method=None):
    if not hasattr(doc, "custom_operating_costs"):
        return

    total = 0.0
    for row in (doc.custom_operating_costs or []):
        total += flt(row.operating_cost)

    doc.custom_total_operating_cost = total
