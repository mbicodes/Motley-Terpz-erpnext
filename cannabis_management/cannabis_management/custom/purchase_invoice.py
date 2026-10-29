import frappe

@frappe.whitelist()
def get_shipments_for_invoice(supplier):
    shipments = frappe.get_all(
        "Shipment",
        filters={
            "custom_invoice_status": "UnInvoiced",
            "custom_invoice_reference": ["is", "not set"],
            "custom_supplier": supplier,
            "docstatus": 1
        },
        fields=["name", "shipment_amount"]
    )

    return shipments


def update_shipments_after_invoice(doc, method):
    for item in doc.items:
        if item.description and item.description.startswith("Shipment:"):
            shipment_id = item.description.replace("Shipment: ", "").strip()

            if frappe.db.exists("Shipment", shipment_id):
                frappe.db.set_value(
                    "Shipment",
                    shipment_id,
                    {
                        "custom_invoice_reference": doc.name,
                        "custom_invoice_status": "Invoiced"
                    }
                )
                frappe.db.commit()


def cancel_linked_shipments(doc, method):
    for item in doc.items:
        if item.description and item.description.startswith("Shipment:"):
            shipment_id = item.description.replace("Shipment: ", "").strip()

            if frappe.db.exists("Shipment", shipment_id):
                frappe.db.set_value(
                    "Shipment",
                    shipment_id,
                    {
                        "custom_invoice_status": "Cancelled"
                    }
                )
                frappe.db.commit()
