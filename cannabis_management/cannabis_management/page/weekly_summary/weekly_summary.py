import frappe
from frappe.utils import today, getdate, add_days, flt, get_first_day, get_last_day, formatdate
from datetime import timedelta
import json


# Categories and their corresponding Item Groups in the DB
CATEGORY_MAPPINGS = {
    "Packaged goods": ["0.5g O2 Vape", "1g O2 Vapes", "1g Jarred Rosin", "3g Jarred Rosin"],
    "Total Rosin": ["VRR", "Primes", "Subprimes", "Full Spec", "Food Grade"],
    "BHO": ["LIQUID LIVE RESIN", "Diamonds"],
    "Gummies": ["Gummies"],
    "Services": ["Services"],
    "Distillate": ["DISTALLATE"],
    "Fresh Frozen": [],  # Matched by LIKE pattern in get_category_for_item_group
}

def get_category_for_item_group(item_group):
    """Reverse lookup: get the display category for a given DB item group."""
    for cat, groups in CATEGORY_MAPPINGS.items():
        if item_group in groups:
            return cat
    # Fresh Frozen items have varying item group names
    if item_group and "Fresh Frozen" in item_group:
        return "Fresh Frozen"
    return "Other"

# Config for which categories show breakdown.
BREAKDOWN_CONFIG = {
    "Total packaged goods produced": True,
    "Packaged goods": True,
    "Total Rosin": True,
    "BHO": True,
}

def get_breakdown_label(category, item_group, item_code=None, item_name=None):
    """Determine what label to show in the drill-down (item group name)."""
    if category in BREAKDOWN_CONFIG and BREAKDOWN_CONFIG[category]:
        return item_group
    return None


def get_companies_to_query(company):
    """
    If the selected company has child companies (i.e. it is a parent/group company),
    return a list containing the parent plus all direct children so that the page
    shows consolidated data for the whole group.
    Otherwise return a single-item list with the company itself.
    """
    children = frappe.get_all(
        "Company",
        filters={"parent_company": company},
        pluck="name"
    )
    if children:
        return [company] + children
    return [company]


def get_month_ranges(to_date):
    """Get month ranges from Jan 1 of the year up to to_date month."""
    to_date = getdate(to_date)
    year = to_date.year
    months = []

    for m in range(1, to_date.month + 1):
        start = get_first_day(f"{year}-{m:02d}-01")
        end = get_last_day(start)
        if end > to_date:
            end = to_date

        months.append({
            "start": str(start),
            "end": str(end),
            "label": formatdate(str(start), "MMM"),
            "is_month": True
        })
    return months

def get_trailing_weeks(to_date, count=4):
    """Get the last N month-weeks ending at to_date."""
    to_date = getdate(to_date)
    weeks = []

    current_end = to_date
    while len(weeks) < count:
        d = current_end.day
        month_str = formatdate(str(current_end), "MMM")

        if d >= 22:
            start_day = 22
            week_num = 4
        elif d >= 15:
            start_day = 15
            week_num = 3
        elif d >= 8:
            start_day = 8
            week_num = 2
        else:
            start_day = 1
            week_num = 1

        start = current_end.replace(day=start_day)

        weeks.append({
            "start": str(start),
            "end": str(current_end),
            "label": f"{month_str} Week {week_num}",
            "is_week": True
        })

        current_end = start - timedelta(days=1)

    return list(reversed(weeks))


@frappe.whitelist()
def get_weekly_summary(from_date=None, to_date=None, company=None, mode="value"):
    """
    Main API for Business Overview page.
    Returns production, sales, revenue, inventory and money-collected data.
    Columns: Consolidated months since Jan, then trailing 4 weeks.

    When the selected company is a parent/group company (has child companies),
    all child companies are automatically included so the figures are consolidated.
    """
    if not to_date:
        to_date = today()

    if not company:
        company = frappe.defaults.get_user_default("Company")
        if not company:
            company = frappe.db.get_single_value("Global Defaults", "default_company")

    to_date = getdate(to_date)

    # Resolve the company to a list (parent company → all children included)
    companies = get_companies_to_query(company)

    # 1. Monthly columns (January to to_date month)
    month_cols = get_month_ranges(to_date)

    # 2. Trailing 4 weeks
    week_cols = get_trailing_weeks(to_date)

    all_cols = month_cols + week_cols

    is_value = mode == "value"

    result = {
        "weeks": all_cols,
        "month_count": len(month_cols),
        "week_count": len(week_cols),
        "company": company,
        "companies": companies,
        "mode": mode,
        "sections": {}
    }

    result["sections"]["production"] = get_production_data(all_cols, companies, is_value)
    result["sections"]["sales"] = get_sales_data(all_cols, companies)
    result["sections"]["revenue"] = get_revenue_data(all_cols, companies)
    result["sections"]["inventory"] = get_inventory_data(all_cols, companies, is_value)
    result["sections"]["money_collected"] = get_money_collected_data(all_cols, companies)

    return result


def get_production_data(weeks, companies, is_value):
    """
    Get production data.
    - Total Tolled/Washed: Out qty/value of Fresh Frozen items from Tolling Partner warehouses
    - Total packaged goods produced: Finished goods from Packaged goods item groups
    companies is always a list (one or more companies).
    """
    rows = {
        "Total Tolled/Washed": {"totals": {}, "details": {}},
        "Total packaged goods produced": {"totals": {}, "details": {}},
    }

    # Get all Tolling Partner warehouses across all relevant companies
    tolling_warehouses = frappe.get_all(
        "Warehouse",
        filters={"warehouse_type": "Tolling Partner", "company": ["in", companies]},
        pluck="name"
    )

    value_field_se = "SUM(sed.amount)" if is_value else "SUM(sed.qty)"
    value_field_sle = "ABS(SUM(sle.stock_value_difference))" if is_value else "ABS(SUM(sle.actual_qty))"

    for week in weeks:
        # 1. Total Tolled/Washed — Fresh Frozen items out of Tolling Partner warehouses
        if tolling_warehouses:
            tolled_data = frappe.db.sql("""
                SELECT
                    i.item_group,
                    {value_field} as val
                FROM `tabStock Ledger Entry` sle
                JOIN `tabItem` i ON i.name = sle.item_code
                WHERE sle.is_cancelled = 0
                    AND sle.posting_date BETWEEN %s AND %s
                    AND sle.company IN %s
                    AND sle.actual_qty < 0
                    AND sle.warehouse IN %s
                    AND i.item_group LIKE '%%Fresh Frozen%%'
                GROUP BY i.item_group
            """.format(value_field=value_field_sle),
                (week["start"], week["end"], companies, tolling_warehouses), as_dict=True)

            total_val = 0
            for r in tolled_data:
                total_val += flt(r.val)
            rows["Total Tolled/Washed"]["totals"][week["label"]] = total_val

        # 2. Total packaged goods produced
        packaged_groups = CATEGORY_MAPPINGS.get("Packaged goods", [])

        if packaged_groups:
            packaged_data = frappe.db.sql("""
                SELECT
                    i.item_group,
                    {value_field} as val
                FROM `tabStock Entry Detail` sed
                JOIN `tabStock Entry` se ON se.name = sed.parent
                JOIN `tabItem` i ON i.name = sed.item_code
                WHERE se.docstatus = 1
                    AND se.stock_entry_type IN ('Manufacture', 'Repack')
                    AND se.posting_date BETWEEN %s AND %s
                    AND se.company IN %s
                    AND sed.is_finished_item = 1
                    AND i.item_group IN %s
                GROUP BY i.item_group
            """.format(value_field=value_field_se),
                (week["start"], week["end"], companies, packaged_groups), as_dict=True)

            total_val = 0
            for r in packaged_data:
                val = flt(r.val)
                total_val += val

                label = get_breakdown_label("Total packaged goods produced", r.item_group)
                if label:
                    details = rows["Total packaged goods produced"]["details"]
                    if label not in details:
                        details[label] = {}
                    details[label][week["label"]] = details[label].get(week["label"], 0) + val

            rows["Total packaged goods produced"]["totals"][week["label"]] = total_val

    return {
        "title": "Production Total",
        "color": "#fef3c7",
        "header_color": "#f59e0b",
        "fixed_mode": "value" if is_value else "quantity",
        "rows": rows
    }


def get_sales_data(weeks, companies):
    """
    Get sales data from Sales Invoice grouped by item group.
    ALWAYS returns QUANTITY — regardless of the mode toggle.
    Excludes inter-company sales (customers with is_internal_customer = 1).
    companies is always a list (one or more companies).
    """
    rows = {}
    for cat in CATEGORY_MAPPINGS.keys():
        rows[cat] = {"totals": {}, "details": {}}
    rows["Other"] = {"totals": {}, "details": {}}

    for week in weeks:
        sales_data = frappe.db.sql("""
            SELECT
                COALESCE(i.item_group, 'Other') as item_group,
                i.name as item_code,
                TRIM(i.item_name) as item_name,
                SUM(sii.stock_qty) as val
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            LEFT JOIN `tabItem` i ON i.name = sii.item_code
            LEFT JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1
                AND si.posting_date BETWEEN %s AND %s
                AND si.company IN %s
                AND si.is_return = 0
                AND IFNULL(c.is_internal_customer, 0) = 0
            GROUP BY i.name
        """, (week["start"], week["end"], companies), as_dict=True)

        for r in sales_data:
            val = flt(r.val)
            ig = r.item_group
            found_cat = get_category_for_item_group(ig)

            rows[found_cat]["totals"][week["label"]] = rows[found_cat]["totals"].get(week["label"], 0) + val

            label = get_breakdown_label(found_cat, ig, r.item_code, r.item_name)
            if label:
                if label not in rows[found_cat]["details"]:
                    rows[found_cat]["details"][label] = {}
                rows[found_cat]["details"][label][week["label"]] = rows[found_cat]["details"][label].get(week["label"], 0) + val

    return {
        "title": "Sales",
        "color": "#fecaca",
        "header_color": "#ef4444",
        "fixed_mode": "quantity",
        "rows": rows
    }


def get_revenue_data(weeks, companies):
    """
    Get revenue data from Sales Invoice (net amount by item group).
    ALWAYS returns VALUE — regardless of the mode toggle.
    Excludes inter-company sales.
    companies is always a list (one or more companies).
    """
    rows = {}
    for cat in CATEGORY_MAPPINGS.keys():
        rows[cat] = {"totals": {}, "details": {}}
    rows["Other"] = {"totals": {}, "details": {}}

    for week in weeks:
        rev_data = frappe.db.sql("""
            SELECT
                COALESCE(i.item_group, 'Other') as item_group,
                i.name as item_code,
                TRIM(i.item_name) as item_name,
                SUM(sii.base_net_amount) as val
            FROM `tabSales Invoice Item` sii
            JOIN `tabSales Invoice` si ON si.name = sii.parent
            LEFT JOIN `tabItem` i ON i.name = sii.item_code
            LEFT JOIN `tabCustomer` c ON c.name = si.customer
            WHERE si.docstatus = 1
                AND si.posting_date BETWEEN %s AND %s
                AND si.company IN %s
                AND si.is_return = 0
                AND IFNULL(c.is_internal_customer, 0) = 0
            GROUP BY i.name
        """, (week["start"], week["end"], companies), as_dict=True)

        for r in rev_data:
            val = flt(r.val)
            ig = r.item_group
            found_cat = get_category_for_item_group(ig)

            rows[found_cat]["totals"][week["label"]] = rows[found_cat]["totals"].get(week["label"], 0) + val

            label = get_breakdown_label(found_cat, ig, r.item_code, r.item_name)
            if label:
                if label not in rows[found_cat]["details"]:
                    rows[found_cat]["details"][label] = {}
                rows[found_cat]["details"][label][week["label"]] = rows[found_cat]["details"][label].get(week["label"], 0) + val

    return {
        "title": "Revenue",
        "color": "#fef3c7",
        "header_color": "#f59e0b",
        "fixed_mode": "value",
        "rows": rows
    }


def get_inventory_data(weeks, companies, is_value):
    """
    Get inventory (stock balance) data grouped by item group.
    Shows closing balance at end of each period.
    Skips 'Services' group.
    companies is always a list (one or more companies).
    """
    rows = {}
    for cat in CATEGORY_MAPPINGS.keys():
        if cat != "Services":
            rows[cat] = {"totals": {}, "details": {}}
    rows["Other"] = {"totals": {}, "details": {}}

    value_field = "SUM(sle.stock_value_difference)" if is_value else "SUM(sle.actual_qty)"

    for week in weeks:
        inv_data = frappe.db.sql("""
            SELECT
                COALESCE(i.item_group, 'Other') as item_group,
                i.name as item_code,
                TRIM(i.item_name) as item_name,
                {value_field} as val
            FROM `tabStock Ledger Entry` sle
            JOIN `tabItem` i ON i.name = sle.item_code
            WHERE sle.is_cancelled = 0
                AND sle.posting_date <= %s
                AND sle.company IN %s
            GROUP BY i.name
        """.format(value_field=value_field), (week["end"], companies), as_dict=True)

        for r in inv_data:
            val = flt(r.val)
            ig = r.item_group
            found_cat = get_category_for_item_group(ig)

            if found_cat == "Services":
                continue

            rows[found_cat]["totals"][week["label"]] = rows[found_cat]["totals"].get(week["label"], 0) + val

            label = get_breakdown_label(found_cat, ig, r.item_code, r.item_name)
            if label:
                if label not in rows[found_cat]["details"]:
                    rows[found_cat]["details"][label] = {}
                rows[found_cat]["details"][label][week["label"]] = rows[found_cat]["details"][label].get(week["label"], 0) + val

    return {
        "title": "Inventory",
        "color": "#fecaca",
        "header_color": "#ef4444",
        "fixed_mode": "value" if is_value else "quantity",
        "rows": rows
    }


# Partial patterns used to match paid_to accounts for Money Collected.
# LIKE matching is used so the same pattern works across companies
# regardless of the company-code suffix (e.g. "- MT", "- MTPZ").
MONEY_ACCOUNT_PATTERNS = {
    "Cash": "Petty Cash-Nikki",
    "Bank": "Bank-7008",
}


def get_money_collected_data(weeks, companies):
    """
    Get money collected by summing GL Entry debits for the specific Cash and Bank
    accounts defined in MONEY_ACCOUNT_PATTERNS.  Using GL Entry (same source as
    the General Ledger report) ensures all voucher types — Payment Entry AND
    Journal Entry — are included, so the figures match the GL exactly.
    companies is always a list (one or more companies).
    """
    rows = {
        "Cash": {"totals": {}, "details": {}},
        "Bank": {"totals": {}, "details": {}},
    }

    cash_pattern = "%" + MONEY_ACCOUNT_PATTERNS["Cash"] + "%"
    bank_pattern = "%" + MONEY_ACCOUNT_PATTERNS["Bank"] + "%"

    for week in weeks:
        gl_data = frappe.db.sql("""
            SELECT
                gle.account,
                SUM(gle.debit) AS val
            FROM `tabGL Entry` gle
            WHERE gle.is_cancelled = 0
                AND gle.posting_date <= %s
                AND gle.company IN %s
                AND (gle.account LIKE %s OR gle.account LIKE %s)
            GROUP BY gle.account
        """, (week["end"], companies, cash_pattern, bank_pattern), as_dict=True)

        for r in gl_data:
            val = flt(r.val)
            if MONEY_ACCOUNT_PATTERNS["Cash"] in r.account:
                rows["Cash"]["totals"][week["label"]] = rows["Cash"]["totals"].get(week["label"], 0) + val
            elif MONEY_ACCOUNT_PATTERNS["Bank"] in r.account:
                rows["Bank"]["totals"][week["label"]] = rows["Bank"]["totals"].get(week["label"], 0) + val

    return {
        "title": "Money Collected",
        "color": "#e0f2fe",
        "header_color": "#0ea5e9",
        "fixed_mode": "value",
        "rows": rows,
    }


@frappe.whitelist()
def get_companies():
    """Return list of companies for the filter dropdown."""
    return frappe.get_all("Company", pluck="name", order_by="name")
