import frappe
from frappe.utils import getdate, add_days, now_datetime, nowdate


NIKKI_EMAIL = "nikki@motleyterpz.com"
MATT_EMAIL  = "matt@motleyterpz.com"
IMRAN_EMAIL = "imran@motleyterpz.com"


def generate_weekly_signoff():
	"""
	Runs every Monday at 8 AM UTC.
	Creates a Weekly Sales Report for the previous Mon-Sun week
	and emails Nikki asking for acknowledgment.
	"""
	today      = getdate(nowdate())
	prev_sun   = add_days(today, -1)              # yesterday = last Sunday (runs on Monday)
	prev_mon   = add_days(prev_sun, -6)            # 6 days before = last Monday
	week_start = str(prev_mon)
	week_end   = str(prev_sun)
	report_name = f"WSR-{week_start}"

	if frappe.db.exists("Weekly Sales Report", report_name):
		return  # already generated

	# compute snapshot numbers
	from cannabis_management.cannabis_management.page.weekly_sales_order.weekly_sales_order import (
		get_week_at_a_glance,
	)
	kpis = get_week_at_a_glance(prev_mon, prev_sun)

	doc = frappe.get_doc({
		"doctype":           "Weekly Sales Report",
		"week_start":        week_start,
		"week_end":          week_end,
		"generated_at":      now_datetime(),
		"total_orders":      kpis["so_count"],
		"total_order_value": kpis["so_value"],
		"total_invoiced":    kpis["invoice_value"],
		"total_collected":   kpis["collected"],
		"total_outstanding": kpis["outstanding_ar"],
	})
	doc.insert(ignore_permissions=True)
	frappe.db.commit()

	_notify_nikki(doc)

	frappe.db.set_value("Weekly Sales Report", report_name, "notification_sent", 1)
	frappe.db.commit()


def send_acknowledgment_reminder():
	"""
	Runs every Tuesday at 8 AM UTC.
	Alerts Matt and Imran if last week's report is still unacknowledged.
	"""
	today      = getdate(nowdate())
	prev_sun   = add_days(today, -2)              # last Sunday
	prev_mon   = add_days(prev_sun, -6)
	report_name = f"WSR-{prev_mon}"

	if not frappe.db.exists("Weekly Sales Report", report_name):
		return

	doc = frappe.get_doc("Weekly Sales Report", report_name)
	if doc.is_acknowledged or doc.reminder_sent:
		return

	subject = f"ACTION REQUIRED — Weekly Sales Report Not Yet Acknowledged ({doc.week_start} to {doc.week_end})"
	message = f"""
		<p><strong>This is an automated alert.</strong></p>
		<p>The weekly sales report for <strong>{doc.week_start} to {doc.week_end}</strong>
		has not been acknowledged by Nikki.</p>
		<ul>
			<li>Total Orders: {doc.total_orders} (${doc.total_order_value:,.0f})</li>
			<li>Invoiced: ${doc.total_invoiced:,.0f}</li>
			<li>Collected: ${doc.total_collected:,.0f}</li>
			<li>Outstanding AR: ${doc.total_outstanding:,.0f}</li>
		</ul>
		<p><a href="/app/weekly-sales-order">Open Weekly Dashboard</a></p>
	"""

	try:
		frappe.sendmail(
			recipients=[MATT_EMAIL, IMRAN_EMAIL],
			subject=subject,
			message=message
		)
	except Exception:
		pass

	frappe.db.set_value("Weekly Sales Report", report_name, "reminder_sent", 1)
	frappe.db.commit()


def _notify_nikki(doc):
	subject = f"Please Acknowledge Weekly Sales Report — {doc.week_start} to {doc.week_end}"
	message = f"""
		<p>Hi Nikki,</p>
		<p>The weekly sales report for <strong>{doc.week_start} to {doc.week_end}</strong>
		is ready for your review and acknowledgment.</p>
		<ul>
			<li>Sales Orders: {doc.total_orders} (${doc.total_order_value:,.0f})</li>
			<li>Invoiced: ${doc.total_invoiced:,.0f}</li>
			<li>Collected: ${doc.total_collected:,.0f}</li>
			<li>Outstanding AR: ${doc.total_outstanding:,.0f}</li>
		</ul>
		<p>Please open the dashboard and click <strong>Acknowledge This Report</strong>
		by end of day.</p>
		<p><a href="/app/weekly-sales-order">Open Weekly Dashboard</a></p>
	"""
	try:
		frappe.sendmail(recipients=[NIKKI_EMAIL], subject=subject, message=message)
	except Exception:
		pass
