import frappe
from frappe.utils import getdate, get_last_day, flt
import calendar


@frappe.whitelist()
def get_payment_calendar(month=None, year=None, entity=None):
    today = getdate()
    month = int(month) if month else today.month
    year = int(year) if year else today.year

    first_day = getdate(f"{year}-{month:02d}-01")
    last_day = get_last_day(first_day)

    filters_scheduled = {
        "docstatus": 0,
        "posting_date": ["between", [first_day, last_day]],
        "payment_type": "Pay",
    }
    if entity and entity not in ("All", "all"):
        filters_scheduled["company"] = entity

    scheduled_payments = frappe.get_all(
        "Payment Entry",
        filters=filters_scheduled,
        fields=[
            "name", "party", "party_name", "paid_amount",
            "posting_date", "company", "mode_of_payment",
            "reference_no"
        ],
        order_by="posting_date asc",
    )

    filters_paid = {
        "docstatus": 1,
        "posting_date": ["between", [first_day, last_day]],
        "payment_type": "Pay",
    }
    if entity and entity not in ("All", "all"):
        filters_paid["company"] = entity

    paid_payments = frappe.get_all(
        "Payment Entry",
        filters=filters_paid,
        fields=[
            "name", "party", "party_name", "paid_amount",
            "posting_date", "company", "mode_of_payment",
            "reference_no"
        ],
        order_by="posting_date asc",
    )

    start_weekday = first_day.weekday()
    start_weekday_sun = (start_weekday + 1) % 7
    days_in_month = (last_day - first_day).days + 1
    month_label = f"{calendar.month_name[month]} {year}"

    payments_by_date = {}
    for p in scheduled_payments:
        d = str(p.posting_date)
        payments_by_date.setdefault(d, []).append({
            "name": p.name,
            "vendor": p.party_name or p.party,
            "amount": flt(p.paid_amount),
            "entity": p.company,
            "mode": p.mode_of_payment,
            "status": "Scheduled",
        })

    for p in paid_payments:
        d = str(p.posting_date)
        payments_by_date.setdefault(d, []).append({
            "name": p.name,
            "vendor": p.party_name or p.party,
            "amount": flt(p.paid_amount),
            "entity": p.company,
            "mode": p.mode_of_payment,
            "status": "Paid",
        })

    calendar_weeks = []
    current_week = [None] * start_weekday_sun

    for day_num in range(1, days_in_month + 1):
        date_str = f"{year}-{month:02d}-{day_num:02d}"
        day_obj = {
            "day": day_num,
            "date": date_str,
            "is_today": getdate(date_str) == today,
            "payments": payments_by_date.get(date_str, []),
        }
        current_week.append(day_obj)
        if len(current_week) == 7:
            calendar_weeks.append(current_week)
            current_week = []

    if current_week:
        while len(current_week) < 7:
            current_week.append(None)
        calendar_weeks.append(current_week)

    scheduled_total = sum(flt(p.paid_amount) for p in scheduled_payments)
    paid_total = sum(flt(p.paid_amount) for p in paid_payments)

    prev_month, prev_year = (12, year - 1) if month == 1 else (month - 1, year)
    next_month, next_year = (1, year + 1) if month == 12 else (month + 1, year)

    return {
        "calendar_weeks": calendar_weeks,
        "month_label": month_label,
        "month": month,
        "year": year,
        "summary": {
            "scheduled_total": scheduled_total,
            "paid_total": paid_total,
            "scheduled_count": len(scheduled_payments),
            "paid_count": len(paid_payments),
        },
        "prev": {"month": prev_month, "year": prev_year},
        "next": {"month": next_month, "year": next_year},
    }