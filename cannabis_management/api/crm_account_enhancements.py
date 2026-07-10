"""
CRM Account Enhancements (sales-rep feedback, July 2026).

Three pieces, all requested by the sales team for cannabis-wholesale workflows:

1. install_crm_account_fields() — cannabis-specific account fields on
   CRM Lead / CRM Organization (License Name, License #, License Type,
   City, State, Credit Terms, Account Owner) plus side-panel layout so
   the fields are visible and editable in the CRM UI.

2. Duplicate account / ownership check — before a new CRM Lead or
   CRM Organization is saved, look for an existing lead/deal/organization
   with the same email, phone, license number or organization name and
   block with a message that names the current owner.

3. Post-won follow-up automation — when a CRM Deal moves to a "Won"-type
   status, auto-create CRM Tasks for the deal owner:
   7-day follow-up, 14-day reorder check-in, 30-day inactivity check.
"""

import re

import frappe
from frappe import _
from frappe.utils import add_days, nowdate

# Dropdown exactly as requested by the sales team (simpler than the
# California license codes used on Customer).
CRM_LICENSE_TYPES = "\n".join([
    "", "Storefront", "Non-storefront", "Distributor", "Manufacturer",
    "Cultivator", "Vertical", "Brand", "Other",
])


# ---------------------------------------------------------------------------
# 1. Account fields + side-panel layout
# ---------------------------------------------------------------------------

def install_crm_account_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    # CRM Lead — Address/City/State are Links (City & State are custom
    # doctypes in this app); License # is a Float per client request.
    lead_fields = [
        {"fieldname": "custom_license_section", "fieldtype": "Section Break",
         "label": "License & Compliance", "insert_after": "organization", "collapsible": 1},
        {"fieldname": "custom_license_name", "fieldtype": "Data",
         "label": "License Name / Organization", "insert_after": "custom_license_section",
         "description": "Legal licensed entity — may differ from the public-facing brand name"},
        {"fieldname": "custom_license_number", "fieldtype": "Float", "label": "License #",
         "precision": "0", "insert_after": "custom_license_name"},
        {"fieldname": "custom_license_type", "fieldtype": "Select", "label": "License Type",
         "options": CRM_LICENSE_TYPES, "insert_after": "custom_license_number"},
        {"fieldname": "custom_license_col_break", "fieldtype": "Column Break",
         "insert_after": "custom_license_type"},
        {"fieldname": "custom_address", "fieldtype": "Link", "options": "Address",
         "label": "Address", "insert_after": "custom_license_col_break"},
        {"fieldname": "custom_city", "fieldtype": "Link", "options": "City", "label": "City",
         "insert_after": "custom_address"},
        {"fieldname": "custom_state", "fieldtype": "Link", "options": "State", "label": "State",
         "insert_after": "custom_city"},
        {"fieldname": "custom_credit_terms", "fieldtype": "Data", "label": "Credit",
         "insert_after": "custom_state",
         "description": "e.g. COD, Net 15, Net 30, credit limit notes"},
    ]

    org_fields = [
        {"fieldname": "custom_license_section", "fieldtype": "Section Break",
         "label": "License & Compliance", "insert_after": "address", "collapsible": 1},
        {"fieldname": "custom_license_name", "fieldtype": "Data",
         "label": "License Name / Organization", "insert_after": "custom_license_section",
         "description": "Legal licensed entity — may differ from the public-facing brand name"},
        {"fieldname": "custom_license_number", "fieldtype": "Data", "label": "License #",
         "insert_after": "custom_license_name"},
        {"fieldname": "custom_license_type", "fieldtype": "Select", "label": "License Type",
         "options": CRM_LICENSE_TYPES, "insert_after": "custom_license_number"},
        {"fieldname": "custom_license_col_break", "fieldtype": "Column Break",
         "insert_after": "custom_license_type"},
        {"fieldname": "custom_city", "fieldtype": "Data", "label": "City",
         "insert_after": "custom_license_col_break"},
        {"fieldname": "custom_state", "fieldtype": "Data", "label": "State",
         "insert_after": "custom_city"},
        {"fieldname": "custom_credit_terms", "fieldtype": "Data", "label": "Credit",
         "insert_after": "custom_state",
         "description": "e.g. COD, Net 15, Net 30, credit limit notes"},
        {"fieldname": "custom_account_owner", "fieldtype": "Link", "options": "User",
         "label": "Account Owner", "insert_after": "custom_credit_terms"},
    ]

    create_custom_fields({
        "CRM Lead": lead_fields,
        "CRM Organization": org_fields,
    }, ignore_validate=True)

    _add_to_side_panel("CRM Lead", "details_section",
                       ["custom_license_name", "custom_license_number", "custom_license_type",
                        "custom_address", "custom_city", "custom_state"])
    _ensure_quick_entry_section(
        "CRM Lead", "license_location_section", "License & Location",
        [["custom_license_number", "custom_address", "custom_city"],
         ["custom_license_type", "custom_state"]])
    _add_to_side_panel("CRM Organization", "details_section",
                       ["custom_license_name", "custom_license_number", "custom_license_type",
                        "custom_city", "custom_state", "custom_credit_terms",
                        "custom_account_owner"])
    frappe.db.commit()


def _add_to_side_panel(doctype, section_name, fieldnames):
    """Append fields to an existing section of the doctype's Side Panel layout."""
    layout_name = frappe.db.exists("CRM Fields Layout", {"dt": doctype, "type": "Side Panel"})
    if not layout_name:
        return
    doc = frappe.get_doc("CRM Fields Layout", layout_name)
    layout = frappe.parse_json(doc.layout)
    for section in layout:
        if section.get("name") != section_name:
            continue
        columns = section.get("columns")
        fields = columns[0].setdefault("fields", []) if columns else section.setdefault("fields", [])
        for fieldname in fieldnames:
            if fieldname not in fields:
                fields.append(fieldname)
    doc.layout = frappe.as_json(layout, indent=None)
    doc.save(ignore_permissions=True)


def _ensure_quick_entry_section(doctype, section_name, label, column_fields):
    """Append a section (list of field-lists, one per column) to the doctype's
    Quick Entry layout — the Create dialog in the CRM UI."""
    layout_name = frappe.db.exists("CRM Fields Layout", {"dt": doctype, "type": "Quick Entry"})
    if not layout_name:
        return
    doc = frappe.get_doc("CRM Fields Layout", layout_name)
    layout = frappe.parse_json(doc.layout)

    # The layout is either a flat list of sections, or a list of tabs each
    # holding a "sections" list — append into the right level.
    has_tabs = any("sections" in entry for entry in layout)
    sections = layout[-1]["sections"] if has_tabs else layout
    if any(section.get("name") == section_name for section in sections):
        return
    sections.append({
        "label": label,
        "name": section_name,
        "opened": True,
        "columns": [
            {"name": f"column_{section_name}_{i}", "fields": fields}
            for i, fields in enumerate(column_fields)
        ],
    })
    doc.layout = frappe.as_json(layout, indent=None)
    doc.save(ignore_permissions=True)


# ---------------------------------------------------------------------------
# 2. Duplicate account / ownership check
# ---------------------------------------------------------------------------

def _digits(number):
    return re.sub(r"\D", "", number or "")[-10:]  # compare last 10 digits


def _license_key(value):
    """Normalize a license # for comparison — Float on CRM Lead,
    free text on CRM Organization / Customer."""
    s = str(value or "").strip()
    if not s:
        return ""
    try:
        f = float(s)
        return "" if f == 0 else ("%g" % f)
    except ValueError:
        return s.lower()


def _owner_label(user):
    if not user:
        return None
    return frappe.db.get_value("User", user, "full_name") or user


def _describe(matches):
    lines = []
    for m in matches:
        owner = _owner_label(m.get("owner_user"))
        owned = _(" — currently assigned to <b>{0}</b>").format(owner) if owner else ""
        lines.append(_("• {0} <b>{1}</b> (matched on {2}){3}").format(
            _(m["doctype"]), m["label"], m["matched_on"], owned))
    return "<br>".join(lines)


def check_lead_duplicate(doc, method=None):
    matches = _find_matches(
        organization=doc.organization,
        email=doc.email,
        phones=[doc.mobile_no, doc.phone],
        license_number=doc.get("custom_license_number"),
        exclude=("CRM Lead", doc.name),
    )
    if matches:
        frappe.throw(
            _("Possible duplicate account found:<br><br>{0}<br><br>"
              "This account may already exist. Please check with the assigned "
              "owner before creating a new record.").format(_describe(matches)),
            title=_("Possible Duplicate"),
        )


def check_organization_duplicate(doc, method=None):
    matches = _find_matches(
        organization=doc.organization_name,
        email=None,
        phones=[],
        license_number=doc.get("custom_license_number"),
        exclude=("CRM Organization", doc.name),
    )
    if matches:
        frappe.throw(
            _("Possible duplicate organization found:<br><br>{0}<br><br>"
              "This account may already exist. Please check with the assigned "
              "owner before creating a new record.").format(_describe(matches)),
            title=_("Possible Duplicate"),
        )


def _find_matches(organization, email, phones, license_number, exclude):
    matches, seen = [], set()

    def add(doctype, name, label, matched_on, owner_user):
        if (doctype, name) == exclude or (doctype, name) in seen:
            return
        seen.add((doctype, name))
        matches.append({"doctype": doctype, "label": label or name,
                        "matched_on": matched_on, "owner_user": owner_user})

    org = (organization or "").strip()
    license_key = _license_key(license_number)

    # -- CRM Lead candidates ------------------------------------------------
    or_filters = {}
    if org:
        or_filters["organization"] = org
    if email:
        or_filters["email"] = email.strip().lower()
    if license_key:
        or_filters["custom_license_number"] = license_number
    if or_filters:
        for row in frappe.get_all(
            "CRM Lead",
            or_filters=or_filters,
            fields=["name", "organization", "lead_name", "email",
                    "custom_license_number", "lead_owner"],
            limit=5,
        ):
            matched = []
            if org and (row.organization or "").strip().lower() == org.lower():
                matched.append(_("organization name"))
            if email and (row.email or "").strip().lower() == email.strip().lower():
                matched.append(_("email"))
            if license_key and _license_key(row.custom_license_number) == license_key:
                matched.append(_("license #"))
            add("CRM Lead", row.name, row.organization or row.lead_name,
                ", ".join(matched) or _("details"), row.lead_owner)

    # phone needs normalized comparison — pull only when a phone was given
    wanted = {p for p in (_digits(p) for p in phones) if len(p) >= 7}
    if wanted:
        for row in frappe.get_all(
            "CRM Lead",
            filters=[["mobile_no", "is", "set"]],
            fields=["name", "organization", "lead_name", "mobile_no", "phone", "lead_owner"],
            limit_page_length=0,
        ):
            if {_digits(row.mobile_no), _digits(row.phone)} & wanted:
                add("CRM Lead", row.name, row.organization or row.lead_name,
                    _("phone number"), row.lead_owner)

    # -- CRM Organization candidates -----------------------------------------
    or_filters = {}
    if org:
        or_filters["organization_name"] = org
    if license_key:
        or_filters["custom_license_number"] = license_key
    if or_filters:
        for row in frappe.get_all(
            "CRM Organization",
            or_filters=or_filters,
            fields=["name", "organization_name", "custom_license_number",
                    "custom_account_owner"],
            limit=5,
        ):
            matched = []
            if org and (row.organization_name or "").strip().lower() == org.lower():
                matched.append(_("organization name"))
            if license_key and _license_key(row.custom_license_number) == license_key:
                matched.append(_("license #"))
            add("CRM Organization", row.name, row.organization_name,
                ", ".join(matched) or _("details"), row.custom_account_owner)

    # -- CRM Deal candidates (existing customers) -----------------------------
    if org:
        for row in frappe.get_all(
            "CRM Deal",
            or_filters={"organization": org, "organization_name": org},
            fields=["name", "organization", "organization_name", "deal_owner"],
            limit=5,
        ):
            add("CRM Deal", row.name, row.organization or row.organization_name,
                _("organization name"), row.deal_owner)

    return matches


# ---------------------------------------------------------------------------
# 3. Post-won follow-up automation
# ---------------------------------------------------------------------------

FOLLOW_UP_PLAN = [
    (7, "7-day follow-up", "Thank-you + delivery/quality check-in after the won deal."),
    (14, "14-day reorder check-in", "Ask about sell-through and start the reorder conversation."),
    (30, "30-day reorder reminder", "No-reorder check — re-engage before the account goes inactive."),
]


def create_won_deal_followups(doc, method=None):
    """doc_event: CRM Deal on_update — fire once when status first becomes Won-type."""
    if not doc.status or doc.has_value_changed("status") is False:
        return
    status_type = frappe.db.get_value("CRM Deal Status", doc.status, "type")
    if status_type != "Won":
        return

    label = doc.organization or doc.get("organization_name") or doc.name
    for days, title, description in FOLLOW_UP_PLAN:
        full_title = f"{title} — {label}"
        if frappe.db.exists("CRM Task", {
            "reference_doctype": "CRM Deal",
            "reference_docname": doc.name,
            "title": full_title,
        }):
            continue
        frappe.get_doc({
            "doctype": "CRM Task",
            "title": full_title,
            "description": description,
            "assigned_to": doc.deal_owner or doc.owner,
            "due_date": add_days(nowdate(), days),
            "start_date": add_days(nowdate(), days),
            "priority": "Medium",
            "status": "Todo",
            "reference_doctype": "CRM Deal",
            "reference_docname": doc.name,
        }).insert(ignore_permissions=True)
