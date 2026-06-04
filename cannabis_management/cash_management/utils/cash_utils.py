import frappe
from frappe.utils import today, now, add_days, getdate


# ---------------------------------------------------------------------------
# before_save helpers
# ---------------------------------------------------------------------------

def auto_fill_month(doc, method):
    if doc.date:
        d = getdate(doc.date)
        doc.month = d.strftime("%b %Y")


def auto_fill_employee(doc, method):
    if doc.cash_tracker_person and not doc.employee:
        emp = frappe.db.get_value(
            "Cash Tracker Person", doc.cash_tracker_person, "employee"
        )
        if emp:
            doc.employee = emp


def validate_receipt_required(doc, method):
    if doc.direction == "Expense" and not doc.receipt:
        frappe.throw(
            "A receipt attachment is required for Expense entries. "
            "Please upload the receipt before saving."
        )


# ---------------------------------------------------------------------------
# Running balance (Cash Ledger Entry only)
# ---------------------------------------------------------------------------

def update_running_balance(doc, method):
    """Compute and store the running balance for this person at this entry."""
    result = frappe.db.sql(
        """
        SELECT running_balance FROM `tabCash Ledger Entry`
        WHERE cash_tracker_person = %s
          AND docstatus = 1
          AND name != %s
        ORDER BY date DESC, creation DESC
        LIMIT 1
        """,
        (doc.cash_tracker_person, doc.name),
    )
    prev = result[0][0] if result else 0
    doc.running_balance = (prev + doc.amount) if doc.direction == "Cash In" \
                          else (prev - doc.amount)
    doc.db_update()


def reverse_running_balance(doc, method):
    """On cancel, recompute running balance — recalculation covers it via ledger."""
    pass


# ---------------------------------------------------------------------------
# Cash Balance Ledger recalculation
# ---------------------------------------------------------------------------

def update_cash_balance_ledger(doc, method):
    """Recalculate all aggregates for the person and update Cash Balance Ledger."""
    p = doc.cash_tracker_person

    cash_in = frappe.db.sql(
        """
        SELECT COALESCE(SUM(amount), 0) FROM `tabCash Ledger Entry`
        WHERE cash_tracker_person = %s AND direction = 'Cash In' AND docstatus = 1
        """,
        p,
    )[0][0]

    cash_out = frappe.db.sql(
        """
        SELECT COALESCE(SUM(amount), 0) FROM `tabCash Ledger Entry`
        WHERE cash_tracker_person = %s AND direction = 'Cash Out' AND docstatus = 1
        """,
        p,
    )[0][0]

    expenses = frappe.db.sql(
        """
        SELECT COALESCE(SUM(amount), 0) FROM `tabExpense Tracker Entry`
        WHERE cash_tracker_person = %s AND direction = 'Expense' AND docstatus = 1
        """,
        p,
    )[0][0]

    reimbursed = frappe.db.sql(
        """
        SELECT COALESCE(SUM(amount), 0) FROM `tabExpense Tracker Entry`
        WHERE cash_tracker_person = %s AND direction = 'Reimbursement' AND docstatus = 1
        """,
        p,
    )[0][0]

    net_cash = cash_in - cash_out
    net_owed = expenses - reimbursed

    ledger_name = frappe.db.get_value(
        "Cash Balance Ledger", {"cash_tracker_person": p}
    )

    if ledger_name:
        frappe.db.set_value(
            "Cash Balance Ledger",
            ledger_name,
            {
                "total_cash_in": cash_in,
                "total_cash_out": cash_out,
                "net_cash": net_cash,
                "total_expenses": expenses,
                "total_reimbursed": reimbursed,
                "net_owed": net_owed,
                "as_of_date": today(),
                "last_updated": now(),
            },
        )
    else:
        frappe.get_doc(
            {
                "doctype": "Cash Balance Ledger",
                "cash_tracker_person": p,
                "total_cash_in": cash_in,
                "total_cash_out": cash_out,
                "net_cash": net_cash,
                "total_expenses": expenses,
                "total_reimbursed": reimbursed,
                "net_owed": net_owed,
                "as_of_date": today(),
                "last_updated": now(),
            }
        ).insert(ignore_permissions=True)

    frappe.db.set_value(
        "Cash Tracker Person",
        p,
        {
            "cash_balance": net_cash,
            "total_expenses": expenses,
            "total_reimbursed": reimbursed,
            "net_owed": net_owed,
        },
    )


def update_expense_balance(doc, method):
    """Thin wrapper — expense entries share the same ledger recalc."""
    update_cash_balance_ledger(doc, method)


# ---------------------------------------------------------------------------
# Real-time balance broadcast
# ---------------------------------------------------------------------------

def publish_realtime_balance(doc, method):
    """Push updated balance to the submitting user's browser via Socket.IO."""
    person_doc = frappe.db.get_value(
        "Cash Tracker Person",
        doc.cash_tracker_person,
        ["user", "cash_balance", "net_owed"],
        as_dict=True,
    )
    if not person_doc:
        return

    frappe.publish_realtime(
        event="cash_balance_update",
        message={
            "person": doc.cash_tracker_person,
            "net_cash": person_doc.get("cash_balance") or 0,
            "net_owed": person_doc.get("net_owed") or 0,
            "last_entry": doc.name,
            "timestamp": now(),
        },
        user=person_doc.get("user"),
    )


# ---------------------------------------------------------------------------
# IRS Form 8300 compliance
# ---------------------------------------------------------------------------

def check_form_8300_trigger(doc, method):
    """Auto-flag Cash In entries >= $10,000 and alert Finance."""
    if doc.direction != "Cash In" or doc.amount < 10000:
        return

    doc.form_8300_required = 1
    doc.db_update()

    finance_users = frappe.get_all(
        "Has Role",
        filters={"role": "Finance Manager"},
        pluck="parent",
    )
    # deduplicate and filter out system users without email
    recipients = list(
        {
            u
            for u in finance_users
            if frappe.db.get_value("User", u, "enabled")
        }
    )
    if not recipients:
        return

    deadline = add_days(doc.date, 15)

    frappe.sendmail(
        recipients=recipients,
        subject=f"⚠️ Form 8300 Required — {doc.cash_tracker_person} — ${doc.amount:,.2f}",
        message=f"""
            <h3>IRS Form 8300 Filing Required</h3>
            <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;">
              <tr><td><b>Entry</b></td><td>{doc.name}</td></tr>
              <tr><td><b>Person</b></td><td>{doc.cash_tracker_person}</td></tr>
              <tr><td><b>Entity</b></td><td>{doc.entity}</td></tr>
              <tr><td><b>Amount</b></td><td>${doc.amount:,.2f}</td></tr>
              <tr><td><b>Date</b></td><td>{doc.date}</td></tr>
              <tr><td><b>Type</b></td><td>{doc.transaction_type}</td></tr>
              <tr><td><b>Filing Deadline</b></td><td><b>{deadline}</b></td></tr>
            </table>
            <p><b>Form 8300 must be filed with the IRS within 15 days of this transaction.</b></p>
            <p><a href="{frappe.utils.get_url()}/app/cash-ledger-entry/{doc.name}">
                Open Entry in ERPNext &rarr;
            </a></p>
        """,
    )

    # Create a high-priority ToDo with 15-day deadline
    frappe.get_doc(
        {
            "doctype": "ToDo",
            "description": (
                f"File IRS Form 8300 for Cash Ledger Entry {doc.name} "
                f"({doc.cash_tracker_person}) — ${doc.amount:,.2f}. "
                f"Deadline: {deadline}."
            ),
            "reference_type": "Cash Ledger Entry",
            "reference_name": doc.name,
            "date": deadline,
            "priority": "High",
            "assigned_by": "Administrator",
        }
    ).insert(ignore_permissions=True)


# ---------------------------------------------------------------------------
# Scheduled job: daily overdue Form 8300 check
# ---------------------------------------------------------------------------

def check_overdue_form_8300():
    """Runs daily. Alerts Finance of any unfiled Form 8300 entries past 15 days."""
    overdue_entries = frappe.db.sql(
        """
        SELECT name, cash_tracker_person, entity, amount, date,
               DATEDIFF(CURDATE(), date) AS days_since
        FROM `tabCash Ledger Entry`
        WHERE docstatus = 1
          AND form_8300_required = 1
          AND form_8300_filed = 0
          AND direction = 'Cash In'
          AND amount >= 10000
          AND DATEDIFF(CURDATE(), date) > 15
        ORDER BY date ASC
        """,
        as_dict=True,
    )

    if not overdue_entries:
        return

    finance_users = frappe.get_all(
        "Has Role",
        filters={"role": "Finance Manager"},
        pluck="parent",
    )
    recipients = list(
        {
            u
            for u in finance_users
            if frappe.db.get_value("User", u, "enabled")
        }
    )
    if not recipients:
        return

    rows = "".join(
        f"<tr><td>{e.name}</td><td>{e.cash_tracker_person}</td>"
        f"<td>{e.entity}</td><td>${e.amount:,.2f}</td>"
        f"<td>{e.date}</td><td style='color:red'><b>{e.days_since} days</b></td></tr>"
        for e in overdue_entries
    )

    frappe.sendmail(
        recipients=recipients,
        subject=f"⚠️ OVERDUE: {len(overdue_entries)} IRS Form 8300 Filing(s) Past Deadline",
        message=f"""
            <h3>Overdue IRS Form 8300 Filings</h3>
            <p>The following cash receipts are past the 15-day filing deadline
            and have not been marked as filed:</p>
            <table cellpadding="6" cellspacing="0" border="1" style="border-collapse:collapse;">
              <tr style="background:#cc0000;color:white;">
                <th>Entry</th><th>Person</th><th>Entity</th>
                <th>Amount</th><th>Date</th><th>Days Overdue</th>
              </tr>
              {rows}
            </table>
            <p>Please file and check <b>Form 8300 Filed</b> on each entry immediately.</p>
        """,
    )


# ---------------------------------------------------------------------------
# Accounting entry creation (Finance-only whitelisted methods)
# ---------------------------------------------------------------------------

def _resolve_accounts(company, transaction_type):
    """Return (cash_account, contra_account) from Cash Account Mapping."""
    mapping = frappe.db.get_value(
        "Cash Account Mapping",
        {"company": company, "transaction_type": transaction_type},
        ["cash_account", "contra_account"],
        as_dict=True,
    )
    if not mapping:
        frappe.throw(
            f"No Cash Account Mapping found for company <b>{company}</b> "
            f"and transaction type <b>{transaction_type}</b>. "
            "Please configure it under Cash Management &rarr; Cash Account Mapping."
        )
    return mapping.cash_account, mapping.contra_account


@frappe.whitelist()
def create_journal_entry(doctype, docname):
    """Create a Journal Entry from a submitted Cash Ledger Entry or Expense Tracker Entry."""
    _assert_finance_role()
    doc = frappe.get_doc(doctype, docname)

    if doc.gl_entry_created:
        frappe.throw("An accounting entry has already been created for this record.")

    cash_acc, contra_acc = _resolve_accounts(doc.company, doc.transaction_type)

    je = frappe.new_doc("Journal Entry")
    je.posting_date = doc.date
    je.company = doc.company
    je.user_remark = (
        f"From {doctype} {docname} — {doc.transaction_type} — {doc.notes or ''}"
    )

    is_inflow = doc.direction in ("Cash In", "Reimbursement")

    if is_inflow:
        je.append("accounts", {
            "account": cash_acc,
            "debit_in_account_currency": doc.amount,
        })
        je.append("accounts", {
            "account": contra_acc,
            "credit_in_account_currency": doc.amount,
        })
    else:
        je.append("accounts", {
            "account": contra_acc,
            "debit_in_account_currency": doc.amount,
        })
        je.append("accounts", {
            "account": cash_acc,
            "credit_in_account_currency": doc.amount,
        })

    je.insert()
    je.submit()

    frappe.db.set_value(doctype, docname, {
        "journal_entry": je.name,
        "gl_entry_created": 1,
    })
    return je.name


@frappe.whitelist()
def create_payment_entry(doctype, docname):
    """Create a Payment Entry from a submitted Cash Ledger Entry or Expense Tracker Entry."""
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
    pe.remarks = f"{doc.transaction_type} — {doc.notes or ''}"
    pe.mode_of_payment = "Cash"

    # Link to Employee for payroll entries
    if doc.transaction_type == "Payroll" and doc.employee:
        pe.party_type = "Employee"
        pe.party = doc.employee

    pe.insert()

    frappe.db.set_value(doctype, docname, {
        "payment_entry": pe.name,
        "gl_entry_created": 1,
    })
    return pe.name


def _assert_finance_role():
    """Raise PermissionError if current user lacks Finance Manager or Accounts Manager role."""
    allowed_roles = {"Finance Manager", "Accounts Manager", "System Manager"}
    user_roles = set(frappe.get_roles(frappe.session.user))
    if not allowed_roles.intersection(user_roles):
        frappe.throw(
            "Only Finance Manager or Accounts Manager can create accounting entries.",
            frappe.PermissionError,
        )
