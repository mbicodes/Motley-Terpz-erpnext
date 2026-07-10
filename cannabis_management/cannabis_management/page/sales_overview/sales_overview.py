import frappe
from frappe.utils import flt, getdate

# Sales persons featured as toggle buttons on the dashboard, in display order.
# Each must be an enabled Sales Person record; their user is resolved from
# the Sales Person's custom_email field.
FEATURED_SALESPERSONS = ["Nikki Manilig", "Douglas Boulware"]

LIST_LIMIT = 100

# Keep in sync with the roles on the sales-overview Page doc.
ALLOWED_ROLES = {"System Manager", "Sales Manager", "Sales User", "Accounts User"}


def _check_access():
    if frappe.session.user == "Administrator":
        return
    if not ALLOWED_ROLES & set(frappe.get_roles()):
        frappe.throw("Not permitted to view the Sales Overview", frappe.PermissionError)


def _featured_salespersons():
    rows = frappe.db.sql(
        """
        SELECT name, sales_person_name, IFNULL(custom_email, '') AS email
        FROM `tabSales Person`
        WHERE name IN %(names)s AND enabled = 1
        """,
        {"names": tuple(FEATURED_SALESPERSONS)},
        as_dict=True,
    )
    by_name = {r.name: r for r in rows}
    out = []
    for name in FEATURED_SALESPERSONS:
        r = by_name.get(name)
        if not r:
            continue
        first_name = (r.sales_person_name or name).split(" ")[0]
        out.append({
            "key": name,
            "label": first_name,
            "full_name": r.sales_person_name or name,
            "email": r.email,
        })
    return out


@frappe.whitelist()
def init_page():
    _check_access()
    return {
        "salespersons": _featured_salespersons(),
        "companies": frappe.db.sql_list("SELECT name FROM `tabCompany` ORDER BY name"),
    }


def _resolve_sp(salesperson):
    if not salesperson or salesperson == "all":
        return None
    for sp in _featured_salespersons():
        if sp["key"] == salesperson:
            return sp
    frappe.throw(f"Unknown sales person: {salesperson}")


def _not_intercompany(alias, party_field="customer"):
    """Exclude intercompany documents (customer flagged is_internal_customer)."""
    return f"""NOT EXISTS (
        SELECT 1 FROM `tabCustomer` c
        WHERE c.name = {alias}.{party_field} AND c.is_internal_customer = 1
    )"""


def _doc_conditions(alias, doctype, date_field, sp, from_date, to_date, company, params):
    """Build WHERE conditions for a sales doctype. A document belongs to a
    sales person if they created it (owner) or appear in its Sales Team."""
    conds = [f"{alias}.docstatus = 1", _not_intercompany(alias)]
    if from_date:
        conds.append(f"{alias}.{date_field} >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conds.append(f"{alias}.{date_field} <= %(to_date)s")
        params["to_date"] = to_date
    if company:
        conds.append(f"{alias}.company = %(company)s")
        params["company"] = company
    if sp:
        params["sp_email"] = sp["email"]
        params["sp_name"] = sp["key"]
        conds.append(
            f"""({alias}.owner = %(sp_email)s OR EXISTS (
                SELECT 1 FROM `tabSales Team` st
                WHERE st.parent = {alias}.name
                  AND st.parenttype = '{doctype}'
                  AND st.sales_person = %(sp_name)s
            ))"""
        )
    return " AND ".join(conds)


def _get_invoices(sp, from_date, to_date, company):
    params = {}
    where = _doc_conditions("si", "Sales Invoice", "posting_date", sp, from_date, to_date, company, params)
    return frappe.db.sql(
        f"""
        SELECT si.name, si.posting_date, si.customer, si.customer_name, si.company,
               si.grand_total, si.outstanding_amount, si.status
        FROM `tabSales Invoice` si
        WHERE {where}
        ORDER BY si.posting_date DESC, si.creation DESC
        """,
        params,
        as_dict=True,
    )


def _get_orders(sp, from_date, to_date, company):
    params = {}
    where = _doc_conditions("so", "Sales Order", "transaction_date", sp, from_date, to_date, company, params)
    return frappe.db.sql(
        f"""
        SELECT so.name, so.transaction_date AS posting_date, so.customer, so.customer_name,
               so.company, so.grand_total, so.status, so.per_billed, so.per_delivered
        FROM `tabSales Order` so
        WHERE {where}
        ORDER BY so.transaction_date DESC, so.creation DESC
        """,
        params,
        as_dict=True,
    )


def _get_delivery_notes(sp, from_date, to_date, company):
    params = {}
    where = _doc_conditions("dn", "Delivery Note", "posting_date", sp, from_date, to_date, company, params)
    return frappe.db.sql(
        f"""
        SELECT dn.name, dn.posting_date, dn.customer, dn.customer_name, dn.company,
               dn.grand_total, dn.status
        FROM `tabDelivery Note` dn
        WHERE {where}
        ORDER BY dn.posting_date DESC, dn.creation DESC
        """,
        params,
        as_dict=True,
    )


def _get_payments(sp, from_date, to_date, company, invoice_names, order_names):
    """Payment Entries (Receive) with each payment tagged Cash or Bank based on
    the account type of the account it was paid into.

    For a sales person, a payment counts if they created it or if it is
    allocated against one of their invoices / orders."""
    params = {}
    conds = ["pe.docstatus = 1", "pe.payment_type = 'Receive'", _not_intercompany("pe", "party")]
    if from_date:
        conds.append("pe.posting_date >= %(from_date)s")
        params["from_date"] = from_date
    if to_date:
        conds.append("pe.posting_date <= %(to_date)s")
        params["to_date"] = to_date
    if company:
        conds.append("pe.company = %(company)s")
        params["company"] = company
    if sp:
        params["sp_email"] = sp["email"]
        ref_names = list(invoice_names) + list(order_names)
        if ref_names:
            params["ref_names"] = tuple(ref_names)
            conds.append(
                """(pe.owner = %(sp_email)s OR EXISTS (
                    SELECT 1 FROM `tabPayment Entry Reference` per
                    WHERE per.parent = pe.name AND per.reference_name IN %(ref_names)s
                ))"""
            )
        else:
            conds.append("pe.owner = %(sp_email)s")

    return frappe.db.sql(
        f"""
        SELECT pe.name, pe.posting_date, pe.party, pe.party_name, pe.company,
               pe.paid_amount, pe.mode_of_payment, pe.paid_to,
               CASE WHEN acc.account_type = 'Cash' THEN 'Cash' ELSE 'Bank' END AS receipt_type
        FROM `tabPayment Entry` pe
        LEFT JOIN `tabAccount` acc ON acc.name = pe.paid_to
        WHERE {" AND ".join(conds)}
        ORDER BY pe.posting_date DESC, pe.creation DESC
        """,
        params,
        as_dict=True,
    )


def _month_key(d):
    d = getdate(d)
    return d.strftime("%Y-%m")


def _monthly_trend(invoices, orders, payments):
    months = {}

    def bump(date, field, amount):
        key = _month_key(date)
        months.setdefault(key, {"invoiced": 0.0, "ordered": 0.0, "received": 0.0})
        months[key][field] += flt(amount)

    for r in invoices:
        bump(r.posting_date, "invoiced", r.grand_total)
    for r in orders:
        bump(r.posting_date, "ordered", r.grand_total)
    for r in payments:
        bump(r.posting_date, "received", r.paid_amount)

    keys = sorted(months.keys())[-12:]
    labels = [getdate(k + "-01").strftime("%b %y") for k in keys]
    return {
        "labels": labels,
        "invoiced": [round(months[k]["invoiced"], 2) for k in keys],
        "ordered": [round(months[k]["ordered"], 2) for k in keys],
        "received": [round(months[k]["received"], 2) for k in keys],
    }


@frappe.whitelist()
def get_dashboard_data(salesperson="all", from_date=None, to_date=None, company=None):
    _check_access()
    sp = _resolve_sp(salesperson)
    company = company or None

    invoices = _get_invoices(sp, from_date, to_date, company)
    orders = _get_orders(sp, from_date, to_date, company)
    delivery_notes = _get_delivery_notes(sp, from_date, to_date, company)
    payments = _get_payments(
        sp, from_date, to_date, company,
        [r.name for r in invoices], [r.name for r in orders],
    )

    cash_total = sum(flt(p.paid_amount) for p in payments if p.receipt_type == "Cash")
    bank_total = sum(flt(p.paid_amount) for p in payments if p.receipt_type == "Bank")

    kpis = {
        "invoices": {
            "count": len(invoices),
            "total": sum(flt(r.grand_total) for r in invoices),
            "outstanding": sum(flt(r.outstanding_amount) for r in invoices),
        },
        "orders": {
            "count": len(orders),
            "total": sum(flt(r.grand_total) for r in orders),
        },
        "delivery_notes": {
            "count": len(delivery_notes),
            "total": sum(flt(r.grand_total) for r in delivery_notes),
        },
        "payments": {
            "count": len(payments),
            "total": cash_total + bank_total,
            "cash": cash_total,
            "bank": bank_total,
            "cash_count": sum(1 for p in payments if p.receipt_type == "Cash"),
            "bank_count": sum(1 for p in payments if p.receipt_type == "Bank"),
        },
    }

    return {
        "salesperson": sp["label"] if sp else "All",
        "kpis": kpis,
        "trend": _monthly_trend(invoices, orders, payments),
        "lists": {
            "invoices": invoices[:LIST_LIMIT],
            "orders": orders[:LIST_LIMIT],
            "delivery_notes": delivery_notes[:LIST_LIMIT],
            "payments": payments[:LIST_LIMIT],
        },
        "list_totals": {
            "invoices": len(invoices),
            "orders": len(orders),
            "delivery_notes": len(delivery_notes),
            "payments": len(payments),
        },
    }
