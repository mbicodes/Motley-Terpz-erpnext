import frappe
from motley_referral.api import portal

BADGE = {'Pending': 'blue', 'Approved': 'blue', 'Paid': 'green', 'Carried Forward': 'purple', 'Submitted': 'grey', 'Under Review': 'amber', 'Acknowledged': 'green', 'Rejected': 'red', 'Expired': 'dark', 'Year 1': 'green', 'Year 2': 'blue', 'Ended': 'dark', 'Awaiting first payment': 'grey'}


def get_context(context):
    context.no_cache = 1
    context.show_sidebar = False
    context.badge = BADGE
    context.update(portal.accounts())
    context.title = "Accounts"
    context.active = "/partner/accounts"
