import frappe
from frappe import _


def get_context(context):
	context.no_cache = 1
	context.title = _("Preorder Entry")

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/preorder"
		raise frappe.Redirect

	context.full_name = (
		frappe.db.get_value("User", frappe.session.user, "full_name")
		or frappe.session.user
	)

	companies = frappe.get_all("Company", fields=["name"], limit_page_length=20)
	context.companies = companies

	return context
