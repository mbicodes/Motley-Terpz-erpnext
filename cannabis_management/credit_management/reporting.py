"""Credit Management — Friday report, Red List, finance charges, periodic reviews."""

import frappe
from frappe.utils import flt, getdate, today, now_datetime, add_days, fmt_money

STATUS_TAG = {
    "COD": "", "Credit Approved": "", "Payment Plan": "PLAN",
    "Workout": "WORKOUT", "Frozen": "FROZEN",
}


def build_red_list():
    """Every past-due / held / plan / workout / disputed account."""
    from cannabis_management.credit_management.doctype.collection_activity.collection_activity import latest_for_customer
    from cannabis_management.credit_management.doctype.ar_dispute.ar_dispute import disputed_total_for_customer

    profiles = frappe.get_all(
        "Credit Profile",
        filters={"hold_status": ["!=", "None"]},
        fields=["customer", "status", "hold_status", "hold_reason",
                "past_due_amount", "oldest_past_due_days", "current_exposure", "approved_line"],
        order_by="past_due_amount desc",
    )
    rows = []
    for p in profiles:
        tag = STATUS_TAG.get(p.status) or (p.hold_status.upper() if p.hold_status else "")
        if disputed_total_for_customer(p.customer) > 0:
            tag = (tag + " DISPUTE").strip()
        act = latest_for_customer(p.customer) or {}
        rows.append({
            "customer": p.customer,
            "balance": flt(p.current_exposure),
            "past_due": flt(p.past_due_amount),
            "days": p.oldest_past_due_days,
            "status": p.hold_status,
            "tag": tag,
            "promise_to_pay": act.get("promise_to_pay_date"),
            "last_contact": act.get("activity_date"),
            "next_action": act.get("next_action"),
        })
    return rows


def plan_book_total():
    plans = frappe.get_all("Payment Plan", filters={"status": "Active"},
                           fields=["plan_balance", "recovered_to_date"])
    return {
        "balance": sum(flt(p.plan_balance) for p in plans),
        "recovered": sum(flt(p.recovered_to_date) for p in plans),
        "count": len(plans),
    }


def _m(v):
    return fmt_money(flt(v), currency="USD")


def send_friday_report():
    """Weekly Finance -> MD & CEO report."""
    s = frappe.get_doc("Credit Control Settings")
    red = build_red_list()
    pb = plan_book_total()

    recipients = _role_emails(["Managing Director", "Chief Executive Officer", "Finance Manager"])
    if not recipients:
        frappe.log_error("No MD/CEO/Finance recipients for Friday credit report", "Credit Friday Report")
        return

    red_rows = "".join(
        f"<tr><td>{frappe.utils.escape_html(r['customer'])}</td>"
        f"<td style='text-align:right'>{_m(r['balance'])}</td>"
        f"<td style='text-align:right'>{_m(r['past_due'])}</td>"
        f"<td style='text-align:right'>{r['days']}</td>"
        f"<td>{r['status']}{(' · ' + r['tag']) if r['tag'] else ''}</td>"
        f"<td>{r.get('promise_to_pay') or ''}</td>"
        f"<td>{frappe.utils.escape_html(str(r.get('next_action') or ''))}</td></tr>"
        for r in red[:200]
    ) or "<tr><td colspan='7'>No past-due accounts.</td></tr>"

    freeze_line = (
        f"<p style='color:#b91c1c'><b>COMPANY-WIDE FREEZE ACTIVE</b> — {frappe.utils.escape_html(s.frozen_reason or '')}</p>"
        if s.is_frozen else ""
    )

    message = f"""
        <h2>Credit &amp; AR — Friday Report</h2>
        {freeze_line}
        <h3>Metrics vs Thresholds</h3>
        <ul>
          <li>Total AR: <b>{_m(s.total_ar)}</b> (cap {_m(s.ar_cap)}) — New book {_m(s.new_book_ar)} · Legacy {_m(s.legacy_ar)}</li>
          <li>DSO (new book): {flt(s.current_dso):.1f} (target {s.dso_target_days}, breach {s.dso_breach_days})</li>
          <li>CEI (new book): {flt(s.current_cei):.0f}% (target {s.cei_target_pct}%, breach &lt;{s.cei_breach_pct}%)</li>
        </ul>
        <h3>Plan Book</h3>
        <p>{pb['count']} active plan(s) — balance {_m(pb['balance'])}, recovered {_m(pb['recovered'])}</p>
        <h3>Red List ({len(red)} accounts)</h3>
        <table border="1" cellspacing="0" cellpadding="5" style="border-collapse:collapse;font-size:12px;">
          <thead><tr style="background:#f1f5f9">
            <th>Customer</th><th>Balance</th><th>Past Due</th><th>Days</th>
            <th>Status</th><th>Promise</th><th>Next Action</th>
          </tr></thead>
          <tbody>{red_rows}</tbody>
        </table>
    """
    frappe.sendmail(recipients=recipients, subject=f"Credit & AR — Friday Report {today()}", message=message)


def _role_emails(roles):
    users = set()
    for role in roles:
        for u in frappe.get_all("Has Role", filters={"role": role, "parenttype": "User"}, pluck="parent"):
            if frappe.db.get_value("User", u, "enabled") and "@" in (u or ""):
                users.add(u)
    return list(users)


# ---------------------------------------------------------------------------
# Finance charges — generate DRAFT Journal Entries for Finance review
# ---------------------------------------------------------------------------

def accrue_finance_charges():
    """1.5%/month simple non-compounding on undisputed past-due balances, only
    under agreements carrying the counsel-approved clause. Creates DRAFT JEs."""
    s = frappe.get_doc("Credit Control Settings")
    rate = flt(s.finance_charge_rate_monthly)
    if flt(s.max_lawful_rate_monthly) > 0:
        rate = min(rate, flt(s.max_lawful_rate_monthly))

    eligible = frappe.get_all(
        "Credit Agreement",
        filters={"signed": 1, "counsel_approved_finance_charge_clause": 1},
        pluck="customer",
    )
    created = 0
    for customer in set(eligible):
        try:
            if _accrue_for_customer(customer, rate):
                created += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Finance charge accrual: {customer}")
    frappe.db.commit()
    return created


def _accrue_for_customer(customer, monthly_rate):
    from cannabis_management.credit_management.doctype.ar_dispute.ar_dispute import disputed_total_for_customer
    profile = frappe.db.get_value(
        "Credit Profile", {"customer": customer}, ["past_due_amount", "oldest_past_due_days"], as_dict=True
    )
    if not profile:
        return False
    disputed = disputed_total_for_customer(customer)
    base = max(0.0, flt(profile.past_due_amount) - disputed)
    days = int(profile.oldest_past_due_days or 0)
    if base <= 0 or days <= 0:
        return False
    charge = round(base * (monthly_rate / 100.0) * (days / 30.0), 2)
    if charge < 1:
        return False

    # Resolve accounts; skip (log) if not configurable — never post to the wrong account.
    company = frappe.defaults.get_global_default("company") or frappe.db.get_value("Company", {}, "name")
    receivable = frappe.db.get_value("Company", company, "default_receivable_account")
    income = frappe.db.get_value("Account", {"account_name": ["like", "%Finance Charge%"], "company": company})
    if not (receivable and income):
        frappe.log_error(
            f"Finance charge ${charge} for {customer} not posted — missing receivable/'Finance Charges' account.",
            "Credit Finance Charge",
        )
        return False

    je = frappe.get_doc({
        "doctype": "Journal Entry", "voucher_type": "Journal Entry", "company": company,
        "posting_date": today(),
        "user_remark": f"Finance charge (draft): {monthly_rate}%/mo x {days}d on ${base:,.2f} past due — {customer}",
        "accounts": [
            {"account": receivable, "party_type": "Customer", "party": customer, "debit_in_account_currency": charge},
            {"account": income, "credit_in_account_currency": charge},
        ],
    })
    je.insert(ignore_permissions=True)  # stays Draft for Finance review
    return True


# ---------------------------------------------------------------------------
# Dispute clock + periodic review reminders
# ---------------------------------------------------------------------------

def check_dispute_clocks():
    """Disputes nobody is actively reconciling convert back to past due."""
    tdy = getdate(today())
    for d in frappe.get_all("AR Dispute", filters={"status": "Open"}, fields=["name", "meeting_by"]):
        if d.meeting_by and getdate(d.meeting_by) < tdy:
            doc = frappe.get_doc("AR Dispute", d.name)
            doc.status = "Reverted to Past Due"
            doc.save(ignore_permissions=True)
    frappe.db.commit()


def monthly_workout_review_reminder():
    stale = add_days(getdate(today()), -30)
    workouts = frappe.get_all("Workout Terms", filters={"status": "Active"},
                              fields=["name", "customer", "last_review_date", "starting_balance", "recovered_to_date"])
    lines = []
    for w in workouts:
        if not w.last_review_date or getdate(w.last_review_date) < stale:
            lines.append(f"{w.customer}: start {_m(w.starting_balance)}, recovered {_m(w.recovered_to_date)}")
    if lines:
        to = _role_emails(["Managing Director", "Finance Manager"])
        if to:
            frappe.sendmail(recipients=to, subject="Workout accounts — monthly review due",
                            message="<br>".join(lines))
