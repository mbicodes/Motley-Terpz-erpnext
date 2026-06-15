import frappe
from frappe.utils import flt

STANDARD_OP_COST_DESC = "Operating Cost as per Work Order / BOM"


def _build_cost_map(work_order_name, company):
    """
    Walk all submitted Job Cards for a Work Order.
    For each time log row → workstation → Workstation Operating Cost components
    → Operating Component Account (per company) → sum cost by expense_account.

    Returns dict: { expense_account: {"amount": float, "label": component_name} }
    Falls back to empty dict if no component-account mappings exist.
    """
    cost_map = {}

    job_cards = frappe.get_all(
        "Job Card",
        filters={"work_order": work_order_name, "docstatus": 1},
        fields=["name", "workstation"],
    )

    # Cache lookups to avoid repeated DB hits
    ws_components_cache = {}   # workstation → list of {operating_component, operating_cost}
    comp_account_cache = {}    # (operating_component, company) → expense_account

    for jc in job_cards:
        jc_doc = frappe.get_doc("Job Card", jc.name)

        for row in (jc_doc.time_logs or []):
            ws_name = row.get("custom_workstation") or jc.workstation or ""
            if not ws_name:
                continue

            time_hrs = flt(row.get("time_in_mins") or 0) / 60.0
            if not time_hrs:
                continue

            if ws_name not in ws_components_cache:
                ws_components_cache[ws_name] = frappe.get_all(
                    "Workstation Operating Cost",
                    filters={"parent": ws_name, "parenttype": "Workstation"},
                    fields=["operating_component", "operating_cost"],
                )

            for comp in ws_components_cache[ws_name]:
                if not comp.operating_component or not flt(comp.operating_cost):
                    continue

                cache_key = (comp.operating_component, company)
                if cache_key not in comp_account_cache:
                    comp_account_cache[cache_key] = frappe.db.get_value(
                        "Operating Component Account",
                        {"parent": comp.operating_component,
                         "parenttype": "Operating Component",
                         "company": company},
                        "expense_account",
                    ) or ""
                expense_account = comp_account_cache[cache_key]
                if not expense_account:
                    continue

                component_cost = time_hrs * flt(comp.operating_cost)
                if expense_account not in cost_map:
                    cost_map[expense_account] = {"amount": 0.0, "label": comp.operating_component}
                cost_map[expense_account]["amount"] += component_cost

    return cost_map


def set_operating_cost_accounts(doc, method=None):
    """
    On validate of a Manufacture Stock Entry:
    Replace the single ERPNext operating cost row with per-expense-account rows
    derived from Workstation Operating Cost components.
    Falls back to wo.total_operating_cost on the default account if no mapping exists.
    """
    if doc.purpose != "Manufacture" or not doc.work_order:
        return

    cost_map = _build_cost_map(doc.work_order, doc.company)

    # Remove the standard single operating cost row regardless
    doc.additional_costs = [
        r for r in (doc.additional_costs or [])
        if r.description != STANDARD_OP_COST_DESC
    ]

    if cost_map:
        for expense_account, info in cost_map.items():
            if info["amount"] > 0:
                doc.append("additional_costs", {
                    "expense_account": expense_account,
                    "description": f"{info['label']}",
                    "amount": info["amount"],
                })
    else:
        # Fallback: lump sum on default account
        wo = frappe.get_doc("Work Order", doc.work_order)
        wo_total = flt(wo.total_operating_cost)
        if wo_total and flt(wo.qty):
            amount = (wo_total / flt(wo.qty)) * flt(doc.fg_completed_qty)
            company_account = frappe.db.get_value(
                "Company", doc.company,
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


@frappe.whitelist()
def get_wo_cost_breakdown(work_order, company, fg_completed_qty=None, wo_qty=None):
    """
    Returns per-expense-account cost breakdown for a Work Order's submitted Job Cards.
    Called from Stock Entry JS on form open.
    """
    cost_map = _build_cost_map(work_order, company)

    if cost_map:
        return [
            {"expense_account": acc, "description": info["label"], "amount": info["amount"]}
            for acc, info in cost_map.items()
            if info["amount"] > 0
        ]

    # Fallback: wo.total_operating_cost proportional to fg qty
    wo_total = flt(frappe.db.get_value("Work Order", work_order, "total_operating_cost"))
    qty = flt(wo_qty) or flt(frappe.db.get_value("Work Order", work_order, "qty")) or 1
    fg_qty = flt(fg_completed_qty) or qty
    amount = (wo_total / qty) * fg_qty if wo_total else 0

    if not amount:
        return []

    company_account = frappe.db.get_value(
        "Company", company,
        ["expenses_included_in_valuation", "default_operating_cost_account"],
        as_dict=1,
    )
    expense_account = (
        company_account.default_operating_cost_account
        or company_account.expenses_included_in_valuation
    )
    return [{"expense_account": expense_account, "description": STANDARD_OP_COST_DESC, "amount": amount}]
