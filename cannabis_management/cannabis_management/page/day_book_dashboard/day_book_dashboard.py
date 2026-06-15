import frappe
from frappe.utils import today
from cannabis_management.cannabis_management.report.day_book_f2.day_book_f2 import execute

@frappe.whitelist()
def get_day_book_data(from_date=None, to_date=None, company=None, account=None):
    if not from_date:
        from_date = today()
    if not to_date:
        to_date = today()

    filters = {
        "from_date": from_date,
        "to_date": to_date,
        "company": company,
        "account": account
    }

    columns, data = execute(filters)
    return data
