import frappe


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters):
    """Link-query for every Muid (Metric Tag) field.

    Every Warehouse carries a METRC License # (custom_metrc_license_number),
    and every Metric Tag carries a License (custom_license). A tag can only
    move through a warehouse that shares its License, so the Source/Target/
    Rejected Muid fields on Stock Entry, Purchase Receipt/Invoice and
    Delivery Note/Sales Invoice all call this instead of Metric Tag's default
    search -- pass the row's warehouse in filters and the dropdown only
    offers tags whose License matches that warehouse's METRC License #.
    """
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    warehouse = filters.get("warehouse")
    license = (
        frappe.db.get_value("Warehouse", warehouse, "custom_metrc_license_number") if warehouse else None
    )

    values = {"txt": f"%{txt}%", "start": start, "page_len": page_len}
    if license:
        license_condition = "and mt.custom_license = %(license)s"
        values["license"] = license
    else:
        # No warehouse picked yet, or it has no License -- there is nothing a
        # "same License" match could return, so offer nothing rather than an
        # unfiltered list someone could pick from by mistake.
        license_condition = "and 1=0"

    return frappe.db.sql(
        f"""
        select mt.name, mt.muid, mt.item_code, mt.status
        from `tabMetric Tag` mt
        where (mt.name like %(txt)s or mt.muid like %(txt)s)
        {license_condition}
        order by mt.name
        limit %(start)s, %(page_len)s
        """,  # nosemgrep
        values,
    )
