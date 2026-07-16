import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_material_transfer_from_so(sales_order, source_warehouse, target_warehouse):
    """
    Create a draft Material Transfer Stock Entry from Sales Order items.
    For each item, transfer min(requested_qty, available_qty) from source to target warehouse.
    """
    if not sales_order or not source_warehouse or not target_warehouse:
        frappe.throw(_("Sales Order, Source Warehouse, and Target Warehouse are required."))

    if source_warehouse == target_warehouse:
        frappe.throw(_("Source and Target Warehouse cannot be the same."))

    so = frappe.get_doc("Sales Order", sales_order)

    se = frappe.new_doc("Stock Entry")
    se.stock_entry_type = "Material Transfer"
    se.company = so.company or "Motley Terpz"
    se.custom_sales_order = sales_order

    has_items = False
    skipped_items = []

    project_mandatory_items = set(
        frappe.get_all(
            "Item",
            filters={
                "name": ["in", [row.item_code for row in so.items if row.item_code]],
                "custom_project_mandatory": 1,
            },
            pluck="name",
        )
    )

    for row in so.items:
        if not row.item_code:
            continue

        if flt(row.qty) <= 0:
            continue

        requested_qty = flt(row.stock_qty or row.qty)
        if requested_qty <= 0:
            continue

        if row.item_code in project_mandatory_items:
            skipped_items.append(
                "{0} (Project is mandatory for this item — transfer it manually via Stock Entry)".format(
                    row.item_code
                )
            )
            continue

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
            _("No items could be transferred. None of the order items have stock in {0}.").format(
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
