import frappe


def fix_scheme_for_unproxied_requests():
	request = getattr(frappe.local, "request", None)
	if request is None:
		return

	if frappe.get_request_header("X-Frappe-Site-Name"):
		return

	request.scheme = "http"
	request.environ["wsgi.url_scheme"] = "http"
