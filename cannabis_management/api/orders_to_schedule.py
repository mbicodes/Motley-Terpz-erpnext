import frappe

@frappe.whitelist()
def get_orders_need_to_schedule(page=1, page_size=10, logistic_status="Need to Schedule", company="Motley Terpz", filters=None):
    """
    Fetch Sales Orders that need to be scheduled with pagination.
    """
    page = int(page)
    page_size = int(page_size)
    offset = (page - 1) * page_size

    if isinstance(filters, str):
        filters = frappe.parse_json(filters)
    if not filters:
        filters = {}

    base_filters = {
        "docstatus": ["<", 2],
        "custom_logistic_status": logistic_status,
        "custom_sales_stages": "Ready to Go Out",
        "company": company
    }

    if filters.get("invoice"):
        base_filters["name"] = ["like", "%{}%".format(filters["invoice"])]
    if filters.get("bill_to"):
        base_filters["customer_name"] = ["like", "%{}%".format(filters["bill_to"])]
    if filters.get("license_holder"):
        base_filters["custom_license"] = ["like", "%{}%".format(filters["license_holder"])]
    if filters.get("pickup_dropoff"):
        base_filters["custom_pickup_or_dropoff"] = filters["pickup_dropoff"]

    # Common custom fields
    custom_fields_common = [
        "custom_notes_for_logistics", "custom_license", "custom_sales_stages",
        "custom_pickup_or_dropoff", "custom_actual_pickup_date_time", "custom_logistic_status",
        "custom_order_support", "custom_trip_line_complete", "custom_order_dine_out",
        "custom_manifest", "custom_lbs_total"
    ]

    # --- Fetch Sales Orders ---
    so_fields = ["name", "customer", "customer_name", "grand_total", "transaction_date as posting_date", "total_qty", "status", "owner", "delivery_date", "creation"]
    so_custom_fields = custom_fields_common + ["custom_distrolab_status", "custom_distro_lab_status"]
    for cf in so_custom_fields:
        if frappe.db.exists("Custom Field", {"dt": "Sales Order", "fieldname": cf}):
            so_fields.append(cf)

    orders = frappe.get_all("Sales Order", filters=base_filters, fields=so_fields)

    combined = []

    # Process Orders
    for order in orders:
        item = order.copy()
        item["doctype_"] = "Sales Order"
        sales_team = frappe.db.get_value("Sales Team", {"parent": order.name, "parenttype": "Sales Order", "idx": 1}, "sales_person")
        item["salesperson"] = sales_team or ""
        item["notes_for_logistics"] = order.get("custom_notes_for_logistics") or "–"
        item["license_holder"] = order.get("custom_license") or ""
        item["sales_status"] = order.get("custom_sales_stages") or ""
        item["pickup_dropoff"] = order.get("custom_pickup_or_dropoff") or ""
        item["logistic_status"] = order.get("custom_logistic_status") or ""
        item["distro_lab_status"] = order.get("custom_distrolab_status") or order.get("custom_distro_lab_status") or ""
        item["requested_date_time"] = order.get("delivery_date") or ""
        item["total_qty"] = order.get("total_qty") or 0
        combined.append(item)

    combined.sort(key=lambda x: x.creation, reverse=True)

    total_count = len(combined)
    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1
    paginated = combined[offset:offset + page_size]

    return {
        "data": paginated,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }

@frappe.whitelist()
def get_orders_need_to_schedule1(page=1, page_size=10, logistic_status="Need to Schedule", company="Motley Terpz", filters=None):
    """
    Fetch Sales Orders that need to be scheduled with pagination.
    This function is identical to get_orders_need_to_schedule to ensure consistency across all scheduling views.
    """
    return get_orders_need_to_schedule(page, page_size, logistic_status, company, filters)