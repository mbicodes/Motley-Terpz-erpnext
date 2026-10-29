import frappe


def update_sales_invoice_delivery_status(doc, method):
    affected_sis = set()
    sales_orders = set()

    for item in doc.items:
        if item.against_sales_invoice:
            affected_sis.add(item.against_sales_invoice)
        if item.against_sales_order:
            sales_orders.add(item.against_sales_order)

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
    has_dn = _sales_invoice_has_delivery_note(si_name)
    frappe.db.set_value(
        "Sales Invoice", si_name, "custom_delivery_note_created", 1 if has_dn else 0
    )


def _sales_invoice_has_delivery_note(si_name):
    if frappe.db.exists(
        "Delivery Note Item",
        {"against_sales_invoice": si_name, "docstatus": ["!=", 0]},
    ):
        return True

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


def update_sales_order_delivery_status(doc, method):
    sales_orders = {
        item.against_sales_order for item in doc.items if item.against_sales_order
    }
    for so_name in sales_orders:
        _recompute_so_delivery_note_created(so_name)


def _recompute_so_delivery_note_created(so_name):
    has_dn = _sales_order_has_delivery_note(so_name)
    frappe.db.set_value(
        "Sales Order", so_name, "custom_delivery_note_created", 1 if has_dn else 0
    )


def _sales_order_has_delivery_note(so_name):
    return bool(
        frappe.db.exists(
            "Delivery Note Item",
            {"against_sales_order": so_name, "docstatus": 1},
        )
    )


def backfill_sales_order_delivery_note_created():
    so_names = frappe.get_all("Sales Order", filters={"docstatus": 1}, pluck="name")

    updated = 0
    for so_name in so_names:
        desired = 1 if _sales_order_has_delivery_note(so_name) else 0
        current = frappe.db.get_value(
            "Sales Order", so_name, "custom_delivery_note_created"
        )
        if (current or 0) != desired:
            frappe.db.set_value(
                "Sales Order", so_name, "custom_delivery_note_created", desired
            )
            updated += 1

    frappe.db.commit()
    msg = "Backfill complete: scanned {0} submitted Sales Orders, updated {1}.".format(
        len(so_names), updated
    )
    print(msg)
    return msg


def backfill_delivery_note_created():
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

SAMPLE_EXPENSE_ACCOUNT_FIELD = "custom_sample_expense_account"
SAMPLE_ORDER_TYPES = ("Samples", "Sample")


def set_expense_head(doc, method):
    if not doc.items:
        return

    so_fieldname = "against_sales_order" if doc.doctype == "Delivery Note" else "sales_order"

    sales_orders = {item.get(so_fieldname) for item in doc.items if item.get(so_fieldname)}
    if not sales_orders:
        return

    so_type_by_name = {
        d.name: d.custom_sales_order_type
        for d in frappe.get_all(
            "Sales Order",
            filters={"name": ["in", list(sales_orders)]},
            fields=["name", "custom_sales_order_type"],
        )
    }

    settings = frappe.get_single("Expense Head Settings")

    expense_account_by_type = {}
    for row in settings.expense_head:
        if row.sales_order_type and row.expense_account:
            expense_account_by_type.setdefault(row.sales_order_type, row.expense_account)

    sample_account = frappe.get_cached_value("Company", doc.company, SAMPLE_EXPENSE_ACCOUNT_FIELD)
    if sample_account:
        for so_type in SAMPLE_ORDER_TYPES:
            expense_account_by_type[so_type] = sample_account

    if not expense_account_by_type:
        return

    for item in doc.items:
        sales_order = item.get(so_fieldname)
        if not sales_order:
            continue

        expense_account = expense_account_by_type.get(so_type_by_name.get(sales_order))
        if expense_account:
            item.expense_account = expense_account
