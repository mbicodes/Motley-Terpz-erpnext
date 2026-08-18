"""Confine a code-unlocked session to the Manufacturing Process page.

Runs as a ``before_request`` hook. Frappe builds ``HTTPRequest()`` (which establishes
the session) immediately before running these hooks, so ``frappe.session`` is
populated by the time this executes.

Sessions opened normally — someone who actually signed in with a password — are not
touched. Only sessions carrying the ``mfg_portal_only`` flag are restricted.

WHAT THIS DOES AND DOES NOT BUY YOU
-----------------------------------
It blocks *routes*: /app, other portal pages, arbitrary REST endpoints. That stops
someone who learns a code from wandering the Desk UI, which is the realistic risk.

It does NOT reduce the underlying account's permissions. The allowlist has to include
``frappe.client.insert`` and ``frappe.client.submit`` because the page's own dialogs
create Material Requests, Work Orders, Job Cards and Stock Entries through them. A
determined person with a code and a browser console could therefore still insert or
submit any doctype that user is permitted to touch. Genuinely limiting that means
giving code holders a low-privilege role, not tightening this list.

The allowlist below was derived from every server call the page makes. If a legitimate
feature breaks, the denial is recorded as a "Blocked Route" row in Process Access Log —
read that log to find what needs adding rather than guessing.
"""

import frappe
from frappe import _
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect as werkzeug_redirect

from cannabis_management.manufacturing_portal.access import (
	PORTAL_ROUTE,
	is_code_session,
	log_attempt,
)


class PortalRedirect(HTTPException):
	"""A redirect that actually works from a before_request hook.

	``frappe.Redirect`` is only honoured by the website rendering layer
	(website/serve.py), which runs *after* before_request — raising it here produces
	a bare 301 with no Location header, which browsers treat as an error.

	app.py returns any werkzeug HTTPException straight back as the response
	(``except HTTPException as e: return e``), so this one carries a real Location.
	302 rather than 301: the target is a permission decision that can change, and it
	must never be cached by the browser.
	"""

	code = 302

	def __init__(self, location):
		super().__init__()
		self.location = location

	def get_response(self, environ=None, scope=None):
		return werkzeug_redirect(self.location, self.code)

# Static assets, uploaded files, and the realtime socket.
ALLOWED_PATH_PREFIXES = (
	"/assets/",
	"/files/",
	"/private/files/",
	"/socket.io/",
)

ALLOWED_EXACT_PATHS = {
	PORTAL_ROUTE,
	"/login",
	"/logout",
	"/favicon.ico",
	"/robots.txt",
	# Loaded by every website page's base template (templates/web.html), code
	# session or not — blocking it just replaces a harmless static request with
	# a redirect that the browser tries (and fails) to execute as JS.
	"/website_script.js",
}

# Exact whitelisted methods this page needs.
ALLOWED_METHODS = {
	# Work Order / Material Request creation, called by the page's dialogs.
	"cannabis_management.api.manufacturing.create_work_orders_from_mr",
	"erpnext.manufacturing.doctype.work_order.work_order.make_job_card",
	"erpnext.manufacturing.doctype.work_order.work_order.make_stock_entry",
	"erpnext.stock.doctype.material_request.material_request.raise_work_orders",
	# Generic document access. Permission-checked server-side against the signed-in
	# user's own roles — see the caveat in this module's docstring.
	"frappe.client.get",
	"frappe.client.get_list",
	"frappe.client.get_value",
	"frappe.client.get_count",
	"frappe.client.insert",
	"frappe.client.submit",
	"frappe.client.validate_link",
	# Form-control framework: Link autocomplete and grid/doctype metadata.
	"frappe.desk.search.search_link",
	"frappe.desk.search.search_widget",
	"frappe.desk.form.load.getdoctype",
	"frappe.desk.form.load.getdoc",
	"frappe.desk.reportview.get",
	"frappe.desk.reportview.get_count",
	# Session teardown.
	"logout",
}

ALLOWED_METHOD_PREFIXES = (
	"cannabis_management.api.manufacturing_process.",
	"cannabis_management.manufacturing_portal.access.",
)

_API_PREFIX = "/api/method/"

# Denials are logged, but a redirect loop or a polling widget could otherwise write
# thousands of identical rows. Log each (session, path) at most once every 10 min.
_DENIAL_LOG_TTL = 600


def guard():
	if not is_code_session():
		return

	request = getattr(frappe.local, "request", None)
	if request is None:
		return

	path = _normalise(request.path)
	if _is_allowed(path):
		return

	_deny(path)


def _normalise(path):
	path = path or "/"
	if len(path) > 1 and path.endswith("/"):
		path = path.rstrip("/")
	return path or "/"


def _is_allowed(path):
	if path in ALLOWED_EXACT_PATHS:
		return True

	# The page's colocated assets are served from the page's own route.
	if path in (PORTAL_ROUTE + ".js", PORTAL_ROUTE + ".css"):
		return True

	if path.startswith(ALLOWED_PATH_PREFIXES):
		return True

	if path.startswith(_API_PREFIX):
		method = path[len(_API_PREFIX) :]
		return _is_allowed_method(method)

	# Legacy RPC dispatch: frappe.call()/xcall() on a WEBSITE page — which is
	# what this portal's own scripts use, since website.js's frappe.call is a
	# different (lighter) implementation than Desk's — POSTs to "/" with the
	# method name in the `cmd` form field instead of hitting
	# /api/method/<method>. Frappe core still honours this on the server side
	# (app.py: `elif frappe.form_dict.cmd`, deprecated but functional), so
	# without this branch every authenticated call this page's own JS makes —
	# Sign out, loading/saving the timer — would silently get redirected right
	# back to this page by the check below instead of ever running.
	if path == "/":
		cmd = frappe.form_dict.get("cmd")
		if cmd and _is_allowed_method(cmd):
			return True

	return False


def _is_allowed_method(method):
	if method in ALLOWED_METHODS:
		return True
	return method.startswith(ALLOWED_METHOD_PREFIXES)


def _log_denial_once(path):
	key = f"mfg_portal_denied:{frappe.session.sid}:{path}"
	# expires=True — see the note in access._failure_count.
	if frappe.cache().get_value(key, expires=True):
		return
	frappe.cache().set_value(key, 1, expires_in_sec=_DENIAL_LOG_TTL)
	log_attempt("Blocked Route", user=frappe.session.user, reason=path[:140])


def _deny(path):
	_log_denial_once(path)

	if path.startswith("/api/"):
		frappe.throw(
			_("This session can only be used for the Manufacturing Process page."),
			frappe.PermissionError,
		)

	# A browser navigation: send them back to the page rather than showing a raw
	# permission error.
	raise PortalRedirect(PORTAL_ROUTE)
