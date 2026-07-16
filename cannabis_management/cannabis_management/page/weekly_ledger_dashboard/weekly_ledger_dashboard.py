import frappe
from frappe.utils import flt, formatdate

ALLOWED_ROLES = {"System Manager", "Sales Manager", "Sales User", "Accounts User"}

SUMMARY_FIELDS = [
    "name", "week_of", "sales_person", "company",
    "coming_in_total", "coming_in_cash", "coming_in_bank",
    "collected_total", "collected_cash", "collected_bank",
    "expected_total", "expected_cash", "expected_bank",
    "sales_written_total", "sales_cod", "sales_terms", "sales_target_total",
    "ar_total", "ar_collected", "ar_expected",
    "outbound_value", "outbound_orders", "inbound_value", "inbound_orders",
]


def _check_access():
    if frappe.session.user == "Administrator":
        return
    if not ALLOWED_ROLES & set(frappe.get_roles()):
        frappe.throw("Not permitted", frappe.PermissionError)


@frappe.whitelist()
def get_dashboard(salesperson=None, week=None):
    _check_access()

    all_docs = frappe.get_all(
        "Weekly Cash Ledger",
        fields=SUMMARY_FIELDS,
        order_by="week_of asc",
    )

    salespersons = sorted({d.sales_person for d in all_docs if d.sales_person})

    docs = all_docs
    if salesperson and salesperson != "all":
        docs = [d for d in docs if d.sales_person == salesperson]

    weeks = [{"key": str(d.week_of), "label": formatdate(d.week_of, "MMM dd"), "name": d.name}
             for d in docs]

    scope = docs
    if week and week != "all":
        scope = [d for d in docs if str(d.week_of) == week]

    def total(field):
        return sum(flt(d.get(field)) for d in scope)

    kpis = {f: total(f) for f in SUMMARY_FIELDS[4:]}
    kpis["weeks_in_scope"] = len(scope)

    trend = {
        "labels": [formatdate(d.week_of, "MMM dd") for d in docs],
        "collected": [round(flt(d.collected_total), 2) for d in docs],
        "expected": [round(flt(d.expected_total), 2) for d in docs],
        "sales_written": [round(flt(d.sales_written_total), 2) for d in docs],
    }

    scope_names = [d.name for d in scope]
    categories, lines = [], []
    if scope_names:
        cat_rows = frappe.db.sql(
            """
            SELECT category,
                   SUM(target_amount) AS target_amount,
                   SUM(actual_amount) AS actual_amount
            FROM `tabWeekly Sales Target Line`
            WHERE parent IN %(parents)s
            GROUP BY category
            HAVING SUM(target_amount) > 0 OR SUM(actual_amount) > 0
            ORDER BY SUM(target_amount) DESC
            """,
            {"parents": tuple(scope_names)},
            as_dict=True,
        )
        categories = cat_rows

        lines = frappe.db.sql(
            """
            SELECT l.parent, p.week_of, l.entry_type, l.account_name, l.customer,
                   l.amount, l.expected_amount, l.method, l.category, l.terms,
                   l.status, l.direction, l.notes
            FROM `tabWeekly Cash Ledger Line` l
            JOIN `tabWeekly Cash Ledger` p ON p.name = l.parent
            WHERE l.parent IN %(parents)s
            ORDER BY p.week_of DESC, l.idx ASC
            LIMIT 300
            """,
            {"parents": tuple(scope_names)},
            as_dict=True,
        )
        for r in lines:
            r["week_label"] = formatdate(r.week_of, "MMM dd")
            r["value"] = flt(r.amount) or flt(r.expected_amount)

    return {
        "salespersons": salespersons,
        "weeks": weeks,
        "kpis": kpis,
        "trend": trend,
        "categories": categories,
        "lines": lines,
    }
