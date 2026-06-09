import frappe
from frappe.utils import flt

STANDARD_OP_COST_DESC = "Operating Cost as per Work Order / BOM"


def set_operating_cost_accounts(doc, method=None):
    """
    For Manufacture Stock Entries linked to a Work Order:
    Replace the standard single operating-cost Additional Cost row with one row
    per expense account, derived from submitted Job Card time logs → workstation
    operating components → Operating Component Account mapping for this company.
    """
    if doc.purpose != "Manufacture" or not doc.work_order:
        return

    company = doc.company
    cost_map = {}  # expense_account → {"amount": float, "label": str}

    job_cards = frappe.get_all(
        "Job Card",
        filters={"work_order": doc.work_order, "docstatus": 1},
        fields=["name", "workstation"],
    )

    op_ws_cache = {}

    for jc in job_cards:
        jc_doc = frappe.get_doc("Job Card", jc.name)

        for row in (jc_doc.time_logs or []):
            ws_name = None
            if row.get("operation"):
                op = row.operation
                if op not in op_ws_cache:
                    op_ws_cache[op] = frappe.db.get_value("Operation", op, "workstation") or ""
                ws_name = op_ws_cache[op]
            if not ws_name:
                ws_name = jc.workstation or ""
            if not ws_name:
                continue

            time_hrs = flt(row.get("time_in_mins") or 0) / 60.0
            if not time_hrs:
                continue

            ws_costs = frappe.get_all(
                "Workstation Operating Cost",
                filters={"parent": ws_name, "parenttype": "Workstation"},
                fields=["operating_component", "operating_cost"],
            )

            for comp_row in ws_costs:
                if not comp_row.operating_component or not flt(comp_row.operating_cost):
                    continue

                expense_account = frappe.db.get_value(
                    "Operating Component Account",
                    {
                        "parent": comp_row.operating_component,
                        "parenttype": "Operating Component",
                        "company": company,
                    },
                    "expense_account",
                )
                if not expense_account:
                    continue

                component_cost = time_hrs * flt(comp_row.operating_cost)

                if expense_account not in cost_map:
                    cost_map[expense_account] = {
                        "amount": 0.0,
                        "label": comp_row.operating_component,
                    }
                cost_map[expense_account]["amount"] += component_cost

    if not cost_map:
        return

    # Remove the standard single operating cost row
    to_remove = [r for r in (doc.additional_costs or []) if r.description == STANDARD_OP_COST_DESC]
    for r in to_remove:
        doc.additional_costs.remove(r)

    for expense_account, info in cost_map.items():
        if info["amount"] > 0:
            doc.append("additional_costs", {
                "expense_account": expense_account,
                "description": f"{info['label']} Operating Cost",
                "amount": info["amount"],
            })
