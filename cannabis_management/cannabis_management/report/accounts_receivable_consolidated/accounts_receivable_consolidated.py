import frappe
from frappe.utils import getdate

from erpnext.accounts.report.accounts_receivable.accounts_receivable import (
    execute as ar_execute,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    company = filters.get("company")

    if company and frappe.get_cached_value("Company", company, "is_group"):
        result = _run_consolidated(filters)
    else:
        result = ar_execute(filters)

    result = list(result)
    result[1] = _apply_date_range(result[1], filters.get("from_date"), filters.get("to_date"))
    return tuple(result)


def _run_consolidated(filters):
    children = _descendant_companies(filters.get("company"))
    if not children:
        return ar_execute(filters)

    columns = None
    skip_total_row = 0
    merged = []
    for child in children:
        child_filters = frappe._dict(filters)
        child_filters.company = child
        result = ar_execute(child_filters)
        cols, data = result[0], result[1]
        if columns is None:
            columns = cols
            if len(result) > 5:
                skip_total_row = result[5]
        merged.extend(data or [])

    return columns, merged, None, None, None, skip_total_row


def _apply_date_range(data, from_date, to_date):
    if not (from_date or to_date) or not data:
        return data
    fd = getdate(from_date) if from_date else None
    td = getdate(to_date) if to_date else None
    kept = []
    for row in data:
        posting = row.get("posting_date")
        if posting:
            posting = getdate(posting)
            if (fd and posting < fd) or (td and posting > td):
                continue
        kept.append(row)
    return kept


def _descendant_companies(group_company):
    lft, rgt = frappe.get_cached_value("Company", group_company, ["lft", "rgt"])
    return frappe.get_all(
        "Company",
        filters={"lft": (">", lft), "rgt": ("<", rgt), "is_group": 0},
        order_by="lft",
        pluck="name",
    )
