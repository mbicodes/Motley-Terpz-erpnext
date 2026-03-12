import frappe

@frappe.whitelist(allow_guest=True)
def get_stock_by_item_group(item_group, _=None):
    items = frappe.db.sql("""
        SELECT 
            b.item_code, 
            i.item_name, 
            b.warehouse, 
            b.actual_qty, 
            b.reserved_qty
        FROM `tabBin` b
        INNER JOIN `tabItem` i ON i.name = b.item_code
        WHERE i.item_group = %s
            AND i.disabled = 0
            AND b.actual_qty != 0
            AND b.warehouse NOT LIKE 'Virtual%%'
        ORDER BY i.item_name
    """, (item_group,), as_dict=True)
    
    total_qty = sum(item.actual_qty or 0 for item in items)
    unique_items = len(set(item.item_code for item in items))
    low_stock = len([i for i in items if (i.actual_qty or 0) - (i.reserved_qty or 0) <= 0])
    
    return {
        "items": items,
        "summary": {
            "total_items": unique_items,
            "total_qty": total_qty,
            "low_stock_items": low_stock
        }
    }