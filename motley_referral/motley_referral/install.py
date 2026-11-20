import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

ROLES = ("Referral Manager", "Referral Partner")


def after_install():
    setup()


def after_migrate():
    setup()


def setup():
    for r in ROLES:
        if not frappe.db.exists("Role", r):
            frappe.get_doc({"doctype": "Role", "role_name": r, "desk_access": 0 if r == "Referral Partner" else 1}).insert(ignore_permissions=True)
    create_custom_fields(
        {
            "Customer": [
                {"fieldname": "referral_section", "label": "Referral", "fieldtype": "Section Break", "insert_after": "tax_category", "collapsible": 1},
                {"fieldname": "referral_partner", "label": "Referral Partner", "fieldtype": "Link", "options": "Referral Partner",
                 "read_only": 1, "no_copy": 1, "insert_after": "referral_section", "search_index": 1},
                {"fieldname": "partner_referral", "label": "Partner Referral", "fieldtype": "Link", "options": "Partner Referral",
                 "read_only": 1, "no_copy": 1, "insert_after": "referral_partner", "search_index": 1},
            ]
        },
        ignore_validate=True,
    )
    if not frappe.db.exists("Supplier Group", "Referral Partners"):
        frappe.get_doc({"doctype": "Supplier Group", "supplier_group_name": "Referral Partners",
                        "parent_supplier_group": "All Supplier Groups"}).insert(ignore_permissions=True)
    ensure_templates()
    ensure_settings()
    from frappe.custom.doctype.property_setter.property_setter import make_property_setter

    for dt, pf in (("Referral Commission Statement", "Referral Commission Statement"), ("Partner Referral", "Partner Referral"), ("Referral Partner", "Referral Partner")):
        make_property_setter(dt, None, "default_print_format", pf, "Data", validate_fields_for_doctype=False)
    frappe.db.commit()


def ensure_templates():
    from motley_referral.notifications import default_templates

    s = frappe.get_doc("Referral Settings")
    changed = False
    for event, (field, subject, message) in default_templates().items():
        if s.get(field):
            continue
        name = f"Referral - {event.replace('_', ' ').title()}"
        if not frappe.db.exists("Email Template", name):
            frappe.get_doc({"doctype": "Email Template", "name": name, "subject": subject, "use_html": 1,
                            "response_html": message, "response": message}).insert(ignore_permissions=True)
        s.set(field, name)
        changed = True
    if changed:
        s.flags.ignore_mandatory = True
        s.save(ignore_permissions=True)


def ensure_settings():
    s = frappe.get_doc("Referral Settings")
    changed = False
    if not s.get("acknowledger_roles"):
        s.append("acknowledger_roles", {"role": "Referral Manager"})
        changed = True
    if changed:
        s.save(ignore_permissions=True)
