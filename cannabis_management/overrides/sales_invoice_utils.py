import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_material_transfer_from_si(sales_invoice, source_warehouse, target_warehouse):
    """
    Create a draft Material Transfer Stock Entry from Sales Invoice items.
    For each item, transfer min(requested_qty, available_qty) from source to target warehouse.
    """
    if not sales_invoice or not source_warehouse or not target_warehouse:
        frappe.throw(_("Sales Invoice, Source Warehouse, and Target Warehouse are required."))

    if source_warehouse == target_warehouse:
        frappe.throw(_("Source and Target Warehouse cannot be the same."))

    si = frappe.get_doc("Sales Invoice", sales_invoice)

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Transfer"
    se.company = si.company or "Motley Terpz"
    se.custom_sales_invoice_reference = sales_invoice  # optional link-back field

    has_items = False
    skipped_items = []

    for row in si.items:
        if not row.item_code:
            continue

        # Skip rows where the invoice qty is zero
        if flt(row.qty) <= 0:
            continue

        requested_qty = flt(row.stock_qty or row.qty)
        if requested_qty <= 0:
            continue

        # Check available qty in source warehouse via Bin
        available_qty = flt(
            frappe.db.get_value(
                "Bin",
                {"item_code": row.item_code, "warehouse": source_warehouse},
                "actual_qty",
            )
            or 0
        )

        transfer_qty = min(requested_qty, available_qty)

        if transfer_qty <= 0:
            skipped_items.append(
                "{0} (requested {1}, available {2})".format(
                    row.item_code, requested_qty, available_qty
                )
            )
            continue

        se.append(
            "items",
            {
                "item_code": row.item_code,
                "qty": transfer_qty,
                "s_warehouse": source_warehouse,
                "t_warehouse": target_warehouse,
                "allow_zero_valuation_rate": 1,
            },
        )
        has_items = True

        if transfer_qty < requested_qty:
            skipped_items.append(
                "{0} (requested {1}, only {2} available — transferred {2})".format(
                    row.item_code, requested_qty, available_qty
                )
            )

    if not has_items:
        frappe.throw(
            _("No items could be transferred. None of the invoice items have stock in {0}.").format(
                source_warehouse
            )
        )

    se.insert(ignore_permissions=True)

    msg = _("Draft Stock Entry {0} created.").format(
        '<a href="/app/stock-entry/{0}">{0}</a>'.format(se.name)
    )

    if skipped_items:
        msg += "<br><br><b>" + _("Partial / Skipped Items:") + "</b><br>"
        msg += "<br>".join(skipped_items)

    return {"stock_entry": se.name, "message": msg}
