"""
License / METRC compliance flags (Feature 18).

Stores each customer's license number, license type and expiry date, and raises
a compliance WARNING (not a hard block) when a Quotation or Sales Order is built
for a customer whose license is expired or expiring within EXPIRY_WARN_DAYS.
"""

import frappe
from frappe import _
from frappe.utils import getdate, nowdate, date_diff

EXPIRY_WARN_DAYS = 30

# Common California cannabis license types — editable via the field's options.
LICENSE_TYPES = "\n".join([
    "", "Type 1 - Cultivation (Specialty Outdoor)", "Type 1A - Cultivation (Specialty Indoor)",
    "Type 2 - Cultivation (Small Outdoor)", "Type 3 - Cultivation (Outdoor)",
    "Type 5 - Cultivation (Large)", "Type 6 - Manufacturer (Non-volatile)",
    "Type 7 - Manufacturer (Volatile)", "Type 8 - Testing Laboratory",
    "Type 10 - Retailer", "Type 11 - Distributor", "Type 12 - Microbusiness",
    "Type N - Manufacturer (Infusions)", "Type P - Manufacturer (Packaging)",
    "Nursery", "Other",
])


def check_license(doc, method=None):
    """Warn (do not block) if the customer's license is expired / expiring soon."""
    customer = doc.get("customer")
    if not customer:
        return
    info = frappe.db.get_value(
        "Customer", customer,
        ["custom_license_number", "custom_license_type", "custom_license_expiry"],
        as_dict=True,
    )
    if not info or not info.custom_license_expiry:
        return

    today = getdate(nowdate())
    expiry = getdate(info.custom_license_expiry)
    days = date_diff(expiry, today)

    if days < 0:
        frappe.msgprint(
            _("⚠️ Compliance: {0}'s license ({1}) <b>EXPIRED</b> {2} day(s) ago ({3}).").format(
                customer, info.custom_license_type or "—", abs(days), expiry),
            title=_("License Expired"), indicator="red")
    elif days <= EXPIRY_WARN_DAYS:
        frappe.msgprint(
            _("⚠️ Compliance: {0}'s license ({1}) expires in {2} day(s) — on {3}.").format(
                customer, info.custom_license_type or "—", days, expiry),
            title=_("License Expiring Soon"), indicator="orange")


def install_license_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields({
        "Customer": [
            {"fieldname": "custom_compliance_section", "fieldtype": "Section Break",
             "label": "License / Compliance", "insert_after": "customer_group", "collapsible": 1},
            {"fieldname": "custom_license_number", "fieldtype": "Data", "label": "License Number",
             "insert_after": "custom_compliance_section"},
            {"fieldname": "custom_license_type", "fieldtype": "Select", "label": "License Type",
             "options": LICENSE_TYPES, "insert_after": "custom_license_number"},
            {"fieldname": "custom_col_break_compliance", "fieldtype": "Column Break",
             "insert_after": "custom_license_type"},
            {"fieldname": "custom_license_expiry", "fieldtype": "Date", "label": "License Expiry",
             "insert_after": "custom_col_break_compliance"},
        ]
    }, ignore_validate=True)
    frappe.db.commit()
