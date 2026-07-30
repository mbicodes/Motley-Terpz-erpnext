import frappe
from frappe.model.document import Document
from frappe.utils import flt, add_days, getdate


class ARDispute(Document):
    def validate(self):
        self.disputed_total = sum(flt(r.disputed_amount) for r in self.invoices)
        if self.filed_date and not self.meeting_by:
            # +10 business days (approximate: 14 calendar days).
            self.meeting_by = add_days(getdate(self.filed_date), 14)
        if self.filed_date and not self.resolution_target:
            self.resolution_target = add_days(getdate(self.filed_date), 30)
        if not self.classified_by:
            self.classified_by = frappe.session.user


def disputed_total_for_customer(customer):
    """Sum of actively-disputed amounts (excluded from the credit line)."""
    rows = frappe.get_all(
        "AR Dispute",
        filters={"customer": customer, "status": ["in", ["Open", "Reconciling"]]},
        pluck="disputed_total",
    )
    return sum(flt(x) for x in rows)
