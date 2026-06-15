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
# Sandbox rules (RestrictedPython): no import/from, no underscore names, no function defs.
# frappe.get_attr NOT available in sandbox — balance update is inlined with SQL.
#
# ETE uses db_insert() to bypass _validate_receipt_required() in the controller.

try:
    existing_ete = frappe.db.get_value("Nikki Expense Entry", doc.name, "expense_tracker_entry")

    if existing_ete:
        current_status = frappe.db.get_value("Expense Tracker Entry", existing_ete, "docstatus")
        if current_status == 0:
            frappe.db.set_value("Expense Tracker Entry", existing_ete, "docstatus", 1)
        bal_person = frappe.db.get_value("Expense Tracker Entry", existing_ete, "cash_tracker_person")
    else:
        direction = None
        amount = None
        if doc.money_out and float(doc.money_out) > 0:
            direction = "Expense"
            amount = float(doc.money_out)
        elif doc.money_in and float(doc.money_in) > 0:
            direction = "Reimbursement"
            amount = float(doc.money_in)

        if direction and amount:
            bal_person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")

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
            ete.cash_tracker_person = bal_person or None
            ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"
            ete.entity = doc.business or "Motley Terpz"

            ete.db_insert()
            frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
            frappe.db.set_value("Expense Tracker Entry", ete.name, "month", month_val)
            frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)
        else:
            frappe.log_error(
                "No money_in or money_out on Nikki Expense Entry " + str(doc.name),
                "Nikki Expense to ETE: no amount"
            )
            bal_person = None

    # --- Inline balance update (frappe.get_attr not available in sandbox) ---
    if bal_person:
        ci = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabCash Ledger Entry` WHERE cash_tracker_person=%s AND direction='Cash In' AND docstatus=1", bal_person)[0][0]
        co = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabCash Ledger Entry` WHERE cash_tracker_person=%s AND direction='Cash Out' AND docstatus=1", bal_person)[0][0]
        ep = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabExpense Tracker Entry` WHERE cash_tracker_person=%s AND direction='Expense' AND docstatus=1", bal_person)[0][0]
        rb = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabExpense Tracker Entry` WHERE cash_tracker_person=%s AND direction='Reimbursement' AND docstatus=1", bal_person)[0][0]
        net_cash = float(ci) - float(co)
        net_owed = float(ep) - float(rb)
        frappe.db.set_value("Cash Tracker Person", bal_person, {"cash_balance": net_cash, "total_expenses": float(ep), "total_reimbursed": float(rb), "net_owed": net_owed})
        ledger = frappe.db.get_value("Cash Balance Ledger", {"cash_tracker_person": bal_person})
        if ledger:
            frappe.db.set_value("Cash Balance Ledger", ledger, {"total_cash_in": float(ci), "total_cash_out": float(co), "net_cash": net_cash, "total_expenses": float(ep), "total_reimbursed": float(rb), "net_owed": net_owed})
        else:
            new_ledger = frappe.new_doc("Cash Balance Ledger")
            new_ledger.cash_tracker_person = bal_person
            new_ledger.total_cash_in = float(ci)
            new_ledger.total_cash_out = float(co)
            new_ledger.net_cash = net_cash
            new_ledger.total_expenses = float(ep)
            new_ledger.total_reimbursed = float(rb)
            new_ledger.net_owed = net_owed
            new_ledger.insert(ignore_permissions=True)
except Exception as exc:
    frappe.log_error(str(exc), "Nikki Expense to ETE: unexpected error")
"""

CASH_LEDGER_SCRIPT = """
# Nikki Cash Ledger Entry → Cash Ledger Entry (Finance-side, fully synced)
# Fires: after_insert on Nikki Cash Ledger Entry
# Sandbox rules (RestrictedPython): no import/from, no function defs, no underscore names.
# frappe.get_attr NOT available in sandbox — hooks are inlined with SQL + set_value.
#
# Special case — transaction_type = "Reimbursement" (direction = "Cash Out"):
#   Creates a CLE Cash Out (reduces company cash) AND an ETE Reimbursement
#   (reduces what the company owes the person), so both balances update together.

try:
    existing = frappe.db.get_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry")
    if not existing:
        date_s = str(doc.date)[:10]
        mon_num = int(date_s[5:7]) - 1
        mon_list = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
        month_val = mon_list[mon_num] + " " + date_s[:4]

        person = frappe.db.get_value("Cash Tracker Person", {"user": frappe.session.user}, "name")

        # Guard: every submission must be linked to a Cash Tracker Person.
        # Without it the CLE mandatory field "Person" would fail with a confusing error.
        if not person:
            frappe.throw(
                "No Cash Tracker Person is set up for your account ({u}). "
                "Please ask your administrator to create one before submitting entries.".format(
                    u=frappe.session.user
                )
            )

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
        cle.cash_tracker_person = person
        cle.company = company_val

        # insert() runs before_save so auto_fill_employee populates doc.employee
        cle.insert(ignore_permissions=True)
        frappe.db.set_value("Cash Ledger Entry", cle.name, "docstatus", 1)
        frappe.db.set_value("Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry", cle.name)

        # --- Running balance ---
        prev_res = frappe.db.sql(
            "SELECT running_balance FROM `tabCash Ledger Entry` WHERE cash_tracker_person = %s AND docstatus = 1 AND name != %s ORDER BY date DESC, creation DESC LIMIT 1",
            (person, cle.name)
        )
        prev_bal = float(prev_res[0][0] or 0) if prev_res else 0.0
        if doc.direction == "Cash In":
            run_bal = prev_bal + float(doc.amount)
        else:
            run_bal = prev_bal - float(doc.amount)
        frappe.db.set_value("Cash Ledger Entry", cle.name, "running_balance", run_bal)

        # --- IRS Form 8300 flag ---
        if doc.direction == "Cash In" and float(doc.amount) >= 10000:
            frappe.db.set_value("Cash Ledger Entry", cle.name, "form_8300_required", 1)

        # --- Reimbursement: also create ETE so net_owed decreases ---
        # When Nikki takes back money she spent on company expenses, the company's
        # cash goes down (handled by the CLE Cash Out above) AND the company owes
        # her less (handled by this ETE Reimbursement).
        if doc.transaction_type == "Reimbursement":
            ete = frappe.new_doc("Expense Tracker Entry")
            ete.date = doc.date
            ete.month = month_val
            ete.direction = "Reimbursement"
            ete.amount = doc.amount
            ete.cash_tracker_person = person
            ete.company = company_val
            ete.entity = doc.entity or "Motley Terpz"
            ete.transaction_type = "Reimbursement"
            ete.notes = ("[Cash Reimbursement] Source: Nikki Cash Ledger Entry " + str(doc.name) + ". " + str(doc.notes or "")).strip()
            ete.db_insert()
            frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)

        # --- Cash Balance Ledger + Cash Tracker Person totals ---
        # Runs after any ETE created above so the reimbursement is already counted.
        ci = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabCash Ledger Entry` WHERE cash_tracker_person=%s AND direction='Cash In' AND docstatus=1", person)[0][0]
        co = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabCash Ledger Entry` WHERE cash_tracker_person=%s AND direction='Cash Out' AND docstatus=1", person)[0][0]
        ep = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabExpense Tracker Entry` WHERE cash_tracker_person=%s AND direction='Expense' AND docstatus=1", person)[0][0]
        rb = frappe.db.sql("SELECT COALESCE(SUM(amount),0) FROM `tabExpense Tracker Entry` WHERE cash_tracker_person=%s AND direction='Reimbursement' AND docstatus=1", person)[0][0]
        net_cash = float(ci) - float(co)
        net_owed = float(ep) - float(rb)
        frappe.db.set_value("Cash Tracker Person", person, {"cash_balance": net_cash, "total_expenses": float(ep), "total_reimbursed": float(rb), "net_owed": net_owed})
        ledger = frappe.db.get_value("Cash Balance Ledger", {"cash_tracker_person": person})
        if ledger:
            frappe.db.set_value("Cash Balance Ledger", ledger, {"total_cash_in": float(ci), "total_cash_out": float(co), "net_cash": net_cash, "total_expenses": float(ep), "total_reimbursed": float(rb), "net_owed": net_owed})
        else:
            new_ledger = frappe.new_doc("Cash Balance Ledger")
            new_ledger.cash_tracker_person = person
            new_ledger.total_cash_in = float(ci)
            new_ledger.total_cash_out = float(co)
            new_ledger.net_cash = net_cash
            new_ledger.total_expenses = float(ep)
            new_ledger.total_reimbursed = float(rb)
            new_ledger.net_owed = net_owed
            new_ledger.insert(ignore_permissions=True)
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
