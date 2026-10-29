from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

DIMENSION_FIELDS = {
    "Stock Reconciliation Item": [
        {"fieldname": "batch", "label": "Source Batch", "fieldtype": "Link",
         "options": "Project", "insert_after": "inventory_dimension"},
        {"fieldname": "inventory_dimension_col_break", "fieldtype": "Column Break",
         "insert_after": "batch"},
        {"fieldname": "to_batch", "label": "Target Batch", "fieldtype": "Link",
         "options": "Project", "insert_after": "inventory_dimension_col_break"},
    ]
}


def install_custom_fields():
    create_custom_fields(DIMENSION_FIELDS, update=True)
