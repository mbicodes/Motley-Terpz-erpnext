import re

import frappe

PREFIX = "/kiosk-api/"
KIOSK_API_MODULE = "cannabis_management.manufacturing_timesheet_kiosk.api"

METHOD_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def route_kiosk_api():
	request = getattr(frappe.local, "request", None)
	if request is None:
		return

	path = request.environ.get("PATH_INFO") or ""
	if not path.startswith(PREFIX):
		return

	method = path[len(PREFIX) :].strip("/")
	if not METHOD_NAME.match(method):
		return

	target = f"/api/method/{KIOSK_API_MODULE}.{method}"
	request.environ["PATH_INFO"] = target
	request.path = target
