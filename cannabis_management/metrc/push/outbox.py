# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Transactional outbox for Metrc writes.

Documents enqueue; a scheduled worker drains. This exists because calling Metrc
synchronously from on_submit would couple ERPNext operations to a third-party
state system's uptime: a Metrc 500 during Sales Invoice submission would either
roll back the invoice or leave it submitted-but-unreported. Neither is
acceptable.

enqueue() runs inside the caller's transaction, so the outbox row and the
document commit together or not at all.
"""

import hashlib
import json

import frappe
from frappe.utils import add_to_date, now_datetime

from cannabis_management.metrc import config
from cannabis_management.metrc.client import get_client
from cannabis_management.metrc.exceptions import TERMINAL_ERRORS

BATCH_SIZE = 50
MAX_ATTEMPTS = 6


def make_key(operation, reference_doctype, reference_name, discriminator=""):
    raw = f"{operation}:{reference_doctype}:{reference_name}:{discriminator}"
    return hashlib.sha256(raw.encode()).hexdigest()[:40]


def enqueue(
    operation,
    license_number,
    payload,
    reference_doctype=None,
    reference_name=None,
    discriminator="",
):
    """Queue a Metrc write.

    Safe to call twice: the unique idempotency key makes a repeat a no-op,
    which is what makes document hooks safe to re-run (amend, resubmit).
    """
    key = make_key(operation, reference_doctype, reference_name, discriminator)
    existing = frappe.db.get_value("Metrc Outbox", {"idempotency_key": key}, "name")
    if existing:
        return existing

    doc = frappe.new_doc("Metrc Outbox")
    doc.status = "Queued"
    doc.operation = operation
    doc.license_number = license_number
    doc.payload = json.dumps(payload, indent=2, default=str)
    doc.idempotency_key = key
    doc.reference_doctype = reference_doctype
    doc.reference_name = reference_name
    doc.next_attempt_at = now_datetime()
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return doc.name


def process_outbox():
    """Scheduled worker. Drains queued and due-for-retry rows."""
    if not config.is_enabled() or not config.push_enabled():
        return

    rows = frappe.get_all(
        "Metrc Outbox",
        filters={
            "status": ["in", ["Queued", "Failed"]],
            "next_attempt_at": ["<=", now_datetime()],
        },
        fields=["name"],
        order_by="creation asc",
        limit=BATCH_SIZE,
    )
    for row in rows:
        try:
            process_one(row.name)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"[metrc] outbox row crashed: {row.name}")


def process_one(name):
    from cannabis_management.metrc.push import HANDLERS

    doc = frappe.get_doc("Metrc Outbox", name)
    handler = HANDLERS.get(doc.operation)
    if not handler:
        _park(doc, f"No handler registered for operation '{doc.operation}'")
        return

    doc.db_set("status", "In Progress", update_modified=False, commit=True)

    try:
        client = get_client(doc.license_number)
        payload = json.loads(doc.payload) if doc.payload else None
        result = handler(client, payload, doc)

        doc.db_set(
            {
                "status": "Success",
                "attempts": (doc.attempts or 0) + 1,
                "response": json.dumps(result, indent=2, default=str) if result is not None else None,
                "metrc_id": _extract_id(result),
                "last_error": None,
            },
            update_modified=False,
            commit=True,
        )
        _stamp_source(doc, "Synced", metrc_id=_extract_id(result))

    except TERMINAL_ERRORS as e:
        _park(doc, str(e))

    except Exception as e:
        attempts = (doc.attempts or 0) + 1
        if attempts >= MAX_ATTEMPTS:
            _park(doc, f"Gave up after {attempts} attempts: {e}")
            return
        doc.db_set(
            {
                "status": "Failed",
                "attempts": attempts,
                "last_error": str(e)[:1000],
                # 2, 4, 8, 16, 32 minutes
                "next_attempt_at": add_to_date(now_datetime(), minutes=2**attempts),
            },
            update_modified=False,
            commit=True,
        )
        _stamp_source(doc, "Failed", message=str(e)[:500])


def _park(doc, error):
    """Terminal failure. Parked rows never retry and need a human."""
    doc.db_set(
        {"status": "Parked", "attempts": (doc.attempts or 0) + 1, "last_error": error[:1000]},
        update_modified=False,
        commit=True,
    )
    _stamp_source(doc, "Parked", message=error[:500])
    frappe.log_error(
        f"Outbox {doc.name} ({doc.operation}) parked:\n{error}", "[metrc] outbox parked"
    )


def _stamp_source(doc, status, metrc_id=None, message=None):
    """Write sync state back onto the source document.

    This is what makes the integration legible in the UI: an operator opens the
    Sales Invoice and sees Synced/Failed plus the Metrc ID, without going near
    the outbox.
    """
    if not (doc.reference_doctype and doc.reference_name):
        return
    if not frappe.db.exists(doc.reference_doctype, doc.reference_name):
        return

    meta = frappe.get_meta(doc.reference_doctype)
    values = {}

    if meta.has_field("custom_metrc_sync_status"):
        values["custom_metrc_sync_status"] = status
    if meta.has_field("custom_metrc_synced_on"):
        values["custom_metrc_synced_on"] = now_datetime()
    if meta.has_field("custom_metrc_message"):
        values["custom_metrc_message"] = message
    if meta.has_field("custom_metrc_license_number"):
        values["custom_metrc_license_number"] = doc.license_number

    if metrc_id:
        for fieldname in (
            "custom_metrc_receipt_id",
            "custom_metrc_transfer_id",
            "custom_metrc_job_id",
            "custom_metrc_reference_id",
        ):
            if meta.has_field(fieldname):
                values[fieldname] = str(metrc_id)
                break

    if meta.has_field("custom_metrc_operation"):
        values["custom_metrc_operation"] = doc.operation

    if values:
        try:
            frappe.db.set_value(
                doc.reference_doctype, doc.reference_name, values, update_modified=False
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), "[metrc] failed stamping source doc")


def _extract_id(result):
    if isinstance(result, dict):
        ids = result.get("Ids")
        if ids:
            return str(ids[0])
        if result.get("Id"):
            return str(result["Id"])
    if isinstance(result, list) and result:
        first = result[0]
        if isinstance(first, dict) and first.get("Id"):
            return str(first["Id"])
        return str(first)
    return None


# ---------------------------------------------------------------------------
# Whitelisted actions
# ---------------------------------------------------------------------------


@frappe.whitelist()
def retry(name):
    """Re-queue a parked or failed row from the UI."""
    frappe.only_for(("System Manager", "Stock Manager"))
    doc = frappe.get_doc("Metrc Outbox", name)
    doc.db_set(
        {"status": "Queued", "next_attempt_at": now_datetime(), "last_error": None},
        update_modified=False,
        commit=True,
    )
    process_one(name)
    return frappe.db.get_value("Metrc Outbox", name, ["status", "last_error", "metrc_id"], as_dict=True)


@frappe.whitelist()
def retry_all_parked():
    frappe.only_for("System Manager")
    names = frappe.get_all("Metrc Outbox", filters={"status": "Parked"}, pluck="name")
    for name in names:
        frappe.db.set_value(
            "Metrc Outbox",
            name,
            {"status": "Queued", "next_attempt_at": now_datetime()},
            update_modified=False,
        )
    frappe.db.commit()
    return len(names)


@frappe.whitelist()
def queue_depth():
    """Counts for the workspace number cards."""
    return {
        status: frappe.db.count("Metrc Outbox", {"status": status})
        for status in ("Queued", "In Progress", "Success", "Failed", "Parked")
    }
