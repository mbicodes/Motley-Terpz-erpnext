import frappe
from frappe.model.document import Document
from frappe.utils import flt


class MotleyCashTracking(Document):
    def validate(self):
        validate_money_in_out(self)


def validate_money_in_out(doc):
    """Exactly one of Money In / Money Out must be filled, and be positive."""
    money_in, money_out = flt(doc.money_in), flt(doc.money_out)
    if money_in and money_out:
        frappe.throw("Fill only ONE of Money In or Money Out — not both.")
    if not money_in and not money_out:
        frappe.throw("Fill Money In (if you collected money) or Money Out (if you spent money).")
    if money_in < 0 or money_out < 0:
        frappe.throw("Amounts cannot be negative.")
