"""Red List (§13) — every past-due account, and what is being done about it.

Three kinds of row, flagged in the Status column:

* **HOLD** — a warning or a stop-work case
* **PLAN** — on an approved payment plan, shown until the plan retires
* **WORKOUT** — prepaid-only, with starting balance and recovery to date

The Plan Book totals sit in the report message: total balance under plan, and
plan payments due versus received this week.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_first_day, getdate, nowdate

from cannabis_management.credit_and_ar import utils
from cannabis_management.credit_and_ar.report import report_utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import INACTIVE_STATUSES

STATUS_HOLD = "HOLD"
STATUS_PLAN = "PLAN"
STATUS_WORKOUT = "WORKOUT"
STATUS_PAST_DUE = "PAST DUE"


def execute(filters=None):
	filters = frappe._dict(filters or {})
	data = get_data(filters)
	return get_columns(), data, get_message(data, filters), get_chart(data)


def get_data(filters):
	excluded = set(report_utils.excluded_customers())
	ar = report_utils.ar_by_customer(company=filters.get("company"))

	cases = _live_cases()
	rows = []

	# Every customer with a live case, plus anyone past due without one yet.
	customers = set(cases) | {
		name for name, bucket in ar.items() if flt(bucket.get("past_due")) > 0
	}
	customers -= excluded

	if filters.get("customer"):
		customers &= {filters["customer"]}

	for customer in sorted(customers):
		bucket = ar.get(customer, {})
		case = cases.get(customer)

		status = STATUS_PAST_DUE
		if case:
			if case["case_type"] in ("Hard Hold", "Immediate Hold", "Warning"):
				status = STATUS_HOLD
			elif case["case_type"] == "Payment Plan":
				status = STATUS_PLAN
			elif case["case_type"] == "Workout":
				status = STATUS_WORKOUT

		if filters.get("status") and filters["status"] != status:
			continue

		rows.append(
			{
				"customer": customer,
				"status": status,
				"case_type": case["case_type"] if case else None,
				"balance": flt(bucket.get("outstanding")),
				"past_due": flt(bucket.get("past_due")),
				"max_days": bucket.get("max_days") or 0,
				"legacy_balance": flt(bucket.get("legacy")),
				"promise_to_pay_date": case.get("promise_to_pay_date") if case else None,
				"promise_to_pay_amount": case.get("promise_to_pay_amount") if case else None,
				"last_contact_date": case.get("last_contact_date") if case else None,
				"next_action": case.get("next_action") if case else None,
				"next_action_date": case.get("next_action_date") if case else None,
				"assigned_to": case.get("assigned_to") if case else None,
				"starting_balance": case.get("starting_balance") if case else None,
				"recovered_to_date": case.get("recovered_to_date") if case else None,
				"missed_installments": case.get("missed_installments") if case else None,
				"ar_case": case["name"] if case else None,
			}
		)

	rows.sort(key=lambda row: (-row["past_due"], -row["max_days"]))
	return rows


def _live_cases() -> dict:
	"""The strongest live case per customer, with its collections detail."""
	cases = frappe.get_all(
		"AR Case",
		filters={"status": ("not in", INACTIVE_STATUSES), "show_on_red_list": 1},
		fields=[
			"name",
			"customer",
			"case_type",
			"status",
			"promise_to_pay_date",
			"promise_to_pay_amount",
			"last_contact_date",
			"next_action",
			"next_action_date",
			"assigned_to",
			"starting_balance",
			"recovered_to_date",
			"missed_installments",
			"opened_on",
		],
		order_by="opened_on asc",
	)

	priority = {
		"Warning": 1,
		"Payment Plan": 2,
		"Workout": 3,
		"Hard Hold": 4,
		"Immediate Hold": 5,
	}

	best: dict[str, dict] = {}
	for case in cases:
		current = best.get(case.customer)
		if not current or priority.get(case.case_type, 0) > priority.get(current["case_type"], 0):
			best[case.customer] = case
	return best


def get_message(data, filters):
	"""The Plan Book: what is under plan, and what is due versus received."""
	if not data:
		return _("Nothing past due and no live cases. The Red List is empty.")

	total_past_due = sum(row["past_due"] for row in data)
	holds = len([row for row in data if row["status"] == STATUS_HOLD])
	plans = [row for row in data if row["status"] == STATUS_PLAN]
	workouts = [row for row in data if row["status"] == STATUS_WORKOUT]

	plan_balance = sum(row["balance"] for row in plans)
	due, received = _plan_week()

	parts = [
		_("<b>{0}</b> account(s) · past due <b>{1}</b>").format(
			len(data), utils.fmt_currency(total_past_due)
		),
		_("<b>{0}</b> on hold").format(holds),
	]

	if plans:
		parts.append(
			_(
				"<b>Plan Book:</b> {0} plan(s), balance <b>{1}</b>, due this week {2}, "
				"received {3}"
			).format(
				len(plans),
				utils.fmt_currency(plan_balance),
				utils.fmt_currency(due),
				utils.fmt_currency(received),
			)
		)

	if workouts:
		recovered = sum(flt(row["recovered_to_date"]) for row in workouts)
		parts.append(
			_("<b>{0}</b> workout(s), recovered to date <b>{1}</b>").format(
				len(workouts), utils.fmt_currency(recovered)
			)
		)

	return " &nbsp;·&nbsp; ".join(parts)


def _plan_week():
	"""Installments due this week, and what has actually come in against them."""
	today = getdate(nowdate())
	week_start = add_days(today, -today.weekday())
	week_end = add_days(week_start, 6)

	rows = frappe.db.sql(
		"""
		SELECT i.amount, i.paid_amount
		FROM `tabAR Case Installment` i
		JOIN `tabAR Case` c ON c.name = i.parent
		WHERE c.case_type = 'Payment Plan'
		  AND c.status NOT IN %(inactive)s
		  AND i.due_date BETWEEN %(start)s AND %(end)s
		""",
		{"inactive": INACTIVE_STATUSES, "start": week_start, "end": week_end},
		as_dict=True,
	)

	due = flt(sum(flt(row.amount) for row in rows))
	received = flt(sum(flt(row.paid_amount) for row in rows))
	return due, received


def get_chart(data):
	if not data:
		return None

	buckets = {"1-30": 0.0, "31-60": 0.0, "61-90": 0.0, "90+": 0.0}
	for row in data:
		days = row["max_days"]
		if days <= 0:
			continue
		key = "1-30" if days <= 30 else "31-60" if days <= 60 else "61-90" if days <= 90 else "90+"
		buckets[key] += row["past_due"]

	return {
		"data": {
			"labels": list(buckets),
			"datasets": [{"name": _("Past Due"), "values": list(buckets.values())}],
		},
		"type": "bar",
		"colors": ["#f59e0b", "#f97316", "#ef4444", "#991b1b"],
	}


def get_columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link",
		 "options": "Customer", "width": 200},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 100},
		{"label": _("Case Type"), "fieldname": "case_type", "fieldtype": "Data", "width": 130},
		{"label": _("Balance"), "fieldname": "balance", "fieldtype": "Currency", "width": 130},
		{"label": _("Past Due"), "fieldname": "past_due", "fieldtype": "Currency", "width": 130},
		{"label": _("Max Days"), "fieldname": "max_days", "fieldtype": "Int", "width": 100},
		{"label": _("Legacy Portion"), "fieldname": "legacy_balance", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("PTP Date"), "fieldname": "promise_to_pay_date", "fieldtype": "Date",
		 "width": 110},
		{"label": _("PTP Amount"), "fieldname": "promise_to_pay_amount", "fieldtype": "Currency",
		 "width": 120},
		{"label": _("Last Contact"), "fieldname": "last_contact_date", "fieldtype": "Date",
		 "width": 120},
		{"label": _("Next Action"), "fieldname": "next_action", "fieldtype": "Data", "width": 180},
		{"label": _("Next Action Date"), "fieldname": "next_action_date", "fieldtype": "Date",
		 "width": 140},
		{"label": _("Assigned To"), "fieldname": "assigned_to", "fieldtype": "Link",
		 "options": "User", "width": 160},
		{"label": _("Missed Installments"), "fieldname": "missed_installments", "fieldtype": "Int",
		 "width": 150},
		{"label": _("Workout Start"), "fieldname": "starting_balance", "fieldtype": "Currency",
		 "width": 130},
		{"label": _("Recovered"), "fieldname": "recovered_to_date", "fieldtype": "Currency",
		 "width": 120},
		{"label": _("AR Case"), "fieldname": "ar_case", "fieldtype": "Link",
		 "options": "AR Case", "width": 150},
	]
