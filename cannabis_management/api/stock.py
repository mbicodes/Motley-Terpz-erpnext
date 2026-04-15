import frappe

# ── Conversion rates to lbs ───────────────────────────────────────────────────
UOM_TO_LBS = {
    # grams
    'g': 0.00220462, 'gram': 0.00220462, 'grams': 0.00220462,
    'grm': 0.00220462, 'gr': 0.00220462,
    # kilograms
    'kg': 2.20462, 'kilogram': 2.20462, 'kilograms': 2.20462,
    # ounces
    'oz': 0.0625, 'ounce': 0.0625, 'ounces': 0.0625,
    # pounds — pass through
    'lb': 1.0, 'lbs': 1.0, 'pound': 1.0, 'pounds': 1.0,
}

def convert_to_lbs(qty, uom):
    if not qty:
        return 0
    if not uom:
        return qty
    factor = UOM_TO_LBS.get(uom.strip().lower())
    if factor is None:
        frappe.logger().warning(f"[tolling_stock] Unknown UOM '{uom}' — returning qty as-is")
        return qty
    return qty * factor

@frappe.whitelist()
def get_tolling_partner_stock_by_batch():
    warehouses = frappe.get_all(
        'Warehouse',
        filters={'warehouse_type': 'Tolling Partner'},
        pluck='name'
    )
    if not warehouses:
        return []

    # ── Source 1: Purchase Receipts — earliest date first ────────────────────
    pr_rows = frappe.db.sql("""
        SELECT
            pr.project,
            p.project_name,
            pr.name                             AS source_doc,
            pri.item_code,
            pri.qty,
            pri.uom,
            pri.stock_qty,
            pri.stock_uom,
            pr.posting_date                     AS last_date
        FROM `tabPurchase Receipt` pr
        INNER JOIN `tabPurchase Receipt Item` pri ON pri.parent = pr.name
        INNER JOIN `tabProject` p               ON p.name = pr.project
        WHERE
            pr.docstatus = 1
            AND pr.project IS NOT NULL
            AND pr.project != ''
            AND pri.warehouse IN %(warehouses)s
            AND p.status = 'Open'
        ORDER BY pr.project, pr.posting_date ASC
    """, {'warehouses': warehouses}, as_dict=True)

    # ── Source 2: Stock Entries — earliest date first ─────────────────────────
    se_rows = frappe.db.sql("""
        SELECT
            se.project,
            p.project_name,
            se.name                             AS source_doc,
            sed.item_code,
            sed.qty,
            sed.uom,
            sed.transfer_qty,
            sed.stock_uom,
            se.posting_date                     AS last_date
        FROM `tabStock Entry` se
        INNER JOIN `tabStock Entry Detail` sed ON sed.parent = se.name
        INNER JOIN `tabProject` p              ON p.name = se.project
        WHERE
            se.docstatus = 1
            AND se.project IS NOT NULL
            AND se.project != ''
            AND sed.t_warehouse IN %(warehouses)s
            AND p.status = 'Open'
        ORDER BY se.project, se.posting_date ASC
    """, {'warehouses': warehouses}, as_dict=True)

    # ── Smart qty resolver ────────────────────────────────────────────────────
    def resolve_qty_in_lbs(row, stock_qty_field='stock_qty'):
        uom       = (row.get('uom') or '').strip().lower()
        stock_uom = (row.get('stock_uom') or '').strip().lower()
        qty       = row.get('qty') or 0
        stock_qty = row.get(stock_qty_field) or 0

        if uom in ('lb', 'lbs', 'pound', 'pounds'):
            return qty

        if stock_qty and stock_uom and stock_uom in UOM_TO_LBS:
            converted = convert_to_lbs(stock_qty, stock_uom)
            frappe.logger().info(
                f"[tolling_stock] {row.get('source_doc')} | {row.get('item_code')} | "
                f"stock_qty={stock_qty} {stock_uom} → {converted:.4f} lbs"
            )
            return converted

        converted = convert_to_lbs(qty, uom)
        frappe.logger().info(
            f"[tolling_stock] {row.get('source_doc')} | {row.get('item_code')} | "
            f"qty={qty} {uom} → {converted:.4f} lbs (fallback)"
        )
        return converted

    # ── Group PR rows: lock to EARLIEST PR per project ────────────────────────
    pr_by_project = {}
    for row in pr_rows:
        proj = row['project']
        if proj not in pr_by_project:
            # First row encountered is now the earliest (ASC order)
            pr_by_project[proj] = {
                'project':      proj,
                'project_name': row['project_name'],
                'total_qty':    0,
                'last_date':    row['last_date'],
                'source':       'Purchase Receipt',
                'source_doc':   row['source_doc'],
                '_doc':         row['source_doc']
            }
        if row['source_doc'] == pr_by_project[proj]['_doc']:
            pr_by_project[proj]['total_qty'] += resolve_qty_in_lbs(row, stock_qty_field='stock_qty')

    # ── Group SE rows: lock to EARLIEST SE per project ────────────────────────
    se_by_project = {}
    for row in se_rows:
        proj = row['project']
        if proj not in se_by_project:
            se_by_project[proj] = {
                'project':      proj,
                'project_name': row['project_name'],
                'total_qty':    0,
                'last_date':    row['last_date'],
                'source':       'Stock Entry',
                'source_doc':   row['source_doc'],
                '_doc':         row['source_doc']
            }
        if row['source_doc'] == se_by_project[proj]['_doc']:
            se_by_project[proj]['total_qty'] += resolve_qty_in_lbs(row, stock_qty_field='transfer_qty')

    # ── Merge: PR wins, SE fills gaps ─────────────────────────────────────────
    result_map = dict(pr_by_project)
    for proj, row in se_by_project.items():
        if proj not in result_map:
            result_map[proj] = row

    # ── Final sort: earliest posting date first ───────────────────────────────
    results = []
    for row in result_map.values():
        row.pop('_doc', None)
        if row['total_qty'] > 0:
            results.append(row)

    results.sort(key=lambda x: x.get('last_date') or '')
    return results