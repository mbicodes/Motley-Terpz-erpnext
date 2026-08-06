# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""One-shot installer for the Metrc module.

    bench --site <site> execute cannabis_management.metrc.install.setup

Creates the six Metrc doctypes and the custom fields that surface the
integration on the documents people already work in. Everything here is
idempotent - re-running it is the supported way to pick up new fields.

Deliberately does NOT recreate anything that predates this module:
Warehouse.custom_metrc_license_number, Batch.custom_metrc_tag,
Batch.custom_strain_name, Purchase Receipt.custom_metrc_tag_original,
Work Order.custom_customer_material_batch and the Stock Reconciliation
compliance block already exist and are reused as-is.
"""

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

MODULE = "Cannabis Management"

SYNC_STATUS_OPTIONS = "\nNot Tracked\nQueued\nSynced\nFailed\nParked"


# ---------------------------------------------------------------------------
# DocTypes
# ---------------------------------------------------------------------------


def _doctype(name, fields, **kw):
    """Create a DocType if absent. In developer mode Frappe writes the JSON
    into the app automatically, so these stay version-controlled."""
    if frappe.db.exists("DocType", name):
        print(f"  = {name} (exists)")
        return

    permissions = kw.pop(
        "permissions",
        [
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
        ],
    )
    doc = frappe.get_doc(
        {
            "doctype": "DocType",
            "name": name,
            "module": MODULE,
            "custom": 0,
            "fields": fields,
            "permissions": [] if kw.get("istable") else permissions,
            **kw,
        }
    )
    doc.insert(ignore_permissions=True)
    print(f"  + {name}")


def create_doctypes():
    print("Creating Metrc doctypes...")

    _doctype(
        "Metrc UOM Map",
        [
            {
                "fieldname": "erpnext_uom",
                "fieldtype": "Link",
                "options": "UOM",
                "label": "ERPNext UOM",
                "in_list_view": 1,
                "reqd": 1,
                "columns": 4,
            },
            {
                "fieldname": "metrc_uom",
                "fieldtype": "Select",
                "label": "Metrc UOM",
                "in_list_view": 1,
                "reqd": 1,
                "columns": 4,
                "options": (
                    "Each\nGrams\nKilograms\nMilligrams\nOunces\nPounds\n"
                    "Fluid Ounces\nGallons\nLiters\nMilliliters\nPints"
                ),
            },
        ],
        istable=1,
    )

    _doctype(
        "Metrc Facility",
        [
            {
                "fieldname": "license_number",
                "fieldtype": "Data",
                "label": "License Number",
                "in_list_view": 1,
                "reqd": 1,
                "columns": 2,
            },
            {
                "fieldname": "facility_name",
                "fieldtype": "Data",
                "label": "Facility Name",
                "in_list_view": 1,
                "columns": 2,
            },
            {
                "fieldname": "warehouse",
                "fieldtype": "Link",
                "options": "Warehouse",
                "label": "Warehouse",
                "in_list_view": 1,
                "columns": 2,
            },
            {"fieldname": "user_key", "fieldtype": "Password", "label": "User API Key"},
            {
                "fieldname": "facility_timezone",
                "fieldtype": "Data",
                "label": "Facility Timezone",
                "default": "America/Los_Angeles",
                "description": "Drives SalesDateTime, which Metrc reads as facility-local wall clock.",
            },
            {
                "fieldname": "is_active",
                "fieldtype": "Check",
                "label": "Active",
                "default": "1",
                "in_list_view": 1,
                "columns": 1,
            },
            {"fieldname": "sec_features", "fieldtype": "Section Break", "label": "Sync Scope"},
            {"fieldname": "sync_packages", "fieldtype": "Check", "label": "Packages", "default": "1"},
            {"fieldname": "sync_transfers", "fieldtype": "Check", "label": "Transfers", "default": "1"},
            {"fieldname": "sync_sales", "fieldtype": "Check", "label": "Sales Receipts"},
            {"fieldname": "cb_features", "fieldtype": "Column Break"},
            {"fieldname": "sync_plants", "fieldtype": "Check", "label": "Plants / Plant Batches"},
            {"fieldname": "sync_harvests", "fieldtype": "Check", "label": "Harvests"},
            {"fieldname": "sync_labtests", "fieldtype": "Check", "label": "Lab Tests"},
        ],
        istable=1,
    )

    _doctype(
        "Metrc Settings",
        [
            {
                "fieldname": "enabled",
                "fieldtype": "Check",
                "label": "Enabled",
                "description": "Master switch. When off, no pull or push runs.",
            },
            {
                "fieldname": "environment",
                "fieldtype": "Select",
                "label": "Environment",
                "options": "Sandbox\nProduction",
                "default": "Sandbox",
                "reqd": 1,
            },
            {"fieldname": "cb_env", "fieldtype": "Column Break"},
            {
                "fieldname": "sandbox_base_url",
                "fieldtype": "Data",
                "label": "Sandbox Base URL",
                "default": "https://sandbox-api-ca.metrc.com",
            },
            {
                "fieldname": "production_base_url",
                "fieldtype": "Data",
                "label": "Production Base URL",
                "default": "https://api-ca.metrc.com",
            },
            {"fieldname": "sec_auth", "fieldtype": "Section Break", "label": "Credentials"},
            {
                "fieldname": "integrator_key",
                "fieldtype": "Password",
                "label": "Integrator (Software) API Key",
                "description": "Vendor-wide key from Metrc Connect. Never share or commit this.",
            },
            {
                "fieldname": "connection_status",
                "fieldtype": "HTML",
                "label": "Connection Status",
            },
            {"fieldname": "sec_fac", "fieldtype": "Section Break", "label": "Facilities"},
            {
                "fieldname": "facilities",
                "fieldtype": "Table",
                "options": "Metrc Facility",
                "label": "Facilities",
                "description": "One row per Metrc licence. Map each to the ERPNext Warehouse it represents.",
            },
            {"fieldname": "sec_uom", "fieldtype": "Section Break", "label": "UOM Mapping"},
            {
                "fieldname": "uom_map",
                "fieldtype": "Table",
                "options": "Metrc UOM Map",
                "label": "UOM Map",
                "description": "Metrc accepts only 11 units. Map every UOM used on tracked items.",
            },
            {"fieldname": "sec_behav", "fieldtype": "Section Break", "label": "Behaviour"},
            {
                "fieldname": "push_enabled",
                "fieldtype": "Check",
                "label": "Enable Push (write to Metrc)",
                "description": "Separate from Enabled, so you can run pull-only.",
            },
            {
                "fieldname": "dry_run",
                "fieldtype": "Check",
                "label": "Dry Run (log payloads, do not transmit)",
                "description": "Rehearse writes against real data without touching Metrc.",
            },
            {"fieldname": "default_page_size", "fieldtype": "Int", "label": "Page Size", "default": "20"},
            {"fieldname": "cb_behav", "fieldtype": "Column Break"},
            {
                "fieldname": "window_hours",
                "fieldtype": "Int",
                "label": "Sync Window (hours)",
                "default": "24",
            },
            {"fieldname": "max_retries", "fieldtype": "Int", "label": "Max Retries", "default": "4"},
            {
                "fieldname": "log_retention_days",
                "fieldtype": "Int",
                "label": "Log Retention (days)",
                "default": "120",
            },
            {"fieldname": "alert_email", "fieldtype": "Data", "label": "Alert Email"},
        ],
        issingle=1,
    )

    _doctype(
        "Metrc Sync State",
        [
            {
                "fieldname": "license_number",
                "fieldtype": "Data",
                "label": "License Number",
                "in_list_view": 1,
                "reqd": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "endpoint_key",
                "fieldtype": "Data",
                "label": "Endpoint",
                "in_list_view": 1,
                "reqd": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "cursor_last_modified",
                "fieldtype": "Datetime",
                "label": "Cursor (LastModified)",
                "in_list_view": 1,
                "description": "Forward-only watermark. Metrc requires chronological sweeps.",
            },
            {"fieldname": "cb_1", "fieldtype": "Column Break"},
            {
                "fieldname": "last_status",
                "fieldtype": "Select",
                "label": "Last Status",
                "options": "\nSuccess\nPartial\nFailed",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {"fieldname": "last_run_start", "fieldtype": "Datetime", "label": "Last Run Start"},
            {"fieldname": "last_run_end", "fieldtype": "Datetime", "label": "Last Run End"},
            {"fieldname": "sec_2", "fieldtype": "Section Break"},
            {"fieldname": "records_synced", "fieldtype": "Int", "label": "Records Synced"},
            {
                "fieldname": "consecutive_failures",
                "fieldtype": "Int",
                "label": "Consecutive Failures",
                "in_list_view": 1,
            },
            {"fieldname": "last_error", "fieldtype": "Small Text", "label": "Last Error"},
        ],
        autoname="prompt",
        sort_field="modified",
        sort_order="DESC",
    )

    _doctype(
        "Metrc API Log",
        [
            {"fieldname": "timestamp", "fieldtype": "Datetime", "label": "Timestamp", "in_list_view": 1},
            {
                "fieldname": "direction",
                "fieldtype": "Select",
                "label": "Direction",
                "options": "Pull\nPush",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {"fieldname": "method", "fieldtype": "Data", "label": "Method", "in_list_view": 1},
            {
                "fieldname": "response_status",
                "fieldtype": "Int",
                "label": "Status",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {"fieldname": "cb_1", "fieldtype": "Column Break"},
            {
                "fieldname": "license_number",
                "fieldtype": "Data",
                "label": "License Number",
                "in_standard_filter": 1,
            },
            {"fieldname": "duration_ms", "fieldtype": "Int", "label": "Duration (ms)"},
            {"fieldname": "sec_ep", "fieldtype": "Section Break"},
            {"fieldname": "endpoint", "fieldtype": "Small Text", "label": "Endpoint"},
            {"fieldname": "error", "fieldtype": "Small Text", "label": "Error"},
            {"fieldname": "sec_body", "fieldtype": "Section Break", "label": "Payloads"},
            {"fieldname": "request_body", "fieldtype": "Code", "options": "JSON", "label": "Request"},
            {"fieldname": "response_body", "fieldtype": "Code", "options": "JSON", "label": "Response"},
            {"fieldname": "sec_ref", "fieldtype": "Section Break", "label": "Reference"},
            {
                "fieldname": "reference_doctype",
                "fieldtype": "Link",
                "options": "DocType",
                "label": "Reference DocType",
            },
            {
                "fieldname": "reference_name",
                "fieldtype": "Dynamic Link",
                "options": "reference_doctype",
                "label": "Reference Name",
            },
        ],
        autoname="hash",
        sort_field="timestamp",
        sort_order="DESC",
        permissions=[
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Stock Manager", "read": 1},
        ],
    )

    _doctype(
        "Metrc Outbox",
        [
            {
                "fieldname": "status",
                "fieldtype": "Select",
                "label": "Status",
                "options": "Queued\nIn Progress\nSuccess\nFailed\nParked",
                "default": "Queued",
                "in_list_view": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "operation",
                "fieldtype": "Data",
                "label": "Operation",
                "in_list_view": 1,
                "reqd": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "license_number",
                "fieldtype": "Data",
                "label": "License Number",
                "reqd": 1,
                "in_standard_filter": 1,
            },
            {"fieldname": "cb_1", "fieldtype": "Column Break"},
            {
                "fieldname": "reference_doctype",
                "fieldtype": "Link",
                "options": "DocType",
                "label": "Reference DocType",
            },
            {
                "fieldname": "reference_name",
                "fieldtype": "Dynamic Link",
                "options": "reference_doctype",
                "label": "Reference Name",
                "in_list_view": 1,
            },
            {"fieldname": "metrc_id", "fieldtype": "Data", "label": "Metrc ID", "read_only": 1},
            {"fieldname": "sec_state", "fieldtype": "Section Break", "label": "Delivery"},
            {"fieldname": "attempts", "fieldtype": "Int", "label": "Attempts", "in_list_view": 1},
            {"fieldname": "next_attempt_at", "fieldtype": "Datetime", "label": "Next Attempt At"},
            {"fieldname": "cb_2", "fieldtype": "Column Break"},
            {
                "fieldname": "idempotency_key",
                "fieldtype": "Data",
                "label": "Idempotency Key",
                "unique": 1,
                "read_only": 1,
            },
            {"fieldname": "sec_err", "fieldtype": "Section Break"},
            {"fieldname": "last_error", "fieldtype": "Small Text", "label": "Last Error"},
            {"fieldname": "sec_payload", "fieldtype": "Section Break", "label": "Payload"},
            {"fieldname": "payload", "fieldtype": "Code", "options": "JSON", "label": "Payload"},
            {"fieldname": "response", "fieldtype": "Code", "options": "JSON", "label": "Response"},
        ],
        autoname="hash",
        sort_field="creation",
        sort_order="DESC",
        permissions=[
            {"role": "System Manager", "read": 1, "write": 1, "create": 1, "delete": 1},
            {"role": "Stock Manager", "read": 1},
        ],
    )


# ---------------------------------------------------------------------------
# Custom fields
# ---------------------------------------------------------------------------


def _sync_status_field(insert_after, label="METRC Sync Status"):
    return {
        "fieldname": "custom_metrc_sync_status",
        "fieldtype": "Select",
        "label": label,
        "options": SYNC_STATUS_OPTIONS,
        "insert_after": insert_after,
        "read_only": 1,
        "allow_on_submit": 1,
        "in_list_view": 0,
        "in_standard_filter": 1,
        "translatable": 0,
    }


def add_settings_fields():
    """Append fields to the Metrc Settings DocType if they are missing.

    Metrc Settings is one of our own doctypes, so new fields are added to the
    DocType itself rather than as Custom Fields. Idempotent: re-running only
    adds what is absent, which is how later releases extend the settings.
    """
    if not frappe.db.exists("DocType", "Metrc Settings"):
        return

    new_fields = [
        {
            "fieldname": "sec_autocreate",
            "fieldtype": "Section Break",
            "label": "Auto-Create Masters",
        },
        {
            "fieldname": "auto_create_items",
            "fieldtype": "Check",
            "label": "Auto-Create Items from METRC",
            "description": (
                "Create an ERPNext Item when METRC has a product we do not carry. "
                "Created items are flagged for review and are NOT sales/purchase enabled "
                "until someone confirms them."
            ),
        },
        {
            "fieldname": "auto_item_group",
            "fieldtype": "Link",
            "options": "Item Group",
            "label": "Default Item Group",
            "depends_on": "auto_create_items",
            "description": "Item Group assigned to auto-created items.",
        },
        {
            "fieldname": "auto_item_uom",
            "fieldtype": "Link",
            "options": "UOM",
            "label": "Fallback UOM",
            "depends_on": "auto_create_items",
            "description": "Used only when the METRC unit has no mapping in the UOM Map.",
        },
        {"fieldname": "cb_autocreate", "fieldtype": "Column Break"},
        {
            "fieldname": "auto_item_is_stock_item",
            "fieldtype": "Check",
            "label": "Create as Stock Item",
            "default": "1",
            "depends_on": "auto_create_items",
        },
        {
            "fieldname": "auto_item_has_batch",
            "fieldtype": "Check",
            "label": "Enable Batch Tracking",
            "default": "1",
            "depends_on": "auto_create_items",
            "description": "Required for METRC package tracking - a Batch is a METRC package.",
        },
        {
            "fieldname": "auto_create_tags",
            "fieldtype": "Check",
            "label": "Auto-Create METRC Tags",
            "default": "1",
            "description": "Create Metric Tag records for tags and packages found in METRC.",
        },
    ]

    doctype = frappe.get_doc("DocType", "Metrc Settings")
    existing = {f.fieldname for f in doctype.fields}
    added = 0
    for spec in new_fields:
        if spec["fieldname"] in existing:
            continue
        doctype.append("fields", spec)
        added += 1

    if added:
        doctype.flags.ignore_permissions = True
        doctype.save(ignore_permissions=True)
        print(f"  + {added} field(s) added to Metrc Settings")
    else:
        print("  = Metrc Settings fields up to date")


def install_custom_fields():
    """Surface the integration on the documents people already use.

    Every field is read-only and allow_on_submit: these are written by the
    sync, never by a user, and they must be updatable after submission
    because that is when the push actually happens.
    """
    print("Installing Metrc custom fields...")

    fields = {
        # -------------------------------------------------------------- Item
        "Item": [
            {
                "fieldname": "custom_metrc_section",
                "fieldtype": "Section Break",
                "label": "METRC",
                "insert_after": "item_group",
                "collapsible": 1,
            },
            {
                "fieldname": "custom_metrc_tracked",
                "fieldtype": "Check",
                "label": "METRC Tracked",
                "insert_after": "custom_metrc_section",
                "description": "Stock of this item is reported to Metrc.",
            },
            {
                "fieldname": "custom_metrc_item_name",
                "fieldtype": "Data",
                "label": "METRC Item Name",
                "insert_after": "custom_metrc_tracked",
                "depends_on": "custom_metrc_tracked",
                "description": "Must match the item name in Metrc exactly. Defaults to Item Name.",
            },
            {
                "fieldname": "custom_metrc_category",
                "fieldtype": "Data",
                "label": "METRC Item Category",
                "insert_after": "custom_metrc_item_name",
                "depends_on": "custom_metrc_tracked",
            },
            {"fieldname": "custom_metrc_cb", "fieldtype": "Column Break", "insert_after": "custom_metrc_category"},
            {
                "fieldname": "custom_metrc_item_id",
                "fieldtype": "Int",
                "label": "METRC Item ID",
                "insert_after": "custom_metrc_cb",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_uom",
                "fieldtype": "Data",
                "label": "METRC UOM",
                "insert_after": "custom_metrc_item_id",
                "read_only": 1,
                "description": "Resolved from the UOM Map in Metrc Settings.",
            },
            {
                "fieldname": "custom_metrc_last_synced",
                "fieldtype": "Datetime",
                "label": "METRC Last Synced",
                "insert_after": "custom_metrc_uom",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_auto_created",
                "fieldtype": "Check",
                "label": "Auto-Created from METRC (needs review)",
                "insert_after": "custom_metrc_last_synced",
                "read_only": 1,
                "in_standard_filter": 1,
                "description": (
                    "Created by the METRC sync from defaults. Confirm item group, UOM and "
                    "accounts, then untick to mark it reviewed."
                ),
            },
        ],
        # --------------------------------------------------------- Warehouse
        # custom_metrc_license_number / custom_license_type already exist.
        "Warehouse": [
            {
                "fieldname": "custom_metrc_facility_name",
                "fieldtype": "Data",
                "label": "METRC Facility Name",
                "insert_after": "custom_metrc_license_number",
                "read_only": 1,
                "description": "Pulled from GET /facilities/v2/.",
            },
            {
                "fieldname": "custom_metrc_last_synced",
                "fieldtype": "Datetime",
                "label": "METRC Last Synced",
                "insert_after": "custom_metrc_facility_name",
                "read_only": 1,
            },
        ],
        # ------------------------------------------------------------- Batch
        # custom_metrc_tag / _last_synced / _license_source / custom_strain_name exist.
        "Batch": [
            {
                "fieldname": "custom_metrc_package_id",
                "fieldtype": "Int",
                "label": "METRC Package ID",
                "insert_after": "custom_metrc_tag",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_status",
                "fieldtype": "Select",
                "label": "METRC Package Status",
                "options": "\nActive\nOn Hold\nIn Transit\nFinished\nNot In METRC",
                "insert_after": "custom_metrc_package_id",
                "read_only": 1,
                "in_standard_filter": 1,
            },
            {
                "fieldname": "custom_metrc_quantity",
                "fieldtype": "Float",
                "label": "METRC Quantity",
                "insert_after": "custom_metrc_status",
                "read_only": 1,
                "precision": "4",
                "description": "Quantity per Metrc. Compared against the stock ledger by the variance report.",
            },
            {
                "fieldname": "custom_metrc_uom",
                "fieldtype": "Data",
                "label": "METRC UOM",
                "insert_after": "custom_metrc_quantity",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_variance",
                "fieldtype": "Float",
                "label": "METRC Variance",
                "insert_after": "custom_metrc_uom",
                "read_only": 1,
                "precision": "4",
                "description": "ERPNext ledger quantity minus Metrc quantity. Non-zero needs investigation.",
            },
            {
                "fieldname": "custom_metrc_lab_state",
                "fieldtype": "Select",
                "label": "METRC Lab Result",
                "options": "\nNot Tested\nPassed\nFailed",
                "insert_after": "custom_metrc_variance",
                "read_only": 1,
                "in_standard_filter": 1,
                "description": "Aggregated from Metrc lab results. Failed product must not be sold.",
            },
            {
                "fieldname": "custom_metrc_lab_result_date",
                "fieldtype": "Date",
                "label": "METRC Lab Result Date",
                "insert_after": "custom_metrc_lab_state",
                "read_only": 1,
            },
        ],
        # ----------------------------------------------------- Sales Invoice
        "Sales Invoice": [
            {
                "fieldname": "custom_metrc_section",
                "fieldtype": "Section Break",
                "label": "METRC",
                "insert_after": "customer",
                "collapsible": 1,
                "collapsible_depends_on": "custom_metrc_sync_status",
            },
            _sync_status_field("custom_metrc_section"),
            {
                "fieldname": "custom_metrc_receipt_id",
                "fieldtype": "Data",
                "label": "METRC Receipt ID",
                "insert_after": "custom_metrc_sync_status",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {"fieldname": "custom_metrc_cb", "fieldtype": "Column Break", "insert_after": "custom_metrc_receipt_id"},
            {
                "fieldname": "custom_metrc_license_number",
                "fieldtype": "Data",
                "label": "METRC License #",
                "insert_after": "custom_metrc_cb",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_synced_on",
                "fieldtype": "Datetime",
                "label": "METRC Synced On",
                "insert_after": "custom_metrc_license_number",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_message",
                "fieldtype": "Small Text",
                "label": "METRC Message",
                "insert_after": "custom_metrc_synced_on",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.custom_metrc_message",
            },
        ],
        # ----------------------------------------------------- Delivery Note
        "Delivery Note": [
            {
                "fieldname": "custom_metrc_section",
                "fieldtype": "Section Break",
                "label": "METRC Transfer",
                "insert_after": "customer",
                "collapsible": 1,
                "collapsible_depends_on": "custom_metrc_sync_status",
            },
            _sync_status_field("custom_metrc_section"),
            {
                "fieldname": "custom_metrc_transfer_id",
                "fieldtype": "Data",
                "label": "METRC Transfer ID",
                "insert_after": "custom_metrc_sync_status",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_manifest_number",
                "fieldtype": "Data",
                "label": "METRC Manifest #",
                "insert_after": "custom_metrc_transfer_id",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_transfer_type",
                "fieldtype": "Data",
                "label": "METRC Transfer Type",
                "insert_after": "custom_metrc_manifest_number",
                "default": "Transfer",
                "description": "Must match a type from GET /transfers/v2/types.",
            },
            {"fieldname": "custom_metrc_cb", "fieldtype": "Column Break", "insert_after": "custom_metrc_transfer_type"},
            {
                "fieldname": "custom_metrc_license_number",
                "fieldtype": "Data",
                "label": "METRC License #",
                "insert_after": "custom_metrc_cb",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_synced_on",
                "fieldtype": "Datetime",
                "label": "METRC Synced On",
                "insert_after": "custom_metrc_license_number",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_message",
                "fieldtype": "Small Text",
                "label": "METRC Message",
                "insert_after": "custom_metrc_synced_on",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.custom_metrc_message",
            },
        ],
        # ------------------------------------------------------- Stock Entry
        "Stock Entry": [
            {
                "fieldname": "custom_metrc_section",
                "fieldtype": "Section Break",
                "label": "METRC",
                "insert_after": "purpose",
                "collapsible": 1,
                "collapsible_depends_on": "custom_metrc_sync_status",
            },
            _sync_status_field("custom_metrc_section"),
            {
                "fieldname": "custom_metrc_operation",
                "fieldtype": "Data",
                "label": "METRC Operation",
                "insert_after": "custom_metrc_sync_status",
                "read_only": 1,
                "allow_on_submit": 1,
                "description": "Which Metrc call this entry produced, e.g. packages.adjust.",
            },
            {"fieldname": "custom_metrc_cb", "fieldtype": "Column Break", "insert_after": "custom_metrc_operation"},
            {
                "fieldname": "custom_metrc_reference_id",
                "fieldtype": "Data",
                "label": "METRC Reference ID",
                "insert_after": "custom_metrc_cb",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_synced_on",
                "fieldtype": "Datetime",
                "label": "METRC Synced On",
                "insert_after": "custom_metrc_reference_id",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_message",
                "fieldtype": "Small Text",
                "label": "METRC Message",
                "insert_after": "custom_metrc_synced_on",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.custom_metrc_message",
            },
        ],
        # ---------------------------------------------- Stock Reconciliation
        # custom_compliance_section / custom_metrc_correction_made exist.
        "Stock Reconciliation": [
            _sync_status_field("custom_metrc_correction_made"),
            {
                "fieldname": "custom_metrc_adjustment_reason",
                "fieldtype": "Data",
                "label": "METRC Adjustment Reason",
                "insert_after": "custom_metrc_sync_status",
                "allow_on_submit": 1,
                "description": "Must match a reason from GET /packages/v2/adjust/reasons.",
            },
            {
                "fieldname": "custom_metrc_synced_on",
                "fieldtype": "Datetime",
                "label": "METRC Synced On",
                "insert_after": "custom_metrc_adjustment_reason",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_message",
                "fieldtype": "Small Text",
                "label": "METRC Message",
                "insert_after": "custom_metrc_synced_on",
                "read_only": 1,
                "allow_on_submit": 1,
                "depends_on": "eval:doc.custom_metrc_message",
            },
        ],
        # --------------------------------------------------- Purchase Receipt
        "Purchase Receipt": [
            {
                "fieldname": "custom_metrc_transfer_id",
                "fieldtype": "Data",
                "label": "METRC Transfer ID",
                "insert_after": "custom_metrc_tag_original",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            {
                "fieldname": "custom_metrc_manifest_number",
                "fieldtype": "Data",
                "label": "METRC Manifest #",
                "insert_after": "custom_metrc_transfer_id",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            _sync_status_field("custom_metrc_manifest_number"),
        ],
        # --------------------------------------------------------- Work Order
        "Work Order": [
            {
                "fieldname": "custom_metrc_job_type",
                "fieldtype": "Data",
                "label": "METRC Processing Job Type",
                "insert_after": "custom_customer_material_batch",
                "description": "Must match a job type from GET /processing/v2/jobtypes/active.",
            },
            {
                "fieldname": "custom_metrc_job_id",
                "fieldtype": "Data",
                "label": "METRC Processing Job ID",
                "insert_after": "custom_metrc_job_type",
                "read_only": 1,
                "allow_on_submit": 1,
            },
            _sync_status_field("custom_metrc_job_id"),
        ],
        # ---------------------------------------------------------- Customer
        # custom_license_number / _type / _expiry already exist.
        "Customer": [
            {
                "fieldname": "custom_metrc_license_verified",
                "fieldtype": "Check",
                "label": "METRC License Verified",
                "insert_after": "custom_license_expiry",
                "read_only": 1,
                "description": "Set when the licence is confirmed as a valid Metrc recipient.",
            },
        ],
        # ------------------------------------------------------- Metric Tag
        "Metric Tag": [
            {
                "fieldname": "custom_metrc_section",
                "fieldtype": "Section Break",
                "label": "METRC Sync",
                "insert_after": "last_updated",
                "collapsible": 1,
            },
            {
                "fieldname": "custom_metrc_package_id",
                "fieldtype": "Int",
                "label": "METRC Package ID",
                "insert_after": "custom_metrc_section",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_status",
                "fieldtype": "Data",
                "label": "METRC Package Status",
                "insert_after": "custom_metrc_package_id",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_license_number",
                "fieldtype": "Data",
                "label": "METRC License #",
                "insert_after": "custom_metrc_status",
                "read_only": 1,
            },
            {"fieldname": "custom_metrc_cb", "fieldtype": "Column Break", "insert_after": "custom_metrc_license_number"},
            {
                "fieldname": "custom_metrc_quantity",
                "fieldtype": "Float",
                "label": "METRC Quantity",
                "insert_after": "custom_metrc_cb",
                "read_only": 1,
                "precision": "4",
            },
            {
                "fieldname": "custom_metrc_uom",
                "fieldtype": "Data",
                "label": "METRC UOM",
                "insert_after": "custom_metrc_quantity",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_variance",
                "fieldtype": "Float",
                "label": "Variance vs Ledger",
                "insert_after": "custom_metrc_uom",
                "read_only": 1,
                "precision": "4",
            },
            {
                "fieldname": "custom_metrc_lab_state",
                "fieldtype": "Data",
                "label": "METRC Lab Result",
                "insert_after": "custom_metrc_variance",
                "read_only": 1,
            },
            {
                "fieldname": "custom_metrc_last_synced",
                "fieldtype": "Datetime",
                "label": "METRC Last Synced",
                "insert_after": "custom_metrc_lab_state",
                "read_only": 1,
            },
        ],
    }

    create_custom_fields(fields, ignore_validate=True)
    print(f"  + custom fields on {len(fields)} doctypes")


def seed_uom_map():
    """Pre-fill the UOM map with any existing ERPNext UOM whose name we can
    confidently resolve, so a fresh install is usable immediately."""
    from cannabis_management.metrc.mapping import to_metrc_uom

    settings = frappe.get_single("Metrc Settings")
    if settings.uom_map:
        print("  = UOM map already populated")
        return

    added = 0
    for uom in frappe.get_all("UOM", pluck="name"):
        mapped = to_metrc_uom(uom, raise_on_missing=False)
        if mapped:
            settings.append("uom_map", {"erpnext_uom": uom, "metrc_uom": mapped})
            added += 1

    if added:
        settings.flags.ignore_permissions = True
        settings.save(ignore_permissions=True)
    print(f"  + seeded {added} UOM mappings")


def setup():
    """Full install. Safe to re-run."""
    create_doctypes()
    frappe.db.commit()
    install_custom_fields()
    frappe.db.commit()
    seed_uom_map()
    frappe.db.commit()
    frappe.clear_cache()
    print("\nMetrc module installed.")
    print("Next: open Metrc Settings, add the integrator key and one facility, then Test Connection.")
