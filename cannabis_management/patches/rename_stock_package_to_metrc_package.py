import frappe


def execute():
    frappe.flags.in_patch = True

    if frappe.db.exists("DocType", "Stock Package Consumption Entry"):
        frappe.rename_doc(
            "DocType", "Stock Package Consumption Entry", "Package Stock Movement", force=True
        )
    elif frappe.db.exists("DocType", "Metrc Package Consumption Entry"):
        frappe.rename_doc(
            "DocType", "Metrc Package Consumption Entry", "Package Stock Movement", force=True
        )

    if frappe.db.exists("DocType", "Stock Package"):
        frappe.rename_doc("DocType", "Stock Package", "Metrc Package", force=True)

    frappe.db.commit()
