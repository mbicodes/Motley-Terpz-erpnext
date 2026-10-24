"""Log desk users out after a stretch with no activity (public/js/idle_logout.js).

The browser tracks activity; the only server part is a readable cookie stamped
at every login, so activity remembered from an earlier login in the same
browser never counts against a fresh one. Desk only: website pages such as the
/timeclock kiosk do not load the script and stay logged in.
"""

import frappe

LOGIN_COOKIE = "idle_login_at"

# Outlives the sid cookie (session_expiry 170h), so it is there whenever the
# session still is.
COOKIE_MAX_AGE = 200 * 60 * 60


def on_session_creation(login_manager):
	if frappe.session.user == "Guest":
		return
	frappe.local.cookie_manager.set_cookie(
		LOGIN_COOKIE, str(int(frappe.utils.now_datetime().timestamp() * 1000)), max_age=COOKIE_MAX_AGE
	)
