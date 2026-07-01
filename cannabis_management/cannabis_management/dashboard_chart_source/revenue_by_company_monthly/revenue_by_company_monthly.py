import frappe
from frappe.utils import getdate, add_months
from calendar import month_abbr

@frappe.whitelist()
def get_data(filters=None):
    today = getdate()
    companies = ["Motley Terpz", "Master Touch Manufacturing", "TSBC Ranch"]

    month_list = []
    for i in range(5, -1, -1):
        d = add_months(today, -i)
        month_list.append((d.year, d.month))

    labels = [f"{month_abbr[m]}" for (y, m) in month_list]

    datasets = []
    for company in companies:
        values = []
        for (year, month_num) in month_list:
            result = frappe.db.sql("""
                SELECT SUM(credit)
                FROM `tabGL Entry`
                WHERE company = %s
                AND MONTH(posting_date) = %s
                AND YEAR(posting_date) = %s
                AND is_cancelled = 0
            """, (company, month_num, year))
            values.append(round(result[0][0] or 0, 2))
        datasets.append({"name": company, "values": values})

    return {
        "labels": labels,
        "datasets": datasets
    }