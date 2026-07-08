import frappe
from frappe.utils import flt

FROZEN_FLIP_ITEM_GROUP = "Fresh Frozen"


@frappe.whitelist()
def get_active_harvests():
    return frappe.get_all(
        "Farm Production Batch",
        filters={"status": "Active"},
        fields=[
            "name", "harvest_name", "strains", "harvest_date", "lbs_produced",
            "revenue_to_date", "costs_to_date", "gross_profit", "net_to_date",
        ],
        order_by="harvest_date desc",
    )


@frappe.whitelist()
def get_archived_harvests():
    return frappe.get_all(
        "Farm Production Batch",
        filters={"status": "Archived"},
        fields=["name", "harvest_name", "strains", "harvest_date", "lbs_produced", "revenue_to_date", "net_to_date"],
        order_by="harvest_date desc",
    )


@frappe.whitelist()
def set_harvest_status(harvest_name, new_status):
    if new_status not in ("Active", "Archived"):
        frappe.throw("new_status must be Active or Archived")

    doc = frappe.get_doc("Farm Production Batch", harvest_name)
    doc.status = new_status
    doc.save()
    return doc.status


@frappe.whitelist()
def get_procurement_cards():
    items = frappe.get_all("Item", filters={"item_group": FROZEN_FLIP_ITEM_GROUP}, pluck="name")
    if not items:
        return []

    batches = frappe.get_all(
        "Batch",
        filters={"item": ["in", items], "custom_procurement_status": "Active"},
        fields=["name", "item", "batch_qty", "supplier", "manufacturing_date"],
    )

    for b in batches:
        # batch_qty is ERPNext's LIVE remaining stock (decreases on every sale) —
        # Lbs Procured must instead be the fixed original incoming quantity.
        # ERPNext v15 stores batch movements in Serial and Batch Entry (child
        # of Serial and Batch Bundle) — Stock Ledger Entry.batch_no is not
        # populated here. Sum every incoming (positive) qty ever posted
        # against this batch on a submitted bundle — Purchase Receipt, Stock
        # Entry top-up, Stock Reconciliation, etc. Sales/deliveries post
        # negative qty, so this total only ever grows: once a quantity is
        # procured it stays counted, even after it is fully sold.
        procured = frappe.db.sql(
            """
            SELECT COALESCE(SUM(sbe.qty), 0)
            FROM `tabSerial and Batch Entry` sbe
            INNER JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
            WHERE sbe.batch_no = %s AND sbe.qty > 0 AND sbb.docstatus = 1
            """,
            b["name"],
        )[0][0]

        sold = frappe.db.sql(
            "SELECT COALESCE(SUM(qty), 0), AVG(rate) FROM `tabSales Invoice Item` WHERE batch_no = %s",
            b["name"],
        )[0]
        b["lbs_procured"] = flt(procured)
        b["remaining_stock"] = flt(b["batch_qty"])
        b["lbs_sold"] = flt(sold[0])
        b["avg_price"] = flt(sold[1])

        # Vendor + date must come from the actual Purchase Receipt that brought this batch in,
        # not the Batch doctype's own supplier/manufacturing_date fields (unreliable/blank).
        receipt = frappe.db.sql(
            """
            SELECT pr.supplier_name, pr.posting_date
            FROM `tabPurchase Receipt Item` pri
            INNER JOIN `tabPurchase Receipt` pr ON pr.name = pri.parent
            WHERE pri.batch_no = %s AND pr.docstatus = 1
            ORDER BY pr.posting_date ASC
            LIMIT 1
            """,
            b["name"],
            as_dict=True,
        )
        b["vendor"] = receipt[0].supplier_name if receipt else b.get("supplier")
        b["receipt_date"] = receipt[0].posting_date if receipt else b.get("manufacturing_date")

    return batches


@frappe.whitelist()
def get_archived_procurement_cards():
    items = frappe.get_all("Item", filters={"item_group": FROZEN_FLIP_ITEM_GROUP}, pluck="name")
    if not items:
        return []

    batches = frappe.get_all(
        "Batch",
        filters={"item": ["in", items], "custom_procurement_status": "Archived"},
        fields=["name", "item", "batch_qty"],
    )

    for b in batches:
        # See note in get_procurement_cards() — batch movements live in
        # Serial and Batch Entry, not Stock Ledger Entry.batch_no, in v15.
        procured = frappe.db.sql(
            """
            SELECT COALESCE(SUM(sbe.qty), 0)
            FROM `tabSerial and Batch Entry` sbe
            INNER JOIN `tabSerial and Batch Bundle` sbb ON sbb.name = sbe.parent
            WHERE sbe.batch_no = %s AND sbe.qty > 0 AND sbb.docstatus = 1
            """,
            b["name"],
        )[0][0]

        sold = frappe.db.sql(
            "SELECT COALESCE(SUM(qty), 0) FROM `tabSales Invoice Item` WHERE batch_no = %s",
            b["name"],
        )[0][0]

        b["lbs_procured"] = flt(procured)
        b["lbs_sold"] = flt(sold)
        b["remaining_stock"] = flt(b["batch_qty"])

    return batches


@frappe.whitelist()
def set_batch_status(batch_name, new_status):
    if new_status not in ("Active", "Archived"):
        frappe.throw("new_status must be Active or Archived")

    doc = frappe.get_doc("Batch", batch_name)
    doc.custom_procurement_status = new_status
    doc.save()
    return doc.custom_procurement_status
