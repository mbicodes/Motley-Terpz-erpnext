import frappe


@frappe.whitelist()
def create_payment_entry(doctype, docname):
    from cannabis_management.cash_management.utils.cash_utils import _assert_finance_role

    _assert_finance_role()

    doc = frappe.get_doc(doctype, docname)

    if doc.gl_entry_created:
        frappe.throw("An accounting entry has already been created for this record.")

    is_inflow = doc.direction in ("Cash In", "Reimbursement")

    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive" if is_inflow else "Pay"
    pe.posting_date = doc.date
    pe.company = doc.company
    pe.paid_amount = doc.amount
    pe.received_amount = doc.amount
    pe.reference_no = getattr(doc, "invoice_number", None) or doc.name
    pe.reference_date = doc.date
    pe.remarks = f"[{doctype}] {doc.transaction_type or ''} — {doc.notes or ''}".strip(" —")
    pe.mode_of_payment = "Cash"

    employee = doc.employee or None
    if not employee and getattr(doc, "cash_tracker_person", None):
        employee = frappe.db.get_value(
            "Cash Tracker Person", doc.cash_tracker_person, "employee"
        )

    if employee:
        pe.party_type = "Employee"
        pe.party = employee

        try:
            company_doc = frappe.get_doc("Company", doc.company)
            cash_account = company_doc.default_cash_account

            from erpnext.accounts.party import get_party_account
            party_account = get_party_account("Employee", employee, doc.company)

            if is_inflow:
                pe.paid_from = party_account or company_doc.default_payable_account
                pe.paid_to = cash_account
            else:
                pe.paid_from = cash_account
                pe.paid_to = party_account or company_doc.default_payable_account
        except Exception:
            pass

    pe.insert()

    frappe.db.set_value(doctype, docname, {
        "payment_entry": pe.name,
        "gl_entry_created": 1,
    })
    return pe.name
