import frappe
from frappe.model.document import Document

from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
    validate_money_in_out,
)


class PersonalCashTracking(Document):
    def before_insert(self):
        self.user = frappe.session.user

    def validate(self):
        validate_money_in_out(self)
