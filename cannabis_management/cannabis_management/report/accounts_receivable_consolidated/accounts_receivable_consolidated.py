"""Accounts Receivable, with group-company roll-up.

An exact duplicate of ERPNext's core **Accounts Receivable** report — same
filters, same columns, same row logic — with one addition: when the selected
Company is a *group* company (``is_group = 1``), the report is run for every
non-group company beneath it in the company tree and the rows are concatenated.
One run then shows the whole group's receivables at once, instead of opening the
report for each subsidiary one by one.

A non-group (leaf) company behaves exactly like the core report, so this can
stand in for it everywhere.

Implementation note: we delegate to the core ``execute`` rather than copy it, so
this stays in lock-step with ERPNext — every column, filter and calculation is
inherited, and only the company fan-out is ours.
"""

import frappe

from erpnext.accounts.report.accounts_receivable.accounts_receivable import (
    execute as ar_execute,
)


def execute(filters=None):
    filters = frappe._dict(filters or {})
    company = filters.get("company")

    # Not a group company (or none chosen) → behave exactly like core AR.
    if not (company and frappe.get_cached_value("Company", company, "is_group")):
        return ar_execute(filters)

    children = _descendant_companies(company)
    if not children:
        # A group with no subsidiaries — nothing to roll up; run it as-is.
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

    # No chart on the consolidated view: the core chart is per-company and would
    # only reflect the last subsidiary. The report's own grand-total row (the
    # report has add_total_row = 1) sums every subsidiary's rows together.
    return columns, merged, None, None, None, skip_total_row


def _descendant_companies(group_company):
    """Every non-group company beneath ``group_company`` in the company tree.

    Company is a nested set, so the descendants are exactly those whose lft/rgt
    fall inside the group's own — no recursion needed. Group nodes are skipped
    because transactions only ever post to leaf companies.
    """
    lft, rgt = frappe.get_cached_value("Company", group_company, ["lft", "rgt"])
    return frappe.get_all(
        "Company",
        filters={"lft": (">", lft), "rgt": ("<", rgt), "is_group": 0},
        order_by="lft",
        pluck="name",
    )
