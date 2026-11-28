import frappe

from cannabis_management.api.inventory_dashboard import RESERVED_SUBQUERY


@frappe.whitelist(allow_guest=True)
def get_live_menu_groups():
    frappe.response["no_cache"] = 1

    groups = frappe.db.sql("""
        SELECT
            ig.name,
            ig.parent_item_group,
            ig.custom_dashboard_text AS notes,
            ig.custom_sequence_number AS sequence,
            ig.custom_min_quantity AS min_qty
        FROM `tabItem Group` ig
        WHERE ig.is_group = 0
          AND ig.custom_show_in_extracts_live = 1
          AND EXISTS (
              SELECT 1 FROM `tabItem` i 
              WHERE (i.item_group = ig.name OR (ig.name = 'Fresh Frozen' AND i.item_group IN ('Fresh Frozen', 'Fresh Frozen - BHO', 'Fresh Frozen - SHO', 'Fresh Frozen Untested', 'Fresh Frozen - To Be Determined')))
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
    frappe.response["no_cache"] = 1

    group_doc = frappe.db.get_value(
        "Item Group",
        item_group,
        ["custom_min_quantity", "custom_dashboard_text"],
        as_dict=True,
    )

    min_qty = float(group_doc.get("custom_min_quantity") or 0)
    notes = group_doc.get("custom_dashboard_text") or ""

    if menu_type == "extracts":
        warehouse_condition = "AND b.warehouse = 'Main Storage - MTM'"
    elif menu_type == "fresh_frozen":
        warehouse_condition = "AND b.warehouse = 'Hemet TSBC - TSBC'"
    else:
        warehouse_condition = "AND b.warehouse IN ('Hemet TSBC - TSBC', 'Main Storage - MTM')"

    items = frappe.db.sql(
        """
        SELECT
            i.item_code,
            i.item_name,
            SUM(COALESCE(b.actual_qty, 0)) AS actual_qty,
            SUM(COALESCE(sre.reserved_qty, 0)) AS reserved_qty,
            SUM(COALESCE(b.actual_qty, 0)) - SUM(COALESCE(sre.reserved_qty, 0)) AS available_qty
        FROM `tabItem` i
        LEFT JOIN `tabBin` b ON b.item_code = i.item_code
            {warehouse_condition}
        LEFT JOIN ({reserved_subquery}) sre
            ON sre.item_code = b.item_code AND sre.warehouse = b.warehouse
        WHERE i.item_group = %(item_group)s
        AND i.disabled = 0
        AND i.custom_show_in_dashboard = 1
        AND i.custom_hide_from_client = 0
        GROUP BY i.item_code, i.item_name
        HAVING (SUM(COALESCE(b.actual_qty, 0)) - SUM(COALESCE(sre.reserved_qty, 0))) > 0
        AND (SUM(COALESCE(b.actual_qty, 0)) - SUM(COALESCE(sre.reserved_qty, 0))) >= %(min_qty)s
        ORDER BY i.item_name
        """.format(
            warehouse_condition=warehouse_condition,
            reserved_subquery=RESERVED_SUBQUERY,
        ),
        {"item_group": item_group, "min_qty": min_qty},
        as_dict=True,
    )

    if str(item_group or "").lower().startswith("fresh frozen"):
        for item in items:
            if str(item.get("item_name") or "").strip().endswith("_6"):
                item["item_group"] = "Fresh Frozen"

    return {
        "items": items,
        "notes": notes,
        "group_name": item_group,
    }


# ──────────────────────────────────────────────────────────────────────────
# Public, cross-origin menu feed (Shopify storefront / any external site)
#
# GET /api/method/cannabis_management.api.live_menu.get_public_menu
#     ?menu_type=extracts|fresh_frozen   (optional; omit for everything)
#
# One request returns every visible category with its in-stock strains.
# Same visibility rules as the internal Live Menu page. Cached 60s so
# storefront traffic does not hit the database on every page view.
# ──────────────────────────────────────────────────────────────────────────
import json
import re

from frappe.utils import now_datetime
from werkzeug.wrappers import Response

PUBLIC_MENU_CACHE_SECONDS = 60
_DISPLAY_NAMES = {
    "vrr tier": "VRR",
    "llr tier": "LLR",
    "vrr": "Vape Ready Rosin",
    "liquid live resin": "Liquid Live Resin",
    "distallate": "Distillate",
}
_QTY_GROUPS = {"fresh frozen"}  # only these show quantity publicly (matches Live Menu page)


def _display_name(group):
    return _DISPLAY_NAMES.get((group or "").lower(), group)


def _clean_strain_name(name):
    """Python port of cleanStrainName() from the Live Menu web page."""
    if not name:
        return ""
    original = name
    name = re.sub(r"\s*[-–]\s*[^-–]+$", "", name)
    name = re.sub(r"_[A-Za-z0-9]-.+$", "", name)
    name = re.sub(r"_CDC$", "", name, flags=re.I)
    name = re.sub(r"_H$", "", name, flags=re.I)
    name = re.sub(r"_[A-Za-z0-9]$", "", name)
    name = name.replace("_", " ").strip()
    return name or original


def _build_public_menu(menu_type):
    groups = get_live_menu_groups()
    if menu_type == "extracts":
        groups = [g for g in groups if not g.name.lower().startswith("fresh frozen")]
    elif menu_type == "fresh_frozen":
        groups = [g for g in groups if g.name.lower() == "fresh frozen"]

    categories = []
    for g in groups:
        data = get_live_menu_items(g.name, menu_type)
        show_qty = g.name.lower() in _QTY_GROUPS
        items = []
        for it in data["items"]:
            row = {"item_code": it.item_code, "name": _clean_strain_name(it.item_name)}
            if show_qty:
                row["qty"] = round(float(it.available_qty or 0), 2)
                row["uom"] = "lbs"
            items.append(row)
        if not items:
            continue
        categories.append({
            "group": g.name,
            "display_name": _display_name(g.name),
            "parent_group": g.parent_item_group,
            "parent_display_name": _display_name(g.parent_item_group),
            "sequence": int(g.sequence) if str(g.sequence or "").isdigit() else None,
            "notes": data.get("notes") or "",
            "shows_qty": show_qty,
            "item_count": len(items),
            "items": items,
        })

    return {
        "updated_at": now_datetime().isoformat(timespec="seconds"),
        "menu_type": menu_type or "all",
        "category_count": len(categories),
        "categories": categories,
    }


@frappe.whitelist(allow_guest=True, methods=["GET"])
def get_public_menu(menu_type=None):
    menu_type = (menu_type or "").strip().lower()
    if menu_type not in ("", "extracts", "fresh_frozen"):
        menu_type = ""

    cache_key = f"public_live_menu:{menu_type or 'all'}"
    payload = frappe.cache.get_value(cache_key)
    if not payload:
        payload = json.dumps(_build_public_menu(menu_type or None), default=str)
        frappe.cache.set_value(cache_key, payload, expires_in_sec=PUBLIC_MENU_CACHE_SECONDS)

    return Response(
        payload,
        status=200,
        mimetype="application/json",
        headers={
            # Public, read-only data with no cookies/credentials → any origin may read it.
            "Access-Control-Allow-Origin": "*",
            "Cache-Control": f"public, max-age={PUBLIC_MENU_CACHE_SECONDS}",
        },
    )
