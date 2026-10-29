import frappe
from frappe import _
from frappe.utils import cint, get_url

from cannabis_management.farm_reports.rules import SETTINGS, farm_now

FLC_GROUP = "FLC"

REPORTS = [
	("Farm Daily Report", "farm_reporter", "/farm-daily-report"),
	("Nursery Daily Report", "nursery_reporter", "/nursery-daily-report"),
]


@frappe.whitelist()
def get_flc_suppliers():
	if not frappe.has_permission("Farm Daily Report", "create"):
		frappe.throw(_("You are not permitted to fill out the Farm Daily Report."), frappe.PermissionError)
	return frappe.get_all(
		"Supplier",
		filters={"supplier_group": FLC_GROUP, "disabled": 0},
		fields=["name as value", "supplier_name as label"],
		order_by="supplier_name asc",
	)


def send_reminders():
	settings = frappe.get_single(SETTINGS)
	if not cint(settings.enable_reminders):
		return

	now = farm_now()
	reminder_hour = 15 if settings.reminder_hour in (None, "") else cint(settings.reminder_hour)
	if now.hour != reminder_hour:
		return
	today = now.date()
	if cint(settings.skip_weekends) and today.weekday() >= 5:
		return

	for doctype, owner_field, route in REPORTS:
		user = settings.get(owner_field)
		if not user or not frappe.db.get_value("User", user, "enabled"):
			continue
		sent_key = f"farm_reports:reminder:{doctype}:{today}"
		if frappe.cache.get_value(sent_key):
			continue
		if frappe.db.exists(doctype, {"submitted_by": user, "report_date": today, "docstatus": 1}):
			continue

		link = get_url(route)
		first_name = frappe.db.get_value("User", user, "first_name")
		greeting = _("Hello {0},").format(frappe.utils.escape_html(first_name)) if first_name else _("Hello,")
		frappe.sendmail(
			recipients=[user],
			subject=_("Reminder: today's {0} has not been submitted").format(_(doctype)),
			message=_(
				"<p>{0}</p>"
				"<p>Today's {1} has not been submitted yet.</p>"
				"<p>Please fill it out here: <a href='{2}'>{2}</a></p>"
			).format(greeting, _(doctype), link),
		)
		frappe.cache.set_value(sent_key, 1, expires_in_sec=24 * 60 * 60)
