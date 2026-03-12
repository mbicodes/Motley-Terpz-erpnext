# Copyright (c) 2026, Your Company
# For license information, please see license.txt

import frappe
from frappe.utils import today


@frappe.whitelist()
def get_stock_summary(from_date=None, to_date=None):
    """
    Fetch stock summary grouped by Item Group.
    Calls the Stock Balance Report directly so numbers always match.
    Date range: beginning of time → today.
    Warehouses: from Stock Summary Setting.
    """
    from erpnext.stock.report.stock_balance.stock_balance import execute

    # Get warehouses from setting
    setting = frappe.get_single("Stock Summary Setting")
    warehouses = [row.warehouse for row in setting.warehouses if row.warehouse]

    if not warehouses:
        return []

    if not to_date:
        to_date = today()
    
    if not from_date:
        # Default to 1 month before to_date if not provided
        from_date = frappe.utils.add_months(to_date, -1)

    filters = frappe._dict(
        {
            "company": frappe.defaults.get_user_default("Company"),
            "from_date": from_date,
            "to_date": to_date,
            "warehouse": warehouses,
            "show_stock_ageing_data": False,
            "show_variant_attributes": False,
            "include_zero_stock_items": False,
            "ignore_closing_balance": True,
        }
    )

    _columns, data = execute(filters)

    # Aggregate by item_group
    group_map = {}
    for row in data:
        ig = row.get("item_group")
        if not ig:
            continue

        if ig not in group_map:
            group_map[ig] = {"item_group": ig, "balance_qty": 0, "reserved_qty": 0}

        group_map[ig]["balance_qty"] += row.get("bal_qty", 0) or 0
        group_map[ig]["reserved_qty"] += row.get("reserved_stock", 0) or 0

    result = []
    for ig in sorted(group_map):
        entry = group_map[ig]
        entry["available_qty"] = entry["balance_qty"] - entry["reserved_qty"]
        result.append(entry)

    return result
