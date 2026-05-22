import frappe


@frappe.whitelist()
def get_item_groups():
    return frappe.db.sql("""
        SELECT ig.name, COUNT(i.name) as item_count
        FROM `tabItem Group` ig
        INNER JOIN `tabItem` i ON i.item_group = ig.name
            AND i.disabled = 0
            AND i.custom_show_in_dashboard = 1
        WHERE ig.is_group = 0
          AND ig.custom_show_in_dashboard = 1
        GROUP BY ig.name
        ORDER BY ig.name
    """, as_dict=True)


@frappe.whitelist()
def get_stock_with_sales(item_group):
    groups_to_load = _get_groups_to_load(item_group)
    placeholders = ", ".join(["%s"] * len(groups_to_load))

    items = frappe.db.sql("""
        SELECT
            b.item_code,
            i.item_name,
            i.item_group,
            b.warehouse,
            b.actual_qty,
            b.reserved_stock AS reserved_qty
        FROM `tabBin` b
        INNER JOIN `tabItem` i ON i.name = b.item_code
        WHERE i.item_group IN ({ph})
          AND i.disabled = 0
          AND i.custom_show_in_dashboard = 1
          AND b.actual_qty != 0
          AND b.warehouse NOT LIKE 'Virtual%%'
        ORDER BY i.item_group, i.item_name
    """.format(ph=placeholders), tuple(groups_to_load), as_dict=True)

    if not items:
        return {"items": [], "sales_data": {}}

    item_codes = list(set(i.item_code for i in items))

    sales_data = _get_sales_data(item_codes)

    return {"items": items, "sales_data": sales_data}


def _get_groups_to_load(item_group):
    if item_group == "Fresh Frozen":
        return ["Fresh Frozen", "Fresh Frozen - BHO", "Fresh Frozen - SHO"]
    return [item_group]


def _get_sales_data(item_codes):
    if not item_codes:
        return {}

    ph = ", ".join(["%s"] * len(item_codes))

    # All submitted delivery note lines for these items
    dn_rows = frappe.db.sql("""
        SELECT
            dni.item_code,
            dni.qty,
            dni.uom,
            dn.name        AS delivery_note,
            dn.customer,
            dn.posting_date,
            dn.status
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dni.item_code IN ({ph})
          AND dn.docstatus = 1
        ORDER BY dn.posting_date DESC
    """.format(ph=ph), tuple(item_codes), as_dict=True)

    # All submitted sales invoice lines for these items
    si_rows = frappe.db.sql("""
        SELECT
            sii.item_code,
            sii.qty,
            sii.delivery_note,
            si.name          AS sales_invoice,
            si.customer,
            si.posting_date,
            si.status,
            si.grand_total,
            si.outstanding_amount
        FROM `tabSales Invoice Item` sii
        JOIN `tabSales Invoice` si ON si.name = sii.parent
        WHERE sii.item_code IN ({ph})
          AND si.docstatus = 1
        ORDER BY si.posting_date DESC
    """.format(ph=ph), tuple(item_codes), as_dict=True)

    # Index SI rows by (item_code, delivery_note) and by (item_code, customer) for direct invoices
    # dn_name -> list of SI rows
    si_by_dn = {}
    si_direct = {}  # item_code -> list (SIs with no DN reference)
    seen_si = set()

    for row in si_rows:
        key = row.sales_invoice
        if key in seen_si:
            continue
        seen_si.add(key)

        dn_ref = row.get("delivery_note") or ""
        if dn_ref:
            si_by_dn.setdefault(dn_ref, []).append(row)
        else:
            si_direct.setdefault(row.item_code, []).append(row)

    # Build per-item sales data
    # Structure: item_code -> { customers: { customer: { dns: [...], direct_invoices: [...] } } }
    seen_dn = set()
    item_map = {}

    for row in dn_rows:
        ic = row.item_code
        if ic not in item_map:
            item_map[ic] = {}

        cust = row.customer or "Unknown"
        if cust not in item_map[ic]:
            item_map[ic][cust] = {"delivery_notes": [], "direct_invoices": []}

        dn = row.delivery_note
        if dn in seen_dn:
            continue
        seen_dn.add(dn)

        linked_invoices = si_by_dn.get(dn, [])
        item_map[ic][cust]["delivery_notes"].append({
            "name": dn,
            "date": str(row.posting_date or ""),
            "qty": float(row.qty or 0),
            "uom": row.uom or "",
            "status": row.status or "",
            "invoices": [
                {
                    "name": si.sales_invoice,
                    "date": str(si.posting_date or ""),
                    "total": float(si.grand_total or 0),
                    "outstanding": float(si.outstanding_amount or 0),
                    "status": si.status or "",
                }
                for si in linked_invoices
            ],
        })

    # Attach direct invoices (SI with no DN reference)
    for ic, si_list in si_direct.items():
        if ic not in item_map:
            item_map[ic] = {}
        for si in si_list:
            cust = si.customer or "Unknown"
            if cust not in item_map[ic]:
                item_map[ic][cust] = {"delivery_notes": [], "direct_invoices": []}
            item_map[ic][cust]["direct_invoices"].append({
                "name": si.sales_invoice,
                "date": str(si.posting_date or ""),
                "total": float(si.grand_total or 0),
                "outstanding": float(si.outstanding_amount or 0),
                "status": si.status or "",
            })

    # Flatten to a list-based structure for JSON serialisation
    result = {}
    for ic, customers in item_map.items():
        result[ic] = []
        for cust, data in customers.items():
            dns = data["delivery_notes"]
            direct = data["direct_invoices"]

            has_dn = len(dns) > 0
            all_invoiced = has_dn and all(len(d["invoices"]) > 0 for d in dns)
            any_invoiced = has_dn and any(len(d["invoices"]) > 0 for d in dns)

            if not has_dn and direct:
                sale_status = "invoiced_direct"
            elif has_dn and all_invoiced:
                sale_status = "fully_invoiced"
            elif has_dn and any_invoiced:
                sale_status = "partially_invoiced"
            elif has_dn:
                sale_status = "delivered_not_invoiced"
            else:
                sale_status = "no_activity"

            result[ic].append({
                "customer": cust,
                "delivery_notes": dns,
                "direct_invoices": direct,
                "sale_status": sale_status,
            })

    return result
