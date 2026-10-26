"""after_migrate for the Farm and Nursery Daily Reports. Idempotent.

Masters, settings defaults and the two Notifications are created only when
missing, so anything the client edits in the desk (activities, recipients,
email text, reminder owners) survives a migrate. The two Web Pages are the
exception: they are rebuilt from web/ every migrate, the same way the
fixture-managed Web Pages are, so edit the files and not the desk record.
"""

import os

import frappe

from cannabis_management.farm_reports.api import FLC_GROUP
from cannabis_management.farm_reports.rules import DEFAULT_TIME_ZONE, SETTINGS

WEB_DIR = os.path.join(os.path.dirname(__file__), "web")

SEED_ACTIVITIES = ["Tagging", "Deleafing", "Watering", "Weeding", "Topping"]
EXISTING_FLC_SUPPLIERS = ["ATD Consulting Limited- Sabor"]

SETTINGS_DEFAULTS = {
	"enable_reminders": 1,
	"skip_weekends": 0,
	"time_zone": DEFAULT_TIME_ZONE,
	"reminder_hour": 15,
}

PAGES = [
	# (Web Page name/route, title, config file)
	("farm-daily-report", "Farm Daily Report", "farm_daily_report.config.js"),
	("nursery-daily-report", "Nursery Daily Report", "nursery_daily_report.config.js"),
]

NOTIFICATION_MESSAGE = """<p>The {{ doc.doctype }} for {{ frappe.utils.formatdate(doc.report_date) }} was submitted by {{ frappe.db.get_value("User", doc.submitted_by, "full_name") or doc.submitted_by }}.</p>
<p>The full report is attached as a PDF.</p>
<p><a href="{{ frappe.utils.get_url_to_form(doc.doctype, doc.name) }}">Open {{ doc.name }} in MotleyERP</a></p>
"""


def install():
	ensure_flc_group()
	seed_activities()
	ensure_settings_defaults()
	ensure_notifications()
	sync_web_pages()


def ensure_flc_group():
	if not frappe.db.exists("Supplier Group", FLC_GROUP):
		frappe.get_doc(
			{
				"doctype": "Supplier Group",
				"supplier_group_name": FLC_GROUP,
				"parent_supplier_group": "All Supplier Groups",
				"is_group": 0,
			}
		).insert(ignore_permissions=True)
	# Only suppliers with no group yet; one moved elsewhere on purpose is left alone.
	for supplier in EXISTING_FLC_SUPPLIERS:
		if frappe.db.exists("Supplier", supplier) and not frappe.db.get_value("Supplier", supplier, "supplier_group"):
			frappe.db.set_value("Supplier", supplier, "supplier_group", FLC_GROUP)


def seed_activities():
	for name in SEED_ACTIVITIES:
		if not frappe.db.exists("Farm Activity", name):
			frappe.get_doc({"doctype": "Farm Activity", "activity_name": name}).insert(ignore_permissions=True)


def ensure_settings_defaults():
	current = frappe.db.get_singles_dict(SETTINGS)
	for field, value in SETTINGS_DEFAULTS.items():
		if current.get(field) in (None, ""):
			frappe.db.set_single_value(SETTINGS, field, value)


def ensure_notifications():
	for doctype in ("Farm Daily Report", "Nursery Daily Report"):
		name = f"{doctype} Submitted"
		if frappe.db.exists("Notification", name):
			continue
		notification = frappe.get_doc(
			{
				"doctype": "Notification",
				"name": name,
				# Subject is a 140-character field, Jinja included.
				"subject": doctype + " {{ frappe.utils.formatdate(doc.report_date) }} submitted by "
				"{{ frappe.get_fullname(doc.submitted_by) }}",
				"document_type": doctype,
				"event": "Submit",
				"channel": "Email",
				"enabled": 1,
				"recipients": [{"receiver_by_role": "Daily Report Recipient"}],
				"message_type": "HTML",
				"message": NOTIFICATION_MESSAGE,
				"attach_print": 1,
				"print_format": f"{doctype} Summary",
			}
		)
		notification.insert(ignore_permissions=True, set_name=name)


def read(filename):
	with open(os.path.join(WEB_DIR, filename)) as fh:
		return fh.read()


def build_page(config_file):
	"""(css, html, javascript) for one page."""
	css = read("daily_report.css")
	html = '<div id="dr-app" class="dr-app"></div>'
	javascript = read(config_file) + "\n" + read("daily_report_engine.js")
	return css, html, javascript


def sync_web_pages():
	for route, title, config_file in PAGES:
		css, html, javascript = build_page(config_file)
		values = {
			"title": title,
			"route": route,
			"published": 1,
			"content_type": "HTML",
			"main_section_html": html,
			"css": css,
			"javascript": javascript,
			"full_width": 1,
			"show_title": 0,
			"dynamic_template": 0,
		}
		if frappe.db.exists("Web Page", route):
			page = frappe.get_doc("Web Page", route)
			if all(page.get(k) == v for k, v in values.items()):
				continue
			page.update(values)
			page.save(ignore_permissions=True)
		else:
			page = frappe.get_doc(dict(doctype="Web Page", **values))
			page.insert(ignore_permissions=True, set_name=route)


def build_previews(out_dir):
	"""Standalone HTML files for preview mode (open in a browser, nothing is
	saved). Run from bench console:
	    from cannabis_management.farm_reports.install import build_previews
	    build_previews("/some/dir")
	"""
	os.makedirs(out_dir, exist_ok=True)
	for route, title, config_file in PAGES:
		css, html, javascript = build_page(config_file)
		page = (
			'<!DOCTYPE html>\n<html lang="en">\n<head>\n<meta charset="utf-8">\n'
			'<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">\n'
			f"<title>{title}</title>\n<style>\n{css}\nbody {{ margin: 0; }}\n</style>\n</head>\n<body>\n"
			f"{html}\n<script>\n{javascript}\n</script>\n</body>\n</html>\n"
		)
		with open(os.path.join(out_dir, route.replace("-", "_") + ".html"), "w") as fh:
			fh.write(page)
