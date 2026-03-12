import frappe
from frappe.utils import today, getdate


@frappe.whitelist()
def get_payable_summary(
    report_date=None, ageing_based_on="Due Date", calculate_ageing_with="Report Date"
):
    """
    Fetch Accounts Payable Summary data (aging buckets) for the given date.
    Calls the standard ERPNext report so numbers always match.
    Returns list of dicts with: party, outstanding, range1..range5
    """
    from erpnext.accounts.report.accounts_payable_summary.accounts_payable_summary import (
        execute,
    )

    if not report_date:
        report_date = today()

    company = frappe.defaults.get_user_default("Company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")

    filters = frappe._dict(
        {
            "company": company,
            "report_date": getdate(report_date),
            "ageing_based_on": ageing_based_on,
            "calculate_ageing_with": calculate_ageing_with,
            "range": "30, 60, 90, 120",
            "show_future_payments": 0,
            "show_gl_balance": 0,
            "show_sales_person": 0,
        }
    )

    _columns, data = execute(filters)

    result = []
    for row in data:
        result.append(
            {
                "party": row.get("party", ""),
                "outstanding": row.get("outstanding", 0),
                "range1": row.get("range1", 0),
                "range2": row.get("range2", 0),
                "range3": row.get("range3", 0),
                "range4": row.get("range4", 0),
                "range5": row.get("range5", 0),
            }
        )

    return result
