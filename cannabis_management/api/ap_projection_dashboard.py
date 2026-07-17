import json

import frappe
from frappe import _
from frappe.utils import add_days, add_months, flt, get_first_day, get_last_day, getdate, nowdate

ALLOWED_ROLES = ("System Manager", "Accounts Manager", "Accounts User")

FREQUENCY_STEP = {
    "Daily": lambda d: add_days(d, 1),
    "Weekly": lambda d: add_days(d, 7),
    "Monthly": lambda d: add_months(d, 1),
    "Quarterly": lambda d: add_months(d, 3),
    "Half-yearly": lambda d: add_months(d, 6),
    "Yearly": lambda d: add_months(d, 12),
}


def _check_permission():
    roles = frappe.get_roles()
    if not any(r in roles for r in ALLOWED_ROLES):
        frappe.throw(_("You are not permitted to view the AP Projection Dashboard"), frappe.PermissionError)


def _scope_companies():
    return frappe.get_list(
        "Company",
        fields=["name", "abbr"],
        order_by="name",
    )


def _intercompany_suppliers():
    return set(frappe.get_all("Company", pluck="name"))


@frappe.whitelist()
def get_scope_companies():
    _check_permission()
    return _scope_companies()


def _resolve_companies(companies):
    scope = {c.name for c in _scope_companies()}
    if not companies:
        return list(scope)
    if isinstance(companies, str):
        try:
            companies = json.loads(companies)
        except ValueError:
            companies = [c.strip() for c in companies.split(",") if c.strip()]
    companies = [c for c in companies if c in scope]
    return companies or list(scope)


def _bucket_definitions(from_date, to_date, weekly):
    buckets = [{"key": "overdue", "label": "Overdue", "start": None, "end": add_days(from_date, -1)}]
    cursor = from_date
    while cursor <= to_date:
        if weekly:
            start = cursor
            end = min(add_days(start, 6), to_date)
            cursor = add_days(end, 1)
        else:
            start = get_first_day(cursor) if cursor != from_date else cursor
            month_end = get_last_day(cursor)
            end = min(month_end, to_date)
            cursor = add_days(end, 1)
        label = (
            start.strftime("%b %-d") + "–" + end.strftime("%-d")
            if weekly
            else start.strftime("%b %Y")
        )
        buckets.append({"key": str(start), "label": label, "start": start, "end": end})
    return buckets


def _bucket_for(buckets, date):
    if date < buckets[1]["start"]:
        return buckets[0]["key"]
    for b in buckets[1:]:
        if b["start"] <= date <= b["end"]:
            return b["key"]
    return buckets[-1]["key"]


@frappe.whitelist()
def get_ap_projection(companies=None, forecast_days=60):
    _check_permission()

    forecast_days = int(forecast_days or 60)
    companies = _resolve_companies(companies)
    if not companies:
        return {
            "kpis": {"total_outstanding": 0, "total_recurring": 0, "grand_total": 0},
            "timeline": {"buckets": [], "outstanding": [], "recurring": []},
            "detail_rows": [],
        }

    today = getdate(nowdate())
    to_date = add_days(today, forecast_days)
    weekly = forecast_days <= 60
    buckets = _bucket_definitions(today, to_date, weekly)
    bucket_totals = {b["key"]: {"outstanding": 0.0, "recurring": 0.0} for b in buckets}

    detail_rows = []
    intercompany = _intercompany_suppliers()

    # ── Layer 1: Outstanding Purchase Invoices (confirmed liability) ────────
    # Intercompany invoices (supplier is itself another Company in the system,
    # e.g. one entity billing another) are internal transfers, not real
    # external AP, and must be excluded — same convention as ap_dashboard.py.
    outstanding_invoices = frappe.get_list(
        "Purchase Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0], "company": ["in", companies]},
        fields=["name", "company", "supplier", "supplier_name", "due_date", "outstanding_amount", "bill_no", "posting_date"],
        order_by="due_date asc",
    )
    outstanding_invoices = [pi for pi in outstanding_invoices if pi.supplier not in intercompany]

    total_outstanding = 0.0
    for pi in outstanding_invoices:
        amount = flt(pi.outstanding_amount)
        total_outstanding += amount
        due_date = getdate(pi.due_date) if pi.due_date else today
        bucket_totals[_bucket_for(buckets, due_date)]["outstanding"] += amount
        detail_rows.append(
            {
                "company": pi.company,
                "source_type": "Outstanding",
                "vendor": pi.supplier_name or pi.supplier,
                "amount": amount,
                "date": str(due_date),
                "reference": pi.bill_no or pi.name,
            }
        )

    # ── Layer 2: Recurring AP projected from active Auto Repeat records ─────
    auto_repeats = frappe.get_list(
        "Auto Repeat",
        filters={"reference_doctype": "Purchase Invoice", "disabled": 0},
        fields=["name", "reference_document", "frequency", "next_schedule_date", "end_date"],
    )

    ref_names = [ar.reference_document for ar in auto_repeats if ar.reference_document]
    ref_invoices = {}
    if ref_names:
        for pi in frappe.get_list(
            "Purchase Invoice",
            filters={"name": ["in", ref_names], "company": ["in", companies]},
            fields=["name", "company", "supplier", "supplier_name", "grand_total"],
        ):
            if pi.supplier in intercompany:
                continue
            ref_invoices[pi.name] = pi

    total_recurring = 0.0
    for ar in auto_repeats:
        ref = ref_invoices.get(ar.reference_document)
        if not ref or not ar.next_schedule_date:
            continue

        step = FREQUENCY_STEP.get(ar.frequency)
        if not step:
            continue

        cap = min(to_date, getdate(ar.end_date)) if ar.end_date else to_date
        cursor = getdate(ar.next_schedule_date)
        safety = 0
        while cursor <= cap and safety < 500:
            if cursor >= today:
                amount = flt(ref.grand_total)
                total_recurring += amount
                bucket_totals[_bucket_for(buckets, cursor)]["recurring"] += amount
                detail_rows.append(
                    {
                        "company": ref.company,
                        "source_type": "Recurring",
                        "vendor": ref.supplier_name or ref.supplier,
                        "amount": amount,
                        "date": str(cursor),
                        "reference": ar.name + " (" + ar.frequency + ")",
                    }
                )
            cursor = step(cursor)
            safety += 1

    detail_rows.sort(key=lambda r: r["date"])

    return {
        "kpis": {
            "total_outstanding": total_outstanding,
            "total_recurring": total_recurring,
            "grand_total": total_outstanding + total_recurring,
        },
        "timeline": {
            "buckets": [b["label"] for b in buckets],
            "outstanding": [bucket_totals[b["key"]]["outstanding"] for b in buckets],
            "recurring": [bucket_totals[b["key"]]["recurring"] for b in buckets],
        },
        "detail_rows": detail_rows,
    }
