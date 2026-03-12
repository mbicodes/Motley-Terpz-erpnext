import frappe

def update_sales_invoice_delivery_status(doc, method):
    """
    Updates the 'custom_delivery_note_created' checkbox on the linked Sales Invoice(s).
    """
    sales_invoices = set()
    for item in doc.items:
        if item.against_sales_invoice:
            sales_invoices.add(item.against_sales_invoice)

    if not sales_invoices:
        return

    for si_name in sales_invoices:
        # Check if there exists ANY Delivery Note for this SI that is NOT a Draft (docstatus != 0)
        # This includes Submitted (1) and Cancelled (2)
        exists = frappe.db.exists("Delivery Note Item", {
            "against_sales_invoice": si_name,
            "docstatus": ["!=", 0]
        })
        
        frappe.db.set_value("Sales Invoice", si_name, "custom_delivery_note_created", 1 if exists else 0)
