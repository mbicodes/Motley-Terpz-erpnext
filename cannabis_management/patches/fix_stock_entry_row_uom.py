import frappe
from frappe.utils import flt


def execute():
    """
    Repair draft Stock Entry rows whose UOM no longer matches the Item's
    stock UOM (items were created with 'Nos' and corrected later, but
    existing rows kept the stale UOM). Only draft entries are touched;
    submitted entries already posted their ledgers in the stock UOM.
    Rows with a real UOM conversion (factor != 1) are left alone.
    """
    rows = frappe.db.sql(
        """
        SELECT sed.name, sed.qty, i.stock_uom
        FROM `tabStock Entry Detail` sed
        JOIN `tabStock Entry` se ON se.name = sed.parent
        JOIN `tabItem` i ON i.name = sed.item_code
        WHERE se.docstatus = 0
          AND (sed.uom != i.stock_uom OR sed.stock_uom != i.stock_uom)
          AND (sed.conversion_factor IS NULL OR sed.conversion_factor IN (0, 1))
        """,
        as_dict=True,
    )

    for row in rows:
        frappe.db.set_value(
            "Stock Entry Detail",
            row.name,
            {
                "uom": row.stock_uom,
                "stock_uom": row.stock_uom,
                "conversion_factor": 1,
                "transfer_qty": flt(row.qty),
            },
            update_modified=False,
        )
