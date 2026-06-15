import frappe
from frappe.model.document import Document
from frappe.utils import today


class CashLedgerEntry(Document):

    def before_save(self):
        self._auto_fill_month()
        self._auto_fill_employee()

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
