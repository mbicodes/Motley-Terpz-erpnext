"""Credit Management — daily engine.

Recomputes, for every Credit Profile:
  * current exposure (open receivables across the customer's credit group)
  * past-due amount and oldest past-due age
  * hold status per the Stop Work Rule

…and the company-wide metrics + freeze state on Credit Control Settings.

Unfreeze is deliberately NOT automatic — policy requires Finance to confirm
in writing before lifting a freeze. The engine only *sets* a freeze on breach.
"""

import frappe
from frappe.utils import flt, getdate, now_datetime, date_diff, today


def _settings():
    return frappe.get_cached_doc("Credit Control Settings")


def group_customers(profile):
    """All customers sharing this profile's credit group (else just this one)."""
    if profile.credit_group:
        names = frappe.get_all(
            "Credit Profile",
            filters={"credit_group": profile.credit_group},
            pluck="customer",
        )
        return names or [profile.customer]
    return [profile.customer]


def receivable_snapshot(customers):
    """Open-invoice totals for a set of customers.

    Returns dict: total_outstanding, past_due_amount, oldest_past_due_days.
    Amounts are taken in invoice currency (Motley invoices are USD).
    """
    if not customers:
        return {"total_outstanding": 0.0, "past_due_amount": 0.0, "oldest_past_due_days": 0}

    rows = frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "customer": ["in", customers],
            "outstanding_amount": [">", 0],
        },
        fields=["outstanding_amount", "due_date"],
    )
    total = 0.0
    past_due = 0.0
    oldest = 0
    tdy = getdate(today())
    for r in rows:
        amt = flt(r.outstanding_amount)
        total += amt
        if r.due_date and getdate(r.due_date) < tdy:
            past_due += amt
            days = date_diff(tdy, getdate(r.due_date))
            oldest = max(oldest, days)
    return {
        "total_outstanding": total,
        "past_due_amount": past_due,
        "oldest_past_due_days": oldest,
    }


def compute_hold(profile, snapshot):
    """Return (hold_status, reason) per the Stop Work Rule.

    Disputed amounts are frozen — excluded from the line and from past-due so
    they never trigger a hold on their own.
    """
    s = _settings()

    # Manual Finance-set immediate hold always wins and is never auto-cleared.
    if profile.manual_hold:
        return "Immediate Hold", (profile.manual_hold_reason or "Manual hold set by Finance")

    # A missed payment-plan installment -> immediate hard hold on all new work.
    from cannabis_management.credit_management.doctype.payment_plan.payment_plan import has_missed_plan_payment
    if has_missed_plan_payment(profile.customer):
        return "Hard Hold", "Missed payment-plan installment"

    # Expired license -> immediate hold.
    expiry = frappe.db.get_value("Customer", profile.customer, "custom_license_expiry")
    if expiry and getdate(expiry) < getdate(today()):
        return "Immediate Hold", f"License expired on {expiry}"

    from cannabis_management.credit_management.doctype.ar_dispute.ar_dispute import disputed_total_for_customer
    disputed = disputed_total_for_customer(profile.customer)
    effective_exposure = max(0.0, flt(snapshot["total_outstanding"]) - disputed)
    effective_past_due = max(0.0, flt(snapshot["past_due_amount"]) - disputed)

    # Limit breach -> immediate hold (exposure over approved line).
    if profile.status in ("Credit Approved", "Payment Plan") and flt(profile.approved_line) > 0:
        if effective_exposure > flt(profile.approved_line):
            return "Immediate Hold", (
                f"Exposure ${effective_exposure:,.2f} exceeds approved line "
                f"${flt(profile.approved_line):,.2f}"
            )

    days = int(snapshot["oldest_past_due_days"])
    if effective_past_due > 0:
        if days > flt(s.hard_hold_days) or effective_past_due >= flt(s.hard_hold_amount):
            return "Hard Hold", f"${effective_past_due:,.2f} past due, oldest {days} day(s)"
        return "Warning", f"${effective_past_due:,.2f} past due, oldest {days} day(s)"

    return "None", ""


def recompute_profile(profile):
    """Recompute exposure + hold for one Credit Profile doc and save."""
    customers = group_customers(profile)
    snap = receivable_snapshot(customers)
    hold_status, reason = compute_hold(profile, snap)

    prev_hold = profile.hold_status
    profile.current_exposure = snap["total_outstanding"]
    profile.past_due_amount = snap["past_due_amount"]
    profile.oldest_past_due_days = snap["oldest_past_due_days"]
    profile.hold_status = hold_status
    profile.hold_reason = reason
    if hold_status != "None" and prev_hold in (None, "None"):
        profile.hold_since = now_datetime()
    if hold_status == "None":
        profile.hold_since = None
    profile.last_computed_on = now_datetime()
    profile.save(ignore_permissions=True)
    return hold_status


def recompute_all_profiles():
    for name in frappe.get_all("Credit Profile", pluck="name"):
        try:
            recompute_profile(frappe.get_doc("Credit Profile", name))
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"Credit recompute failed: {name}")


def _total_ar_split():
    """Total AR from GL, split into new-book vs legacy by effective_date."""
    s = _settings()
    eff = s.effective_date or "2026-06-01"
    total = frappe.db.sql(
        """SELECT COALESCE(SUM(debit - credit), 0)
           FROM `tabGL Entry`
           WHERE party_type = 'Customer' AND is_cancelled = 0""",
    )[0][0]
    # New book vs legacy by posting date.
    new_book = frappe.db.sql(
        """SELECT COALESCE(SUM(debit - credit), 0)
           FROM `tabGL Entry`
           WHERE party_type = 'Customer' AND is_cancelled = 0
             AND posting_date >= %s""",
        (eff,),
    )[0][0]
    total = flt(total)
    new_book = flt(new_book)
    return total, new_book, total - new_book


def recompute_freeze_and_metrics():
    """Update live metrics on Credit Control Settings and SET the freeze on
    breach. Never auto-unfreezes (policy: Finance confirms in writing)."""
    s = frappe.get_doc("Credit Control Settings")
    total_ar, new_book, legacy = _total_ar_split()
    s.total_ar = total_ar
    s.new_book_ar = new_book
    s.legacy_ar = legacy
    s.metrics_updated_on = now_datetime()

    # Phase 1 auto-freeze trigger: Total AR cap. (DSO/CEI freezes land in Phase 4.)
    if not s.is_frozen and flt(total_ar) >= flt(s.ar_cap):
        s.is_frozen = 1
        s.frozen_reason = f"Total AR ${total_ar:,.2f} reached the ${flt(s.ar_cap):,.2f} cap"
        s.frozen_since = now_datetime()
    s.save(ignore_permissions=True)


def run_daily():
    """Scheduler entry point."""
    from cannabis_management.credit_management import reporting
    reporting.check_dispute_clocks()
    recompute_all_profiles()
    recompute_freeze_and_metrics()
    frappe.db.commit()
