import frappe
from frappe.utils import today, getdate, flt


@frappe.whitelist()
def get_sales_summary(from_date=None, to_date=None):
    """
    Fetch Item-wise Sales Register data and group by Item Group.
    Returns list of dicts with: item_group, stock_qty, amount
    """
    from erpnext.accounts.report.item_wise_sales_register.item_wise_sales_register import (
        execute,
    )

    if not from_date:
        from_date = today()
    
    if not to_date:
        to_date = today()

    company = frappe.defaults.get_user_default("Company")
    if not company:
        company = frappe.db.get_single_value("Global Defaults", "default_company")

    # We fetch data for the selected period
    filters = frappe._dict(
        {
            "company": company,
            "from_date": getdate(from_date), 
            "to_date": getdate(to_date),
            "group_by": "Item Group", # Let the report do the grouping if possible, but standard report grouping might add subtotals etc. 
                                      # Actually, standard report grouping adds subtotal rows which might be messy to parse.
                                      # Better to fetch raw item data and group ourselves for cleaner control.
        }
    )
    
    # Let's try fetching without grouping first to get raw lines
    filters.group_by = None

    # Execute returns columns, data, None, None, None, skip_total_row
    result_data = execute(filters)
    data = result_data[1]

    # Manual Grouping
    grouped_data = {}

    for row in data:
        item_group = row.get("item_group")
        if not item_group:
            continue
            
        if item_group not in grouped_data:
            grouped_data[item_group] = {
                "item_group": item_group,
                "stock_qty": 0.0,
                "amount": 0.0
            }
        
        grouped_data[item_group]["stock_qty"] += flt(row.get("stock_qty", 0))
        grouped_data[item_group]["amount"] += flt(row.get("amount", 0))

    # Convert to list
    result = list(grouped_data.values())
    
    # Sort by Item Group name
    result.sort(key=lambda x: x["item_group"])

    return result
