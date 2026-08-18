"""Code-based access to the Manufacturing Process portal page.

A worker types a code at /manufacturing-process. If it matches exactly one enabled
user, that user is logged in for real (``login_manager.login_as``) so every existing
whitelisted endpoint keeps enforcing *their* permissions — no parallel permission
system is invented here.

The resulting session is marked ``mfg_portal_only``. ``session_guard`` CAN confine
that session to this page alone, but that confinement is currently switched off
(hooks.py's ``before_request`` entry for it is commented out) — by request, so a
code holder can also use the rest of the ERP without signing out of the portal
first. See session_guard's own module docstring for the trade-off and how to
switch it back on.

Threat model, stated plainly: a short code typed on a shop floor is a low-value
credential. Hashing it would not meaningfully help — the keyspace is small enough to
enumerate offline regardless. What actually protects it is enforced uniqueness, a
per-IP failure budget with lockout, and the fact that every attempt (success or
failure) is written to Process Access Log.
"""

import frappe
from frappe import _
from frappe.utils import cint, now_datetime

SESSION_FLAG = "mfg_portal_only"
PORTAL_ROUTE = "/manufacturing-process"

# Per-IP failure budget. A sliding window: each failure re-arms the TTL, so a
# patient attacker stays locked out rather than draining the window.
MAX_FAILURES = 5
FAILURE_WINDOW_SECONDS = 15 * 60


# ---------------------------------------------------------------------------
# request helpers
# ---------------------------------------------------------------------------


def _request_context():
	ip = getattr(frappe.local, "request_ip", None)
	try:
		agent = frappe.get_request_header("User-Agent") or ""
	except Exception:
		agent = ""
	return ip, agent[:500]


def _failure_key(ip):
	return f"mfg_portal_failures:{ip or 'unknown'}"


def _failure_count(ip):
	# expires=True is required, not optional: set_value(expires_in_sec=...) never
	# populates frappe.local.cache, while a plain get_value memoises its miss there.
	# Without this flag the counter reads a stale None for the life of the process.
	return cint(frappe.cache().get_value(_failure_key(ip), expires=True))


def _record_failure(ip):
	count = _failure_count(ip) + 1
	frappe.cache().set_value(_failure_key(ip), count, expires_in_sec=FAILURE_WINDOW_SECONDS)
	return count


def _clear_failures(ip):
	frappe.cache().delete_value(_failure_key(ip))


def is_locked_out(ip):
	return _failure_count(ip) >= MAX_FAILURES


# ---------------------------------------------------------------------------
# audit log
# ---------------------------------------------------------------------------


def log_attempt(result, user=None, reason=None):
	"""Write one Process Access Log row.

	Never allowed to break the request it is auditing: a logging failure must not
	hand an attacker a way to suppress the audit trail by breaking the insert, nor
	lock a legitimate worker out of the page.
	"""
	ip, agent = _request_context()
	try:
		doc = frappe.new_doc("Process Access Log")
		doc.timestamp = now_datetime()
		doc.result = result
		doc.user = user
		doc.user_full_name = (
			frappe.db.get_value("User", user, "full_name") if user else None
		)
		doc.ip_address = ip
		doc.reason = reason
		doc.user_agent = agent
		doc.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(
			title="Manufacturing Portal: access log write failed",
			message=frappe.get_traceback(),
		)


# ---------------------------------------------------------------------------
# code matching
# ---------------------------------------------------------------------------


def match_code(code):
	"""Return the single enabled user holding this code, or None.

	Uniqueness is enforced on the User form, so this can only ever match one row.
	Note the comparison is case-insensitive: MySQL's default collation makes it so,
	which is why the uniqueness check on User is case-insensitive too.
	"""
	if not code:
		return None

	return frappe.db.get_value(
		"User",
		{
			"custom_process_code": code,
			"custom_process_code_enabled": 1,
			"enabled": 1,
		},
		"name",
	)


# ---------------------------------------------------------------------------
# session state
# ---------------------------------------------------------------------------


def is_code_session():
	"""True when the current session was opened with a portal code."""
	session = getattr(frappe.local, "session", None)
	if not session:
		return False
	return bool((session.get("data") or {}).get(SESSION_FLAG))


PREVIOUS_USER_KEY = "mfg_portal_previous_user"


def _mark_session_restricted():
	frappe.local.session.data[SESSION_FLAG] = 1
	# Force the write: Frappe only flushes session data to the Sessions table every
	# 10 minutes otherwise, and the guard must see this flag on the very next
	# request.
	frappe.local.session_obj.update(force=True)
	frappe.db.commit()


def _clear_session_restricted():
	"""Drop the portal markers without touching the underlying login.

	Used by lock() when the current session's real identity has nothing to
	restore and nothing to log out of — the session itself stays exactly as
	valid as it was.
	"""
	data = frappe.local.session.data
	data.pop(SESSION_FLAG, None)
	data.pop(PREVIOUS_USER_KEY, None)
	frappe.local.session_obj.update(force=True)
	frappe.db.commit()


# ---------------------------------------------------------------------------
# endpoints
# ---------------------------------------------------------------------------


@frappe.whitelist(allow_guest=True)
def unlock(code=None):
	"""Exchange a portal code for a restricted session.

	Guest-accessible by necessity — the caller has no session yet. Every path
	through this function writes an audit row.
	"""
	ip, _agent = _request_context()

	# If this browser already has a real Desk login, remember it — login_as()
	# below replaces the session outright (cookie-based sessions are one per
	# browser, not one per tab), so without this the person would just be
	# dropped as Guest once they hit Sign out. Restoring it there instead
	# means unlocking a code never has to feel like being logged out of your
	# own account, without ever blocking the unlock itself.
	previous_user = frappe.session.user
	if previous_user in (None, "Guest") or is_code_session():
		previous_user = None

	if is_locked_out(ip):
		log_attempt("Locked Out", reason=f"{_failure_count(ip)} failures from this address")
		frappe.throw(
			_("Too many incorrect codes from this device. Try again in 15 minutes."),
			frappe.AuthenticationError,
			title=_("Temporarily Locked"),
		)

	code = (code or "").strip()
	if not code:
		frappe.throw(_("Enter your code."), frappe.AuthenticationError)

	user = match_code(code)

	if not user:
		count = _record_failure(ip)
		log_attempt("Failed", reason=f"unrecognised code (attempt {count} of {MAX_FAILURES})")
		remaining = MAX_FAILURES - count
		if remaining <= 0:
			frappe.throw(
				_("Too many incorrect codes from this device. Try again in 15 minutes."),
				frappe.AuthenticationError,
				title=_("Temporarily Locked"),
			)
		# Deliberately generic: never reveal whether a code exists but is disabled.
		frappe.throw(
			_("That code was not recognised. {0} attempt(s) left.").format(remaining),
			frappe.AuthenticationError,
		)

	_clear_failures(ip)

	frappe.local.login_manager.login_as(user)
	_mark_session_restricted()
	if previous_user:
		# login_as() just built a brand new session — stash the note in *that*
		# one so lock() can find it later.
		frappe.local.session.data[PREVIOUS_USER_KEY] = previous_user
		frappe.local.session_obj.update(force=True)
	log_attempt(
		"Success", user=user,
		reason=f"was signed in as {previous_user}" if previous_user else None,
	)

	return {
		"ok": True,
		"user": user,
		"full_name": frappe.db.get_value("User", user, "full_name") or user,
		"redirect": PORTAL_ROUTE,
	}


@frappe.whitelist()
def lock():
	"""End a code session (the page's Sign out button).

	Returns to whichever real Desk login this browser had before the code was
	entered (see unlock's ``previous_user``), rather than always dropping to
	Guest — unlocking a code never has to end with someone stranded logged out
	of their own ERP account. And when the code just belonged to the account
	that was already logged in here (e.g. testing your own code), there is
	nothing to restore either: signing out must only drop back to the Access
	Code screen, never tear down a real ERP session that has nothing to do
	with the code — including in every other tab this browser is signed into.
	"""
	user = frappe.session.user
	previous_user = None
	if is_code_session():
		session = getattr(frappe.local, "session", None)
		previous_user = (session.get("data") or {}).get(PREVIOUS_USER_KEY) if session else None
		log_attempt("Success", user=user, reason="signed out")

	if previous_user and previous_user == user:
		_clear_session_restricted()
	elif (
		previous_user
		and frappe.db.get_value("User", previous_user, "enabled")
	):
		frappe.local.login_manager.login_as(previous_user)
	else:
		frappe.local.login_manager.logout()
	frappe.db.commit()
	return {"ok": True, "redirect": PORTAL_ROUTE}


@frappe.whitelist()
def whoami():
	"""Small helper the page uses to render the header and confirm session state."""
	return {
		"user": frappe.session.user,
		"full_name": frappe.db.get_value("User", frappe.session.user, "full_name")
		or frappe.session.user,
		"code_session": is_code_session(),
	}
