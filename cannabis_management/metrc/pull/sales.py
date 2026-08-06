# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Pull Metrc sales receipts back onto Sales Invoices.

This is confirmation, not creation. We never build a Sales Invoice from a Metrc
receipt - the invoice is the source document and already exists. What matters
is closing the loop: proving the receipt Metrc holds matches what we pushed, so
an operator can see at a glance that a sale is reported.

ExternalReceiptNumber is set to the Sales Invoice name on push, which is what
makes the match possible.
"""

import frappe
from frappe.utils import flt, now_datetime

from cannabis_management.metrc.pull.base import sweep


def sync_receipts(license_number):
    total = 0
    for endpoint_key, path in (
        ("sales.receipts.active", "/sales/v2/receipts/active"),
        ("sales.receipts.inactive", "/sales/v2/receipts/inactive"),
    ):
        total += sweep(license_number, endpoint_key, path, upsert_receipts)
    return total


def upsert_receipts(rows, license_number):
    for receipt in rows:
        external = receipt.get("ExternalReceiptNumber")
        receipt_id = receipt.get("Id")
        if not receipt_id:
            continue
        try:
            _confirm(receipt, external, receipt_id, license_number)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"[metrc] receipt confirm failed: {receipt_id}")
    frappe.db.commit()


def _confirm(receipt, external, receipt_id, license_number):
    """Match a Metrc receipt to its Sales Invoice and record confirmation."""
    invoice = None

    if external and frappe.db.exists("Sales Invoice", external):
        invoice = external
    else:
        invoice = frappe.db.get_value(
            "Sales Invoice", {"custom_metrc_receipt_id": str(receipt_id)}, "name"
        )

    if not invoice:
        # A receipt recorded directly in Metrc, or by another integrator.
        # reconcile.unmatched_receipts() surfaces these.
        return

    total = flt(receipt.get("TotalPrice") or receipt.get("TotalPackagedQuantity"))
    values = {
        "custom_metrc_receipt_id": str(receipt_id),
        "custom_metrc_sync_status": "Synced",
        "custom_metrc_license_number": license_number,
        "custom_metrc_synced_on": now_datetime(),
    }

    if receipt.get("IsVoided"):
        values["custom_metrc_sync_status"] = "Failed"
        values["custom_metrc_message"] = "Receipt is voided in Metrc."
    elif total:
        invoice_total = flt(frappe.db.get_value("Sales Invoice", invoice, "grand_total"))
        if invoice_total and abs(invoice_total - total) > 0.01:
            values["custom_metrc_message"] = (
                f"Metrc receipt total {total:.2f} differs from invoice total {invoice_total:.2f}."
            )

    frappe.db.set_value("Sales Invoice", invoice, values, update_modified=False)
