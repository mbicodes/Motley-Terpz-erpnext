import frappe
from frappe.utils import flt

SOURCE_DOCTYPES = (
    "Motley Cash Tracking", "TSBC Cash Tracking", "Safe Cash Tracking", "Personal Cash Tracking",
)


def _get_source(source_doctype, source_name):
    if source_doctype not in SOURCE_DOCTYPES:
        frappe.throw(f"{source_doctype} is not a cash tracking doctype.")

    doc = frappe.get_doc(source_doctype, source_name)
    doc.check_permission("read")
    if doc.docstatus != 1:
        frappe.throw("Submit the entry before creating a Payment Entry or Journal Entry.")
    return doc


def _amount_and_direction(doc):
    money_in, money_out = flt(doc.money_in), flt(doc.money_out)
    if money_in:
        return money_in, True
    return money_out, False


def _notes(doc):
    return doc.get("transaction_notes") or doc.get("reason") or ""


def _remark(doc):
    parts = [f"{doc.doctype} {doc.name}"]
    if doc.get("transaction_type"):
        parts.append(doc.transaction_type)
    if _notes(doc):
        parts.append(_notes(doc))
    return " — ".join(parts)


def _account_mapping(doc):
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


def _stamp_source(target, doc):
    for fieldname, value in (
        ("custom_cash_tracking_doctype", doc.doctype),
        ("custom_cash_tracking_entry", doc.name),
    ):
        if target.meta.get_field(fieldname):
            target.set(fieldname, value)


def _payment_reference(doc):
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
                pe.paid_amount = amount
                pe.received_amount = amount
                for ref in pe.references:
                    ref.allocated_amount = min(flt(ref.outstanding_amount) or amount, amount)
        except Exception:
            pe = None
            if hasattr(frappe, "clear_messages"):
                frappe.clear_messages()

    if pe is None:
        pe = _bare_payment_entry(doc, amount, is_money_in)

    mode = _cash_mode_of_payment()
    if mode:
        pe.mode_of_payment = mode
    pe.remarks = _remark(doc)
    _stamp_source(pe, doc)
    return pe.as_dict()


def _cash_mode_of_payment():
    return frappe.db.get_value("Mode of Payment", {"name": "Cash", "enabled": 1}, "name")


@frappe.whitelist()
def make_journal_entry(source_doctype, source_name):
    doc = _get_source(source_doctype, source_name)
    amount, is_money_in = _amount_and_direction(doc)
    cash_account, contra_account = _account_mapping(doc)

    je = frappe.new_doc("Journal Entry")
    je.voucher_type = "Cash Entry" if cash_account else "Journal Entry"
    je.company = doc.get("business")
    je.posting_date = doc.transaction_date
    je.user_remark = _remark(doc)

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

    _stamp_source(je, doc)
    return je.as_dict()


def _money(amount, currency=None):
    symbol = None
    if currency:
        symbol = frappe.db.get_value("Currency", currency, "symbol")
    return f"{symbol or '$'}{frappe.utils.fmt_money(flt(amount))}"


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def sales_order_query(doctype, txt, searchfield, start, page_len, filters):
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


@frappe.whitelist()
def get_post_state(voucher_doctype, voucher_name):
    from cannabis_management.cash_management.permissions import can_mark_processed

    if voucher_doctype not in ("Payment Entry", "Journal Entry"):
        return {}

    source = frappe.db.get_value(
        voucher_doctype,
        voucher_name,
        ["custom_cash_tracking_doctype", "custom_cash_tracking_entry", "docstatus"],
        as_dict=True,
    )
    if not source or not source.custom_cash_tracking_entry:
        return {}

    return {
        "source_doctype": source.custom_cash_tracking_doctype,
        "source_name": source.custom_cash_tracking_entry,
        "submitted": source.docstatus == 1,
        "processed": int(
            frappe.db.get_value(
                source.custom_cash_tracking_doctype, source.custom_cash_tracking_entry, "processed"
            )
            or 0
        ),
        "can_post": can_mark_processed(),
    }


@frappe.whitelist()
def set_posted(voucher_doctype, voucher_name, posted):
    from cannabis_management.cash_management.permissions import can_mark_processed

    if not can_mark_processed():
        frappe.throw(
            "Only the finance team can post a cash tracking entry.",
            frappe.PermissionError,
        )

    state = get_post_state(voucher_doctype, voucher_name)
    if not state:
        frappe.throw("This document is not linked to a cash tracking entry.")
    if not state["submitted"]:
        frappe.throw(f"Submit the {voucher_doctype} before posting.")

    posted = int(frappe.parse_json(posted) if isinstance(posted, str) else posted)
    frappe.db.set_value(
        state["source_doctype"],
        state["source_name"],
        {
            "processed": posted,
            "processed_by": frappe.session.user if posted else None,
            "processed_on": frappe.utils.now_datetime() if posted else None,
        },
        update_modified=False,
    )
    return {"source": state["source_name"], "processed": posted}
