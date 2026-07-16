import frappe
from frappe.custom.doctype.property_setter.property_setter import make_property_setter


def execute():
    """
    Allow Purchase Invoice to be used as reference doctype in Auto Repeat.
    This ERPNext version ships Purchase Invoice with allow_auto_repeat = 0;
    a doctype-level Property Setter enables it without touching core.
    """
    make_property_setter(
        "Purchase Invoice",
        None,
        "allow_auto_repeat",
        1,
        "Check",
        for_doctype=True,
    )
    frappe.clear_cache(doctype="Purchase Invoice")
