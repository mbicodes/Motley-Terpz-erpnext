import frappe
from frappe.model.document import Document
from frappe.utils import flt


class CreditApproval(Document):
    def on_submit(self):
        self.apply_credit_limit()

    def on_cancel(self):
        # Recompute the customer's limit from the remaining approved approvals.
        self.recompute_customer_limit()

    def apply_credit_limit(self):
        """Set the customer's Credit Limit. If this approval's amount exceeds the
        current limit, raise it accordingly."""
        current = flt(frappe.db.get_value("Customer", self.customer, "custom_credit_limit"))
        new_amount = flt(self.credit_amount)
        if new_amount and new_amount != current:
            frappe.db.set_value("Customer", self.customer, "custom_credit_limit", new_amount)
            frappe.msgprint(
                f"Credit Limit for {self.customer} set to {frappe.utils.fmt_money(new_amount)}.",
                alert=True,
            )

    def recompute_customer_limit(self):
        """After a cancellation, fall back to the highest remaining submitted approval
        (or 0 if none)."""
        rows = frappe.get_all(
            "Credit Approval",
            filters={"customer": self.customer, "docstatus": 1, "name": ["!=", self.name]},
            pluck="credit_amount",
        )
        frappe.db.set_value(
            "Customer", self.customer, "custom_credit_limit", max([flt(x) for x in rows], default=0)
        )
