import frappe
from frappe import _


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    raw     = get_data(filters)
    data    = build_grouped_rows(raw)
    chart   = get_chart(raw)
    summary = get_summary(raw)
    return columns, data, None, chart, summary


# ── Columns ──────────────────────────────────────────────────────────────────

def get_columns():
    return [
        {
            "label": _("Invoice"),
            "fieldname": "name",
            "fieldtype": "Link",
            "options": "Sales Invoice",
            "width": 250,
        },
        {
            "label": _("Customer"),
            "fieldname": "customer_name",
            "fieldtype": "Data",
            "width": 180,
        },
        {
            "label": _("Date"),
            "fieldname": "posting_date",
            "fieldtype": "Date",
            "width": 110,
        },
        {
            "label": _("Item Code"),
            "fieldname": "item_code",
            "fieldtype": "Link",
            "options": "Item",
            "width": 160,
        },
        {
            "label": _("Item Name"),
            "fieldname": "item_name",
            "fieldtype": "Data",
            "width": 200,
        },
        {
            "label": _("Qty"),
            "fieldname": "qty",
            "fieldtype": "Float",
            "width": 80,
        },
        {
            "label": _("Rate"),
            "fieldname": "rate",
            "fieldtype": "Currency",
            "width": 110,
        },
        {
            "label": _("Amount"),
            "fieldname": "amount",
            "fieldtype": "Currency",
            "width": 120,
        },
        {
            "label": _("Status"),
            "fieldname": "status",
            "fieldtype": "Data",
            "width": 100,
        },
        {
            "label": _("Company"),
            "fieldname": "company",
            "fieldtype": "Link",
            "options": "Company",
            "width": 150,
        },
    ]


# ── Raw query ─────────────────────────────────────────────────────────────────

def get_data(filters):
    conditions = get_conditions(filters)

    return frappe.db.sql(
        """
        SELECT
            si.name,
            si.customer_name,
            si.posting_date,
            si.grand_total,
            si.status,
            si.company,
            sii.item_code,
            sii.item_name,
            sii.qty,
            sii.rate,
            sii.amount
        FROM
            `tabSales Invoice`      si
        INNER JOIN
            `tabSales Invoice Item` sii ON sii.parent = si.name
        WHERE
            si.docstatus = 1
            AND si.custom_order_type = 'Samples'
            {conditions}
        ORDER BY
            si.posting_date DESC, si.name, sii.idx
        """.format(conditions=conditions),
        filters,
        as_dict=1,
    )


def get_conditions(filters):
    conditions = []

    if filters.get("company"):
        conditions.append("AND si.company = %(company)s")

    if filters.get("customer"):
        conditions.append("AND si.customer = %(customer)s")

    if filters.get("item_code"):
        conditions.append("AND sii.item_code = %(item_code)s")

    return " ".join(conditions)


def build_grouped_rows(raw):
    """
    Groups raw rows by invoice name and inserts a bold subtotal row
    after each invoice group showing the invoice grand_total in the
    amount column.

    Result per group:
        item row 1
        item row 2
        ...
        SUBTOTAL row  ← is_subtotal = 1, amount = grand_total
    """
    if not raw:
        return []

    result       = []
    current_inv  = None
    group_rows   = []

    def flush_group(rows):
        result.extend(rows)
        ref = rows[0]
        result.append(frappe._dict({
            "name":          ref.name,
            "customer_name": "",
            "posting_date":  None,
            "item_code":     None,
            "item_name":     "Invoice Total — {}".format(ref.name),
            "qty":           None,
            "rate":          None,
            "amount":        ref.grand_total,
            "status":        None,
            "company":       None,
            "is_subtotal":   1,
        }))

    for row in raw:
        if row.name != current_inv:
            if group_rows:
                flush_group(group_rows)
            group_rows  = []
            current_inv = row.name
        group_rows.append(row)

    if group_rows:
        flush_group(group_rows)

    return result


# ── Chart ─────────────────────────────────────────────────────────────────────

def get_chart(data):
    if not data:
        return None

    customer_totals = {}
    for row in data:
        customer_totals[row.customer_name] = (
            customer_totals.get(row.customer_name, 0) + (row.amount or 0)
        )

    sorted_customers = sorted(customer_totals.items(), key=lambda x: x[1], reverse=True)[:15]

    return {
        "data": {
            "labels":   [c[0] for c in sorted_customers],
            "datasets": [{"name": _("Sample Value"), "values": [c[1] for c in sorted_customers]}],
        },
        "type":      "bar",
        "colors":    ["#b45309"],
        "fieldtype": "Currency",
        "title":     _("Sample Value by Customer (Top 15)"),
    }


# ── Summary ───────────────────────────────────────────────────────────────────

def get_summary(data):
    if not data:
        return []

    total_amount   = sum(row.amount or 0 for row in data)
    total_invoices = len(set(row.name for row in data))
    total_qty      = sum(row.qty or 0 for row in data)

    return [
        {"value": total_invoices, "label": _("Sample Invoices"),  "datatype": "Int",      "indicator": "blue"},
        {"value": len(data),      "label": _("Line Items"),        "datatype": "Int",      "indicator": "gray"},
        {"value": total_qty,      "label": _("Total Qty Given"),   "datatype": "Float",    "indicator": "orange"},
        {"value": total_amount,   "label": _("Total Sample Value"),"datatype": "Currency", "indicator": "red"},
    ]