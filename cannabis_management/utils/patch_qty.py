import frappe

def patch_submitted_stock_entries():
    entries = frappe.get_all("Stock Entry", filters={"docstatus": 1})
    count = 0
    for entry in entries:
        doc = frappe.get_doc("Stock Entry", entry.name)
        total_qty = sum((item.qty) for item in doc.items if item.get("is_finished_item"))
        
        # update without triggering standard validations since docstatus=1
        if doc.get("total_quantity") != total_qty:
            frappe.db.set_value("Stock Entry", doc.name, "total_quantity", total_qty, update_modified=False)
            count += 1
            
    frappe.db.commit()
    print(f"Updated {count} submitted Stock Entries")
