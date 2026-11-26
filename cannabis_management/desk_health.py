import hashlib
import json
import re

import frappe
from werkzeug.exceptions import NotFound

UNDEFINED_ROUTE = re.compile(r"^/app(/.*)?/undefined/?$")

REPORT_KINDS = {
	"stuck_boot": 5 * 60,
	"startup_error": 6 * 60 * 60,
	"undefined_url": 24 * 60 * 60,
}


def reject_undefined_route():
	request = getattr(frappe.local, "request", None)
	if request is None or request.method != "GET":
		return
	if UNDEFINED_ROUTE.match(request.path or ""):
		raise NotFound()


@frappe.whitelist(methods=["POST"])
def report(kind, details=None):
	if kind not in REPORT_KINDS:
		return {"logged": False}

	if isinstance(details, str):
		try:
			details = json.loads(details)
		except ValueError:
			details = {"raw": details}
	details = details if isinstance(details, dict) else {}

	signature = str(details.get("signature") or "")[:120]
	digest = hashlib.sha1(signature.encode()).hexdigest()[:12] if signature else ""
	key = f"desk_health:{kind}:{frappe.session.user}:{digest}"
	cache = frappe.cache()
	if cache.get_value(key, expires=True):
		return {"logged": False}
	cache.set_value(key, 1, expires_in_sec=REPORT_KINDS[kind])

	details["user"] = frappe.session.user
	try:
		details["user_agent"] = (frappe.get_request_header("User-Agent") or "")[:300]
	except RuntimeError:
		details["user_agent"] = None
	frappe.log_error(
		title=f"Desk health: {kind}"[:140],
		message=json.dumps(details, indent=1, default=str)[:30000],
	)
	return {"logged": True}
