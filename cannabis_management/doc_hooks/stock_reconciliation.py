"""Stock Reconciliation Item: the same Inventory Dimension layout as Stock Entry.

A Stock Entry row shows the Batch dimension twice -- Source on the left, Target
on the right. Stock Reconciliation has one warehouse per row, so it only ever
got the source field. This lays the row out like Stock Entry: Source Batch, a
column break, then Target Batch.

Target Batch is recorded on the row only: ERPNext copies just the source
dimension into the Stock Ledger Entry of a single-warehouse row.
"""

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
    """Idempotent; re-asserted on every migrate via after_migrate."""
    create_custom_fields(DIMENSION_FIELDS, update=True)
