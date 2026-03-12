import frappe

@frappe.whitelist()
def get_pending_sales_orders(page=1, page_size=10, company="Motley Terpz", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "company": company,
        "billing_status": ["in", ["Not Billed", "Partly Billed"]]
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]
    if filters.get("pickup_dropoff"):
        base_filters["custom_pickup_or_dropoff"] = filters["pickup_dropoff"]

    total_count = frappe.db.count("Sales Order", filters=base_filters)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=base_filters,
        fields=[
            "name",
            "customer",
            "customer_name",
            "total_qty",
            "transaction_date",
            "status",
            "custom_pickup_or_dropoff",
            "custom_notes_for_logistics"
        ],
        order_by="creation desc",
        start=offset,
        page_length=page_size
    )

    for order in sales_orders:
        sales_team = frappe.get_all(
            "Sales Team",
            filters={"parent": order["name"], "parenttype": "Sales Order"},
            fields=["sales_person"],
            order_by="idx asc",
            limit=1
        )
        order["sales_person"] = sales_team[0].sales_person if sales_team else ""

    total_pages = (total_count + page_size - 1) // page_size

    return {
        "data": sales_orders,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }


@frappe.whitelist()
def get_orders_at_lab(page=1, page_size=10, company="Motley Terpz", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "custom_logistic_status": "Scheduled",
        "custom_sales_stages": "Ready to Go Out",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]
    if filters.get("pickup_dropoff"):
        base_filters["custom_pickup_or_dropoff"] = filters["pickup_dropoff"]

    total_count = frappe.db.count("Sales Invoice", filters=base_filters)

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "posting_date", "status", "owner",
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distro_lab_status",
        "custom_order_staged",
        "custom_tag_scan_completed",
        "custom_order_sent_out",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": cf}):
            fields.append(cf)

    sales_invoices = frappe.get_all(
        "Sales Invoice",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=offset,
        page_length=page_size
    )

    for inv in sales_invoices:
        sales_team = frappe.db.get_value(
            "Sales Team",
            {"parent": inv.name, "parenttype": "Sales Invoice", "idx": 1},
            "sales_person"
        )
        inv["salesperson"] = sales_team or ""
        inv["notes_for_logistics"] = inv.get("custom_notes_for_logistics") or "–"
        inv["license_holder"] = inv.get("custom_license") or ""
        inv["sales_status"] = inv.get("custom_sales_stages") or ""
        inv["pickup_dropoff"] = inv.get("custom_pickup_or_dropoff") or ""

        sales_order = frappe.db.get_value("Sales Invoice Item", {"parent": inv.name}, "sales_order")
        inv["requested_date_time"] = ""
        if sales_order:
            inv["requested_date_time"] = frappe.db.get_value("Sales Order", sales_order, "delivery_date") or ""

        inv["logistic_status"] = inv.get("custom_logistic_status") or ""
        inv["distro_lab_status"] = inv.get("custom_distro_lab_status") or ""
        inv["order_staged"] = inv.get("custom_order_staged") or 0
        inv["tag_scan_completed"] = inv.get("custom_tag_scan_completed") or 0
        inv["order_sent_out"] = inv.get("custom_order_sent_out") or 0
        inv["total_qty"] = inv.get("total_qty") or 0

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        "data": sales_invoices,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }

@frappe.whitelist()
def get_orders_ready_for_closeout(page=1, page_size=20, company="Motley Terpz", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "posting_date", "status", "owner",
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distro_lab_status",
        "custom_controller_check",
        "custom_final_closeout",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": cf}):
            fields.append(cf)

    sales_invoices = frappe.get_all(
        "Sales Invoice",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=0,
        page_length=0  # fetch all first for sent_out filter
    )

    for inv in sales_invoices:
        inv["sales_status"] = inv.get("custom_sales_stages") or ""
        inv["logistic_status"] = inv.get("custom_logistic_status") or ""
        inv["distro_lab_status"] = inv.get("custom_distro_lab_status") or ""
        inv["logistics_notes"] = inv.get("custom_notes_for_logistics") or ""
        inv["controller_check"] = inv.get("custom_controller_check") or 0
        inv["final_closeout"] = inv.get("custom_final_closeout") or 0

        delivery_note = frappe.db.get_value(
            "Delivery Note Item",
            {"against_sales_invoice": inv.name, "docstatus": 1},
            "parent"
        )
        inv["order_sent_out"] = 1 if delivery_note else 0

        inv["manifest"] = ""
        if delivery_note:
            inv["manifest"] = frappe.db.get_value(
                "Delivery Note", delivery_note, "custom_manifest"
            ) or ""

        inv["bill_to"] = inv.get("customer") or ""

    # Apply sent_out filter after enrichment (since it's computed, not a DB column)
    if "order_sent_out" in filters:
        sent_val = int(filters["order_sent_out"])
        sales_invoices = [inv for inv in sales_invoices if inv["order_sent_out"] == sent_val]

    total_count = len(sales_invoices)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Manual pagination after filtering
    paginated = sales_invoices[offset:offset + page_size]

    return {
        "data": paginated,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }