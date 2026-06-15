"""
Make Nikki Cash Ledger Entry and Nikki Expense Entry submittable so that
once saved (submitted), Nikki cannot edit or delete them.

What this script does:
  1. Enables is_submittable on both doctypes
  2. Moves the CLE/ETE creation scripts from After Insert → On Submit
  3. Adds lightweight After Insert scripts that immediately auto-submit the doc
  4. Updates DocPerms: Website Manager gets submit; Finance/Accounts get cancel
  5. Bulk-submits all existing draft (docstatus=0) NCLE and NEE entries

Run:
  bench --site stage.alltechvirtual.com execute cannabis_management.make_nikki_doctypes_submittable.run
"""
import frappe


AUTO_SUBMIT_SCRIPT = """\
try:
    if frappe.db.get_value(doc.doctype, doc.name, "docstatus") == 0:
        frappe.get_doc(doc.doctype, doc.name).submit()
except Exception as exc:
    frappe.log_error(str(exc), doc.doctype + " auto-submit error")
"""


def _set_submittable(doctype_name):
    frappe.db.set_value("DocType", doctype_name, "is_submittable", 1)
    print(f"  is_submittable = 1  →  {doctype_name}")


def _move_script_to_on_submit(script_name, doctype_name):
    if not frappe.db.exists("Server Script", script_name):
        print(f"  WARNING: script not found: {script_name}")
        return
    frappe.db.set_value("Server Script", script_name, "doctype_event", "On Submit")
    print(f"  Moved to On Submit: {script_name}")


def _ensure_auto_submit_script(name, ref_doctype):
    if frappe.db.exists("Server Script", name):
        doc = frappe.get_doc("Server Script", name)
        doc.script = AUTO_SUBMIT_SCRIPT
        doc.doctype_event = "After Insert"
        doc.disabled = 0
        doc.save(ignore_permissions=True)
        print(f"  Updated auto-submit script: {name}")
    else:
        doc = frappe.get_doc({
            "doctype":           "Server Script",
            "name":              name,
            "script_type":       "DocType Event",
            "reference_doctype": ref_doctype,
            "doctype_event":     "After Insert",
            "script":            AUTO_SUBMIT_SCRIPT,
            "disabled":          0,
        })
        doc.insert(ignore_permissions=True)
        print(f"  Created auto-submit script: {name}")


def _set_perm(doctype, role, **kwargs):
    row = frappe.db.get_value(
        "DocPerm",
        {"parent": doctype, "role": role, "permlevel": 0},
        "name"
    )
    if row:
        frappe.db.set_value("DocPerm", row, kwargs)
        print(f"  Updated perm  [{doctype}] {role}: {kwargs}")
    else:
        # Insert new perm row
        perm = frappe.get_doc({
            "doctype":    "DocPerm",
            "parent":     doctype,
            "parenttype": "DocType",
            "parentfield":"permissions",
            "permlevel":  0,
            "role":       role,
            **kwargs,
        })
        perm.insert(ignore_permissions=True)
        print(f"  Created perm  [{doctype}] {role}: {kwargs}")


def _bulk_submit_drafts(doctype):
    drafts = frappe.db.sql(
        f"SELECT name FROM `tab{doctype}` WHERE docstatus = 0",
        as_list=True
    )
    count = 0
    for row in drafts:
        name = row[0]
        try:
            frappe.get_doc(doctype, name).submit()
            count += 1
        except Exception as exc:
            print(f"  WARNING: could not submit {name}: {exc}")
    print(f"  Bulk-submitted {count}/{len(drafts)} draft(s) in {doctype}")


def run():
    frappe.set_user("Administrator")

    print("\n── 1. Enable is_submittable ──────────────────────────────────")
    _set_submittable("Nikki Cash Ledger Entry")
    _set_submittable("Nikki Expense Entry")
    frappe.db.commit()

    # Reload doctype metadata so submit() works immediately
    frappe.reload_doctype("Nikki Cash Ledger Entry")
    frappe.reload_doctype("Nikki Expense Entry")

    print("\n── 2. Move creation scripts to On Submit ─────────────────────")
    _move_script_to_on_submit("Nikki Cash → Cash Ledger Entry",     "Nikki Cash Ledger Entry")
    _move_script_to_on_submit("Nikki Expense → Expense Tracker Entry", "Nikki Expense Entry")
    frappe.db.commit()

    print("\n── 3. Add auto-submit After Insert scripts ───────────────────")
    _ensure_auto_submit_script("Nikki Cash → Auto Submit",    "Nikki Cash Ledger Entry")
    _ensure_auto_submit_script("Nikki Expense → Auto Submit", "Nikki Expense Entry")
    frappe.db.commit()

    print("\n── 4. Update role permissions ────────────────────────────────")
    for dt in ("Nikki Cash Ledger Entry", "Nikki Expense Entry"):
        # Website Manager (Nikki's role): can submit, cannot cancel or delete
        _set_perm(dt, "Website Manager",
                  read=1, write=1, create=1, submit=1, cancel=0, delete=0)
        # Finance Manager: can submit and cancel (to correct mistakes)
        _set_perm(dt, "Finance Manager",
                  read=1, write=1, create=1, submit=1, cancel=1, delete=0)
        # Accounts Manager: same as Finance
        _set_perm(dt, "Accounts Manager",
                  read=1, write=1, create=1, submit=1, cancel=1, delete=0)
        # System Manager: full access
        _set_perm(dt, "System Manager",
                  read=1, write=1, create=1, submit=1, cancel=1, delete=1)
    frappe.db.commit()

    print("\n── 5. Bulk-submit existing drafts ────────────────────────────")
    _bulk_submit_drafts("Nikki Cash Ledger Entry")
    _bulk_submit_drafts("Nikki Expense Entry")
    frappe.db.commit()

    print("\nDone. Run bench clear-cache to apply changes.")
