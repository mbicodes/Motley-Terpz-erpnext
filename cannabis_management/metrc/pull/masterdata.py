# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Master-data pulls: facilities, items, strains, tag pool, enumerations.

These are small, cheap and change rarely, so they run hourly rather than on a
cursor. Enumerations are cached rather than stored, because their only job is
to populate Select options and validate pushes.
"""

import frappe
from frappe.utils import now_datetime

from cannabis_management.metrc import config, mapping
from cannabis_management.metrc.client import get_client

ENUM_CACHE_TTL = 6 * 60 * 60  # 6 hours

# Enumerations worth caching. Keyed by a short name used by push validation.
ENUMERATIONS = {
    "uoms": "/unitsofmeasure/v2/active",
    "item_categories": "/items/v2/categories",
    "package_types": "/packages/v2/types",
    "adjust_reasons": "/packages/v2/adjust/reasons",
    "transfer_types": "/transfers/v2/types",
    "customer_types": "/sales/v2/customertypes",
    "labtest_types": "/labtests/v2/types",
    "job_types": "/processing/v2/jobtypes/active",
    "location_types": "/locations/v2/types",
    "waste_methods": "/wastemethods/v2/",
}


# ---------------------------------------------------------------------------
# Facilities
# ---------------------------------------------------------------------------


def sync_facilities(license_number):
    """Stamp facility names onto the mapped Warehouses.

    GET /facilities/v2/ is licence-agnostic - it returns every facility the
    user key can reach - so one call covers all configured licences.
    """
    client = get_client(license_number)
    rows = client.get("/facilities/v2/")
    count = 0

    for facility in rows:
        lic = (facility.get("License") or {}).get("Number")
        if not lic:
            continue
        warehouse = config.warehouse_for_license(lic)
        if not warehouse:
            continue
        frappe.db.set_value(
            "Warehouse",
            warehouse,
            {
                "custom_metrc_facility_name": facility.get("DisplayName") or facility.get("Name"),
                "custom_metrc_last_synced": now_datetime(),
            },
            update_modified=False,
        )
        count += 1

    frappe.db.commit()
    return count


# ---------------------------------------------------------------------------
# Items
# ---------------------------------------------------------------------------


def sync_items(license_number, create=None):
    """Match Metrc items to ERPNext Items, and optionally create the missing ones.

    Matching is always safe and runs hourly. Creation is gated on the
    Auto-Create Items setting because an Item is a master record: one created
    with the wrong item group, UOM or valuation breaks every downstream
    transaction, and it is far easier to prevent than to unpick afterwards.

    Pass create=True/False to override the setting for one run.
    """
    if create is None:
        create = bool(frappe.db.get_single_value("Metrc Settings", "auto_create_items"))

    client = get_client(license_number)
    matched = created = skipped = 0

    for item in client.get_all("/items/v2/active"):
        name = item.get("Name")
        if not name:
            continue

        item_code = mapping.erpnext_item_for_metrc(name)

        if not item_code:
            if not create:
                skipped += 1
                continue
            item_code = _create_item(item, name)
            if not item_code:
                skipped += 1
                continue
            created += 1

        values = {
            "custom_metrc_item_id": item.get("Id"),
            "custom_metrc_category": item.get("ProductCategoryName") or item.get("ItemCategory"),
            "custom_metrc_uom": item.get("UnitOfMeasureName"),
            "custom_metrc_last_synced": now_datetime(),
        }
        # Backfill the explicit name link so future lookups are exact rather
        # than falling through to the item_name fuzzy match.
        if not frappe.db.get_value("Item", item_code, "custom_metrc_item_name"):
            values["custom_metrc_item_name"] = name

        frappe.db.set_value("Item", item_code, values, update_modified=False)
        matched += 1

    frappe.db.commit()
    if created or skipped:
        frappe.logger("metrc").info(
            f"items {license_number}: matched={matched} created={created} unmatched={skipped}"
        )
    return matched


def _auto_item_defaults():
    settings = config.get_settings()
    group = settings.auto_item_group or frappe.db.get_value(
        "Item Group", {"is_group": 0}, "name"
    )
    return {
        "item_group": group,
        "fallback_uom": settings.auto_item_uom or "Nos",
        "is_stock_item": 1 if settings.auto_item_is_stock_item else 0,
        "has_batch_no": 1 if settings.auto_item_has_batch else 0,
    }


def _create_item(metrc_item, name):
    """Create an ERPNext Item for a Metrc product.

    The created Item is deliberately conservative:
      * flagged custom_metrc_auto_created so it shows up for review
      * is_sales_item / is_purchase_item off, so it cannot be quoted or ordered
        until a human has confirmed the master data
      * batch tracking on, because a Batch IS the Metrc package
    """
    defaults = _auto_item_defaults()
    if not defaults["item_group"]:
        frappe.log_error(
            "No Item Group configured for METRC auto-creation. "
            "Set 'Default Item Group' in Metrc Settings.",
            "[metrc] item auto-create",
        )
        return None

    uom = mapping.to_metrc_uom_reverse(metrc_item.get("UnitOfMeasureName")) or defaults[
        "fallback_uom"
    ]
    if not frappe.db.exists("UOM", uom):
        uom = defaults["fallback_uom"]

    doc = frappe.new_doc("Item")
    doc.item_code = name[:140]
    doc.item_name = name[:140]
    doc.description = metrc_item.get("ProductCategoryName") or name
    doc.item_group = defaults["item_group"]
    doc.stock_uom = uom
    doc.is_stock_item = defaults["is_stock_item"]
    doc.has_batch_no = defaults["has_batch_no"]
    doc.create_new_batch = 0  # batches are Metrc tags, never auto-generated
    # Off until reviewed: an unconfirmed master must not reach a quotation.
    doc.is_sales_item = 0
    doc.is_purchase_item = 0
    doc.custom_metrc_tracked = 1
    doc.custom_metrc_item_name = name
    doc.custom_metrc_item_id = metrc_item.get("Id")
    doc.custom_metrc_category = metrc_item.get("ProductCategoryName") or metrc_item.get(
        "ItemCategory"
    )
    doc.custom_metrc_uom = metrc_item.get("UnitOfMeasureName")
    doc.custom_metrc_auto_created = 1
    doc.custom_metrc_last_synced = now_datetime()
    doc.flags.ignore_permissions = True

    try:
        doc.insert(ignore_permissions=True)
        return doc.name
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"[metrc] item auto-create failed: {name}")
        return None


def create_missing_items(license_number):
    """Daily entry point - create Items for Metrc products we do not carry."""
    if not frappe.db.get_single_value("Metrc Settings", "auto_create_items"):
        return 0

    before = frappe.db.count("Item", {"custom_metrc_auto_created": 1})
    sync_items(license_number, create=True)
    return frappe.db.count("Item", {"custom_metrc_auto_created": 1}) - before


# ---------------------------------------------------------------------------
# Strains
# ---------------------------------------------------------------------------


def sync_strains(license_number):
    """Create missing Strain records. Safe to create: Strain is a thin master."""
    if not frappe.db.exists("DocType", "Strain"):
        return 0

    client = get_client(license_number)
    created = 0

    for strain in client.get_all("/strains/v2/active"):
        name = strain.get("Name")
        if not name or frappe.db.exists("Strain", name):
            continue
        doc = frappe.new_doc("Strain")
        # Strain's title field varies by install; set whatever it uses.
        meta = frappe.get_meta("Strain")
        for field in ("strain_name", "title", "strain"):
            if meta.has_field(field):
                doc.set(field, name)
                break
        else:
            doc.name = name
        doc.flags.ignore_permissions = True
        doc.flags.ignore_mandatory = True
        try:
            doc.insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"[metrc] strain create failed: {name}")

    frappe.db.commit()
    return created


# ---------------------------------------------------------------------------
# Tag pool
# ---------------------------------------------------------------------------


def sync_available_tags(license_number):
    """Pull the unused tag pool into Metric Tag.

    /tags/v2/*/available returns a bare array, not a paginated envelope.
    MetrcClient._unwrap already normalises that.
    """
    client = get_client(license_number)
    created = 0

    for path, kind in (
        ("/tags/v2/package/available", "Package"),
        ("/tags/v2/plant/available", "Plant"),
    ):
        try:
            rows = client.get(path)
        except Exception:
            # A cultivator has no package tags and a retailer has no plant
            # tags; a 401/404 on one of these is expected, not an error.
            frappe.log_error(frappe.get_traceback(), f"[metrc] tag pull {license_number} {path}")
            continue

        for tag in rows:
            label = tag.get("Label")
            if not label or frappe.db.exists("Metric Tag", label):
                continue
            doc = frappe.new_doc("Metric Tag")
            doc.tag_code = label
            doc.status = "Unused"
            doc.last_transaction_type = f"Metrc {kind} Tag"
            doc.custom_metrc_license_number = license_number
            doc.custom_metrc_last_synced = now_datetime()
            doc.flags.ignore_permissions = True
            try:
                doc.insert(ignore_permissions=True)
                created += 1
            except Exception:
                frappe.log_error(frappe.get_traceback(), f"[metrc] tag insert failed: {label}")

    frappe.db.commit()
    return created


def claim_tag(license_number, kind="Package"):
    """Reserve the lowest unused tag for a new package.

    FOR UPDATE is essential: two workers claiming the same row would produce
    two Metrc packages sharing one physical label, which cannot be undone
    through the API.
    """
    rows = frappe.db.sql(
        """
        select name from `tabMetric Tag`
        where status = 'Unused' and last_transaction_type = %s
        order by tag_code asc limit 1
        for update
        """,
        (f"Metrc {kind} Tag",),
        as_dict=True,
    )
    if not rows:
        frappe.throw(
            f"No unused Metrc {kind} tags available for {license_number}. "
            "Receive tags in Metrc, then run the tag sync."
        )

    tag = rows[0].name
    frappe.db.set_value("Metric Tag", tag, "status", "Active", update_modified=False)
    return tag


# ---------------------------------------------------------------------------
# Enumerations
# ---------------------------------------------------------------------------


def get_enumeration(key, license_number=None, refresh=False):
    """Cached enumeration list. Returns raw rows as Metrc sends them."""
    path = ENUMERATIONS.get(key)
    if not path:
        return []

    cache_key = f"enum:{key}"
    if not refresh:
        cached = frappe.cache.hget("metrc", cache_key)
        if cached is not None:
            return cached

    license_number = license_number or (config.configured_licenses() or [None])[0]
    if not license_number:
        return []

    try:
        rows = get_client(license_number).get(path)
    except Exception:
        frappe.log_error(frappe.get_traceback(), f"[metrc] enumeration pull failed: {key}")
        rows = []

    frappe.cache.hset("metrc", cache_key, rows)
    return rows


def enumeration_names(key, license_number=None):
    """Just the Name values, for validating pushes and building Selects."""
    out = []
    for row in get_enumeration(key, license_number):
        if isinstance(row, dict):
            name = row.get("Name") or row.get("name")
            if name:
                out.append(name)
        elif isinstance(row, str):
            out.append(row)
    return out


def refresh_enumerations(license_number):
    count = 0
    for key in ENUMERATIONS:
        if get_enumeration(key, license_number, refresh=True):
            count += 1
    return count
