import frappe

LOGIN_COOKIE = "idle_login_at"

COOKIE_MAX_AGE = 200 * 60 * 60


def on_session_creation(login_manager):
	if frappe.session.user == "Guest":
		return
	frappe.local.cookie_manager.set_cookie(
		LOGIN_COOKIE, str(int(frappe.utils.now_datetime().timestamp() * 1000)), max_age=COOKIE_MAX_AGE
	)
