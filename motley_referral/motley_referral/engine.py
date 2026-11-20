"""Referral commission engine.

Payment Ledger Entry (PLE) is the single source of commission lines. Every line is keyed on the
PLE name (unique together with is_reversal), so running the engine any number of times never
creates a duplicate. Hooks never break the source transaction: errors are logged and the
nightly sync picks anything up that a hook missed.
"""
import calendar

import frappe
from frappe import _
from frappe.utils import add_months, flt, get_first_day, get_last_day, getdate, nowdate

LEDGER = "Referral Commission Ledger"
NON_MONEY_JE_TYPES = (
    "Write Off Entry", "Credit Note", "Debit Note", "Exchange Rate Revaluation", "Exchange Gain Or Loss",
    "Deferred Revenue", "Deferred Expense",
)


# ----------------------------------------------------------------------------- helpers
def settings():
    return frappe.get_cached_doc("Referral Settings")


def eligible_companies():
    return [r.company for r in settings().get("eligible_companies") or []]


def month_no_for(start, posting_date):
    """Calendar month counting (Decision 3): the month of the first qualifying payment is Month 1."""
    start, posting_date = getdate(start), getdate(posting_date)
    return (posting_date.year - start.year) * 12 + (posting_date.month - start.month) + 1


def window_end(start, months):
    """Last day of Month `months` of a window that began in the month of `start`."""
    return get_last_day(add_months(get_first_day(getdate(start)), months - 1))


def get_partner(name):
    return frappe.get_cached_doc("Referral Partner", name)


def partner_rates(partner):
    s = settings()
    return dict(
        y1_rate=flt(partner.year1_rate) or flt(s.year1_rate),
        y2_rate=flt(partner.year2_rate) or flt(s.year2_rate),
        y1_months=partner.year1_months or s.year1_months or 12,
        y2_months=partner.year2_months or s.year2_months or 12,
    )


def rate_for_month(partner, month_no):
    r = partner_rates(partner)
    if month_no < 1:
        return None
    if month_no <= r["y1_months"]:
        return r["y1_rate"]
    if month_no <= r["y1_months"] + r["y2_months"]:
        return r["y2_rate"]
    return None


def partner_can_earn(partner, referral):
    if partner.status == "Draft":
        return False
    if partner.status == "Terminated" and partner.termination_date:
        # keeps earning on referrals acknowledged before the termination date
        return getdate(referral.acknowledged_on) < getdate(partner.termination_date)
    return True


# ----------------------------------------------------------------------------- start stamp
def stamp_start(ref, posting_date):
    partner = get_partner(ref.referral_partner)
    r = partner_rates(partner)
    posting_date = getdate(posting_date)
    vals = dict(
        commission_start_date=posting_date,
        year1_end=window_end(posting_date, r["y1_months"]),
        year2_end=window_end(posting_date, r["y1_months"] + r["y2_months"]),
        window_status="Year 1",
        current_month_no=1,
    )
    for k, v in vals.items():
        ref.db_set(k, v, update_modified=False)
        ref.set(k, v)
    from motley_referral import notifications

    notifications.notify("first_payment", ref=ref)


# ----------------------------------------------------------------------------- process_ple
def process_ple(ple):
    """Create the commission line for one Payment Ledger Entry. Idempotent. Returns the line name or None."""
    if isinstance(ple, str):
        ple = frappe.get_doc("Payment Ledger Entry", ple)
    if ple.delinked or ple.party_type != "Customer" or ple.account_type != "Receivable":
        return
    if ple.company not in eligible_companies():
        return
    if ple.voucher_type not in ("Payment Entry", "Journal Entry"):
        return  # a credit note alone moves no money
    if ple.against_voucher_type != "Sales Invoice":
        return  # unallocated advance: wait until it is allocated
    if ple.voucher_type == "Journal Entry":
        je_type = frappe.db.get_value("Journal Entry", ple.voucher_no, "voucher_type")
        if je_type in NON_MONEY_JE_TYPES:
            return  # write-offs, credit/debit notes: no money moved
    if frappe.db.exists(LEDGER, {"payment_ledger_entry": ple.name, "is_reversal": 0}):
        return
    if _relink_line(ple):
        return  # same money, re-created PLE (Payment Reconciliation): no second line

    ref_name = frappe.db.get_value("Customer", ple.party, "partner_referral")
    if not ref_name:
        return
    ref = frappe.get_doc("Partner Referral", ref_name)
    if ref.status != "Acknowledged" or not ref.acknowledged_on:
        return
    if getdate(ple.posting_date) < getdate(ref.acknowledged_on):
        return  # Decision 2: nothing before acknowledgement
    partner = get_partner(ref.referral_partner)
    if not partner_can_earn(partner, ref):
        return

    # receipt credits the receivable, so the PLE amount is negative; a refund to the customer is positive
    amount = -flt(ple.amount)
    if not amount:
        return

    if not ref.commission_start_date:
        if amount <= 0:
            return
        stamp_start(ref, ple.posting_date)

    month_no = month_no_for(ref.commission_start_date, ple.posting_date)
    rate = rate_for_month(partner, month_no)
    if rate is None:
        return  # before the start month or window ended (refunds after Month 24 are ignored)

    return insert_ledger_line(ref, ple, month_no, rate, amount)


def insert_ledger_line(ref, ple, month_no, rate, amount):
    line = frappe.get_doc(
        {
            "doctype": LEDGER,
            "referral_partner": ref.referral_partner,
            "partner_referral": ref.name,
            "customer": ref.customer,
            "company": ple.company,
            "payment_ledger_entry": ple.name,
            "voucher_type": ple.voucher_type,
            "voucher_no": ple.voucher_no,
            "sales_invoice": ple.against_voucher_no,
            "posting_date": getdate(ple.posting_date),
            "period": getdate(ple.posting_date).strftime("%Y-%m"),
            "month_no": month_no,
            "rate": rate,
            "amount_received": amount,
            "commission_amount": flt(amount * rate / 100, 2),
            "is_reversal": 0,
        }
    )
    line.flags.ignore_permissions = True
    line.insert()
    refresh_referral_totals(ref.name)
    return line.name


def refresh_referral_totals(ref_name):
    row = frappe.db.sql(
        "select coalesce(sum(amount_received),0), coalesce(sum(commission_amount),0) "
        "from `tabReferral Commission Ledger` where partner_referral=%s",
        ref_name,
    )[0]
    frappe.db.set_value(
        "Partner Referral", ref_name, {"total_received": row[0], "total_commission": row[1]}, update_modified=False
    )


# ----------------------------------------------------------------------------- reversals
def reverse_line(orig, today=None):
    """Insert the mirror line of `orig` (a ledger line dict/doc). Returns the new name."""
    if frappe.db.exists(LEDGER, {"reverses": orig.name}):
        return
    today = getdate(today or nowdate())
    in_open_statement = False
    if orig.statement:
        st = frappe.db.get_value("Referral Commission Statement", orig.statement, ["docstatus", "status"], as_dict=True)
        in_open_statement = bool(st) and st.docstatus == 1  # Approved / Paid / Carried Forward
    if in_open_statement:
        period, statement = today.strftime("%Y-%m"), None  # current open period, reduces the next statement
    else:
        period, statement = orig.period, orig.statement  # same period, Draft statement is rebuilt
    rev = frappe.get_doc(
        {
            "doctype": LEDGER,
            "referral_partner": orig.referral_partner,
            "partner_referral": orig.partner_referral,
            "customer": orig.customer,
            "company": orig.company,
            "payment_ledger_entry": orig.payment_ledger_entry,
            "voucher_type": orig.voucher_type,
            "voucher_no": orig.voucher_no,
            "sales_invoice": orig.sales_invoice,
            "posting_date": today,
            "period": period,
            "month_no": orig.month_no,
            "rate": orig.rate,
            "amount_received": -flt(orig.amount_received),
            "commission_amount": -flt(orig.commission_amount),
            "is_reversal": 1,
            "reverses": orig.name,
            "statement": statement,
        }
    )
    rev.flags.ignore_permissions = True
    rev.insert()
    refresh_referral_totals(orig.partner_referral)
    if statement:
        from motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement import (
            rebuild_draft,
        )

        rebuild_draft(statement)
    return rev.name


def _open_lines(**filters):
    """Original (non-reversal) lines that have no reversal yet."""
    rows = frappe.get_all(
        LEDGER,
        filters={"is_reversal": 0, **filters},
        fields=["*"],
    )
    done = set(
        frappe.get_all(
            LEDGER,
            filters={"is_reversal": 1, "reverses": ["in", [r.name for r in rows] or [""]]},
            pluck="reverses",
        )
    )
    return [r for r in rows if r.name not in done]


def reverse_voucher(voucher_type, voucher_no):
    """Cancelled voucher: reverse every non-reversed line of it."""
    created = []
    for orig in _open_lines(voucher_type=voucher_type, voucher_no=voucher_no):
        name = reverse_line(orig)
        if name:
            created.append(name)
    return created


def _ple_holds_line(ple_name, line):
    """True while this PLE still applies the line's money to the line's Sales Invoice."""
    row = frappe.db.get_value(
        "Payment Ledger Entry",
        ple_name,
        ["delinked", "voucher_no", "against_voucher_type", "against_voucher_no"],
        as_dict=True,
    )
    return bool(
        row
        and not row.delinked
        and row.voucher_no == line.voucher_no
        and row.against_voucher_type == "Sales Invoice"
        and row.against_voucher_no == line.sales_invoice
    )


def _relink_line(ple):
    """Payment Reconciliation deletes every PLE of the voucher and re-creates them under new names.

    When an open line of the same voucher, invoice and amount has lost its PLE, point it at the
    new PLE instead of commissioning the same money a second time. Returns the line name.
    """
    amount = -flt(ple.amount)
    for line in _open_lines(voucher_type=ple.voucher_type, voucher_no=ple.voucher_no, sales_invoice=ple.against_voucher_no):
        if abs(flt(line.amount_received) - amount) > 0.005:
            continue
        if _ple_holds_line(line.payment_ledger_entry, line):
            continue  # that line's own PLE is still live
        frappe.db.set_value(LEDGER, line.name, "payment_ledger_entry", ple.name, update_modified=False)
        return line.name
    return None


def _relink_to_live_ple(line):
    """Find a live PLE of the line's voucher, applied to its invoice for the same amount, that no line holds."""
    held = set(
        frappe.get_all(
            LEDGER, filters={"voucher_type": line.voucher_type, "voucher_no": line.voucher_no, "is_reversal": 0}, pluck="payment_ledger_entry"
        )
    )
    candidates = frappe.get_all(
        "Payment Ledger Entry",
        filters={
            "voucher_type": line.voucher_type,
            "voucher_no": line.voucher_no,
            "delinked": 0,
            "against_voucher_type": "Sales Invoice",
            "against_voucher_no": line.sales_invoice,
        },
        fields=["name", "amount"],
    )
    for p in candidates:
        if p.name not in held and abs(-flt(p.amount) - flt(line.amount_received)) <= 0.005:
            frappe.db.set_value(LEDGER, line.name, "payment_ledger_entry", p.name, update_modified=False)
            return True
    return False


def reverse_delinked(voucher_type=None, voucher_no=None):
    """Reverse lines whose money is no longer applied to their Sales Invoice.

    That covers a delinked PLE (cancel), a PLE re-pointed at the payment itself (Unreconcile
    Payment in v15 rewrites against_voucher and leaves delinked = 0) and a PLE that was deleted
    and not re-created against the same invoice. A line whose PLE was only re-created under a
    new name (Payment Reconciliation) is re-linked, not reversed.
    """
    filters = {}
    if voucher_type:
        filters.update(voucher_type=voucher_type, voucher_no=voucher_no)
    created = []
    for orig in _open_lines(**filters):
        if _ple_holds_line(orig.payment_ledger_entry, orig) or _relink_to_live_ple(orig):
            continue
        name = reverse_line(orig)
        if name:
            created.append(name)
    return created


# ----------------------------------------------------------------------------- hooks
def _safe(fn, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except Exception:
        frappe.log_error(title="Referral Engine", message=frappe.get_traceback())


def on_ple_submit(doc, method=None):
    _safe(process_ple, doc)


def on_voucher_submit(doc, method=None):
    """Payment Entry / Journal Entry submit: safety net over every PLE of the voucher."""

    def run():
        for name in frappe.get_all(
            "Payment Ledger Entry",
            filters={"voucher_type": doc.doctype, "voucher_no": doc.name, "delinked": 0},
            pluck="name",
        ):
            process_ple(name)

    _safe(run)


def on_voucher_cancel(doc, method=None):
    _safe(reverse_voucher, doc.doctype, doc.name)


def on_unreconcile_submit(doc, method=None):
    """Unreconcile Payment: PLE rows are delinked directly in SQL, so reverse by voucher."""

    def run():
        vtype, vno = doc.voucher_type, doc.voucher_no
        reverse_delinked(vtype, vno)

    _safe(run)


# ----------------------------------------------------------------------------- scheduler
def sync_ple(days=60):
    """Nightly: pick up missed PLE rows and reverse delinked ones. Writes one Error Log summary when it did work."""
    created, reversed_ = [], []
    companies = eligible_companies()
    if companies:
        customers = frappe.get_all(
            "Customer", filters={"partner_referral": ["is", "set"]}, pluck="name"
        )
        if customers:
            ples = frappe.get_all(
                "Payment Ledger Entry",
                filters={
                    "party_type": "Customer",
                    "party": ["in", customers],
                    "company": ["in", companies],
                    "delinked": 0,
                    "voucher_type": ["in", ["Payment Entry", "Journal Entry"]],
                    "against_voucher_type": "Sales Invoice",
                    "posting_date": [">=", frappe.utils.add_days(nowdate(), -days)],
                },
                order_by="posting_date asc, creation asc",
                pluck="name",
            )
            for name in ples:
                try:
                    res = process_ple(name)
                    if res:
                        created.append(res)
                except Exception:
                    frappe.log_error(title="Referral Engine", message=frappe.get_traceback())
    reversed_ = reverse_delinked()
    if created or reversed_:
        frappe.log_error(
            title="Referral Sync",
            message=f"Created {len(created)} line(s): {', '.join(created)}\nReversed {len(reversed_)} line(s): {', '.join(reversed_)}",
        )
    return {"created": created, "reversed": reversed_}


def refresh_window_fields():
    """Daily: current month number, window status, month 13 / month 24 notices."""
    from motley_referral import notifications

    today = getdate(nowdate())
    for ref in frappe.get_all(
        "Partner Referral",
        filters={"status": "Acknowledged"},
        fields=["name", "commission_start_date", "window_status", "current_month_no", "referral_partner"],
    ):
        if not ref.commission_start_date:
            vals = {"current_month_no": 0, "window_status": "Awaiting first payment"}
            frappe.db.set_value("Partner Referral", ref.name, vals, update_modified=False)
            continue
        partner = get_partner(ref.referral_partner)
        r = partner_rates(partner)
        m = month_no_for(ref.commission_start_date, today)
        if m <= r["y1_months"]:
            status = "Year 1"
        elif m <= r["y1_months"] + r["y2_months"]:
            status = "Year 2"
        else:
            status = "Ended"
        frappe.db.set_value(
            "Partner Referral", ref.name, {"current_month_no": min(m, r["y1_months"] + r["y2_months"]), "window_status": status},
            update_modified=False,
        )
        if status != ref.window_status:
            doc = frappe.get_doc("Partner Referral", ref.name)
            if status == "Year 2":
                _safe(notifications.notify, "month13", ref=doc)
            elif status == "Ended":
                _safe(notifications.notify, "month24", ref=doc)
        refresh_referral_totals(ref.name)


def expire_old_referrals():
    from motley_referral import notifications

    days = settings().referral_expiry_days or 90
    cutoff = frappe.utils.add_days(nowdate(), -days)
    for name in frappe.get_all(
        "Partner Referral", filters={"status": "Submitted", "submitted_on": ["<", cutoff]}, pluck="name"
    ):
        doc = frappe.get_doc("Partner Referral", name)
        doc.flags.ignore_permissions = True
        doc.status = "Expired"
        doc.save()
        _safe(notifications.notify, "expired", ref=doc)


def alert_overdue_statements():
    from motley_referral import notifications

    for name in frappe.get_all(
        "Referral Commission Statement",
        filters={"docstatus": 1, "status": "Approved", "due_date": ["<", nowdate()], "overdue_alert_sent": 0},
        pluck="name",
    ):
        st = frappe.get_doc("Referral Commission Statement", name)
        _safe(notifications.notify, "overdue", statement=st)
        frappe.db.set_value("Referral Commission Statement", name, "overdue_alert_sent", 1, update_modified=False)


def daily():
    _safe(sync_ple)
    _safe(refresh_window_fields)
    _safe(expire_old_referrals)
    _safe(alert_overdue_statements)


def hourly_statement_tick():
    """Runs hourly; creates the monthly statements on the Settings run day and hour (idempotent)."""
    s = settings()
    now = frappe.utils.now_datetime()
    run_day = min(max(int(s.run_day or 1), 1), 28)
    run_hour = frappe.utils.get_time(s.run_time or "06:00:00").hour
    if now.day == run_day and now.hour == run_hour:
        from motley_referral.referral_program.doctype.referral_commission_statement.referral_commission_statement import (
            create_monthly_statements,
        )

        _safe(create_monthly_statements)
