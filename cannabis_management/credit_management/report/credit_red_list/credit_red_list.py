import frappe
from cannabis_management.credit_management.reporting import build_red_list


def execute(filters=None):
    columns = [
        {"label": "Customer", "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 220},
        {"label": "Balance", "fieldname": "balance", "fieldtype": "Currency", "width": 120},
        {"label": "Past Due", "fieldname": "past_due", "fieldtype": "Currency", "width": 120},
        {"label": "Days", "fieldname": "days", "fieldtype": "Int", "width": 70},
        {"label": "Hold", "fieldname": "status", "fieldtype": "Data", "width": 110},
        {"label": "Tag", "fieldname": "tag", "fieldtype": "Data", "width": 130},
        {"label": "Promise To Pay", "fieldname": "promise_to_pay", "fieldtype": "Date", "width": 110},
        {"label": "Last Contact", "fieldname": "last_contact", "fieldtype": "Datetime", "width": 150},
        {"label": "Next Action", "fieldname": "next_action", "fieldtype": "Data", "width": 200},
    ]
    return columns, build_red_list()
