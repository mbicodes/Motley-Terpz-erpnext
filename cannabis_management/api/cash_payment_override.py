import frappe


@frappe.whitelist()
def create_payment_entry(doctype, docname):
    """
    Override of cash_utils.create_payment_entry.

    Business logic:
      Cash Ledger Entry  — Nikki collects money for the company.
        Cash In  → she hands cash to the company   (Receive from Employee)
        Cash Out → company gives cash to Nikki      (Pay to Employee)
      Expense Tracker Entry — Nikki pays from her own pocket; company owes her.
        Expense       → company owes Nikki          (Pay to Employee when reimbursing)
        Reimbursement → liability is cleared        (Receive from Employee)

    Key fix: always set party_type = "Employee" whenever an employee can be
    resolved — not just for Payroll transaction_type as the original does.
    Employee is resolved from doc.employee first, then via Cash Tracker Person.
    """
    from cannabis_management.cash_management.utils.cash_utils import _assert_finance_role

    _assert_finance_role()

    doc = frappe.get_doc(doctype, docname)

    if doc.gl_entry_created:
        frappe.throw("An accounting entry has already been created for this record.")

    # Cash In / Reimbursement = company receives money → "Receive"
    # Cash Out / Expense      = company pays money    → "Pay"
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

    # Resolve employee: doc.employee may be blank for entries created via db_insert
    # (Server Script bypasses before_save / auto_fill_employee hook).
    employee = doc.employee or None
    if not employee and getattr(doc, "cash_tracker_person", None):
        employee = frappe.db.get_value(
            "Cash Tracker Person", doc.cash_tracker_person, "employee"
        )

    if employee:
        pe.party_type = "Employee"
        pe.party = employee

        # Set accounts explicitly so Finance can review a complete draft.
        try:
            company_doc = frappe.get_doc("Company", doc.company)
            cash_account = company_doc.default_cash_account

            # Get the employee-side payable account
            from erpnext.accounts.party import get_party_account
            party_account = get_party_account("Employee", employee, doc.company)

            if is_inflow:
                # Nikki hands cash to company: employee payable → company cash
                pe.paid_from = party_account or company_doc.default_payable_account
                pe.paid_to = cash_account
            else:
                # Company pays Nikki: company cash → employee payable
                pe.paid_from = cash_account
                pe.paid_to = party_account or company_doc.default_payable_account
        except Exception:
            # If account resolution fails, let ERPNext auto-fill on insert
            pass

    pe.insert()

    frappe.db.set_value(doctype, docname, {
        "payment_entry": pe.name,
        "gl_entry_created": 1,
    })
    return pe.name
