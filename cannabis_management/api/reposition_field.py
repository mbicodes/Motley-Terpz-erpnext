import frappe

def run():
    doctype = "Stock Entry"
    fieldname = "total_quantity"
    insert_after = "total_outgoing_value"
    
    # Check if field exists
    cf_name = f"{doctype}-{fieldname}"
    if frappe.db.exists("Custom Field", cf_name):
        doc = frappe.get_doc("Custom Field", cf_name)
        doc.insert_after = insert_after
        doc.save(ignore_permissions=True)
        print(f"Update field {cf_name} insert_after to {insert_after}")
    else:
        # Create it if it doesn't exist? Wait, it should exist.
        print(f"Error: Custom Field {cf_name} not found!")

    # Also check and remove any property setters that might be conflicting
    frappe.db.delete("Property Setter", {"doc_type": doctype, "field_name": fieldname, "property": "insert_after"})
    
    # Finally clear cache
    frappe.clear_cache(doctype=doctype)
    frappe.db.commit()
    print("Done!")

if __name__ == "__main__":
    run()
