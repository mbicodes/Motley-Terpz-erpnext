import frappe
from frappe.model.document import Document


class CreditExceptionLog(Document):
    def validate(self):
        if self.exception_type == "Freeze Exception" and not self.co_approved_by_ceo:
            frappe.throw("A Freeze Exception requires CEO co-approval (both CEO and MD).")

    def before_submit(self):
        # The approver must actually hold the MD role.
        if "Managing Director" not in frappe.get_roles(self.approved_by_md) \
                and self.approved_by_md != "Administrator":
            frappe.throw(f"{self.approved_by_md} does not hold the Managing Director role.")
