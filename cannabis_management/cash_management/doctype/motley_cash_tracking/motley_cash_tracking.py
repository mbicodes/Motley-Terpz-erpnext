import frappe
from frappe.model.document import Document
from frappe.utils import flt

INVOICE_REQUIRED_TYPES = (
    "Motley - Hardware",
    "Client - Hardware",
    "Client Payment Towards Invoice",
)


class MotleyCashTracking(Document):
    def validate(self):
        self.set_person_links()
        self.validate_motley_allowed()
        validate_money_in_out(self)
        if self.transaction_type in INVOICE_REQUIRED_TYPES and not self.invoice_number:
            frappe.throw(
                f"Invoice # (Sales Order) is required for '{self.transaction_type}' transactions."
            )

    def validate_motley_allowed(self):
        from cannabis_management.cash_management.permissions import (
            can_use_motley,
            person_allows_motley,
        )

        if person_allows_motley(self.cash_tracker_person):
            return

        if not self.cash_tracker_person and can_use_motley():
            return

        who = self.cash_tracker_person or frappe.session.user
        frappe.throw(
            f"{who} is not allowed to file Motley entries. "
            "Tick <b>Allow For Motley</b> on their Cash Tracker Person record first.",
            frappe.PermissionError,
            title="Not allowed for Motley",
        )

    def set_person_links(self):
        if not self.cash_tracker_person:
            self.cash_tracker_person = get_person_for_user(frappe.session.user)
        if self.cash_tracker_person:
            person = frappe.db.get_value(
                "Cash Tracker Person", self.cash_tracker_person, ["user", "employee"], as_dict=True
            )
            self.user = person.user
            self.employee = person.employee


def get_person_for_user(user):
    return frappe.db.get_value("Cash Tracker Person", {"user": user, "is_active": 1}, "name")


def validate_money_in_out(doc):
    money_in, money_out = flt(doc.money_in), flt(doc.money_out)
    if money_in and money_out:
        frappe.throw("Fill only ONE of Money In or Money Out — not both.")
    if not money_in and not money_out:
        frappe.throw("Fill Money In (if you collected money) or Money Out (if you spent money).")
    if money_in < 0 or money_out < 0:
        frappe.throw("Amounts cannot be negative.")
