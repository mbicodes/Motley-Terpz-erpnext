# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Translation between ERPNext and Metrc vocabularies.

Two rules drive everything here:

  * Metrc accepts exactly 11 units of measure. Anything else is rejected at
    push time, so we validate at save time instead - a blocked save beats a
    parked outbox row at 2am.
  * Never convert quantities. Send the number in the unit Metrc holds for that
    package; rounding drift between grams and ounces is a compliance variance.
"""

import frappe

from cannabis_management.metrc import config

# Confirmed live from GET /unitsofmeasure/v2/active.
METRC_UOMS = {
    "Each": "CountBased",
    "Grams": "WeightBased",
    "Kilograms": "WeightBased",
    "Milligrams": "WeightBased",
    "Ounces": "WeightBased",
    "Pounds": "WeightBased",
    "Fluid Ounces": "VolumeBased",
    "Gallons": "VolumeBased",
    "Liters": "VolumeBased",
    "Milliliters": "VolumeBased",
    "Pints": "VolumeBased",
}

# Fallbacks for the common ERPNext UOM spellings, used when the Metrc UOM Map
# table has no explicit row. Keys are lower-cased.
_IMPLICIT = {
    "each": "Each",
    "nos": "Each",
    "unit": "Each",
    "pcs": "Each",
    "piece": "Each",
    "gram": "Grams",
    "grams": "Grams",
    "g": "Grams",
    "gm": "Grams",
    "kilogram": "Kilograms",
    "kilograms": "Kilograms",
    "kg": "Kilograms",
    "milligram": "Milligrams",
    "milligrams": "Milligrams",
    "mg": "Milligrams",
    "ounce": "Ounces",
    "ounces": "Ounces",
    "oz": "Ounces",
    "pound": "Pounds",
    "pounds": "Pounds",
    "lb": "Pounds",
    "lbs": "Pounds",
    "fluid ounce": "Fluid Ounces",
    "fluid ounces": "Fluid Ounces",
    "fl oz": "Fluid Ounces",
    "gallon": "Gallons",
    "gallons": "Gallons",
    "gal": "Gallons",
    "litre": "Liters",
    "liter": "Liters",
    "liters": "Liters",
    "litres": "Liters",
    "l": "Liters",
    "millilitre": "Milliliters",
    "milliliter": "Milliliters",
    "milliliters": "Milliliters",
    "ml": "Milliliters",
    "pint": "Pints",
    "pints": "Pints",
    "pt": "Pints",
}


def _explicit_map():
    def _fetch():
        try:
            rows = config.get_settings().uom_map
        except Exception:
            return {}
        return {(r.erpnext_uom or "").lower(): r.metrc_uom for r in rows if r.metrc_uom}

    return frappe.cache.hget("metrc", "uom_map", _fetch)


def clear_cache():
    frappe.cache.hdel("metrc", "uom_map")
    frappe.cache.hdel("metrc", "tracked_items")


def to_metrc_uom(erpnext_uom, raise_on_missing=True):
    """ERPNext UOM -> Metrc UOM name."""
    if not erpnext_uom:
        if raise_on_missing:
            frappe.throw("Cannot map an empty UOM to Metrc.")
        return None

    key = erpnext_uom.strip().lower()

    mapped = _explicit_map().get(key)
    if mapped:
        return mapped

    # Already a valid Metrc name?
    for name in METRC_UOMS:
        if name.lower() == key:
            return name

    mapped = _IMPLICIT.get(key)
    if mapped:
        return mapped

    if raise_on_missing:
        frappe.throw(
            f"UOM <b>{frappe.utils.escape_html(erpnext_uom)}</b> has no Metrc equivalent. "
            "Add a row to the UOM Map in <b>Metrc Settings</b> mapping it to one of: "
            + ", ".join(METRC_UOMS)
        )
    return None


def is_metrc_uom(name):
    return name in METRC_UOMS


def to_metrc_uom_reverse(metrc_uom):
    """Metrc UOM name -> the ERPNext UOM that maps to it.

    Used when auto-creating an Item: we want the ERPNext unit that will map
    back to the same Metrc unit on the way out, so a round trip does not
    silently change the unit a package is reported in.
    """
    if not metrc_uom:
        return None

    # An explicit mapping wins, and the first one configured is authoritative.
    for erpnext_uom, mapped in _explicit_map().items():
        if mapped == metrc_uom:
            actual = frappe.db.get_value("UOM", {"name": ["like", erpnext_uom]}, "name")
            if actual:
                return actual

    # Otherwise accept the Metrc name itself if ERPNext already has that UOM.
    if frappe.db.exists("UOM", metrc_uom):
        return metrc_uom

    # Finally, any UOM whose implicit mapping lands on the same Metrc unit.
    for candidate, mapped in _IMPLICIT.items():
        if mapped == metrc_uom:
            actual = frappe.db.get_value("UOM", {"name": ["like", candidate]}, "name")
            if actual:
                return actual
    return None


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


def is_tracked_item(item_code):
    """Whether an Item is flagged as Metrc-tracked."""
    if not item_code:
        return False
    return bool(frappe.db.get_value("Item", item_code, "custom_metrc_tracked"))


def metrc_item_name(item_code):
    """Metrc item name for an ERPNext Item, falling back to item_name."""
    row = frappe.db.get_value(
        "Item", item_code, ["custom_metrc_item_name", "item_name"], as_dict=True
    )
    if not row:
        return None
    return row.custom_metrc_item_name or row.item_name


def erpnext_item_for_metrc(metrc_name, strain=None):
    """Reverse lookup: Metrc item name -> ERPNext Item code."""
    if not metrc_name:
        return None
    return frappe.db.get_value("Item", {"custom_metrc_item_name": metrc_name}, "name") or frappe.db.get_value(
        "Item", {"item_name": metrc_name}, "name"
    )
