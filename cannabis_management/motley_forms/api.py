import frappe

@frappe.whitelist(allow_guest=False)
def get_current_employee():
    employee = frappe.db.get_value(
        "Employee",
        {"user_id": frappe.session.user},
        ["name", "employee_name"],
        as_dict=True
    )
    return employee


def create_expense_tracker_draft(doc, method):
    from frappe.utils import getdate

    if doc.money_out and doc.money_out > 0:
        direction = "Expense"
        amount = doc.money_out
    elif doc.money_in and doc.money_in > 0:
        direction = "Reimbursement"
        amount = doc.money_in
    else:
        return

    person = frappe.db.get_value(
        "Cash Tracker Person", {"user": frappe.session.user}, "name"
    )

    ete = frappe.new_doc("Expense Tracker Entry")
    ete.date = doc.transaction_date
    ete.month = getdate(doc.transaction_date).strftime("%b %Y")
    ete.direction = direction
    ete.amount = amount
    ete.receipt = doc.receipt or None
    ete.notes = (
        f"[Web Form] Source: Nikki Expense Entry {doc.name}. "
        f"{doc.transaction_notes or ''}"
    ).strip()
    ete.company = doc.business or None
    ete.cash_tracker_person = person or None
    ete.transaction_type = "Reimbursement" if direction == "Reimbursement" else "Other"

    ete.db_insert()

    frappe.db.set_value("Expense Tracker Entry", ete.name, "docstatus", 1)
    ete.docstatus = 1

    if person:
        try:
            from cannabis_management.cash_management.utils.cash_utils import (
                update_expense_balance,
                publish_realtime_balance,
            )
            update_expense_balance(ete, None)
            publish_realtime_balance(ete, None)
        except Exception:
            frappe.log_error(
                frappe.get_traceback(), "Expense Tracker Entry on_submit hooks failed"
            )

    frappe.db.set_value("Nikki Expense Entry", doc.name, "expense_tracker_entry", ete.name)


def create_cash_ledger_draft(doc, method):
    from frappe.utils import getdate

    cle = frappe.new_doc("Cash Ledger Entry")
    cle.date = doc.date
    cle.month = getdate(doc.date).strftime("%b %Y")
    cle.entity = doc.entity
    cle.transaction_type = doc.transaction_type
    cle.direction = doc.direction
    cle.amount = doc.amount
    cle.invoice_number = doc.invoice_number or None
    cle.receipt = doc.receipt or None
    cle.notes = (
        f"[Web Form] Source: Nikki Cash Ledger Entry {doc.name}. "
        f"{doc.notes or ''}"
    ).strip()
    cle.db_insert()

    frappe.db.set_value(
        "Nikki Cash Ledger Entry", doc.name, "cash_ledger_entry", cle.name
    )
