# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Settings accessor and Warehouse <-> Metrc licence resolution.

A Metrc "Facility" is an ERPNext Warehouse. The join is
Warehouse.custom_metrc_license_number, which already existed in this app
before the integration was built, so every routing decision keys off it.
"""

import frappe

from cannabis_management.metrc.exceptions import MetrcNotConfigured

SETTINGS = "Metrc Settings"


def get_settings():
    return frappe.get_cached_doc(SETTINGS)


def is_enabled():
    return bool(frappe.db.get_single_value(SETTINGS, "enabled"))


def push_enabled():
    return bool(frappe.db.get_single_value(SETTINGS, "push_enabled"))


def is_dry_run():
    return bool(frappe.db.get_single_value(SETTINGS, "dry_run"))


def base_url():
    s = get_settings()
    url = s.production_base_url if s.environment == "Production" else s.sandbox_base_url
    if not url:
        raise MetrcNotConfigured(f"No base URL configured for environment {s.environment}")
    return url.rstrip("/")


def integrator_key():
    key = get_settings().get_password("integrator_key", raise_exception=False)
    if not key:
        raise MetrcNotConfigured("Integrator API key is not set in Metrc Settings")
    return key


def get_facility(license_number):
    """Metrc Facility child row for a licence."""
    for row in get_settings().facilities:
        if row.license_number == license_number:
            return row
    raise MetrcNotConfigured(f"License {license_number} is not configured in Metrc Settings")


def user_key(license_number):
    row = get_facility(license_number)
    key = row.get_password("user_key", raise_exception=False)
    if not key:
        raise MetrcNotConfigured(f"No user key configured for licence {license_number}")
    return key


def active_facilities(feature=None):
    """Active facilities, optionally filtered by a sync_* feature flag."""
    out = []
    for row in get_settings().facilities:
        if not row.is_active:
            continue
        if feature and not row.get(feature):
            continue
        out.append(row)
    return out


def facility_timezone(license_number):
    try:
        return get_facility(license_number).facility_timezone or "America/Los_Angeles"
    except MetrcNotConfigured:
        return "America/Los_Angeles"


# ---------------------------------------------------------------------------
# Warehouse <-> licence resolution
# ---------------------------------------------------------------------------


def warehouse_for_license(license_number):
    """Warehouse mapped to a licence. The child row wins; fall back to the
    Warehouse custom field so a partially-configured site still resolves."""
    try:
        row = get_facility(license_number)
        if row.warehouse:
            return row.warehouse
    except MetrcNotConfigured:
        pass
    return frappe.db.get_value("Warehouse", {"custom_metrc_license_number": license_number}, "name")


def company_for_license(license_number):
    """Company that owns a Metrc licence.

    Resolution order:
      1. Facility -> Warehouse -> Warehouse.company (the physical facility is an
         ERPNext Warehouse, and a Warehouse always belongs to a Company).
      2. Company whose `custom_license` link matches the licence number directly
         (lets an operator pin a company to a licence without a warehouse).

    Returns None when nothing maps, which callers treat as "leave company blank".
    """
    if not license_number:
        return None

    warehouse = warehouse_for_license(license_number)
    if warehouse:
        company = frappe.db.get_value("Warehouse", warehouse, "company")
        if company:
            return company

    return frappe.db.get_value("Company", {"custom_license": license_number}, "name")


def license_for_warehouse(warehouse):
    """Licence for a warehouse, walking up the group tree if the leaf has none.

    Operations often tag the parent warehouse with the licence and keep child
    bins untagged, so a leaf lookup alone would silently skip the push.
    """
    if not warehouse:
        return None

    seen = set()
    current = warehouse
    while current and current not in seen:
        seen.add(current)
        row = frappe.db.get_value(
            "Warehouse", current, ["custom_metrc_license_number", "parent_warehouse"], as_dict=True
        )
        if not row:
            return None
        if row.custom_metrc_license_number:
            return row.custom_metrc_license_number
        current = row.parent_warehouse
    return None


def license_for_doc(doc):
    """Best-effort licence for a stock/sales document.

    Checks the document's own warehouse fields first, then each item row.
    Returns None when nothing maps, which callers treat as "not Metrc-tracked".
    """
    for fieldname in ("set_warehouse", "from_warehouse", "warehouse", "s_warehouse", "t_warehouse"):
        value = doc.get(fieldname)
        if value:
            lic = license_for_warehouse(value)
            if lic:
                return lic

    for row in doc.get("items") or []:
        for fieldname in ("warehouse", "s_warehouse", "t_warehouse"):
            value = row.get(fieldname)
            if value:
                lic = license_for_warehouse(value)
                if lic:
                    return lic
    return None


def configured_licenses():
    return [row.license_number for row in get_settings().facilities if row.is_active]
