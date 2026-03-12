import frappe

@frappe.whitelist()
def get_shipments_for_invoice(supplier):
    # Fetch shipments based on your conditions
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
    """
    When Purchase Invoice is submitted,
    update Shipment:
      - custom_invoice_reference = doc.name
      - custom_invoice_status = 'Invoiced'
    Based on child item description: "Shipment: SHIP-0001"
    """

    for item in doc.items:
        # Only rows added from Get Shipments button
        if item.description and item.description.startswith("Shipment:"):

            # extract shipment id -> "Shipment: SHIP-0001"
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
    """
    When Purchase Invoice is cancelled,
    reset shipments linked through description field:
      - custom_invoice_reference = NULL
      - custom_invoice_status = 'Cancelled'
    """

    for item in doc.items:
        if item.description and item.description.startswith("Shipment:"):

            # Extract shipment ID
            shipment_id = item.description.replace("Shipment: ", "").strip()

            if frappe.db.exists("Shipment", shipment_id):

                # Clear invoice reference and set cancelled status
                frappe.db.set_value(
                    "Shipment",
                    shipment_id,
                    {
                        # "custom_invoice_reference": None,
                        "custom_invoice_status": "Cancelled"
                    }
                )
                frappe.db.commit()
