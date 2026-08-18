import frappe
from frappe import _

from cannabis_management.time_clock.api import TIME_CLOCK_ROLE, can_manage_notes


def get_context(context):
	context.no_cache = 1
	context.title = _("Time Clock")

	if frappe.session.user == "Guest":
		# Bounce to login rather than throwing — this page is meant to be opened
		# cold from a phone bookmark.
		frappe.local.flags.redirect_location = "/login?redirect-to=/timeclock"
		raise frappe.Redirect

	roles = frappe.get_roles(frappe.session.user)
	context.has_clock_access = TIME_CLOCK_ROLE in roles
	context.clock_role = TIME_CLOCK_ROLE
	context.can_manage_notes = can_manage_notes(frappe.session.user)
	context.full_name = frappe.db.get_value("User", frappe.session.user, "full_name") or frappe.session.user

	return context
