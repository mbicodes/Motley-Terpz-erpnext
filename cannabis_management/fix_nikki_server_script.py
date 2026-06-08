"""
Fix the Nikki Expense Server Script to properly create and submit the ETE.
Run: bench --site stage.alltechvirtual.com execute cannabis_management.fix_nikki_server_script.run
"""
import frappe


def _make_month_str(date_val):
    """Convert a date string or date object to 'Mon YYYY' string.
    Uses only sandbox-safe operations (no imports, no frappe.utils.getdate)."""
    MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
    s = str(date_val)[:10]  # "2026-06-08" or "2026-6-8"
    parts = s.split("-")
    year = parts[0]
    mon = MONTHS[int(parts[1]) - 1]
    return mon + " " + year


# Month helper inline (no function def allowed in Server Script top level? Use inline dict)
MONTH_SCRIPT_HELPER = """
_MONTHS = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
def _month_str(d):
    s = str(d)[:10]
    p = s.split("-")
    return _MONTHS[int(p[1]) - 1] + " " + p[0]
"""

EXPENSE_SCRIPT = """
# Nikki Expense Entry → Expense Tracker Entry (auto-submit)
# Fires: after_insert on Nikki Expense Entry
# Sandbox rules (RestrictedPython): no import/from, no underscore-prefixed names,
# no function definitions (closures break), no frappe.utils.getdate.
# Balance hooks omitted — Finance reviews and recalculates via ETE if needed.

try:
    # Re-load from DB to pick up any value the controller wrote via db_set
    existing_ete = frappe.db.get_value("Nikki Expense Entry", doc.name, "expense_tracker_entry")

    if existing_ete:
        # Controller created it — make sure it is submitted (docstatus=1)
        current_status = frappe.db.get_value("Expense Tracker Entry", existing_ete, "docstatus")
        if current_status == 0:
            frappe.db.set_value("Expense Tracker Entry", existing_ete, "docstatus", 1)
    else:
        # Controller failed or was skipped — create via db_insert() to bypass before_save
        direction = None
        amount = None
        if doc.money_out and float(doc.money_out) > 0:
            direction = "Expense"
            amount = float(doc.money_out)
        elif doc.money_in and float(doc.money_in) > 0:
            direction = "Reimbursement"
            amount = float(doc.money_in)

        if direction and amount:
            person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")

            # Inline month: "2026-06-08" -> "Jun 2026" (no import, no function def)
            date_s = str(doc.transaction_date)[:10]
            mon_num = int(date_s[5:7]) - 1
            mon_list = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
            month_val = mon_list[mon_num] + " " + date_s[:4]

            ete = frappe.new_doc("Expense Tracker Entry")
            ete.date = doc.transaction_date
            ete.month = month_val
            ete.direction = direction
            ete.amount = amount
            ete.receipt = doc.receipt or None
            ete.notes = ("[Web Form] Source: Nikki Expense Entry " + str(doc.name) + ". " + str(doc.transaction_notes or "")).strip()
            ete.company = doc.business or None
            ete.cash_tracker_person = person or None
            ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"
            ete.entity = doc.business or "Motley Terpz"

            ete.db_insert()
            frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
            frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)
        else:
            frappe.log_error(
                "No money_in or money_out on Nikki Expense Entry " + str(doc.name),
                "Nikki Expense to ETE: no amount"
            )
except Exception as exc:
    frappe.log_error(str(exc), "Nikki Expense to ETE: unexpected error")
"""

CASH_LEDGER_SCRIPT = """
# Nikki Cash Ledger Entry → Cash Ledger Entry (Finance-only draft)
# Fires: after_insert on Nikki Cash Ledger Entry
# Sandbox rules (RestrictedPython): no import/from, no function definitions (closures break).

try:
    existing = frappe.db.get_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry")
    if not existing:
        # Inline month: "2026-06-08" -> "Jun 2026" (no import, no function def)
        date_s = str(doc.date)[:10]
        mon_num = int(date_s[5:7]) - 1
        mon_list = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        month_val = mon_list[mon_num] + " " + date_s[:4]

        # Cash Tracker Person for the submitting user
        person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")

        # Map entity Select value to Company name ("LA Canna" differs from company "LA Canna Distro")
        entity_val = doc.entity or ""
        if entity_val == "LA Canna":
            company_val = "LA Canna Distro"
        elif entity_val:
            company_val = entity_val
        else:
            company_val = None

        cle = frappe.new_doc("Cash Ledger Entry")
        cle.date = doc.date
        cle.month = month_val
        cle.entity = doc.entity
        cle.transaction_type = doc.transaction_type
        cle.direction = doc.direction
        cle.amount = doc.amount
        cle.invoice_number = doc.invoice_number or None
        cle.receipt = doc.receipt or None
        cle.notes = ("[Web Form] Source: Nikki Cash Ledger Entry " + str(doc.name) + ". " + str(doc.notes or "")).strip()
        cle.cash_tracker_person = person or None
        cle.company = company_val
        cle.db_insert()
        frappe.db.set_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry", cle.name)
except Exception as exc:
    frappe.log_error(str(exc), "Nikki Cash to CLE: unexpected error")
"""


def run():
    frappe.set_user("Administrator")

    # Check Server Script columns
    cols = frappe.db.sql("SHOW COLUMNS FROM `tabServer Script`", as_dict=True)
    col_names = [c['Field'] for c in cols]
    print("Server Script columns:", col_names)

    # Get all Nikki server scripts
    scripts = frappe.db.sql(
        "SELECT name FROM `tabServer Script` WHERE name LIKE 'Nikki%'",
        as_dict=True
    )
    print("Existing Nikki Server Scripts:", [s.name for s in scripts])

    # Upsert the Expense script
    expense_script_name = "Nikki Expense → Expense Tracker Entry"
    if frappe.db.exists("Server Script", expense_script_name):
        ss = frappe.get_doc("Server Script", expense_script_name)
        ss.script = EXPENSE_SCRIPT.strip()
        ss.disabled = 0
        ss.save(ignore_permissions=True)
        print(f"Updated: {expense_script_name}")
    else:
        ss = frappe.get_doc({
            "doctype": "Server Script",
            "name": expense_script_name,
            "script_type": "DocType Event",
            "reference_doctype": "Nikki Expense Entry",
            "doctype_event": "After Insert",
            "disabled": 0,
            "script": EXPENSE_SCRIPT.strip(),
        })
        ss.insert(ignore_permissions=True)
        print(f"Created: {expense_script_name}")

    # Upsert the Cash Ledger script
    cash_script_name = "Nikki Cash → Cash Ledger Entry"
    if frappe.db.exists("Server Script", cash_script_name):
        ss2 = frappe.get_doc("Server Script", cash_script_name)
        ss2.script = CASH_LEDGER_SCRIPT.strip()
        ss2.disabled = 0
        ss2.save(ignore_permissions=True)
        print(f"Updated: {cash_script_name}")
    else:
        ss2 = frappe.get_doc({
            "doctype": "Server Script",
            "name": cash_script_name,
            "script_type": "DocType Event",
            "reference_doctype": "Nikki Cash Ledger Entry",
            "doctype_event": "After Insert",
            "disabled": 0,
            "script": CASH_LEDGER_SCRIPT.strip(),
        })
        ss2.insert(ignore_permissions=True)
        print(f"Created: {cash_script_name}")

    frappe.db.commit()
    print("\nDone. Run bench clear-cache to apply.")
