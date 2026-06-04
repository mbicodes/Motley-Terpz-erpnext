import frappe


@frappe.whitelist(allow_guest=True)
def get_live_menu_groups():
    """Fetch item groups configured for the live menu, ordered by sequence number."""
    frappe.response["no_cache"] = 1

    groups = frappe.db.sql("""
        SELECT
            ig.name,
            ig.custom_dashboard_text AS notes,
            ig.custom_sequence_number AS sequence,
            ig.custom_min_quantity AS min_qty
        FROM `tabItem Group` ig
        WHERE ig.is_group = 0
          AND ig.custom_show_in_dashboard = 1
          AND EXISTS (
              SELECT 1 FROM `tabItem` i 
              WHERE i.item_group = ig.name 
                AND i.custom_show_in_dashboard = 1
                AND i.disabled = 0
                AND i.custom_hide_from_client = 0
          )
        ORDER BY
            CASE
                WHEN ig.custom_sequence_number IS NOT NULL
                     AND ig.custom_sequence_number != ''
                THEN CAST(ig.custom_sequence_number AS UNSIGNED)
                ELSE 9999
            END,
            ig.name
    """, as_dict=True)

    return groups


@frappe.whitelist(allow_guest=True)
def get_live_menu_items(item_group, menu_type=None):
    """Fetch stock items for a group, filtered by warehouse and min quantity.

    Args:
        item_group: Item Group name
        menu_type: 'extracts' filters to Nature's Lab - MT,
                   'fresh_frozen' filters to Hemet TSBC - TSBC,
                   None/empty uses both warehouses
    """
    frappe.response["no_cache"] = 1

    group_doc = frappe.db.get_value(
        "Item Group",
        item_group,
        ["custom_min_quantity", "custom_dashboard_text"],
        as_dict=True,
    )

    min_qty = float(group_doc.get("custom_min_quantity") or 0)
    notes = group_doc.get("custom_dashboard_text") or ""

    # Warehouse filter based on menu type
    if menu_type == "extracts":
        warehouse_condition = "AND b.warehouse = 'Master Touch Manufacturing Toll - MTM'"
    elif menu_type == "fresh_frozen":
        warehouse_condition = "AND b.warehouse = 'Hemet TSBC - TSBC'"
    else:
        warehouse_condition = "AND b.warehouse IN ('Hemet TSBC - TSBC', 'Master Touch Manufacturing Toll - MTM')"

    items = frappe.db.sql(
        """
        SELECT
            i.item_code,
            i.item_name,
            SUM(COALESCE(b.actual_qty, 0)) AS actual_qty,
            SUM(COALESCE(b.reserved_qty, 0)) AS reserved_qty,
            SUM(COALESCE(b.actual_qty, 0)) - SUM(COALESCE(b.reserved_qty, 0)) AS available_qty
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON b.item_code = i.item_code
            {warehouse_condition}
        WHERE i.item_group = %(item_group)s
        AND i.disabled = 0
        AND i.custom_show_in_dashboard = 1
        AND i.custom_hide_from_client = 0
        GROUP BY i.item_code, i.item_name
        HAVING (SUM(COALESCE(b.actual_qty, 0)) - SUM(COALESCE(b.reserved_qty, 0))) > 0
        AND (SUM(COALESCE(b.actual_qty, 0)) - SUM(COALESCE(b.reserved_qty, 0))) >= %(min_qty)s
        ORDER BY i.item_name
        """.format(
            warehouse_condition=warehouse_condition,
        ),
        {"item_group": item_group, "min_qty": min_qty},
        as_dict=True,
    )

    return {
        "items": items,
        "notes": notes,
        "group_name": item_group,
    }