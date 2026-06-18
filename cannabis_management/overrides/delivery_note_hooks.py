import frappe


def update_sales_invoice_delivery_status(doc, method):
    """
    Updates the 'custom_delivery_note_created' checkbox on the linked Sales Invoice(s).

    A Delivery Note may be linked to a Sales Invoice either:
      1. Directly  — DN Item.against_sales_invoice points at the SI, or
      2. Indirectly — DN Item.against_sales_order points at a Sales Order that the
         Sales Invoice was also billed against (SI Item.sales_order).

    Both paths flag the SI. We gather every SI affected by this DN through either
    path and recompute its checkbox from scratch (so cancellations clear it too).
    """
    affected_sis = set()
    sales_orders = set()

    for item in doc.items:
        if item.against_sales_invoice:
            affected_sis.add(item.against_sales_invoice)
        if item.against_sales_order:
            sales_orders.add(item.against_sales_order)

    # Sales Invoices billed against the same Sales Order(s) as this Delivery Note
    if sales_orders:
        for si_name in frappe.get_all(
            "Sales Invoice Item",
            filters={"sales_order": ["in", list(sales_orders)], "docstatus": ["!=", 2]},
            pluck="parent",
        ):
            affected_sis.add(si_name)

    for si_name in affected_sis:
        _recompute_delivery_note_created(si_name)


def _recompute_delivery_note_created(si_name):
    """Set custom_delivery_note_created based on whether any non-draft Delivery
    Note is linked to the Sales Invoice, directly or via a shared Sales Order."""
    has_dn = _sales_invoice_has_delivery_note(si_name)
    frappe.db.set_value(
        "Sales Invoice", si_name, "custom_delivery_note_created", 1 if has_dn else 0
    )


def _sales_invoice_has_delivery_note(si_name):
    # 1. Direct link: a non-draft DN Item points straight at this Sales Invoice.
    if frappe.db.exists(
        "Delivery Note Item",
        {"against_sales_invoice": si_name, "docstatus": ["!=", 0]},
    ):
        return True

    # 2. Indirect link: a non-draft DN Item shares a Sales Order with this SI.
    sales_orders = frappe.get_all(
        "Sales Invoice Item",
        filters={"parent": si_name, "sales_order": ["is", "set"]},
        pluck="sales_order",
    )
    if sales_orders:
        if frappe.db.exists(
            "Delivery Note Item",
            {"against_sales_order": ["in", sales_orders], "docstatus": ["!=", 0]},
        ):
            return True

    return False


def backfill_delivery_note_created():
    """One-off correction for previously created Sales Invoices: recompute the
    custom_delivery_note_created checkbox for every submitted Sales Invoice.

    Run with:
        bench --site <site> execute \
          cannabis_management.overrides.delivery_note_hooks.backfill_delivery_note_created
    """
    si_names = frappe.get_all(
        "Sales Invoice", filters={"docstatus": 1}, pluck="name"
    )

    updated = 0
    for si_name in si_names:
        desired = 1 if _sales_invoice_has_delivery_note(si_name) else 0
        current = frappe.db.get_value(
            "Sales Invoice", si_name, "custom_delivery_note_created"
        )
        if (current or 0) != desired:
            frappe.db.set_value(
                "Sales Invoice", si_name, "custom_delivery_note_created", desired
            )
            updated += 1

    frappe.db.commit()
    msg = "Backfill complete: scanned {0} submitted Sales Invoices, updated {1}.".format(
        len(si_names), updated
    )
    print(msg)
    return msg
