import frappe
from frappe.utils import flt

STANDARD_OP_COST_DESC = "Operating Cost as per Work Order / BOM"


def set_operating_cost_accounts(doc, method=None):
    """
    For Manufacture Stock Entries linked to a Work Order:
    Replace the ERPNext-calculated operating cost amount with wo.total_operating_cost
    (proportional to fg_completed_qty / wo.qty).
    """
    if doc.purpose != "Manufacture" or not doc.work_order:
        return

    wo = frappe.get_doc("Work Order", doc.work_order)
    wo_total = flt(wo.total_operating_cost)

    if not wo_total or not flt(wo.qty):
        return

    amount = (wo_total / flt(wo.qty)) * flt(doc.fg_completed_qty)

    # Replace the existing standard row if present
    for row in (doc.additional_costs or []):
        if row.description == STANDARD_OP_COST_DESC:
            row.amount = amount
            return

    # No standard row yet — add one
    company_account = frappe.db.get_value(
        "Company", wo.company,
        ["expenses_included_in_valuation", "default_operating_cost_account"],
        as_dict=1,
    )
    expense_account = (
        company_account.default_operating_cost_account
        or company_account.expenses_included_in_valuation
    )
    doc.append("additional_costs", {
        "expense_account": expense_account,
        "description": STANDARD_OP_COST_DESC,
        "amount": amount,
    })
