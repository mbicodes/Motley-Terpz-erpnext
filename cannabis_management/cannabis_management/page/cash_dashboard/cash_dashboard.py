import frappe
from frappe import _

# Thin wrapper — delegates to the writable API module so root-owned file
# can be replaced without losing the page route.
from cannabis_management.api.nikki_cash_dashboard import (
    get_nikki_ledger_summary,
    get_dashboard_data,
    _month_sort_key,
)

# Re-export so the page route continues to work after copy
get_nikki_ledger_summary = get_nikki_ledger_summary
get_dashboard_data = get_dashboard_data
