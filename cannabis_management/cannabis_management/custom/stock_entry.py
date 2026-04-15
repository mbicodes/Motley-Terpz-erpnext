import frappe
from frappe import _


def validate(doc, method):
    """
    For any stock entry where material is going out (s_warehouse is set),
    if an item row has custom_project_mandatory checked:
    1. Ensure the project field is filled
    2. Fetch the available project qty from Stock Ledger Entry
    3. Block submission if qty exceeds available project qty
    """
    for item in doc.items:
        if not item.custom_project_mandatory:
            continue

        # Only validate items where material is going out (source warehouse is set)
        if not item.s_warehouse:
            continue

        if not item.project:
            frappe.throw(
                _("Row {0}: Project is mandatory for Item {1} as 'Project Mandatory' is checked").format(
                    item.idx, frappe.bold(item.item_code)
                )
            )

        available_qty = get_project_qty(item.item_code, item.s_warehouse, item.project)
        item.custom_project_back_qty = available_qty

        if item.qty > available_qty:
            frappe.throw(
                _("Row {0}: Qty ({1}) exceeds available Project Qty ({2}) for Item {3}, "
                  "Project {4}, Warehouse {5}").format(
                    item.idx,
                    frappe.bold(item.qty),
                    frappe.bold(available_qty),
                    frappe.bold(item.item_code),
                    frappe.bold(item.project),
                    frappe.bold(item.s_warehouse),
                )
            )

    # Calculate Total Quantity for finished goods only
    doc.total_quantity = sum(item.qty for item in doc.items if item.get("is_finished_item"))

    # ── For Repack: Match Valuation and Allow Zero Rates ──
    if doc.stock_entry_type == "Repack" and doc.get("custom_rosin_recording_reference"):
        # First: allow zero rate for outgoing items
        for item in doc.items:
            if item.s_warehouse and not item.t_warehouse:
                item.allow_zero_valuation_rate = 1
        
        # Second: distribute the input value (even if 0) across outputs
        set_repack_valuation(doc)


def set_repack_valuation(doc):
    """
    Custom valuation for Rosin Repack entries.
    Formula applied per 'block' (1 Raw Material followed by N Finished Goods).
    Example block: $1,808.50 RM / 563 total FG qty = $3.21 basic rate assigned to those specific FG rows.
    """
    from frappe.utils import flt
    
    blocks = []
    current_block = None
    
    # 1. Group items into clusters (1 Raw Material -> Many Finished Goods)
    for item in doc.items:
        if item.s_warehouse and not item.t_warehouse:
            # Start of a new yield operation
            current_block = {
                "rm_item": item,
                "fg_items": []
            }
            blocks.append(current_block)
        elif item.t_warehouse and not item.s_warehouse:
            if current_block is not None:
                current_block["fg_items"].append(item)
                
    # 2. Calculate and assign valuation rate per cluster independently
    for block in blocks:
        rm_item = block["rm_item"]
        fg_items = block["fg_items"]
        
        # Calculate Raw Material Amount
        rate = flt(rm_item.valuation_rate)
        if rate <= 0:
            rate = flt(frappe.db.get_value("Stock Ledger Entry", {
                "item_code": rm_item.item_code,
                "warehouse": rm_item.s_warehouse,
                "is_cancelled": 0
            }, "valuation_rate", order_by="posting_date desc, creation desc"))
        
        rm_item.basic_rate = rate
        rm_amount = flt(rm_item.qty) * rate
        rm_item.amount = rm_amount
        
        # Divide amount among this block's specific finished goods
        sum_fg_qty = sum(flt(fg.qty) for fg in fg_items)
        if sum_fg_qty > 0:
            new_rate = rm_amount / sum_fg_qty
            for fg in fg_items:
                fg.basic_rate = flt(new_rate, 4)
                fg.amount = flt(fg.qty) * fg.basic_rate



@frappe.whitelist()
def get_project_qty(item_code, warehouse, project):
    """
    Get the available qty for an Item in a specific Warehouse and Project
    by summing actual_qty from Stock Ledger Entry.
    """
    result = frappe.db.sql(
        """
        SELECT IFNULL(SUM(actual_qty), 0) as qty
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND warehouse = %s
          AND project = %s
          AND is_cancelled = 0
        """,
        (item_code, warehouse, project),
        as_dict=True,
    )

    return result[0].qty if result else 0