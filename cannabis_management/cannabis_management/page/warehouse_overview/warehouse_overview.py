import frappe


def get_context(context):
    pass


@frappe.whitelist()
def get_item_groups():
    """Fetch all item groups that are flagged for dashboard display."""
    groups = frappe.db.sql("""
        SELECT
            ig.name,
            COUNT(i.name) as item_count
        FROM `tabItem Group` ig
        INNER JOIN `tabItem` i ON i.item_group = ig.name
            AND i.disabled = 0
            AND i.custom_show_in_dashboard = 1
        WHERE ig.is_group = 0
          AND ig.custom_show_in_dashboard = 1
        GROUP BY ig.name
        ORDER BY ig.name
    """, as_dict=True)

    return groups


@frappe.whitelist()
def get_stock_by_item_group(item_group, _=None):
    """Return stock rows for a given item group, with yield data attached."""
    items = frappe.db.sql("""
        SELECT
            b.item_code,
            i.item_name,
            i.item_group,
            b.warehouse,
            b.actual_qty,
            b.reserved_stock as reserved_qty
        FROM `tabBin` b
        INNER JOIN `tabItem` i ON i.name = b.item_code
        WHERE i.item_group = %s
            AND i.disabled = 0
            AND i.custom_show_in_dashboard = 1
            AND b.actual_qty != 0
            AND b.warehouse NOT LIKE 'Virtual%%'
        ORDER BY i.item_name
    """, (item_group,), as_dict=True)

    item_codes = list(set(item.item_code for item in items))
    yield_map = get_yield_data_for_items(item_codes)

    for item in items:
        code = item.item_code
        if code in yield_map:
            item["yield_to_hash"] = yield_map[code].get("yield_to_hash", "")
            item["hash_to_rosin"] = yield_map[code].get("hash_to_rosin", "")
        else:
            item["yield_to_hash"] = ""
            item["hash_to_rosin"] = ""

    total_qty = sum(item.actual_qty or 0 for item in items)
    unique_items = len(set(item.item_code for item in items))
    low_stock = len([i for i in items if (i.actual_qty or 0) - (i.reserved_qty or 0) <= 0])

    return {
        "items": items,
        "summary": {
            "total_items": unique_items,
            "total_qty": total_qty,
            "low_stock_items": low_stock
        }
    }


def get_yield_data_for_items(item_codes):
    """
    Fetch Yield to Hash and Actual Rosin Yield from Rosin Recording -> Lab Tolling Data.
    """
    if not item_codes:
        return {}

    placeholders = ", ".join(["%s"] * len(item_codes))

    records = frappe.db.sql("""
        SELECT
            ltd.strain_name AS item_code,
            ltd.yield_to_hash,
            ltd.actual_rosin_yield
        FROM `tabLab Tolling Data` ltd
        INNER JOIN `tabRosin Recording` rr ON rr.name = ltd.parent
        WHERE ltd.strain_name IN ({placeholders})
            AND rr.docstatus < 2
        ORDER BY ltd.strain_name, rr.creation
    """.format(placeholders=placeholders), tuple(item_codes), as_dict=True)

    yield_map = {}
    for row in records:
        code = row.item_code
        if code not in yield_map:
            yield_map[code] = {
                "yield_to_hash_values": [],
                "hash_to_rosin_values": []
            }

        yth = row.get("yield_to_hash")
        arr = row.get("actual_rosin_yield")

        if yth is not None and yth != "" and yth != 0:
            try:
                formatted_yth = "{:.2f}%".format(float(yth))
            except (ValueError, TypeError):
                formatted_yth = str(yth)
            if formatted_yth not in yield_map[code]["yield_to_hash_values"]:
                yield_map[code]["yield_to_hash_values"].append(formatted_yth)

        if arr is not None and arr != "" and arr != 0:
            try:
                formatted_arr = "{:.2f}%".format(float(arr))
            except (ValueError, TypeError):
                formatted_arr = str(arr)
            if formatted_arr not in yield_map[code]["hash_to_rosin_values"]:
                yield_map[code]["hash_to_rosin_values"].append(formatted_arr)

    result = {}
    for code, data in yield_map.items():
        result[code] = {
            "yield_to_hash": ", ".join(data["yield_to_hash_values"]),
            "hash_to_rosin": ", ".join(data["hash_to_rosin_values"])
        }

    return result


@frappe.whitelist()
def get_batch_warehouse_summary(item_group):
    """Returns count of unique project (batch) dimensions per warehouse with positive stock."""
    data = frappe.db.sql("""
        SELECT
            warehouse,
            COUNT(DISTINCT project) AS batch_count
        FROM (
            SELECT
                sle.warehouse,
                sle.project,
                SUM(sle.actual_qty) AS qty
            FROM `tabStock Ledger Entry` sle
            INNER JOIN `tabItem` i ON i.name = sle.item_code
            WHERE i.item_group = %s
              AND i.disabled = 0
              AND i.custom_show_in_dashboard = 1
              AND sle.is_cancelled = 0
              AND sle.project IS NOT NULL
              AND sle.project != ''
            GROUP BY sle.warehouse, sle.project
            HAVING SUM(sle.actual_qty) > 0
        ) sub
        GROUP BY warehouse
        ORDER BY batch_count DESC
    """, (item_group,), as_dict=True)
    return data