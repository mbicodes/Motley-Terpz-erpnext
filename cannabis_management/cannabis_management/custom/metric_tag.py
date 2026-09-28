import frappe


def _tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters,
                        forced_status=None, allow_unlicensed=False):
    """Shared implementation. `forced_status`, when given, always wins over
    whatever status the caller's filters ask for -- used by the Source/Target
    wrappers below so the restriction can never be dropped by anything on the
    client side failing to forward a `status` filter key."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    warehouse = filters.get("warehouse")
    status = forced_status or filters.get("status")
    license = (
        frappe.db.get_value("Warehouse", warehouse, "custom_metrc_license_number") if warehouse else None
    )

    values = {"txt": f"%{txt}%", "start": start, "page_len": page_len}
    if license:
        if allow_unlicensed:
            # A tag that has never been used is not in any warehouse yet, so it
            # carries no License of its own. An equality match would exclude
            # every Unused tag; callers that hand out fresh tags opt in here so
            # the not-yet-assigned ones stay pickable while a tag that HAS a
            # License is still held to matching the warehouse's.
            license_condition = (
                "and (mt.custom_license = %(license)s or ifnull(mt.custom_license, '') = '')"
            )
        else:
            license_condition = "and mt.custom_license = %(license)s"
        values["license"] = license
    else:
        # No warehouse picked yet, or it has no License -- there is nothing a
        # "same License" match could return, so offer nothing rather than an
        # unfiltered list someone could pick from by mistake.
        license_condition = "and 1=0"

    status_condition = ""
    if status:
        status_condition = "and mt.status = %(status)s"
        values["status"] = status

    return frappe.db.sql(
        f"""
        select mt.name, mt.muid, mt.item_code, mt.status
        from `tabMetric Tag` mt
        where (mt.name like %(txt)s or mt.muid like %(txt)s)
        {license_condition}
        {status_condition}
        order by mt.name
        limit %(start)s, %(page_len)s
        """,  # nosemgrep
        values,
    )


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
    return _tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters)


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def source_tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters):
    """Same as tags_for_warehouse, but always restricted to status=Active --
    used for the Source Tags field on Stock Entry / Purchase Receipt /
    Delivery Note. Status is hardcoded here (not read from the client's
    filters) so it can't be silently dropped by anything upstream."""
    return _tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters, forced_status="Active")


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def target_tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters):
    """Same as tags_for_warehouse, but always restricted to status=Unused --
    used for the Target Tags field on Stock Entry / Purchase Receipt /
    Delivery Note. Status is hardcoded here (not read from the client's
    filters) so it can't be silently dropped by anything upstream."""
    return _tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters, forced_status="Unused")


# ── Conversion Entry ──────────────────────────────────────────────────────────
# Scoped to Conversion Entry's Source Tag N / Target Tag N fields. Kept separate
# from the wrappers above so the stock documents (Stock Entry, Purchase Receipt,
# Delivery Note, Purchase/Sales Invoice) keep their own behaviour untouched.


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def conversion_source_tags(doctype, txt, searchfield, start, page_len, filters):
    """Source Tag N on Conversion Entry: status=Active, and the tag's License
    must equal the Source Warehouse's METRC License #. An Active tag is holding
    stock somewhere, so it always has a License -- no allowance is needed."""
    return _tags_for_warehouse(
        doctype, txt, searchfield, start, page_len, filters, forced_status="Active"
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def conversion_target_tags(doctype, txt, searchfield, start, page_len, filters):
    """Target Tag N on Conversion Entry: status=Unused, matched against the
    Target Warehouse's METRC License #. Unused tags have not been assigned to a
    License yet, so those are allowed through as well -- otherwise the picker
    would be empty for every warehouse."""
    return _tags_for_warehouse(
        doctype, txt, searchfield, start, page_len, filters,
        forced_status="Unused", allow_unlicensed=True,
    )


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def reconcile_tags_for_warehouse(doctype, txt, searchfield, start, page_len, filters):
    """Reconcile Tag on Stock Reconciliation Item: the Active tags already
    holding this item under the warehouse's License (reconciled as Source),
    plus Unused tags (reconciled as Target -- no License yet, so allowed)."""
    filters = frappe.parse_json(filters) if isinstance(filters, str) else (filters or {})
    warehouse = filters.get("warehouse")
    license = (
        frappe.db.get_value("Warehouse", warehouse, "custom_metrc_license_number") if warehouse else None
    )
    if not license:
        return []

    return frappe.db.sql(
        """
        select mt.name, mt.muid, mt.item_code, mt.status, mt.current_qty
        from `tabMetric Tag` mt
        where (mt.name like %(txt)s or mt.muid like %(txt)s)
          and (
            (mt.status = 'Active' and mt.custom_license = %(license)s
             and (%(item_code)s = '' or mt.item_code = %(item_code)s))
            or (mt.status = 'Unused'
             and (mt.custom_license = %(license)s or ifnull(mt.custom_license, '') = ''))
          )
        order by field(mt.status, 'Active', 'Unused'), mt.name
        limit %(start)s, %(page_len)s
        """,
        {
            "txt": f"%{txt}%",
            "license": license,
            "item_code": filters.get("item_code") or "",
            "start": start,
            "page_len": page_len,
        },
    )
