"""Serve the kiosk's neutral /kiosk-api/ path from the app itself.

The kiosk page posts to /kiosk-api/<method> rather than to the real
/api/method/cannabis_management.manufacturing_timesheet_kiosk.api.<method>,
because some client-side network filters block any URL containing "cannabis" —
this app's name — which failed every board load and clock in/out even though
the page itself loaded fine.

That alias used to exist only as an nginx `location` block, in a file
`bench setup nginx` regenerates from the bench template. Rebuilding the conf
dropped the block and took the whole kiosk down with it ("Could not load the
board" in place of every card), with nothing in the app to say why. The bench
template has no hook to keep a custom block through a rebuild, so the alias
lives here instead, next to the code that depends on it: Frappe routes /api/
requests off the WSGI environ, so rewriting the path before the request is
dispatched is enough, and no web-server config is involved at all.

The nginx block may still be present, in which case it rewrites first and this
never sees the request. Neither one needs the other.
"""

import re

import frappe

PREFIX = "/kiosk-api/"
KIOSK_API_MODULE = "cannabis_management.manufacturing_timesheet_kiosk.api"

# Bare method names only. The alias addresses one module and nothing else — a
# dotted or slashed name would let it reach any whitelisted method on the site.
METHOD_NAME = re.compile(r"^[a-z_][a-z0-9_]*$")


def route_kiosk_api():
	"""before_request hook: /kiosk-api/<method> -> the real whitelisted path."""
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
	# Both have to move. frappe.api.handle() matches its URL map against the
	# WSGI environ, while frappe.app.application() decides the request is an API
	# call from request.path - a plain attribute werkzeug assigns once in
	# Request.__init__, so it does not follow the environ on its own.
	request.environ["PATH_INFO"] = target
	request.path = target
