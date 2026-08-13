"""The notification matrix (§17).

Most rows are already emailed directly by the engine that raises them, because
they carry computed context an alert cannot express — exposure, available line,
score, the release basis. Those are listed below for the record.

What is left are **in-desk alerts** that are better as native `Notification`
records: they appear in the notification bell, respect each user's preferences,
and can be edited without a deploy.
"""

import frappe

# Handled in code, with computed context — do not duplicate as Notifications.
CODE_HANDLED = {
	"Terms Sales Order submitted for approval": "credit_and_ar.api._email_approval_request",
	"Terms Sales Order approved / rejected": "credit_and_ar.api._email_decision",
	"Credit Application approved": "credit_application._notify_approved",
	"Credit Application rejected": "credit_application._notify_rejected",
	"Credit line revoked / expired": "credit_application._notify_revoked",
	"Warning / Hard Hold / Immediate Hold raised": "hold_engine._notify_case",
	"Hold released": "hold_engine._notify_release",
	"MD exception used on release": "hold_engine._log_md_exception",
	"License expiring T-30 / T-7": "hold_engine._notify_license_expiry",
	"Plan installment missed": "plan_workout._notify_missed_installment",
	"Workout rising / no-shrink / review": "plan_workout._notify_workout",
	"Company freeze triggered": "metrics._notify_freeze",
	"Company freeze lifted": "metrics._lift_freeze",
	"Freeze eligible for unfreeze": "metrics._flag_eligible_for_unfreeze",
	"Finance charges assessed": "finance_charge._notify",
	"Friday report": "weekly_report.send_weekly_report",
}


NOTIFICATIONS = [
	{
		"name": "Credit Application Received",
		"document_type": "Credit Application",
		"event": "New",
		"condition": "doc.workflow_state == 'Submit for Review'",
		"subject": "New credit application received — {{ doc.exact_legal_buyer or doc.customer or doc.name }}",
		"message": (
			"<p>A new credit application has been received"
			"{% if doc.exact_legal_buyer %} from <b>{{ doc.exact_legal_buyer }}</b>{% endif %} "
			"and is sitting in <b>Submit for Review</b>.</p>"
			"<p>Requested limit <b>{{ frappe.utils.fmt_money(doc.requested_limit, currency='USD') }}</b>.</p>"
		),
		"recipients": [{"receiver_by_role": "Accounts Manager"}],
		"send_system_notification": 1,
		"send_email": 1,
	},
	{
		"name": "Credit Application Pending MD Approval",
		"document_type": "Credit Application",
		"event": "Value Change",
		"value_changed": "workflow_state",
		"condition": "doc.workflow_state == 'Pending MD Approval'",
		"subject": "Credit application for {{ doc.customer }} needs your approval",
		"message": (
			"<p><b>{{ doc.customer }}</b> is waiting on Managing Director approval.</p>"
			"<p>Recommended limit <b>{{ frappe.utils.fmt_money(doc.recommended_limit, currency='USD') }}</b> "
			"on <b>{{ doc.recommended_terms }}</b>, recommended by {{ doc.finance_recommended_by }}.</p>"
			"<p>Group exposure already standing: "
			"<b>{{ frappe.utils.fmt_money(doc.group_existing_exposure, currency='USD') }}</b>.</p>"
		),
		"recipients": [{"receiver_by_role": "Managing Director"}],
		"send_system_notification": 1,
		"send_email": 1,
	},
	{
		"name": "Credit Application Submitted for Finance Review",
		"document_type": "Credit Application",
		"event": "Value Change",
		"value_changed": "workflow_state",
		"condition": "doc.workflow_state == 'Finance Review'",
		"subject": "New credit application for {{ doc.customer }}",
		"message": (
			"<p>A credit application for <b>{{ doc.customer }}</b> has been submitted for "
			"Finance review.</p><p>Requested limit "
			"<b>{{ frappe.utils.fmt_money(doc.requested_limit, currency='USD') }}</b>.</p>"
		),
		"recipients": [{"receiver_by_role": "Credit Finance"}],
		"send_system_notification": 1,
		"send_email": 0,
	},
	{
		"name": "AR Case Opened",
		"document_type": "AR Case",
		"event": "New",
		"condition": "doc.case_type in ('Warning', 'Hard Hold', 'Immediate Hold')",
		"subject": "{{ doc.case_type }} — {{ doc.customer }}",
		"message": (
			"<p><b>{{ doc.customer }}</b> is on <b>{{ doc.case_type }}</b>.</p>"
			"<p>{{ doc.trigger_reason }} — {{ doc.trigger_details }}</p>"
			"<p>Past due <b>{{ frappe.utils.fmt_money(doc.past_due_amount, currency='USD') }}</b>, "
			"oldest invoice {{ doc.max_days_past_due }} days overdue.</p>"
		),
		"recipients": [
			{"receiver_by_role": "Credit Finance"},
			{"receiver_by_role": "Collections Officer"},
		],
		"send_system_notification": 1,
		"send_email": 0,
	},
	{
		"name": "AR Case Promise to Pay Due Today",
		"document_type": "AR Case",
		"event": "Days Before",
		"date_changed": "promise_to_pay_date",
		"days_in_advance": 1,
		"condition": "doc.status in ('Open', 'Active')",
		"subject": "Promise to pay due tomorrow — {{ doc.customer }}",
		"message": (
			"<p><b>{{ doc.customer }}</b> promised "
			"<b>{{ frappe.utils.fmt_money(doc.promise_to_pay_amount, currency='USD') }}</b> "
			"by {{ doc.promise_to_pay_date }}.</p>"
			"<p>A promise that passes without payment becomes an immediate hold.</p>"
		),
		"recipients": [
			{"receiver_by_document_field": "assigned_to"},
			{"receiver_by_role": "Credit Finance"},
		],
		"send_system_notification": 1,
		"send_email": 1,
	},
	{
		"name": "AR Case Workout Review Due",
		"document_type": "AR Case",
		"event": "Days Before",
		"date_changed": "next_review_date",
		"days_in_advance": 3,
		"condition": "doc.case_type == 'Workout' and doc.status in ('Open', 'Active')",
		"subject": "Workout review due — {{ doc.customer }}",
		"message": (
			"<p>Workout review for <b>{{ doc.customer }}</b> is due "
			"{{ doc.next_review_date }}.</p>"
			"<p>Started at {{ frappe.utils.fmt_money(doc.starting_balance, currency='USD') }}, "
			"now {{ frappe.utils.fmt_money(doc.current_balance, currency='USD') }} "
			"({{ doc.balance_trend or 'trend not yet established' }}).</p>"
		),
		"recipients": [{"receiver_by_role": "Managing Director"}],
		"send_system_notification": 1,
		"send_email": 1,
	},
]


def install_notifications():
	for spec in NOTIFICATIONS:
		if frappe.db.exists("Notification", spec["name"]):
			continue

		recipients = spec.pop("recipients", [])
		doc = frappe.get_doc(
			{
				"doctype": "Notification",
				"enabled": 1,
				"channel": "Email",
				"module": "Credit and AR",
				**spec,
			}
		)
		for recipient in recipients:
			doc.append("recipients", recipient)

		doc.flags.ignore_permissions = True
		doc.insert(ignore_permissions=True)
		spec["recipients"] = recipients
