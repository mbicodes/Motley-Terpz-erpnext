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
def get_presale_sales_orders(page=1, page_size=10, company="TSBC Ranch", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": ["<", 2],
        "company": company,
        "custom_sales_order_type": "Presale",
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

    total_count = frappe.db.count("Sales Order", filters=base_filters)

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "transaction_date", "status", "owner", "delivery_date"
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distrolab_status",
        "custom_order_staged",
        "custom_tag_scan_completed",
        "custom_order_sent_out",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            fields.append(cf)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=offset,
        page_length=page_size
    )

    for order in sales_orders:
        sales_team = frappe.db.get_value(
            "Sales Team",
            {"parent": order.name, "parenttype": "Sales Order", "idx": 1},
            "sales_person"
        )
        order["salesperson"] = sales_team or ""
        order["notes_for_logistics"] = order.get("custom_notes_for_logistics") or "–"
        order["license_holder"] = order.get("custom_license") or ""
        order["sales_status"] = order.get("custom_sales_stages") or ""
        order["pickup_dropoff"] = order.get("custom_pickup_or_dropoff") or ""
        order["logistic_status"] = order.get("custom_logistic_status") or ""
        order["distro_lab_status"] = order.get("custom_distrolab_status") or ""
        order["order_staged"] = order.get("custom_order_staged") or 0
        order["tag_scan_completed"] = order.get("custom_tag_scan_completed") or 0
        order["order_sent_out"] = order.get("custom_order_sent_out") or 0
        order["total_qty"] = order.get("total_qty") or 0
        order["requested_date_time"] = order.get("delivery_date") or ""

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        "data": sales_orders,
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
        "custom_logistic_status": "Order Closed Out",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "transaction_date", "status", "owner",
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distrolab_status",
        "custom_controller_check",
        "custom_final_closeout",
    ]

    # Add optional fields if they exist
    optional_fields = ["custom_lab_status", "custom_sales_order_type"]
    for f in optional_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": f}):
            fields.append(f)

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            fields.append(cf)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=0,
        page_length=0  # fetch all first for sent_out filter
    )

    for order in sales_orders:
        order["sales_status"] = order.get("custom_sales_stages") or ""
        order["logistic_status"] = order.get("custom_logistic_status") or ""
        order["distro_lab_status"] = order.get("custom_distrolab_status") or ""
        order["logistics_notes"] = order.get("custom_notes_for_logistics") or ""
        order["controller_check"] = order.get("custom_controller_check") or 0
        order["final_closeout"] = order.get("custom_final_closeout") or 0
        order["lab_status"] = order.get("custom_lab_status") or ""
        order["order_type"] = order.get("custom_sales_order_type") or ""

        delivery_note = frappe.db.get_value(
            "Delivery Note Item",
            {"against_sales_order": order.name, "docstatus": 1},
            "parent"
        )
        order["order_sent_out"] = 1 if delivery_note else 0

        order["manifest"] = ""
        if delivery_note:
            order["manifest"] = frappe.db.get_value(
                "Delivery Note", delivery_note, "custom_manifest"
            ) or ""

        order["bill_to"] = order.get("customer") or ""

    # Apply sent_out filter after enrichment
    if "order_sent_out" in filters:
        sent_val = int(filters["order_sent_out"])
        sales_orders = [o for o in sales_orders if o["order_sent_out"] == sent_val]

    total_count = len(sales_orders)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    # Manual pagination after filtering
    paginated = sales_orders[offset:offset + page_size]

    return {
        "data": paginated,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }
    

@frappe.whitelist()
def get_orders_ready_for_closeout1(page=1, page_size=20, company="TSBC Ranch", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "custom_logistic_status": "Order Closed Out",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "transaction_date", "status", "owner",
    ]

    # Updated custom field names for Sales Order
    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_sales_order_type",       # was custom_order_type on Sales Invoice
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distrolab_status",       # was custom_distro_lab_status on Sales Invoice
        "custom_lab_status",             # new field on Sales Order
        "custom_controller_check",
        "custom_final_closeout",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            fields.append(cf)

    sales_orders = frappe.get_all(
        "Sales Order",                   # changed from Sales Invoice
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=0,
        page_length=0                    # fetch all for sent_out filter
    )

    for order in sales_orders:
        order["sales_status"]      = order.get("custom_sales_stages") or ""
        order["logistic_status"]   = order.get("custom_logistic_status") or ""
        order["distro_lab_status"] = order.get("custom_distrolab_status") or ""
        order["lab_status"]        = order.get("custom_lab_status") or ""
        order["logistics_notes"]   = order.get("custom_notes_for_logistics") or ""
        order["order_type"]        = order.get("custom_sales_order_type") or ""
        order["controller_check"]  = order.get("custom_controller_check") or 0
        order["final_closeout"]    = order.get("custom_final_closeout") or 0
        order["bill_to"]           = order.get("customer") or ""

        # Link Delivery Note via Sales Order instead of Sales Invoice
        delivery_note = frappe.db.get_value(
            "Delivery Note Item",
            {"against_sales_order": order.name, "docstatus": 1},  # changed field
            "parent"
        )
        order["order_sent_out"] = 1 if delivery_note else 0

        order["manifest"] = ""
        if delivery_note:
            order["manifest"] = frappe.db.get_value(
                "Delivery Note", delivery_note, "custom_manifest"
            ) or ""

    # Apply sent_out filter post-enrichment (computed field, not a DB column)
    if "order_sent_out" in filters:
        sent_val = int(filters["order_sent_out"])
        sales_orders = [o for o in sales_orders if o["order_sent_out"] == sent_val]

    total_count = len(sales_orders)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    paginated = sales_orders[offset:offset + page_size]

    return {
        "data": paginated,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }


@frappe.whitelist()
def get_orders_preparing(page=1, page_size=10, company="Motley Terpz", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "custom_logistic_status": "Order Preparing",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]
    if filters.get("pickup_dropoff"):
        base_filters["custom_pickup_or_dropoff"] = filters["pickup_dropoff"]

    total_count = frappe.db.count("Sales Order", filters=base_filters)

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "transaction_date", "status", "owner", "delivery_date"
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distrolab_status",
        "custom_order_staged",
        "custom_tag_scan_completed",
        "custom_order_sent_out",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            fields.append(cf)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=offset,
        page_length=page_size
    )

    for order in sales_orders:
        sales_team = frappe.db.get_value(
            "Sales Team",
            {"parent": order.name, "parenttype": "Sales Order", "idx": 1},
            "sales_person"
        )
        order["salesperson"]          = sales_team or ""
        order["notes_for_logistics"]  = order.get("custom_notes_for_logistics") or "–"
        order["license_holder"]       = order.get("custom_license") or ""
        order["sales_status"]         = order.get("custom_sales_stages") or ""
        order["pickup_dropoff"]       = order.get("custom_pickup_or_dropoff") or ""
        order["logistic_status"]      = order.get("custom_logistic_status") or ""
        order["distro_lab_status"]    = order.get("custom_distrolab_status") or ""
        order["order_staged"]         = order.get("custom_order_staged") or 0
        order["tag_scan_completed"]   = order.get("custom_tag_scan_completed") or 0
        order["order_sent_out"]       = order.get("custom_order_sent_out") or 0
        order["total_qty"]            = order.get("total_qty") or 0
        order["requested_date_time"]  = order.get("delivery_date") or ""

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        "data":         sales_orders,
        "total_count":  total_count,
        "total_pages":  total_pages,
        "current_page": page,
        "page_size":    page_size
    }



@frappe.whitelist()
def get_orders_prepared(page=1, page_size=10, company="Motley Terpz", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "custom_logistic_status": "Order Prepared",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]
    if filters.get("pickup_dropoff"):
        base_filters["custom_pickup_or_dropoff"] = filters["pickup_dropoff"]

    total_count = frappe.db.count("Sales Order", filters=base_filters)

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "transaction_date", "status", "owner", "delivery_date"
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distrolab_status",
        "custom_order_staged",
        "custom_tag_scan_completed",
        "custom_order_sent_out",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            fields.append(cf)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=offset,
        page_length=page_size
    )

    for order in sales_orders:
        sales_team = frappe.db.get_value(
            "Sales Team",
            {"parent": order.name, "parenttype": "Sales Order", "idx": 1},
            "sales_person"
        )
        order["salesperson"]          = sales_team or ""
        order["notes_for_logistics"]  = order.get("custom_notes_for_logistics") or "–"
        order["license_holder"]       = order.get("custom_license") or ""
        order["sales_status"]         = order.get("custom_sales_stages") or ""
        order["pickup_dropoff"]       = order.get("custom_pickup_or_dropoff") or ""
        order["logistic_status"]      = order.get("custom_logistic_status") or ""
        order["distro_lab_status"]    = order.get("custom_distrolab_status") or ""
        order["order_staged"]         = order.get("custom_order_staged") or 0
        order["tag_scan_completed"]   = order.get("custom_tag_scan_completed") or 0
        order["order_sent_out"]       = order.get("custom_order_sent_out") or 0
        order["total_qty"]            = order.get("total_qty") or 0
        order["requested_date_time"]  = order.get("delivery_date") or ""

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        "data":         sales_orders,
        "total_count":  total_count,
        "total_pages":  total_pages,
        "current_page": page,
        "page_size":    page_size
    }


@frappe.whitelist()
def get_orders_staged(page=1, page_size=10, company="Motley Terpz", filters=None):
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": 1,
        "custom_logistic_status": "Order Staged",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]
    if filters.get("pickup_dropoff"):
        base_filters["custom_pickup_or_dropoff"] = filters["pickup_dropoff"]

    total_count = frappe.db.count("Sales Order", filters=base_filters)

    fields = [
        "name", "customer", "customer_name", "grand_total", "total_qty",
        "transaction_date", "status", "owner", "delivery_date"
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_logistic_status",
        "custom_distrolab_status",
        "custom_order_staged",
        "custom_tag_scan_completed",
        "custom_order_sent_out",
    ]

    for cf in custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            fields.append(cf)

    sales_orders = frappe.get_all(
        "Sales Order",
        filters=base_filters,
        fields=fields,
        order_by="creation desc",
        start=offset,
        page_length=page_size
    )

    for order in sales_orders:
        sales_team = frappe.db.get_value(
            "Sales Team",
            {"parent": order.name, "parenttype": "Sales Order", "idx": 1},
            "sales_person"
        )
        order["salesperson"]          = sales_team or ""
        order["notes_for_logistics"]  = order.get("custom_notes_for_logistics") or "–"
        order["license_holder"]       = order.get("custom_license") or ""
        order["sales_status"]         = order.get("custom_sales_stages") or ""
        order["pickup_dropoff"]       = order.get("custom_pickup_or_dropoff") or ""
        order["logistic_status"]      = order.get("custom_logistic_status") or ""
        order["distro_lab_status"]    = order.get("custom_distrolab_status") or ""
        # custom_order_staged drives the Staged column tick
        order["staged"]               = 1 if order.get("custom_order_staged") else 0
        order["tag_scan_completed"]   = order.get("custom_tag_scan_completed") or 0
        order["order_sent_out"]       = order.get("custom_order_sent_out") or 0
        order["total_qty"]            = order.get("total_qty") or 0
        order["requested_date_time"]  = order.get("delivery_date") or ""

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        "data":         sales_orders,
        "total_count":  total_count,
        "total_pages":  total_pages,
        "current_page": page,
        "page_size":    page_size
    }