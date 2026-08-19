# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""Variance detection between Metrc and the ERPNext stock ledger.

Never auto-corrects. A quantity difference is either a data-entry error or a
real physical discrepancy; both need a human, and the fix belongs in a Stock
Reconciliation with custom_metrc_correction_made set so the correction is
itself auditable.

This is the part of the integration that earns its keep before any write goes
live - a read-only install already produces a daily variance report.
"""

import frappe
from frappe.utils import flt, now_datetime

TOLERANCE = 0.01


def find_variances(license_number=None, limit=None):
    """Tags where Metrc quantity and the ledger disagree.

    Metric Tag.current_qty is maintained by the existing Inventory Dimension
    sync and is ledger-derived, so it is the authoritative ERPNext number - no
    need to re-aggregate the ledger here.
    """
    filters = {"custom_metrc_package_id": [">", 0]}
    if license_number:
        filters["custom_metrc_license_number"] = license_number

    tags = frappe.get_all(
        "Metric Tag",
        filters=filters,
        fields=[
            "name",
            "item_code",
            "warehouse",
            "status",
            "current_qty",
            "custom_metrc_quantity",
            "custom_metrc_uom",
            "custom_metrc_status",
            "custom_metrc_license_number",
            "custom_metrc_last_synced",
        ],
        limit=limit,
    )

    variances = []
    for tag in tags:
        ledger = flt(tag.current_qty)
        metrc = flt(tag.custom_metrc_quantity)
        difference = ledger - metrc
        if abs(difference) <= TOLERANCE:
            continue
        variances.append(
            {
                "metric_tag": tag.name,
                "item_code": tag.item_code,
                "warehouse": tag.warehouse,
                "license_number": tag.custom_metrc_license_number,
                "erpnext_qty": ledger,
                "metrc_qty": metrc,
                "difference": difference,
                "uom": tag.custom_metrc_uom,
                "erpnext_status": tag.status,
                "metrc_status": tag.custom_metrc_status,
                "last_synced": tag.custom_metrc_last_synced,
            }
        )

    return sorted(variances, key=lambda v: abs(v["difference"]), reverse=True)


def refresh_variance_fields(license_number=None):
    """Recompute the stored variance mirror so it is queryable and filterable."""
    filters = {"custom_metrc_package_id": [">", 0]}
    if license_number:
        filters["custom_metrc_license_number"] = license_number

    updated = 0
    for tag in frappe.get_all(
        "Metric Tag", filters=filters, fields=["name", "current_qty", "custom_metrc_quantity"]
    ):
        variance = flt(tag.current_qty) - flt(tag.custom_metrc_quantity)
        frappe.db.set_value(
            "Metric Tag", tag.name, "custom_metrc_variance", variance, update_modified=False
        )
        updated += 1

    frappe.db.commit()
    return updated


def find_orphan_tags(license_number=None):
    """Tags Metrc reports as active with no ERPNext Batch behind them."""
    conditions = "and mt.custom_metrc_license_number = %(lic)s" if license_number else ""
    return frappe.db.sql(
        f"""
        select mt.name as metric_tag, mt.item_code, mt.custom_metrc_quantity as metrc_qty,
               mt.custom_metrc_uom as uom, mt.custom_metrc_license_number as license_number
        from `tabMetric Tag` mt
        left join `tabBatch` b on b.custom_metrc_tag = mt.name
        where mt.custom_metrc_status = 'Active'
          and mt.custom_metrc_quantity > 0
          and b.name is null
          {conditions}
        order by mt.custom_metrc_quantity desc
        """,  # nosemgrep
        {"lic": license_number},
        as_dict=True,
    )


def find_untagged_stock(license_number=None):
    """The reverse gap: ERPNext stock of a tracked item with no Metrc tag.

    This is the more dangerous direction - product we hold but have not
    reported.
    """
    return frappe.db.sql(
        """
        select b.name as batch, b.item as item_code, sum(sle.actual_qty) as erpnext_qty
        from `tabStock Ledger Entry` sle
        inner join `tabBatch` b on b.name = sle.batch_no
        inner join `tabItem` i on i.name = b.item
        where sle.is_cancelled = 0
          and i.custom_metrc_tracked = 1
          and (b.custom_metrc_tag is null or b.custom_metrc_tag = '')
        group by b.name, b.item
        having sum(sle.actual_qty) > 0
        order by erpnext_qty desc
        """,
        as_dict=True,
    )


def unmatched_items(license_number=None):
    """Items flagged as tracked that Metrc has never confirmed an ID for."""
    return frappe.get_all(
        "Item",
        filters={"custom_metrc_tracked": 1, "custom_metrc_item_id": ["in", [0, None]]},
        fields=["name", "item_name", "item_group", "stock_uom", "custom_metrc_item_name"],
    )


def unmatched_receipts(license_number=None):
    """Invoices queued or failed for longer than a day."""
    return frappe.get_all(
        "Sales Invoice",
        filters={
            "docstatus": 1,
            "custom_metrc_sync_status": ["in", ["Queued", "Failed", "Parked"]],
            "posting_date": ["<", frappe.utils.add_days(frappe.utils.nowdate(), -1)],
        },
        fields=["name", "customer", "posting_date", "grand_total", "custom_metrc_sync_status"],
    )


# ---------------------------------------------------------------------------
# Daily report
# ---------------------------------------------------------------------------


def send_daily_variance_report():
    refresh_variance_fields()

    variances = find_variances()
    orphans = find_orphan_tags()
    untagged = find_untagged_stock()
    stale = unmatched_receipts()

    if not (variances or orphans or untagged or stale):
        return

    recipient = frappe.db.get_single_value("Metrc Settings", "alert_email")
    if not recipient:
        return

    sections = []

    if variances:
        rows = "".join(
            f"<tr><td>{v['metric_tag']}</td><td>{v['item_code'] or ''}</td>"
            f"<td align='right'>{v['erpnext_qty']:.4f}</td>"
            f"<td align='right'>{v['metrc_qty']:.4f}</td>"
            f"<td align='right'><b>{v['difference']:+.4f}</b></td>"
            f"<td>{v['uom'] or ''}</td></tr>"
            for v in variances[:100]
        )
        sections.append(
            f"<h3>Quantity variances ({len(variances)})</h3>"
            "<table border='1' cellpadding='4' cellspacing='0'><tr><th>Tag</th><th>Item</th>"
            "<th>ERPNext</th><th>Metrc</th><th>Difference</th><th>UOM</th></tr>"
            f"{rows}</table>"
        )

    if untagged:
        rows = "".join(
            f"<tr><td>{u['batch']}</td><td>{u['item_code']}</td>"
            f"<td align='right'>{flt(u['erpnext_qty']):.4f}</td></tr>"
            for u in untagged[:50]
        )
        sections.append(
            f"<h3>Untagged stock of tracked items ({len(untagged)})</h3>"
            "<p>Product we hold that has no Metrc tag - the higher-risk direction.</p>"
            "<table border='1' cellpadding='4' cellspacing='0'>"
            f"<tr><th>Batch</th><th>Item</th><th>Qty</th></tr>{rows}</table>"
        )

    if orphans:
        sections.append(
            f"<h3>Orphan Metrc tags ({len(orphans)})</h3>"
            "<p>Active in Metrc with no ERPNext Batch - usually an unmapped Item.</p>"
        )

    if stale:
        sections.append(
            f"<h3>Sales Invoices not synced ({len(stale)})</h3>"
            "<p>Submitted over a day ago and still Queued/Failed/Parked.</p>"
        )

    frappe.sendmail(
        recipients=[recipient],
        subject=(
            f"[METRC] {len(variances)} variance(s), {len(untagged)} untagged, "
            f"{len(orphans)} orphan tag(s)"
        ),
        message="".join(sections),
    )


@frappe.whitelist()
def variance_summary(license_number=None):
    """Counts for the workspace cards and the Settings dashboard."""
    return {
        "variances": len(find_variances(license_number)),
        "orphan_tags": len(find_orphan_tags(license_number)),
        "untagged_stock": len(find_untagged_stock(license_number)),
        "unmatched_items": len(unmatched_items(license_number)),
        "stale_receipts": len(unmatched_receipts(license_number)),
        "as_of": now_datetime(),
    }
