import frappe
from frappe.model.document import Document

# Shared with Motley Cash Tracking — identical money/person rules.
from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
    get_person_for_user,
    validate_money_in_out,
)

# Transaction types that must reference a Sales Order
INVOICE_REQUIRED_TYPES = (
    "Motley - Hardware",
    "Client - Hardware",
    "Client Payment Towards Invoice",
)


class TSBCCashTracking(Document):
    def validate(self):
        self.set_person_links()
        self.validate_tsbc_allowed()
        validate_money_in_out(self)
        if self.transaction_type in INVOICE_REQUIRED_TYPES and not self.invoice_number:
            frappe.throw(
                f"Invoice # (Sales Order) is required for '{self.transaction_type}' transactions."
            )

    def validate_tsbc_allowed(self):
        """Only people flagged "Allow For TSBC" on their Cash Tracker Person may
        file TSBC entries. Checked against the person ON THE DOCUMENT, not the
        session user, so an admin filing on someone's behalf still respects the
        flag. Cash admins filing for themselves are covered by can_use_tsbc.
        """
        from cannabis_management.cash_management.permissions import (
            can_use_tsbc,
            person_allows_tsbc,
        )

        if person_allows_tsbc(self.cash_tracker_person):
            return

        if not self.cash_tracker_person and can_use_tsbc():
            return

        who = self.cash_tracker_person or frappe.session.user
        frappe.throw(
            f"{who} is not allowed to file TSBC entries. "
            "Tick <b>Allow For TSBC</b> on their Cash Tracker Person record first.",
            frappe.PermissionError,
            title="Not allowed for TSBC",
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
