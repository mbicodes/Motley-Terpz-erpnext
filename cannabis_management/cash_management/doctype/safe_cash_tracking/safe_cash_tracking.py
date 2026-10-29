import frappe
from frappe.model.document import Document

from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
    INVOICE_REQUIRED_TYPES,
    get_person_for_user,
    validate_money_in_out,
)


class SafeCashTracking(Document):
    def validate(self):
        self.set_person_links()
        self.validate_safe_allowed()
        validate_money_in_out(self)
        if self.transaction_type in INVOICE_REQUIRED_TYPES and not self.invoice_number:
            frappe.throw(
                f"Invoice # (Sales Order) is required for '{self.transaction_type}' transactions."
            )

    def validate_safe_allowed(self):
        from cannabis_management.cash_management.permissions import (
            can_use_safe,
            person_allows_safe,
        )

        if person_allows_safe(self.cash_tracker_person):
            return

        if not self.cash_tracker_person and can_use_safe():
            return

        who = self.cash_tracker_person or frappe.session.user
        frappe.throw(
            f"{who} is not allowed to file Safe entries. "
            "Tick <b>Allow For Safe</b> on their Cash Tracker Person record first.",
            frappe.PermissionError,
            title="Not allowed for Safe",
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
