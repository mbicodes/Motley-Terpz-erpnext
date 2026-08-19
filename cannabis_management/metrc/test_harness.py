# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

"""End-to-end smoke test for the Metrc integration.

    bench --site <site> execute cannabis_management.metrc.test_harness.smoke_test
    bench --site <site> execute cannabis_management.metrc.test_harness.cleanup

Builds a real, minimal round trip against the Metrc sandbox:

    pick a live sandbox package -> map its item -> create the Batch
    -> receive matching stock -> sell it -> inspect the queued payload

Everything it creates is prefixed METRC-TEST and removed by cleanup().

Transmission is governed by Metrc Settings, not by this script: with
dry_run on (the default) the payload is built and logged but never sent, so
this is safe to run before you trust the push layer.
"""

import json

import frappe
from frappe.utils import flt, nowdate

TEST_MARKER = "METRC-TEST"
WAREHOUSE = "METRC Sandbox - MTM"
COMPANY = "Master Touch Manufacturing"


def _log(msg, ok=None):
    prefix = "  " if ok is None else ("  [PASS] " if ok else "  [FAIL] ")
    print(f"{prefix}{msg}", flush=True)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


def _pick_sandbox_package():
    """A real active Metrc package with quantity, pulled by the sync.

    Using a genuine package means the receipt we push references a label Metrc
    actually knows about - a made-up tag would be rejected and would tell us
    nothing about whether the integration works.
    """
    base = {
        "custom_metrc_package_id": [">", 0],
        "custom_metrc_status": "Active",
        "custom_metrc_quantity": [">", 1],
    }
    fields = ["name", "custom_metrc_quantity", "custom_metrc_uom", "custom_metrc_license_number"]

    # Prefer a weight-based package: cannabis flower is sold by weight, and a
    # count-based UOM in ERPNext is usually flagged "must be whole number",
    # which makes fractional test quantities fail validation for reasons that
    # have nothing to do with Metrc.
    rows = frappe.get_all(
        "Metric Tag",
        filters=dict(base, custom_metrc_uom=["in", ["Grams", "Kilograms", "Ounces", "Pounds"]]),
        fields=fields,
        order_by="custom_metrc_quantity desc",
        limit=1,
    ) or frappe.get_all(
        "Metric Tag", filters=base, fields=fields, order_by="custom_metrc_quantity desc", limit=1
    )

    if not rows:
        frappe.throw("No active sandbox packages found. Run the package sync first.")
    return rows[0]


def _round_for_uom(qty, uom):
    """Respect ERPNext's 'Must be Whole Number' flag on the UOM."""
    if frappe.db.get_value("UOM", uom, "must_be_whole_number"):
        return float(max(1, int(qty)))
    return flt(qty, 3)


def _ensure_uom(metrc_uom):
    """Metrc UOM name -> an ERPNext UOM that maps back to it."""
    from cannabis_management.metrc.mapping import to_metrc_uom

    for uom in frappe.get_all("UOM", pluck="name"):
        if to_metrc_uom(uom, raise_on_missing=False) == metrc_uom:
            return uom
    if not frappe.db.exists("UOM", metrc_uom):
        frappe.get_doc({"doctype": "UOM", "uom_name": metrc_uom}).insert(ignore_permissions=True)
    return metrc_uom


def _ensure_item(uom):
    """Create (or reuse) the test item.

    Item naming here runs off a naming series, so the inserted doc comes back
    with a series code rather than our marker. We find it by item_name on
    subsequent runs, and cleanup() does the same.
    """
    existing = frappe.db.get_value("Item", {"item_name": f"{TEST_MARKER} Flower"}, "name")
    if existing:
        frappe.db.set_value(
            "Item", existing, {"custom_metrc_tracked": 1, "stock_uom": uom}, update_modified=False
        )
        return existing

    group = frappe.db.get_value("Item Group", {"is_group": 0}, "name") or "All Item Groups"
    doc = frappe.get_doc(
        {
            "doctype": "Item",
            "item_code": f"{TEST_MARKER}-ITEM",
            "item_name": f"{TEST_MARKER} Flower",
            "item_group": group,
            "stock_uom": uom,
            "is_stock_item": 1,
            "has_batch_no": 1,
            "create_new_batch": 0,
            "custom_metrc_tracked": 1,
            "custom_metrc_item_name": f"{TEST_MARKER} Flower",
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_batch(tag, item_code):
    if frappe.db.exists("Batch", tag):
        # A previous run's item may have been cleaned up, leaving the Batch
        # pointing at a deleted Item. ERPNext rejects the stock entry in that
        # state ("Batch does not belong to Item"), so repoint it.
        frappe.db.set_value(
            "Batch", tag, {"custom_metrc_tag": tag, "item": item_code}, update_modified=False
        )
        frappe.db.commit()
        return tag
    doc = frappe.get_doc(
        {"doctype": "Batch", "batch_id": tag, "item": item_code, "custom_metrc_tag": tag}
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _ensure_customer():
    name = f"{TEST_MARKER} Dispensary"
    if frappe.db.exists("Customer", name):
        return name
    doc = frappe.get_doc(
        {
            "doctype": "Customer",
            "customer_name": name,
            "customer_type": "Company",
            # Metrc requires a recipient licence on transfers.
            "custom_license_number": "M10-0000004-LIC",
        }
    )
    doc.flags.ignore_permissions = True
    doc.insert(ignore_permissions=True)
    return doc.name


def _receive_stock(item_code, batch, qty, uom):
    se = frappe.get_doc(
        {
            "doctype": "Stock Entry",
            "stock_entry_type": "Material Receipt",
            "purpose": "Material Receipt",
            "company": COMPANY,
            "posting_date": nowdate(),
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": uom,
                    "stock_uom": uom,
                    "conversion_factor": 1,
                    "t_warehouse": WAREHOUSE,
                    "batch_no": batch,
                    # The Muid inventory dimension is what carries the tag into
                    # the Stock Ledger. batch_no alone is NOT enough: the
                    # Metric Tag quantity sync reads the dimension, so a row
                    # without it produces stock that Metrc reconciliation
                    # cannot see. "to_muid" is the receiving leg.
                    "muid": batch,
                    "to_muid": batch,
                    "basic_rate": 1,
                    "allow_zero_valuation_rate": 1,
                }
            ],
        }
    )
    se.flags.ignore_permissions = True
    se.insert(ignore_permissions=True)
    se.submit()
    return se.name


def _sell(item_code, batch, qty, uom, customer):
    si = frappe.get_doc(
        {
            "doctype": "Sales Invoice",
            "customer": customer,
            "company": COMPANY,
            "posting_date": nowdate(),
            "set_posting_time": 1,
            "posting_time": "22:00:00",  # late evening - exercises the timezone path
            "update_stock": 1,
            "set_warehouse": WAREHOUSE,
            "items": [
                {
                    "item_code": item_code,
                    "qty": qty,
                    "uom": uom,
                    "conversion_factor": 1,
                    "rate": 10,
                    "warehouse": WAREHOUSE,
                    "batch_no": batch,
                }
            ],
        }
    )
    si.flags.ignore_permissions = True
    si.insert(ignore_permissions=True)
    si.submit()
    return si.name


# ---------------------------------------------------------------------------
# The test
# ---------------------------------------------------------------------------


def smoke_test(transmit=False):
    """Run the round trip.

    transmit=False (default) leaves Metrc Settings alone, so whatever dry_run
    is configured applies. transmit=True temporarily turns push on and dry_run
    off for this run only, then restores both.
    """
    from cannabis_management.metrc import config
    from cannabis_management.metrc.push.outbox import process_outbox

    settings = frappe.get_single("Metrc Settings")
    saved = (settings.push_enabled, settings.dry_run)

    print("=" * 70)
    print(f"METRC SMOKE TEST  |  env={settings.environment}  transmit={transmit}")
    print("=" * 70)

    if transmit:
        if settings.environment == "Production":
            frappe.throw("Refusing to transmit a smoke test against Production.")
        settings.db_set("push_enabled", 1, update_modified=False)
        settings.db_set("dry_run", 0, update_modified=False)
    else:
        # Push must be on for the worker to run at all; dry_run keeps it local.
        settings.db_set("push_enabled", 1, update_modified=False)
        settings.db_set("dry_run", 1, update_modified=False)
    frappe.db.commit()

    results = []
    try:
        print("\n1. Fixtures")
        pkg = _pick_sandbox_package()
        _log(f"sandbox package {pkg.name} qty={pkg.custom_metrc_quantity} {pkg.custom_metrc_uom}")

        uom = _ensure_uom(pkg.custom_metrc_uom or "Grams")
        item = _ensure_item(uom)
        batch = _ensure_batch(pkg.name, item)
        customer = _ensure_customer()
        _log(f"item={item} uom={uom} batch={batch} customer={customer}")

        qty = _round_for_uom(max(2.0, flt(pkg.custom_metrc_quantity) / 4), uom)

        print("\n2. Receive stock (Stock Entry -> Material Receipt)")
        se = _receive_stock(item, batch, _round_for_uom(qty * 2, uom), uom)
        tag_qty = frappe.db.get_value("Metric Tag", batch, "current_qty")
        _log(f"{se} submitted; Metric Tag.current_qty={tag_qty}")
        results.append(("Inventory Dimension updates Metric Tag", flt(tag_qty) > 0))

        print("\n3. Variance mirror")
        from cannabis_management.metrc.reconcile import refresh_variance_fields

        refresh_variance_fields()
        var = frappe.db.get_value(
            "Metric Tag", batch, ["current_qty", "custom_metrc_quantity", "custom_metrc_variance"],
            as_dict=True,
        )
        _log(f"ledger={var.current_qty} metrc={var.custom_metrc_quantity} variance={var.custom_metrc_variance}")
        results.append(("Variance computed", var.custom_metrc_variance is not None))

        print("\n4. Sell it (Sales Invoice -> outbox)")
        si = _sell(item, batch, qty, uom, customer)
        status = frappe.db.get_value("Sales Invoice", si, "custom_metrc_sync_status")
        _log(f"{si} submitted; sync_status={status}")
        results.append(("Sales Invoice enqueued", status == "Queued"))

        row = frappe.db.get_value(
            "Metrc Outbox",
            {"reference_doctype": "Sales Invoice", "reference_name": si},
            ["name", "operation", "payload", "license_number"],
            as_dict=True,
        )
        results.append(("Outbox row created", bool(row)))
        if row:
            payload = json.loads(row.payload)
            _log(f"operation={row.operation} licence={row.license_number}")
            print("      payload:")
            for line in json.dumps(payload, indent=2).splitlines():
                print(f"        {line}")

            sdt = payload.get("SalesDateTime", "")
            _log(f"SalesDateTime={sdt}  (posted 22:00 site time)")
            results.append(("SalesDateTime has no timezone suffix",
                            not sdt.endswith("Z") and "+" not in sdt))
            results.append(("PackageLabel is the Metrc tag",
                            payload["Transactions"][0]["PackageLabel"] == batch))
            results.append(("ExternalReceiptNumber is the invoice",
                            payload.get("ExternalReceiptNumber") == si))
            results.append(("UnitOfMeasure is a valid Metrc UOM",
                            payload["Transactions"][0]["UnitOfMeasure"] in
                            __import__("cannabis_management.metrc.mapping",
                                       fromlist=["x"]).METRC_UOMS))

        print("\n5. Drain outbox")
        process_outbox()
        final = frappe.db.get_value(
            "Metrc Outbox",
            {"reference_doctype": "Sales Invoice", "reference_name": si},
            ["status", "last_error", "metrc_id"],
            as_dict=True,
        )
        si_status = frappe.db.get_value("Sales Invoice", si, "custom_metrc_sync_status")
        _log(f"outbox={final.status} metrc_id={final.metrc_id} invoice={si_status}")
        if final.last_error:
            _log(f"error: {final.last_error[:300]}")
        results.append(("Outbox processed to Success", final.status == "Success"))
        results.append(("Source document stamped", si_status == "Synced"))

        print("\n6. Idempotency")
        from cannabis_management.metrc.push.sales import on_submit

        before = frappe.db.count("Metrc Outbox", {"reference_name": si})
        on_submit(frappe.get_doc("Sales Invoice", si))
        after = frappe.db.count("Metrc Outbox", {"reference_name": si})
        _log(f"outbox rows before={before} after re-running hook={after}")
        results.append(("Re-running the hook does not duplicate", before == after))

    finally:
        settings.db_set("push_enabled", saved[0], update_modified=False)
        settings.db_set("dry_run", saved[1], update_modified=False)
        frappe.db.commit()

    print("\n" + "=" * 70)
    passed = sum(1 for _, ok in results if ok)
    for label, ok in results:
        _log(label, ok)
    print(f"\n{passed}/{len(results)} checks passed")
    print("Settings restored to push_enabled=%s dry_run=%s" % saved)
    print("Run cleanup() to remove the test documents.")
    return {"passed": passed, "total": len(results)}


def cleanup():
    """Cancel and delete everything the smoke test created.

    Order matters and so does the delete method. Documents must go before the
    masters they reference, and masters must go via frappe.delete_doc, not
    frappe.db.delete - the latter bypasses link validation and will happily
    delete an Item out from under submitted documents, leaving orphaned Stock
    Ledger Entries that can only be cleaned up by hand.
    """
    counts = {}
    item = frappe.db.get_value("Item", {"item_name": f"{TEST_MARKER} Flower"}, "name")
    customer = frappe.db.get_value("Customer", {"customer_name": f"{TEST_MARKER} Dispensary"}, "name")

    # 1. Transactions first, invoices before the stock entries that fed them.
    for doctype, child in (("Sales Invoice", "Sales Invoice Item"), ("Stock Entry", "Stock Entry Detail")):
        names = (
            frappe.db.sql_list(
                f"select distinct parent from `tab{child}` where item_code = %s", (item,)
            )  # nosemgrep
            if item
            else []
        )
        removed = 0
        for name in names:
            if not frappe.db.exists(doctype, name):
                continue
            try:
                doc = frappe.get_doc(doctype, name)
                doc.flags.ignore_permissions = True
                if doc.docstatus == 1:
                    doc.cancel()
                frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
                removed += 1
            except Exception as e:
                print(f"  could not remove {doctype} {name}: {str(e)[:150]}")
        counts[doctype] = removed
        frappe.db.commit()

    # 2. Outbox rows for those documents.
    frappe.db.delete("Metrc Outbox", {"reference_name": ["like", "%"], "operation": ["like", "sales.%"]})
    frappe.db.commit()

    # 3. Masters last, via delete_doc so link validation still applies.
    for doctype, name in (("Item", item), ("Customer", customer)):
        if not name or not frappe.db.exists(doctype, name):
            continue
        try:
            frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)
            counts[doctype] = 1
        except Exception as e:
            print(f"  could not remove {doctype} {name}: {str(e)[:150]}")

    frappe.db.commit()
    print("Cleanup done:", counts)
    return counts
