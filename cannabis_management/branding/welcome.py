import frappe

COOKIE = "mlt_welcome"
SPLASH_CSS = "/assets/cannabis_management/css/mlt_splash.css?v=1"


def add_welcome_splash(context):
	if "boot" not in context or "include_css" not in context:
		return None

	request = getattr(frappe.local, "request", None)
	if request is None or not request.cookies.get(COOKIE):
		return None

	include_css = list(context.get("include_css") or [])
	if SPLASH_CSS not in include_css:
		include_css.append(SPLASH_CSS)
	return {"include_css": include_css}
