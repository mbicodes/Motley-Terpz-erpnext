import frappe
from frappe.model.document import Document


class NikkiCashLedgerEntry(Document):

    def validate(self):
        if self.amount and self.amount <= 0:
            frappe.throw("Amount must be greater than zero.")

    def before_save(self):
        if not self.submitted_by_user:
            self.submitted_by_user = frappe.session.user
