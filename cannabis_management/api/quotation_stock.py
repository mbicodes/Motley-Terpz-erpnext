import json
import frappe
from frappe.utils import flt


@frappe.whitelist()
def get_item_availability(item_codes):
    if isinstance(item_codes, str):
        try:
            item_codes = json.loads(item_codes)
        except (ValueError, TypeError):
            item_codes = [item_codes]
    item_codes = [c for c in (item_codes or []) if c]
    if not item_codes:
        return {}

    rows = frappe.db.sql(
        """
        SELECT b.item_code, b.warehouse,
               COALESCE(b.actual_qty, 0)                              AS actual,
               COALESCE(b.reserved_qty, 0)                            AS reserved,
               COALESCE(b.actual_qty, 0) - COALESCE(b.reserved_qty, 0) AS available
        FROM `tabBin` b
        WHERE b.item_code IN %(items)s
          AND COALESCE(b.actual_qty, 0) <> 0
        ORDER BY b.item_code, b.warehouse
        """,
        {"items": tuple(item_codes)},
        as_dict=True,
    )

    out = {}
    for r in rows:
        d = out.setdefault(r.item_code, {"available": 0.0, "actual": 0.0, "reserved": 0.0, "warehouses": []})
        d["available"] += flt(r.available)
        d["actual"] += flt(r.actual)
        d["reserved"] += flt(r.reserved)
        if flt(r.available):
            d["warehouses"].append({"warehouse": r.warehouse, "available": flt(r.available)})
    for ic in item_codes:
        out.setdefault(ic, {"available": 0.0, "actual": 0.0, "reserved": 0.0, "warehouses": []})
    return out


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def items_in_price_list(doctype, txt, searchfield, start, page_len, filters):
    price_list = (filters or {}).get("price_list")
    like = f"%{txt or ''}%"

    if price_list:
        return frappe.db.sql(
            """
            SELECT i.name, i.item_name
            FROM `tabItem` i
            LEFT JOIN `tabItem Price` ip
              ON ip.item_code = i.name AND ip.price_list = %(pl)s AND ip.selling = 1
            WHERE i.disabled = 0
              AND (i.name LIKE %(txt)s OR i.item_name LIKE %(txt)s)
            GROUP BY i.name, i.item_name
            ORDER BY MAX(ip.name IS NOT NULL) DESC, i.name
            LIMIT %(start)s, %(page_len)s
            """,
            {"pl": price_list, "txt": like, "start": start, "page_len": page_len},
        )

    return frappe.db.sql(
        """
        SELECT name, item_name FROM `tabItem`
        WHERE disabled = 0 AND (name LIKE %(txt)s OR item_name LIKE %(txt)s)
        ORDER BY name LIMIT %(start)s, %(page_len)s
        """,
        {"txt": like, "start": start, "page_len": page_len},
    )


def install_quotation_stock_fields():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

    if not frappe.db.has_column("Quotation Item", "custom_available_stock"):
        create_custom_fields({
            "Quotation Item": [
                {"fieldname": "custom_available_stock", "fieldtype": "Float",
                 "label": "Avail. Qty", "read_only": 1, "in_list_view": 1,
                 "no_copy": 1, "insert_after": "qty",
                 "description": "Live available stock (actual − reserved) across warehouses"},
            ]
        }, ignore_validate=True)
        frappe.db.commit()
