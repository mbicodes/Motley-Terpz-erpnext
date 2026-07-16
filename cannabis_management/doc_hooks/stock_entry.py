import frappe
from frappe.utils import flt

STANDARD_OP_COST_DESC = "Operating Cost as per Work Order / BOM"


def sync_row_uom_with_item(doc, method=None):
    """
    Keep each item row's UOM consistent with the Item's current stock UOM.
    Rows created before an item's UOM was corrected keep the stale value
    (e.g. uom 'Nos' with conversion_factor 1 while the item is now 'Gram').
    Rows with a real UOM conversion (factor != 1) are left untouched.
    """
    for row in doc.get("items", []):
        if not row.item_code:
            continue

        stock_uom = frappe.get_cached_value("Item", row.item_code, "stock_uom")
        if not stock_uom:
            continue

        if row.uom == stock_uom and row.stock_uom == stock_uom:
            continue

        if row.uom != stock_uom and flt(row.conversion_factor or 1) != 1:
            continue

        row.uom = stock_uom
        row.stock_uom = stock_uom
        row.conversion_factor = 1
        row.transfer_qty = flt(row.qty)


def populate_micron_finished_goods(doc, method=None):
    """
    For a Manufacture Stock Entry from a Work Order:
    if any linked Job Card has micron_collection_detail rows with an `item` set,
    replace the standard BOM-derived finished good with those items.
    Cost is split proportionally (per gram) from total raw material value.
    """
    if doc.purpose != "Manufacture" or not doc.work_order:
        return

    job_cards = frappe.get_all(
        "Job Card",
        filters={"work_order": doc.work_order},
        fields=["name"],
    )

    micron_items = []
    for jc in job_cards:
        jc_doc = frappe.get_doc("Job Card", jc.name)

        # Only use micron flow when the linked Operation has the flag enabled
        use_micron = bool(frappe.db.get_value(
            "Operation", jc_doc.operation, "custom_stock_entry_based_on_micron"
        )) if jc_doc.operation else False

        if not use_micron:
            continue

        for row in (jc_doc.custom_micron_collection_detail or []):
            if row.item and flt(row.grams_collected) > 0:
                micron_items.append({
                    "item_code": row.item,
                    "qty": flt(row.grams_collected),
                })

    if not micron_items:
        return  # micron flow not enabled or no micron rows — use standard BOM finished good

    # Get target warehouse, expense_account, and cost_center from existing FG item
    t_warehouse = None
    expense_account = None
    cost_center = None
    for se_item in doc.items:
        if getattr(se_item, "is_finished_item", 0):
            if se_item.t_warehouse and not t_warehouse:
                t_warehouse = se_item.t_warehouse
            if se_item.expense_account and not expense_account:
                expense_account = se_item.expense_account
            if se_item.cost_center and not cost_center:
                cost_center = se_item.cost_center
    if not t_warehouse:
        t_warehouse = frappe.db.get_value("Work Order", doc.work_order, "fg_warehouse") or ""
    if not expense_account or not cost_center:
        co = frappe.db.get_value(
            "Company", doc.company,
            ["stock_adjustment_account", "cost_center"],
            as_dict=1,
        ) or {}
        if not expense_account:
            expense_account = co.get("stock_adjustment_account") or ""
        if not cost_center:
            cost_center = co.get("cost_center") or ""

    # Sum raw material value (source-only items)
    total_rm_value = sum(
        flt(i.basic_amount)
        for i in doc.items
        if i.s_warehouse and not i.t_warehouse and not getattr(i, "is_finished_item", 0)
    )

    total_grams = sum(r["qty"] for r in micron_items)
    rate_per_gram = (total_rm_value / total_grams) if total_grams else 0.0

    # Remove standard finished good rows
    doc.items = [i for i in doc.items if not getattr(i, "is_finished_item", 0)]

    # Add one row per micron item
    for row in micron_items:
        stock_uom = frappe.db.get_value("Item", row["item_code"], "stock_uom") or "Gram"
        doc.append("items", {
            "item_code": row["item_code"],
            "qty": row["qty"],
            "transfer_qty": row["qty"],
            "uom": "Gram",
            "stock_uom": stock_uom,
            "conversion_factor": 1.0,
            "t_warehouse": t_warehouse,
            "is_finished_item": 1,
            "basic_rate": rate_per_gram,
            "basic_amount": rate_per_gram * row["qty"],
            "valuation_rate": rate_per_gram,
            "amount": rate_per_gram * row["qty"],
            "expense_account": expense_account,
            "cost_center": cost_center,
        })

    doc.fg_completed_qty = total_grams


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

    # Clear all additional costs — we fully own this field for Manufacture SEs.
    # Clearing prevents duplicate rows when validate fires more than once.
    doc.additional_costs = []

    if cost_map:
        for expense_account, info in cost_map.items():
            if info["amount"] > 0:
                doc.append("additional_costs", {
                    "expense_account": expense_account,
                    "description": info["label"],
                    "amount": info["amount"],
                    "base_amount": info["amount"],
                    "exchange_rate": 1.0,
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
                "base_amount": amount,
                "exchange_rate": 1.0,
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
