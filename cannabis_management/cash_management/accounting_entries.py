"""Turn a submitted cash-tracking entry into a Payment Entry or a Journal Entry.

Both cash-tracking doctypes (Motley / Personal) are pure capture forms — they
record that money moved, with no GL effect of their own. These builders are what
an accountant uses afterwards to post the movement, pre-filled from the capture
form so nothing is re-typed.

Nothing here saves anything: each function returns an UNSAVED document that the
form-side JS routes to, so the accountant reviews and submits it by hand. That is
deliberate — accounts and amounts are theirs to confirm.
"""

import frappe
from frappe.utils import flt

SOURCE_DOCTYPES = ("Motley Cash Tracking", "TSBC Cash Tracking", "Personal Cash Tracking")


def _get_source(source_doctype, source_name):
    """Load the capture form, refusing anything unexpected or unsubmitted."""
    if source_doctype not in SOURCE_DOCTYPES:
        frappe.throw(f"{source_doctype} is not a cash tracking doctype.")

    doc = frappe.get_doc(source_doctype, source_name)
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw("Submit the entry before creating a Payment Entry or Journal Entry.")
    return doc


def _amount_and_direction(doc):
    """(amount, is_money_in). Money In = cash received, Money Out = cash paid."""
    money_in, money_out = flt(doc.money_in), flt(doc.money_out)
    if money_in:
        return money_in, True
    return money_out, False


def _notes(doc):
    """The free-text field differs between the two doctypes."""
    return doc.get("transaction_notes") or doc.get("reason") or ""


def _remark(doc):
    parts = [f"{doc.doctype} {doc.name}"]
    if doc.get("transaction_type"):
        parts.append(doc.transaction_type)
    if _notes(doc):
        parts.append(_notes(doc))
    return " — ".join(parts)


def _account_mapping(doc):
    """Cash / contra accounts configured for this company + transaction type.

    Returns (cash_account, contra_account); either may be None when no Cash
    Account Mapping row exists, in which case the accountant picks the accounts
    on the generated document.
    """
    company = doc.get("business")
    txn_type = doc.get("transaction_type")
    mapping = None
    if company and txn_type:
        mapping = frappe.db.get_value(
            "Cash Account Mapping",
            {"company": company, "transaction_type": txn_type},
            ["cash_account", "contra_account"],
            as_dict=True,
        )
    cash_account = mapping.cash_account if mapping else None
    contra_account = mapping.contra_account if mapping else None

    if not cash_account and company:
        cash_account = frappe.db.get_value("Company", company, "default_cash_account")

    return cash_account, contra_account


# ── Payment Entry ─────────────────────────────────────────────────────────────

def _payment_reference(doc):
    """What a Payment Entry should actually be raised against, as (doctype, name).

    A Sales Order that has already been invoiced cannot take a payment — ERPNext
    refuses with "Can only make payment against unbilled Sales Order", because
    the money is owed on the invoice. So prefer an unpaid Sales Invoice raised
    from that order, fall back to the order itself while it is still unbilled,
    and give up (returning None) when neither applies.
    """
    sales_order = doc.get("invoice_number")
    if not sales_order:
        return None, None
    if frappe.db.get_value("Sales Order", sales_order, "docstatus") != 1:
        return None, None

    invoice = frappe.db.sql(
        """
        SELECT si.name
        FROM `tabSales Invoice` si
        JOIN `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE sii.sales_order = %s AND si.docstatus = 1 AND si.outstanding_amount > 0
        ORDER BY si.posting_date DESC
        LIMIT 1
        """,
        sales_order,
    )
    if invoice:
        return "Sales Invoice", invoice[0][0]

    if flt(frappe.db.get_value("Sales Order", sales_order, "per_billed")) < 100:
        return "Sales Order", sales_order

    return None, None


def _bare_payment_entry(doc, amount, is_money_in):
    """Payment Entry with no reference document — company, date, amount, and
    whatever accounts the Cash Account Mapping can supply."""
    pe = frappe.new_doc("Payment Entry")
    pe.payment_type = "Receive" if is_money_in else "Pay"
    pe.company = doc.get("business")
    pe.posting_date = doc.transaction_date
    pe.paid_amount = amount
    pe.received_amount = amount

    cash_account, contra_account = _account_mapping(doc)
    if is_money_in:
        pe.paid_to = cash_account
        pe.paid_from = contra_account
    else:
        pe.paid_from = cash_account
        pe.paid_to = contra_account
    return pe


@frappe.whitelist()
def make_payment_entry(source_doctype, source_name):
    """Payment Entry pre-filled from a cash tracking entry.

    When the entry points at a Sales Order we hand off to ERPNext's own
    get_payment_entry() against the right reference (see _payment_reference), so
    party, accounts, currencies and the allocation row are built exactly as they
    are from the source document itself — then this entry's date and amount are
    layered on top. Anything ERPNext refuses falls back to the bare build rather
    than failing the click.
    """
    doc = _get_source(source_doctype, source_name)
    amount, is_money_in = _amount_and_direction(doc)

    pe = None
    ref_doctype, ref_name = _payment_reference(doc)
    if ref_doctype:
        from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

        try:
            pe = get_payment_entry(ref_doctype, ref_name)
            pe.posting_date = doc.transaction_date
            if amount:
                # Re-allocate to what was actually collected, never above the
                # outstanding amount ERPNext computed for the reference.
                pe.paid_amount = amount
                pe.received_amount = amount
                for ref in pe.references:
                    ref.allocated_amount = min(flt(ref.outstanding_amount) or amount, amount)
        except Exception:
            # e.g. nothing left outstanding by the time the button is clicked.
            pe = None
            if hasattr(frappe, "clear_messages"):
                frappe.clear_messages()

    if pe is None:
        pe = _bare_payment_entry(doc, amount, is_money_in)

    mode = _cash_mode_of_payment()
    if mode:
        pe.mode_of_payment = mode
    pe.remarks = _remark(doc)
    return pe.as_dict()


def _cash_mode_of_payment():
    """The plain "Cash" Mode of Payment, if it exists.

    Deliberately an exact-name match: this site also has account-specific cash
    modes ("Petty Cash - Jamie", "1104-Nikki Expense Tracker") and picking one of
    those at random would attach the wrong account to someone else's payment.
    """
    return frappe.db.get_value("Mode of Payment", {"name": "Cash", "enabled": 1}, "name")


# ── Journal Entry ─────────────────────────────────────────────────────────────

@frappe.whitelist()
def make_journal_entry(source_doctype, source_name):
    """Journal Entry pre-filled from a cash tracking entry.

    Money In debits the cash account and credits the contra; Money Out is the
    mirror. Accounts come from Cash Account Mapping (company + transaction type)
    and are simply left blank when no mapping exists — the rows and the amounts
    are still there, so the accountant only fills in the two accounts.
    """
    doc = _get_source(source_doctype, source_name)
    amount, is_money_in = _amount_and_direction(doc)
    cash_account, contra_account = _account_mapping(doc)

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Cash Entry" if cash_account else "Journal Entry"
    je.company = doc.get("business")
    je.posting_date = doc.transaction_date
    je.user_remark = _remark(doc)

    # Cash side first, then the contra side, so the accountant reads it top-down.
    if is_money_in:
        rows = [(cash_account, amount, 0), (contra_account, 0, amount)]
    else:
        rows = [(contra_account, amount, 0), (cash_account, 0, amount)]

    for account, debit, credit in rows:
        row = je.append("accounts", {})
        if account:
            row.account = account
        row.debit_in_account_currency = debit
        row.credit_in_account_currency = credit

    return je.as_dict()


# ── Sales Order picker ────────────────────────────────────────────────────────

def _money(amount, currency=None):
    """"$24,150.00" — symbol tight against the amount, thousands separated."""
    symbol = None
    if currency:
        symbol = frappe.db.get_value("Currency", currency, "symbol")
    return f"{symbol or '$'}{frappe.utils.fmt_money(flt(amount))}"


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def sales_order_query(doctype, txt, searchfield, start, page_len, filters):
    """Link-field search for Invoice # (Sales Order), with the total as currency.

    Same columns as the stock Sales Order lookup, in the same order — this
    exists only so the amount at the end of each dropdown line reads
    "$24,150.00" instead of a bare "24150.0".

    Uses get_list rather than raw SQL so the caller's own permissions and User
    Permissions still apply: a rep restricted to two companies must not start
    seeing every company's orders just because the picker was customised.
    """
    orders = frappe.get_list(
        "Sales Order",
        filters={"docstatus": ["<", 2]},
        or_filters=[
            ["name", "like", f"%{txt}%"],
            ["customer_name", "like", f"%{txt}%"],
            ["customer", "like", f"%{txt}%"],
        ],
        fields=[
            "name", "customer_name", "status", "transaction_date",
            "order_type", "company", "grand_total", "currency",
        ],
        order_by="transaction_date desc, name desc",
        limit_start=start,
        limit_page_length=page_len,
    )

    return [
        [
            o.name,
            o.customer_name or "",
            o.status or "",
            str(o.transaction_date or ""),
            o.order_type or "",
            o.company or "",
            _money(o.grand_total, o.currency),
        ]
        for o in orders
    ]
