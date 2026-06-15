import frappe
from frappe.utils import today, getdate, add_days, flt, get_first_day, get_last_day, formatdate
from datetime import timedelta

def setup_custom_fields():
    if not frappe.db.exists('Custom Field', 'Target Detail-average_rate'):
        custom_field = frappe.get_doc({
            'doctype': 'Custom Field',
            'dt': 'Target Detail',
            'fieldname': 'average_rate',
            'label': 'Average Rate',
            'fieldtype': 'Currency',
            'insert_after': 'target_qty'
        })
        custom_field.insert(ignore_permissions=True)

@frappe.whitelist()
def init_page():
    setup_custom_fields()
    return {
        "companies": frappe.get_all("Company", pluck="name", order_by="name"),
        "territories": frappe.get_all("Territory", pluck="name", order_by="name")
    }

def get_month_ranges(year, month):
    year = int(year)
    month = int(month)
    months = []
    for m in range(1, month + 1):
        start = get_first_day(f"{year}-{m:02d}-01")
        end = get_last_day(start)
        months.append({
            "start": str(start),
            "end": str(end),
            "label": formatdate(str(start), "MMM"),
            "key": formatdate(str(start), "MMM")
        })
    return months

def get_weeks_of_month(year, month):
    year = int(year)
    month = int(month)
    weeks = []
    month_str = formatdate(f"{year}-{month:02d}-01", "MMM")
    
    weeks.append({
        "start": f"{year}-{month:02d}-01",
        "end": f"{year}-{month:02d}-07",
        "label": f"{month_str} Week 1",
        "key": f"{month_str} Week 1"
    })
    weeks.append({
        "start": f"{year}-{month:02d}-08",
        "end": f"{year}-{month:02d}-14",
        "label": f"{month_str} Week 2",
        "key": f"{month_str} Week 2"
    })
    weeks.append({
        "start": f"{year}-{month:02d}-15",
        "end": f"{year}-{month:02d}-21",
        "label": f"{month_str} Week 3",
        "key": f"{month_str} Week 3"
    })
    end_of_month = str(get_last_day(f"{year}-{month:02d}-01"))
    weeks.append({
        "start": f"{year}-{month:02d}-22",
        "end": end_of_month,
        "label": f"{month_str} Week 4",
        "key": f"{month_str} Week 4"
    })
    return weeks

def get_days_of_week(year, month, week):
    year = int(year)
    month = int(month)
    week = int(week)
    
    if week == 1:
        start_day = 1
        end_day = 7
    elif week == 2:
        start_day = 8
        end_day = 14
    elif week == 3:
        start_day = 15
        end_day = 21
    else:
        start_day = 22
        end_day = get_last_day(f"{year}-{month:02d}-01").day
        
    days = []
    labels = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
    
    for d in range(start_day, end_day + 1):
        date_str = f"{year}-{month:02d}-{d:02d}"
        date_obj = getdate(date_str)
        day_label = f"{labels[date_obj.weekday()]} {d}"
        days.append({
            "start": date_str,
            "end": date_str,
            "label": day_label,
            "key": day_label
        })
    return days

def get_companies_to_query(company):
    children = frappe.get_all("Company", filters={"parent_company": company}, pluck="name")
    if children:
        return [company] + children
    return [company]

@frappe.whitelist()
def get_sales_data(company, territory, year=None, month=None, week=None):
    if not year or not month or not week:
        t = getdate(today())
        year = t.year
        month = t.month
        d = t.day
        week = 4 if d >= 22 else (3 if d >= 15 else (2 if d >= 8 else 1))
        
    companies = get_companies_to_query(company)
    
    # Get Targets from Territory
    targets = []
    if territory:
        target_details = frappe.get_all(
            "Target Detail",
            filters={"parent": territory, "parenttype": "Territory"},
            fields=["item_group", "target_qty", "average_rate", "target_amount"]
        )
        for t in target_details:
            t_qty = flt(t.target_qty)
            avg_rate = flt(t.average_rate)
            t_amount = flt(t.target_amount)
            if t_qty and avg_rate and not t_amount:
                t_amount = t_qty * avg_rate
                
            targets.append({
                "item_group": t.item_group,
                "target_qty": t_qty,
                "average_rate": avg_rate,
                "target_amount": t_amount
            })
            
    months = get_month_ranges(year, month)
    weeks = get_weeks_of_month(year, month)
    days = get_days_of_week(year, month, week)
    
    def fetch_revenue(periods):
        from cannabis_management.cannabis_management.page.weekly_summary.weekly_summary import get_category_for_item_group
        data = {}
        for period in periods:
            rev_data = frappe.db.sql("""
                SELECT
                    COALESCE(i.item_group, 'Other') as item_group,
                    i.name as item_code,
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
            """, (period["start"], period["end"], companies), as_dict=True)
            
            for r in rev_data:
                val = flt(r.val)
                if not val:
                    continue
                ig = r.item_group
                mapped_cat = get_category_for_item_group(ig)
                
                # Attempt to map this sales value to one of the defined targets
                matched_target = None
                for t in targets:
                    t_ig = t["item_group"]
                    if t_ig == ig or t_ig == mapped_cat:
                        matched_target = t_ig
                        break
                    if t_ig.lower() in mapped_cat.lower() or mapped_cat.lower() in t_ig.lower():
                        matched_target = t_ig
                        break
                    if t_ig.lower() in ig.lower():
                        matched_target = t_ig
                        break
                
                if matched_target:
                    if matched_target not in data:
                        data[matched_target] = {}
                    data[matched_target][period["key"]] = data[matched_target].get(period["key"], 0) + val
                    
        return data

    month_data = fetch_revenue(months)
    week_data = fetch_revenue(weeks)
    day_data = fetch_revenue(days)
    
    return {
        "targets": targets,
        "months": months,
        "weeks": weeks,
        "days": days,
        "month_data": month_data,
        "week_data": week_data,
        "day_data": day_data,
        "company": company
    }
