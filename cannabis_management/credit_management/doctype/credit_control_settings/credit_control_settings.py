import frappe
from frappe.model.document import Document


class CreditControlSettings(Document):
    pass


def get_settings():
    """Cached single doc."""
    return frappe.get_cached_doc("Credit Control Settings")
