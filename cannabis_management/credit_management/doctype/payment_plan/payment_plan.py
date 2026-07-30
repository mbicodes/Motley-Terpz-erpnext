import frappe
from frappe.model.document import Document
from frappe.utils import flt, getdate, today


class PaymentPlan(Document):
    def validate(self):
        if self.status == "Active":
            if not (self.signed and self.finance_approved and self.md_ratified):
                frappe.throw("An Active plan must be signed, Finance-approved, and MD-ratified.")
        self.recovered_to_date = sum(
            flt(r.amount) for r in self.schedule if r.status == "Paid"
        )

    def on_update(self):
        _sync_plan_status_to_profile(self.customer)


def _sync_plan_status_to_profile(customer):
    """A customer with an Active plan shows status Payment Plan; a missed plan
    payment triggers a hold via the daily engine (see tasks.compute_hold)."""
    name = frappe.db.get_value("Credit Profile", {"customer": customer})
    if not name:
        return
    active = frappe.db.exists("Payment Plan", {"customer": customer, "status": "Active"})
    profile = frappe.get_doc("Credit Profile", name)
    if active and profile.status not in ("Payment Plan", "Workout"):
        profile.db_set("status", "Payment Plan")


def has_missed_plan_payment(customer):
    """True if any active plan has a due-and-unpaid or explicitly-missed row."""
    plans = frappe.get_all("Payment Plan", filters={"customer": customer, "status": "Active"}, pluck="name")
    tdy = getdate(today())
    for p in plans:
        for r in frappe.get_all("Payment Plan Schedule", filters={"parent": p}, fields=["due_date", "status"]):
            if r.status == "Missed":
                return True
            if r.status == "Due" and r.due_date and getdate(r.due_date) < tdy:
                return True
    return False
