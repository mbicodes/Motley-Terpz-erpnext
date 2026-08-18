"""Fix Secure-cookie-over-a-plain-HTTP-tunnel when this site is reached
through something other than this bench's own nginx — e.g. VS Code's port
forwarding hitting gunicorn (port 8000) directly.

Frappe marks the session cookie Secure whenever ``request.scheme`` is
``"https"`` (auth.py ``CookieManager.set_cookie``), and Werkzeug's ProxyFix
(app.py) trusts a single ``X-Forwarded-Proto`` hop to decide that scheme, no
matter how the request actually reached this process. A dev tunnel that
forwards a *plain-HTTP* port can still add its own ``X-Forwarded-Proto:
https`` header (common for HTTP-aware forwarders) — so the browser gets
handed a Secure cookie for a page it loaded over plain ``http://``, and
silently refuses to store it. Every login through that tunnel (the standard
``/login`` page, or the Manufacturing Portal's own code-unlock) then looks
like a fresh Guest on the very next request — the session never actually
persisted.

Distinguishing "real nginx" from "some other forwarder" can't be done from
the Host header — a raw port-forward straight to gunicorn still carries
whatever real site hostname the browser was told to send, same as nginx's
own proxied requests would. What nginx uniquely adds is
``X-Frappe-Site-Name`` (see this app's own nginx config,
``proxy_set_header X-Frappe-Site-Name $site_name_vrubgsm``, on the location
block that fronts every non-static/non-socket.io request) — a header no
generic, Frappe-unaware port-forwarding tool has any reason to replicate.
Its absence is what this checks, not the Host header.

Must run as an early ``before_request`` hook, before any login/cookie code —
see hooks.py.
"""

import frappe


def fix_scheme_for_unproxied_requests():
	request = getattr(frappe.local, "request", None)
	if request is None:
		return

	if frappe.get_request_header("X-Frappe-Site-Name"):
		return  # genuinely came through this bench's own nginx — leave it alone

	# request.scheme is a plain attribute Werkzeug resolves once, at Request
	# construction (werkzeug/sansio/request.py: `self.scheme = scheme`) — not
	# a property that re-reads the environ live. Mutating
	# request.environ["wsgi.url_scheme"] alone has no effect for that reason;
	# the attribute itself has to be reassigned too.
	request.scheme = "http"
	request.environ["wsgi.url_scheme"] = "http"
