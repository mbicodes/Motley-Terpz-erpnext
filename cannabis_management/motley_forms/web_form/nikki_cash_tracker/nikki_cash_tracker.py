import frappe


def get_context(context):
    pass


def after_insert(doc, http_form_doc):
    """
    Auto-fill cash_tracker_person, company, employee and leave as Draft
    so Finance can review before submitting.
    """
    user = frappe.session.user

    person = frappe.db.get_value("Cash Tracker Person", {"user": user}, "name")
    if not person:
        frappe.log_error(
            title="Cash Web Form — No Cash Tracker Person",
            message=f"User {user} submitted a Cash Ledger Entry via web form "
                    f"but has no Cash Tracker Person record."
        )
        return

    employee = frappe.db.get_value("Cash Tracker Person", person, "employee")

    # Resolve company from entity
    entity_company_map = {
        "Motley Terpz":              "Motley Terpz",
        "TSBC Ranch":                "TSBC Ranch",
        "Master Touch Manufacturing": "Master Touch Manufacturing",
        "LA Canna":                  "Motley Terpz",
    }
    company = entity_company_map.get(doc.entity, "Motley Terpz")

    frappe.db.set_value("Cash Ledger Entry", doc.name, {
        "cash_tracker_person": person,
        "employee":            employee or None,
        "company":             company,
        "approval_status":     "Pending",
    })
