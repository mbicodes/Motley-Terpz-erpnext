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
    "Caligreen": ["Caligreen"],
    "Hardware Inventory": ["Hardware Inventory"], # Corrected from Hardware
}

def get_category_for_item_group(item_group):
    """Reverse lookup: get the display category for a given DB item group."""
    for cat, groups in CATEGORY_MAPPINGS.items():
        if item_group in groups:
            return cat
    return "Other"

# Config for which categories show breakdown. 
# We now break down *by* Item Group since the user put the items into these groups.
BREAKDOWN_CONFIG = {
    "Total packaged goods produced": True,
    "Packaged goods": True,
    "Total Rosin": True,
    "BHO": True,
    "Hardware Inventory": True
}

def get_breakdown_label(category, item_group, item_code=None, item_name=None):
    """
    Determine what label to show in the drill-down.
    - For 'Hardware Inventory', we show item code and name.
    - For others, we show the item group.
    """
    if category == "Hardware Inventory":
        return (item_name or item_group).strip()

    if category in BREAKDOWN_CONFIG and BREAKDOWN_CONFIG[category]:
        return item_group
    return None



def get_month_ranges(to_date):
    """Get month ranges from Jan 1 of the year up to to_date month."""
    to_date = getdate(to_date)
    year = to_date.year
    months = []
    
    for m in range(1, to_date.month + 1):
        start = get_first_day(f"{year}-{m:02d}-01")
        # For flow entries, we need the range. 
        # For inventory, we use the end date.
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
        
        # Next week end is the day before this week start
        current_end = start - timedelta(days=1)
        
    return list(reversed(weeks))


@frappe.whitelist()
def get_weekly_summary(from_date=None, to_date=None, company=None, mode="value"):
    """
    Main API for Business Overview page.
    Returns production, sales, revenue, and inventory data.
    Columns: Consolidated months since Jan, then trailing 4 weeks.
    """
    if not to_date:
        to_date = today()
    
    if not company:
        company = frappe.defaults.get_user_default("Company")
        if not company:
            company = frappe.db.get_single_value("Global Defaults", "default_company")
    
    to_date = getdate(to_date)
    
    # 1. Monthly columns (January to to_date month)
    month_cols = get_month_ranges(to_date)
    
    # 2. Trailing 4 weeks
    week_cols = get_trailing_weeks(to_date)
    
    all_cols = month_cols + week_cols
    
    is_value = mode == "value"
    
    result = {
        "weeks": all_cols, # Keeping key name 'weeks' for frontend compatibility but it contains months too
        "month_count": len(month_cols),
        "week_count": len(week_cols),
        "company": company,
        "mode": mode,
        "sections": {}
    }
    
    # Data fetching remains mostly the same as it iterates over the columns (all_cols)
    result["sections"]["production"] = get_production_data(all_cols, company, is_value)
    result["sections"]["sales"] = get_sales_data(all_cols, company)
    result["sections"]["revenue"] = get_revenue_data(all_cols, company)
    result["sections"]["inventory"] = get_inventory_data(all_cols, company, is_value)
    
    return result


def get_production_data(weeks, company, is_value):
    """
    Get production data.
    - Total Tolled/Washed: Out qty/value of Fresh Frozen items from Tolling Partner warehouses (Stock Ledger Entry)
    - Total packaged goods produced: Finished goods from item group 'Packaged goods' (Stock Entry)
    """
    rows = {
        "Total Tolled/Washed": {"totals": {}, "details": {}},
        "Total packaged goods produced": {"totals": {}, "details": {}},
    }
    
    # Get all warehouses with warehouse_type = 'Tolling Partner'
    tolling_warehouses = frappe.get_all(
        'Warehouse',
        filters={'warehouse_type': 'Tolling Partner', 'company': company},
        pluck='name'
    )
    
    value_field_se = "SUM(sed.amount)" if is_value else "SUM(sed.qty)"
    # For SLE out entries: actual_qty < 0, so we use ABS to get positive values
    value_field_sle = "ABS(SUM(sle.stock_value_difference))" if is_value else "ABS(SUM(sle.actual_qty))"
    
    for week in weeks:
        # 1. Total Tolled/Washed — Fresh Frozen items
        if tolling_warehouses:
            tolled_data = frappe.db.sql("""
                SELECT 
                    i.item_group,
                    {value_field} as val
                FROM `tabStock Ledger Entry` sle
                JOIN `tabItem` i ON i.name = sle.item_code
                WHERE sle.is_cancelled = 0
                    AND sle.posting_date BETWEEN %s AND %s
                    AND sle.company = %s
                    AND sle.actual_qty < 0
                    AND sle.warehouse IN %s
                    AND i.item_group LIKE '%%Fresh Frozen%%'
                GROUP BY i.item_group
            """.format(value_field=value_field_sle), (week["start"], week["end"], company, tolling_warehouses), as_dict=True)
            
            cat = "Total Tolled/Washed"
            if cat not in rows: rows[cat] = {"totals": {}, "details": {}}
            
            total_val = 0
            for r in tolled_data:
                val = flt(r.val)
                total_val += val
            rows[cat]["totals"][week["label"]] = total_val
        
        # 2. Total packaged goods 
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
                    AND se.company = %s
                    AND sed.is_finished_item = 1
                    AND i.item_group IN %s
                GROUP BY i.item_group
            """.format(value_field=value_field_se), (week["start"], week["end"], company, packaged_groups), as_dict=True)
            
            cat = "Total packaged goods produced"
            if cat not in rows: rows[cat] = {"totals": {}, "details": {}}
            
            total_val = 0
            for r in packaged_data:
                val = flt(r.val)
                total_val += val
                
                # Check for breakdown
                label = get_breakdown_label(cat, r.item_group)
                if label:
                    if label not in rows[cat]["details"]: rows[cat]["details"][label] = {}
                    rows[cat]["details"][label][week["label"]] = rows[cat]["details"][label].get(week["label"], 0) + val
            rows[cat]["totals"][week["label"]] = total_val
    
    return {
        "title": "Production Total",
        "color": "#fef3c7",
        "header_color": "#f59e0b",
        "fixed_mode": "value" if is_value else "quantity",
        "rows": rows
    }


def get_sales_data(weeks, company):
    """
    Get sales data from Sales Invoice grouped by item group.
    ALWAYS returns QUANTITY — regardless of the mode toggle.
    Excludes inter-company sales (customers with is_internal_customer = 1).
    Maps display labels to actual DB item groups.
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
                AND si.company = %s
                AND si.is_return = 0
                AND IFNULL(c.is_internal_customer, 0) = 0
            GROUP BY i.name
        """, (week["start"], week["end"], company), as_dict=True)
        
        for r in sales_data:
            val = flt(r.val)
            ig = r.item_group
            
            # Find which display category
            found_cat = get_category_for_item_group(ig)
            
            # Add to totals
            rows[found_cat]["totals"][week["label"]] = rows[found_cat]["totals"].get(week["label"], 0) + val
            
            # Add to details if whitelisted
            label = get_breakdown_label(found_cat, ig, r.item_code, r.item_name)
            if label:
                if label not in rows[found_cat]["details"]: rows[found_cat]["details"][label] = {}
                rows[found_cat]["details"][label][week["label"]] = rows[found_cat]["details"][label].get(week["label"], 0) + val
    
    return {
        "title": "Sales",
        "color": "#fecaca",
        "header_color": "#ef4444",
        "fixed_mode": "quantity",
        "rows": rows
    }


def get_revenue_data(weeks, company):
    """
    Get revenue data from Sales Invoice (net amount by item group).
    ALWAYS returns VALUE — regardless of the mode toggle.
    Excludes inter-company sales.
    Maps display labels to actual DB item groups.
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
                AND si.company = %s
                AND si.is_return = 0
                AND IFNULL(c.is_internal_customer, 0) = 0
            GROUP BY i.name
        """, (week["start"], week["end"], company), as_dict=True)
        
        for r in rev_data:
            val = flt(r.val)
            ig = r.item_group
            
            # Find display category
            found_cat = get_category_for_item_group(ig)
            
            # Add to totals
            rows[found_cat]["totals"][week["label"]] = rows[found_cat]["totals"].get(week["label"], 0) + val
            
            # Add to details if whitelisted
            label = get_breakdown_label(found_cat, ig, r.item_code, r.item_name)
            if label:
                if label not in rows[found_cat]["details"]: rows[found_cat]["details"][label] = {}
                rows[found_cat]["details"][label][week["label"]] = rows[found_cat]["details"][label].get(week["label"], 0) + val
    
    return {
        "title": "Revenue",
        "color": "#fef3c7",
        "header_color": "#f59e0b",
        "fixed_mode": "value",
        "rows": rows
    }


def get_inventory_data(weeks, company, is_value):
    """
    Get inventory (stock balance) data grouped by item group.
    Shows closing balance at end of each week.
    Skips 'Services' group; includes 'Hardware'.
    Maps display labels to actual DB item groups.
    """
    rows = {}
    # Use ALL categories now since we standardized the mapping
    for cat in CATEGORY_MAPPINGS.keys():
        # Do not include Services in Inventory
        if cat != "Services":
            rows[cat] = {"totals": {}, "details": {}}
    
    # Also add Other for unmapped items
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
                AND sle.company = %s
            GROUP BY i.name
        """.format(
            value_field=value_field
        ), (week["end"], company), as_dict=True)
        
        for r in inv_data:
            val = flt(r.val)
            ig = r.item_group
            
            # Find category
            found_cat = get_category_for_item_group(ig)
            if found_cat == "Services": 
                continue # Ignore services for inventory
                
            # Add to totals
            rows[found_cat]["totals"][week["label"]] = rows[found_cat]["totals"].get(week["label"], 0) + val
            
            # Add to details if whitelisted
            label = get_breakdown_label(found_cat, ig, r.item_code, r.item_name)
            if label:
                if label not in rows[found_cat]["details"]: rows[found_cat]["details"][label] = {}
                rows[found_cat]["details"][label][week["label"]] = rows[found_cat]["details"][label].get(week["label"], 0) + val
    
    return {
        "title": "Inventory",
        "color": "#fecaca",
        "header_color": "#ef4444",
        "fixed_mode": "value" if is_value else "quantity",
        "rows": rows
    }


@frappe.whitelist()
def get_companies():
    """Return list of companies for the filter dropdown."""
    return frappe.get_all("Company", pluck="name", order_by="name")
