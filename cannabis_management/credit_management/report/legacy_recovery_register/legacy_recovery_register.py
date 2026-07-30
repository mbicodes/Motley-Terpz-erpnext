import frappe
from frappe.utils import flt


def execute(filters=None):
    """All invoices dated before the effective date, still open — collected on
    their original terms. Counts against the cap; reported separately."""
    eff = frappe.db.get_single_value("Credit Control Settings", "effective_date") or "2026-06-01"
    columns = [
        {"label": "Invoice", "fieldname": "name", "fieldtype": "Link", "options": "Sales Invoice", "width": 160},
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 220},
        {"label": "Posting Date", "fieldname": "posting_date", "fieldtype": "Date", "width": 110},
        {"label": "Due Date", "fieldname": "due_date", "fieldtype": "Date", "width": 110},
        {"label": "Grand Total", "fieldname": "grand_total", "fieldtype": "Currency", "width": 120},
        {"label": "Outstanding", "fieldname": "outstanding_amount", "fieldtype": "Currency", "width": 120},
    ]
    rows = frappe.get_all(
        "Sales Invoice",
        filters={"docstatus": 1, "outstanding_amount": [">", 0], "posting_date": ["<", eff]},
        fields=["name", "customer", "posting_date", "due_date", "grand_total", "outstanding_amount"],
        order_by="outstanding_amount desc",
    )
    total = sum(flt(r.outstanding_amount) for r in rows)
    if rows:
        rows.append({"customer": "TOTAL", "outstanding_amount": total})
    return columns, rows
