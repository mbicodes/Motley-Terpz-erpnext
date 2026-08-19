# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Populate Metrc Settings from site_config.json.

    bench --site <site> execute cannabis_management.metrc.bootstrap.configure

Keys live in site_config.json, not in this file and not in git. Frappe encrypts
them into the Password fields on save, so site_config is the staging area, not
the permanent home - but it keeps credentials out of the repo either way.

Expected site_config keys:

    "metrc_environment":     "Sandbox" | "Production"
    "metrc_integrator_key":  "<vendor key from Metrc Connect>"
    "metrc_facilities": [
        {"license_number": "C12-1000001-LIC",
         "user_key": "<per-user key>",
         "warehouse": "Stores - MTM",          # optional
         "facility_name": "Microbusiness 01",  # optional
         "is_active": 1,
         "sync_packages": 1, "sync_transfers": 1, "sync_sales": 0}
    ]
    "metrc_alert_email":     "compliance@example.com"
"""

import frappe

DEFAULTS = {
    "environment": "Sandbox",
    "sandbox_base_url": "https://sandbox-api-ca.metrc.com",
    "production_base_url": "https://api-ca.metrc.com",
    "default_page_size": 20,
    "window_hours": 24,
    "max_retries": 4,
    "log_retention_days": 120,
}

FACILITY_FLAGS = (
    "sync_packages",
    "sync_transfers",
    "sync_sales",
    "sync_plants",
    "sync_harvests",
    "sync_labtests",
)


def configure(enable=True, push=False, dry_run=True):
    """Write settings from site_config.

    Defaults are deliberately conservative: pull enabled, push OFF. Turning on
    writes to a state system should be an explicit, separate decision.
    """
    conf = frappe.conf
    integrator = conf.get("metrc_integrator_key")
    if not integrator:
        frappe.throw(
            "site_config.json has no 'metrc_integrator_key'. Add the credentials there first "
            "(see the docstring in cannabis_management/metrc/bootstrap.py)."
        )

    settings = frappe.get_single("Metrc Settings")

    for field, value in DEFAULTS.items():
        if not settings.get(field):
            settings.set(field, value)

    if conf.get("metrc_environment"):
        settings.environment = conf.get("metrc_environment")

    settings.integrator_key = integrator
    settings.enabled = 1 if enable else 0
    settings.push_enabled = 1 if push else 0
    settings.dry_run = 1 if dry_run else 0

    if conf.get("metrc_alert_email"):
        settings.alert_email = conf.get("metrc_alert_email")

    existing = {row.license_number: row for row in settings.facilities}
    added = updated = 0

    for entry in conf.get("metrc_facilities") or []:
        licence = entry.get("license_number")
        if not licence:
            continue

        row = existing.get(licence)
        if row is None:
            row = settings.append("facilities", {"license_number": licence})
            added += 1
        else:
            updated += 1

        if entry.get("user_key"):
            row.user_key = entry["user_key"]
        for field in ("warehouse", "facility_name", "facility_timezone"):
            if entry.get(field):
                row.set(field, entry[field])
        if not row.facility_timezone:
            row.facility_timezone = "America/Los_Angeles"

        row.is_active = 1 if entry.get("is_active", 1) else 0
        for flag in FACILITY_FLAGS:
            if flag in entry:
                row.set(flag, 1 if entry[flag] else 0)

    settings.flags.ignore_permissions = True
    settings.save(ignore_permissions=True)
    frappe.db.commit()

    mode = f"{settings.environment} | pull={'on' if enable else 'off'} | "
    mode += f"push={'on' if push else 'OFF'} | dry_run={'on' if dry_run else 'off'}"
    print(f"Metrc Settings configured: {mode}")
    print(f"  facilities: {added} added, {updated} updated, {len(settings.facilities)} total")
    for row in settings.facilities:
        state = "active" if row.is_active else "inactive"
        print(f"    {row.license_number:22} {state:9} warehouse={row.warehouse or '-'}")
    return {"added": added, "updated": updated}


def map_warehouse(license_number, warehouse):
    """Link a licence to a Warehouse on both sides of the join."""
    settings = frappe.get_single("Metrc Settings")
    for row in settings.facilities:
        if row.license_number == license_number:
            row.warehouse = warehouse
            break
    else:
        frappe.throw(f"License {license_number} is not in Metrc Settings.")

    settings.flags.ignore_permissions = True
    settings.save(ignore_permissions=True)

    # The Warehouse custom field is what license_for_warehouse() walks, so it
    # must be set too or pushes from that warehouse will not route.
    frappe.db.set_value(
        "Warehouse", warehouse, "custom_metrc_license_number", license_number, update_modified=False
    )
    frappe.db.commit()
    print(f"Mapped {license_number} <-> {warehouse}")
