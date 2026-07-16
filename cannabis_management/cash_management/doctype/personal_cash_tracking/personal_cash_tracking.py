import frappe
from frappe.model.document import Document

from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
    validate_money_in_out,
)


class PersonalCashTracking(Document):
    def before_insert(self):
        self.set_person_links()

    def validate(self):
        self.set_person_links()
        validate_money_in_out(self)

    def set_person_links(self):
        if not self.cash_tracker_person:
            from cannabis_management.cash_management.doctype.motley_cash_tracking.motley_cash_tracking import (
                get_person_for_user,
            )
            self.cash_tracker_person = get_person_for_user(frappe.session.user)
        if self.cash_tracker_person:
            person = frappe.db.get_value(
                "Cash Tracker Person", self.cash_tracker_person, ["user", "employee"], as_dict=True
            )
            self.user = person.user
            self.employee = person.employee
        elif not self.user:
            self.user = frappe.session.user
