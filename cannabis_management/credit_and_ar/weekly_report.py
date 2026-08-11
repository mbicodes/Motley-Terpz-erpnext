"""The Friday Credit & AR report to the MD and CEO (§13).

One email, assembled from the same engines the desk reports use, so the numbers
in the inbox and the numbers on screen can never disagree.

New book and legacy are always shown **separately** — the whole point of §12 is
that they are collected on different terms and measured against different
thresholds.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate

from cannabis_management.credit_and_ar import metrics, utils
from cannabis_management.credit_and_ar.report import report_utils
from cannabis_management.credit_and_ar.report.red_list import red_list

TABLE = "border-collapse:collapse;font-size:13px;width:100%;margin:6px 0 18px;"
TH = "padding:6px 10px;border:1px solid #e2e8f0;background:#f8fafc;text-align:left;"
TD = "padding:6px 10px;border:1px solid #e2e8f0;"
TDR = TD + "text-align:right;"


def send_weekly_report():
	"""Friday. Inert until the policy effective date is set."""
	if not utils.require_policy_live("send_weekly_report"):
		return

	recipients = utils.dedupe_recipients(
		utils.routed_user("managing_director"),
		utils.routed_user("chief_executive_officer"),
		utils.finance_recipients(),
	)
	if not recipients:
		frappe.logger("credit_and_ar").warning(
			"Weekly Credit & AR report has no recipients — MD and CEO are not set."
		)
		return

	html = build_report()

	try:
		frappe.sendmail(
			recipients=recipients,
			subject=_("Weekly Credit & AR Report — {0}").format(
				frappe.format(getdate(nowdate()), {"fieldtype": "Date"})
			),
			message=html,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Weekly Credit & AR report failed")


@frappe.whitelist()
def build_report() -> str:
	"""Assemble the report body. Whitelisted so it can be previewed on demand."""
	current = metrics.get_current_metrics()
	week = _week_bounds()

	sections = [
		_freeze_banner(current),
		_metrics_section(current),
		_legacy_section(week),
		_new_ar_section(week),
		_ar_vs_cod_section(week),
		_red_list_section(),
	]

	return (
		"<div style='font-family:-apple-system,BlinkMacSystemFont,Segoe UI,Roboto,sans-serif;"
		"max-width:860px'>"
		+ f"<h2 style='margin:0 0 4px'>{_('Weekly Credit &amp; AR Report')}</h2>"
		+ f"<p style='color:#64748b;margin:0 0 18px'>{_('Week ending {0}').format(frappe.format(week['end'], {'fieldtype': 'Date'}))}</p>"
		+ "".join(sections)
		+ "</div>"
	)


def _week_bounds() -> dict:
	today = getdate(nowdate())
	start = add_days(today, -today.weekday())
	return {"start": start, "end": today}


def _freeze_banner(current) -> str:
	if not current.get("freeze_active"):
		return (
			"<div style='background:#f0fdf4;border-left:4px solid #16a34a;padding:10px 14px;"
			f"margin-bottom:16px'><b>{_('No freeze in effect.')}</b> "
			f"{_('New terms business may proceed within approved lines.')}</div>"
		)

	return (
		"<div style='background:#fef2f2;border-left:4px solid #dc2626;padding:10px 14px;"
		f"margin-bottom:16px'><b>{_('CREDIT FREEZE ACTIVE')}</b><br>"
		f"{frappe.utils.escape_html(current.get('freeze_reason') or '')}<br>"
		f"<span style='color:#64748b'>{_('No account may add new unsecured exposure, good standing included.')}</span></div>"
	)


def _metrics_section(current) -> str:
	cap = flt(current.get("total_ar_cap"))
	rows = [
		(
			_("Total AR — new book"),
			utils.fmt_currency(current["total_ar"]),
			_("cap {0}").format(utils.fmt_currency(cap)),
			current["total_ar"] > cap if cap else False,
		),
		(
			_("Total AR — legacy"),
			utils.fmt_currency(current["legacy_ar"]),
			_("reported separately, not capped"),
			False,
		),
		(
			_("DSO"),
			_("{0:.1f} days").format(current["dso"]),
			_("target {0} · breach {1}").format(
				current.get("dso_target"), current.get("dso_breach")
			),
			bool(current.get("dso_breach")) and current["dso"] >= flt(current["dso_breach"]),
		),
		(
			_("CEI"),
			_("{0:.1f}%").format(current["cei"]),
			_("target {0}% · breach below {1}%").format(
				current.get("cei_target"), current.get("cei_breach_below")
			),
			bool(current.get("cei_breach_below"))
			and current["cei"] < flt(current["cei_breach_below"]),
		),
		(
			_("Credit sales — last 30 days"),
			utils.fmt_currency(current["credit_sales"]),
			"",
			False,
		),
	]

	body = "".join(
		"<tr><td style='{td}'>{label}</td><td style='{tdr}'><b style='color:{colour}'>{value}</b></td>"
		"<td style='{td}color:#64748b'>{note}</td></tr>".format(
			td=TD, tdr=TDR, label=label, value=value, note=note,
			colour="#dc2626" if breached else "#0f172a",
		)
		for label, value, note, breached in rows
	)

	return (
		f"<h3 style='margin:18px 0 6px'>{_('Metrics vs. thresholds')}</h3>"
		f"<table style='{TABLE}'><thead><tr><th style='{TH}'>{_('Metric')}</th>"
		f"<th style='{TH}text-align:right'>{_('Value')}</th><th style='{TH}'>{_('Threshold')}</th>"
		f"</tr></thead><tbody>{body}</tbody></table>"
	)


def _legacy_section(week) -> str:
	effective_date = utils.policy_effective_date()

	rows = frappe.db.sql(
		"""
		SELECT COUNT(*) AS invoices,
		       COALESCE(SUM(si.outstanding_amount * si.conversion_rate), 0) AS outstanding
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.outstanding_amount > 0
		  AND si.posting_date < %(effective_date)s
		""",
		{"effective_date": effective_date},
		as_dict=True,
	)
	remaining = flt(rows[0].outstanding) if rows else 0.0
	count = rows[0].invoices if rows else 0

	recovered = _legacy_recovered_this_week(week)

	return (
		f"<h3 style='margin:18px 0 6px'>{_('Legacy recovery')}</h3>"
		f"<table style='{TABLE}'><tbody>"
		f"<tr><td style='{TD}'>{_('Recovered this week')}</td>"
		f"<td style='{TDR}'><b style='color:#16a34a'>{utils.fmt_currency(recovered)}</b></td></tr>"
		f"<tr><td style='{TD}'>{_('Register balance remaining')}</td>"
		f"<td style='{TDR}'><b>{utils.fmt_currency(remaining)}</b></td></tr>"
		f"<tr><td style='{TD}'>{_('Open legacy invoices')}</td>"
		f"<td style='{TDR}'>{count}</td></tr>"
		f"</tbody></table>"
		f"<p style='color:#64748b;font-size:12px;margin:-12px 0 16px'>"
		f"{_('Collected on original terms. No finance charges apply, and legacy does not count toward the new-book cap.')}</p>"
	)


def _legacy_recovered_this_week(week) -> float:
	effective_date = utils.policy_effective_date()
	accounts = metrics.receivable_accounts()
	if not accounts:
		return 0.0

	rows = frappe.db.sql(
		"""
		SELECT COALESCE(SUM(ge.credit - ge.debit), 0) AS recovered
		FROM `tabGL Entry` ge
		JOIN `tabSales Invoice` si ON si.name = ge.against_voucher
		WHERE ge.is_cancelled = 0
		  AND ge.party_type = 'Customer'
		  AND ge.against_voucher_type = 'Sales Invoice'
		  AND ge.account IN %(accounts)s
		  AND ge.posting_date BETWEEN %(start)s AND %(end)s
		  AND si.posting_date < %(effective_date)s
		""",
		{
			"accounts": accounts,
			"start": week["start"],
			"end": week["end"],
			"effective_date": effective_date,
		},
		as_dict=True,
	)
	return flt(rows[0].recovered) if rows else 0.0


def _new_ar_section(week) -> str:
	"""New AR extended this week — good-standing accounts only, per §13."""
	rows = frappe.db.sql(
		"""
		SELECT si.customer, si.base_grand_total, si.custom_mode_of_payment,
		       si.custom_order_type, si.payment_terms_template,
		       c.custom_hold_type, c.custom_credit_status
		FROM `tabSales Invoice` si
		JOIN `tabCustomer` c ON c.name = si.customer
		WHERE si.docstatus = 1 AND si.is_return = 0
		  AND IFNULL(si.custom_is_finance_charge, 0) = 0
		  AND si.posting_date BETWEEN %(start)s AND %(end)s
		""",
		{"start": week["start"], "end": week["end"]},
		as_dict=True,
	)

	excluded = set(report_utils.excluded_customers())
	good = 0.0
	distressed = 0.0

	for row in rows:
		if row.customer in excluded:
			continue
		if not metrics.is_credit_sale(row):
			continue
		if (row.custom_hold_type or utils.HOLD_NONE) == utils.HOLD_NONE and row.custom_credit_status in (
			utils.STATUS_TERMS_APPROVED,
			utils.STATUS_COD,
		):
			good += flt(row.base_grand_total)
		else:
			distressed += flt(row.base_grand_total)

	return (
		f"<h3 style='margin:18px 0 6px'>{_('New AR extended this week')}</h3>"
		f"<table style='{TABLE}'><tbody>"
		f"<tr><td style='{TD}'>{_('Good-standing accounts')}</td>"
		f"<td style='{TDR}'><b>{utils.fmt_currency(good)}</b></td></tr>"
		f"<tr><td style='{TD}'>{_('Accounts under warning, hold, plan or workout')}</td>"
		f"<td style='{TDR}'><b style='color:{'#dc2626' if distressed else '#0f172a'}'>"
		f"{utils.fmt_currency(distressed)}</b></td></tr>"
		f"</tbody></table>"
	)


def _ar_vs_cod_section(week) -> str:
	rows = frappe.db.sql(
		"""
		SELECT si.base_grand_total, si.custom_mode_of_payment, si.custom_order_type,
		       si.payment_terms_template
		FROM `tabSales Invoice` si
		WHERE si.docstatus = 1 AND si.is_return = 0
		  AND IFNULL(si.custom_is_finance_charge, 0) = 0
		  AND si.posting_date BETWEEN %(start)s AND %(end)s
		""",
		{"start": week["start"], "end": week["end"]},
		as_dict=True,
	)

	credit = flt(sum(flt(row.base_grand_total) for row in rows if metrics.is_credit_sale(row)))
	cod = flt(sum(flt(row.base_grand_total) for row in rows if not metrics.is_credit_sale(row)))
	total = credit + cod
	ratio = flt(credit / total * 100) if total else 0.0

	return (
		f"<h3 style='margin:18px 0 6px'>{_('AR vs. COD — this week&#39;s sales')}</h3>"
		f"<table style='{TABLE}'><tbody>"
		f"<tr><td style='{TD}'>{_('On terms (AR)')}</td>"
		f"<td style='{TDR}'><b>{utils.fmt_currency(credit)}</b></td>"
		f"<td style='{TDR}'>{ratio:.1f}%</td></tr>"
		f"<tr><td style='{TD}'>{_('COD / prepaid')}</td>"
		f"<td style='{TDR}'><b>{utils.fmt_currency(cod)}</b></td>"
		f"<td style='{TDR}'>{100 - ratio:.1f}%</td></tr>"
		f"<tr><td style='{TD}'><b>{_('Total')}</b></td>"
		f"<td style='{TDR}'><b>{utils.fmt_currency(total)}</b></td><td style='{TDR}'></td></tr>"
		f"</tbody></table>"
	)


def _red_list_section() -> str:
	data = red_list.get_data(frappe._dict({}))
	if not data:
		return (
			f"<h3 style='margin:18px 0 6px'>{_('Red List')}</h3>"
			f"<p style='color:#16a34a'>{_('Nothing past due and no live cases.')}</p>"
		)

	body = "".join(
		"<tr><td style='{td}'>{customer}</td><td style='{td}'><b>{status}</b></td>"
		"<td style='{tdr}'>{balance}</td><td style='{tdr}'>{past_due}</td>"
		"<td style='{tdr}'>{days}</td><td style='{td}'>{ptp}</td>"
		"<td style='{td}'>{action}</td><td style='{td}'>{owner}</td></tr>".format(
			td=TD,
			tdr=TDR,
			customer=frappe.utils.escape_html(row["customer"]),
			status=row["status"],
			balance=utils.fmt_currency(row["balance"]),
			past_due=utils.fmt_currency(row["past_due"]),
			days=row["max_days"],
			ptp=frappe.format(row["promise_to_pay_date"], {"fieldtype": "Date"})
			if row["promise_to_pay_date"]
			else "—",
			action=frappe.utils.escape_html(row["next_action"] or "—"),
			owner=frappe.utils.escape_html(row["assigned_to"] or "—"),
		)
		for row in data[:40]
	)

	plans = [row for row in data if row["status"] == "PLAN"]
	workouts = [row for row in data if row["status"] == "WORKOUT"]
	plan_note = ""

	if plans:
		due, received = red_list._plan_week()
		plan_note = _(
			"<p style='font-size:12px;color:#64748b'><b>Plan Book:</b> {0} plan(s), "
			"balance {1}; due this week {2}, received {3}.</p>"
		).format(
			len(plans),
			utils.fmt_currency(sum(row["balance"] for row in plans)),
			utils.fmt_currency(due),
			utils.fmt_currency(received),
		)

	if workouts:
		plan_note += _(
			"<p style='font-size:12px;color:#64748b'><b>Workouts:</b> {0} account(s), "
			"recovered to date {1}.</p>"
		).format(
			len(workouts),
			utils.fmt_currency(sum(flt(row["recovered_to_date"]) for row in workouts)),
		)

	truncated = (
		_("<p style='font-size:12px;color:#64748b'>Showing the 40 largest of {0} accounts.</p>").format(
			len(data)
		)
		if len(data) > 40
		else ""
	)

	return (
		f"<h3 style='margin:18px 0 6px'>{_('Red List')}</h3>"
		f"<table style='{TABLE}'><thead><tr>"
		f"<th style='{TH}'>{_('Customer')}</th><th style='{TH}'>{_('Status')}</th>"
		f"<th style='{TH}text-align:right'>{_('Balance')}</th>"
		f"<th style='{TH}text-align:right'>{_('Past Due')}</th>"
		f"<th style='{TH}text-align:right'>{_('Days')}</th>"
		f"<th style='{TH}'>{_('PTP')}</th><th style='{TH}'>{_('Next Action')}</th>"
		f"<th style='{TH}'>{_('Owner')}</th>"
		f"</tr></thead><tbody>{body}</tbody></table>{truncated}{plan_note}"
	)
