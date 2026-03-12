import frappe

@frappe.whitelist()
def get_orders_need_to_schedule(page=1, page_size=10, logistic_status="Need to Schedule", company="Motley Terpz", filters=None):
    """
    Fetch Sales Invoices that need to be scheduled with pagination.
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

    total_count = frappe.db.count("Sales Invoice", filters=base_filters)

    fields = [
        "name",
        "customer",
        "customer_name",
        "grand_total",
        "posting_date",
        "total_qty",
        "status",
        "owner",
    ]

    custom_fields = [
        "custom_notes_for_logistics",
        "custom_license",
        "custom_sales_stages",
        "custom_pickup_or_dropoff",
        "custom_actual_pickup_date_time",
        "custom_logistic_status",
        "custom_distro_lab_status",
        "custom_order_support",
        "custom_trip_line_complete",
        "custom_order_dine_out",
        "custom_manifest",
        "custom_lbs_total"
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
        sales_team = frappe.db.get_value("Sales Team", {"parent": inv.name, "parenttype": "Sales Invoice", "idx": 1}, "sales_person")
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
        inv["total_qty"] = inv.get("total_qty") or 0

    total_pages = (total_count + page_size - 1) // page_size if total_count > 0 else 1

    return {
        "data": sales_invoices,
        "total_count": total_count,
        "total_pages": total_pages,
        "current_page": page,
        "page_size": page_size
    }