import frappe


@frappe.whitelist()
def get_item_groups():
    return frappe.db.sql("""
        SELECT ig.name, COUNT(i.name) AS item_count
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
    groups = _get_groups_to_load(item_group)
    gph = ", ".join(["%s"] * len(groups))

    # Every dashboard item in the group(s) — regardless of stock level
    all_items = frappe.db.sql("""
        SELECT item_code, item_name, item_group
        FROM `tabItem`
        WHERE item_group IN ({ph})
          AND disabled = 0
          AND custom_show_in_dashboard = 1
        ORDER BY item_group, item_name
    """.format(ph=gph), tuple(groups), as_dict=True)

    if not all_items:
        return {"items": [], "sales_data": {}}

    item_codes = [i.item_code for i in all_items]
    iph = ", ".join(["%s"] * len(item_codes))

    # Warehouse stock rows — one per (item, warehouse)
    bin_rows = frappe.db.sql("""
        SELECT item_code, warehouse,
               actual_qty,
               reserved_stock AS reserved_qty
        FROM `tabBin`
        WHERE item_code IN ({ph})
          AND warehouse NOT LIKE 'Virtual%%'
    """.format(ph=iph), tuple(item_codes), as_dict=True)

    bin_map = {}
    for row in bin_rows:
        bin_map.setdefault(row.item_code, []).append(row)

    # Build final list: one row per warehouse; or one empty row if never stocked
    items = []
    for item in all_items:
        wh_rows = bin_map.get(item.item_code, [])
        if wh_rows:
            for row in wh_rows:
                items.append({
                    "item_code": item.item_code,
                    "item_name": item.item_name,
                    "item_group": item.item_group,
                    "warehouse": row.warehouse,
                    "actual_qty": float(row.actual_qty or 0),
                    "reserved_qty": float(row.reserved_qty or 0),
                })
        else:
            items.append({
                "item_code": item.item_code,
                "item_name": item.item_name,
                "item_group": item.item_group,
                "warehouse": "",
                "actual_qty": 0.0,
                "reserved_qty": 0.0,
            })

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

    dn_rows = frappe.db.sql("""
        SELECT
            dni.item_code,
            dni.qty,
            dni.uom,
            dn.name         AS delivery_note,
            dn.customer,
            dn.posting_date,
            dn.status       AS dn_status
        FROM `tabDelivery Note Item` dni
        JOIN `tabDelivery Note` dn ON dn.name = dni.parent
        WHERE dni.item_code IN ({ph})
          AND dn.docstatus = 1
        ORDER BY dn.posting_date DESC
    """.format(ph=ph), tuple(item_codes), as_dict=True)

    si_rows = frappe.db.sql("""
        SELECT
            sii.item_code,
            sii.qty,
            sii.delivery_note,
            si.name              AS sales_invoice,
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

    # --- build DN -> [invoices] map ---
    # Deduplicate per (dn, sales_invoice) so the same SI isn't listed twice under one DN.
    si_by_dn = {}
    seen_dn_si = set()

    # --- build item_code -> [direct invoices] map ---
    # Deduplicate per (item_code, sales_invoice).
    si_direct = {}
    seen_item_si = set()

    for row in si_rows:
        dn_ref = row.get("delivery_note") or ""
        if dn_ref:
            key = (dn_ref, row.sales_invoice)
            if key not in seen_dn_si:
                seen_dn_si.add(key)
                si_by_dn.setdefault(dn_ref, []).append(row)
        else:
            key = (row.item_code, row.sales_invoice)
            if key not in seen_item_si:
                seen_item_si.add(key)
                si_direct.setdefault(row.item_code, []).append(row)

    # --- build per-(item, customer) delivery note data ---
    # Deduplicate per (item_code, delivery_note): a DN can have multiple item lines
    # so the same DN name appears in dn_rows more than once for the same item.
    seen_item_dn = set()
    item_map = {}

    for row in dn_rows:
        ic = row.item_code
        dn = row.delivery_note
        key = (ic, dn)
        if key in seen_item_dn:
            continue
        seen_item_dn.add(key)

        cust = row.customer or "Unknown"
        item_map.setdefault(ic, {})
        item_map[ic].setdefault(cust, {"delivery_notes": [], "direct_invoices": []})

        linked_invoices = si_by_dn.get(dn, [])
        item_map[ic][cust]["delivery_notes"].append({
            "name": dn,
            "date": str(row.posting_date or ""),
            "qty": float(row.qty or 0),
            "uom": row.uom or "",
            "dn_status": row.dn_status or "",
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

    # Attach direct invoices (SI with no delivery_note reference)
    for ic, si_list in si_direct.items():
        item_map.setdefault(ic, {})
        for si in si_list:
            cust = si.customer or "Unknown"
            item_map[ic].setdefault(cust, {"delivery_notes": [], "direct_invoices": []})
            item_map[ic][cust]["direct_invoices"].append({
                "name": si.sales_invoice,
                "date": str(si.posting_date or ""),
                "total": float(si.grand_total or 0),
                "outstanding": float(si.outstanding_amount or 0),
                "status": si.status or "",
            })

    # Flatten and compute per-customer sale_status
    result = {}
    for ic, customers in item_map.items():
        result[ic] = []
        for cust, data in customers.items():
            dns    = data["delivery_notes"]
            direct = data["direct_invoices"]

            has_dn       = bool(dns)
            has_direct   = bool(direct)
            all_invoiced = has_dn and all(len(d["invoices"]) > 0 for d in dns)
            any_invoiced = has_dn and any(len(d["invoices"]) > 0 for d in dns)

            if not has_dn and not has_direct:
                sale_status = "no_activity"
            elif not has_dn and has_direct:
                # Invoice exists but no delivery note at all
                sale_status = "invoiced_direct"
            elif has_dn and all_invoiced:
                # Every DN has a linked invoice (standard flow)
                sale_status = "fully_invoiced"
            elif has_dn and any_invoiced:
                # Some DNs have linked invoices, some don't
                sale_status = "partially_invoiced"
            elif has_dn and has_direct:
                # DN exists + a separate SI exists but the SI wasn't created from the DN
                # (delivery_note field on SI item is blank) — likely the same transaction
                # but not linked through the standard ERPNext flow
                sale_status = "delivered_invoiced_unlinked"
            elif has_dn:
                # DN exists, zero invoices anywhere for this customer
                sale_status = "delivered_not_invoiced"
            else:
                sale_status = "no_activity"

            result[ic].append({
                "customer":       cust,
                "delivery_notes": dns,
                "direct_invoices": direct,
                "sale_status":    sale_status,
            })

    return result
