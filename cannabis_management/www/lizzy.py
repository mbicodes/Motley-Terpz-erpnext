import frappe

def get_context(context):
    context.no_cache = 1
    context.title = "Lizzy's Dashboard"

    if frappe.session.user == "Guest":
        frappe.throw("Not permitted", frappe.PermissionError)