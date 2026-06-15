import frappe
from frappe.model.document import Document


class ExpenseTrackerEntry(Document):

    def before_save(self):
        self._auto_fill_month()
        self._auto_fill_employee()
        self._validate_receipt_required()

    def validate(self):
        if self.amount and self.amount <= 0:
            frappe.throw("Amount must be greater than zero.")

    def _auto_fill_month(self):
        if self.date:
            from frappe.utils import getdate
            d = getdate(self.date)
            self.month = d.strftime("%b %Y")

    def _auto_fill_employee(self):
        if self.cash_tracker_person and not self.employee:
            emp = frappe.db.get_value(
                "Cash Tracker Person", self.cash_tracker_person, "employee"
            )
            if emp:
                self.employee = emp

    def _validate_receipt_required(self):
        if self.direction == "Expense" and not self.receipt:
            frappe.throw(
                "A receipt attachment is required for Expense entries. "
                "Please upload the receipt before saving."
            )
