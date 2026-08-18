import frappe
from frappe import _

from cannabis_management.manufacturing_portal.access import is_code_session


def get_context(context):
	context.no_cache = 1
	context.title = _("Manufacturing Process")

	# This page is code-only. Being signed in is deliberately NOT enough — an
	# Administrator browsing here still gets the lock screen, because the whole
	# point of the page is that access is granted by the code and recorded.
	#
	# Staff who need the page without a code use the Desk version at
	# /app/manufacturing-process, which is unchanged and permission-gated as normal.
	context.locked = not is_code_session()

	if not context.locked:
		user = frappe.session.user
		context.full_name = frappe.db.get_value("User", user, "full_name") or user

	return context
