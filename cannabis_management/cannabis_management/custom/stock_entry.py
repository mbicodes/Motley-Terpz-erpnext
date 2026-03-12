import frappe
from frappe import _


def validate(doc, method):
    """
    For any stock entry where material is going out (s_warehouse is set),
    if an item row has custom_project_mandatory checked:
    1. Ensure the project field is filled
    2. Fetch the available project qty from Stock Ledger Entry
    3. Block submission if qty exceeds available project qty
    """
    for item in doc.items:
        if not item.custom_project_mandatory:
            continue

        # Only validate items where material is going out (source warehouse is set)
        if not item.s_warehouse:
            continue

        if not item.project:
            frappe.throw(
                _("Row {0}: Project is mandatory for Item {1} as 'Project Mandatory' is checked").format(
                    item.idx, frappe.bold(item.item_code)
                )
            )

        available_qty = get_project_qty(item.item_code, item.s_warehouse, item.project)
        item.custom_project_back_qty = available_qty

        if item.qty > available_qty:
            frappe.throw(
                _("Row {0}: Qty ({1}) exceeds available Project Qty ({2}) for Item {3}, "
                  "Project {4}, Warehouse {5}").format(
                    item.idx,
                    frappe.bold(item.qty),
                    frappe.bold(available_qty),
                    frappe.bold(item.item_code),
                    frappe.bold(item.project),
                    frappe.bold(item.s_warehouse),
                )
            )


@frappe.whitelist()
def get_project_qty(item_code, warehouse, project):
    """
    Get the available qty for an Item in a specific Warehouse and Project
    by summing actual_qty from Stock Ledger Entry.
    """
    result = frappe.db.sql(
        """
        SELECT IFNULL(SUM(actual_qty), 0) as qty
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND warehouse = %s
          AND project = %s
          AND is_cancelled = 0
        """,
        (item_code, warehouse, project),
        as_dict=True,
    )

    return result[0].qty if result else 0
