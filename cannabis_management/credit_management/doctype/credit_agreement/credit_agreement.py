import frappe
from frappe.model.document import Document


class CreditAgreement(Document):
    def on_update(self):
        _sync_profile_flag(self.customer)

    def on_trash(self):
        _sync_profile_flag(self.customer)


def _sync_profile_flag(customer):
    """Credit Profile.agreement_on_file reflects whether a signed agreement exists."""
    has_signed = bool(frappe.db.exists("Credit Agreement", {"customer": customer, "signed": 1}))
    name = frappe.db.get_value("Credit Profile", {"customer": customer})
    if name and frappe.db.get_value("Credit Profile", name, "agreement_on_file") != int(has_signed):
        frappe.db.set_value("Credit Profile", name, "agreement_on_file", int(has_signed))
