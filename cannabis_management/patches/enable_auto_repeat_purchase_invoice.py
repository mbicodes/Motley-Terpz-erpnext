import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    make_property_setter(
        "Purchase Invoice",
        None,
        "allow_auto_repeat",
        1,
        "Check",
        for_doctype=True,
    )
    frappe.clear_cache(doctype="Purchase Invoice")
