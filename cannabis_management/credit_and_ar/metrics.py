"""Company-wide metrics and the credit freeze (§11).

Three numbers govern whether the group may extend any new unsecured exposure at
all: **total AR**, **DSO** and **CEI**. A breach on any one of them freezes new
terms business for everyone — good standing included — while existing invoices
keep their agreed due dates.

Everything here is **new book only**. Legacy is reported separately and never
freezes the company: at build time the site carried $4.77M of legacy AR against
a $400k cap, so counting it would leave the group permanently frozen and the
freeze would mean nothing.

The daily snapshot is stored as JSON in a global default, not a new DocType.
"""

import json

import frappe
from frappe import _
from frappe.utils import add_days, flt, get_first_day, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import utils

SNAPSHOT_KEY = "credit_ar_metrics_history"
OVERRIDE_KEY = "credit_ar_unfreeze_signoffs"
SNAPSHOT_RETENTION_DAYS = 400

# The window DSO and CEI are measured over.
PERIOD_DAYS = 30

BREACH_AR = "AR Cap"
BREACH_DSO = "DSO"
BREACH_CEI = "CEI"


# ── receivable accounts ──────────────────────────────────────────────────────


def receivable_accounts(company: str | None = None) -> list[str]:
	filters = {"account_type": "Receivable", "is_group": 0}
	if company:
		filters["company"] = company
	return frappe.get_all("Account", filters=filters, pluck="name")


# ── AR at a point in time ────────────────────────────────────────────────────


def _invoice_scope(company: str | None, new_book_only: bool = True) -> dict[str, dict]:
	"""Every Sales Invoice in scope, keyed by name.

	Finance-charge invoices are excluded throughout: they are a penalty on top
	of the debt, not sales, and folding them into DSO or CEI would flatter the
	numbers exactly when collections are worst.
	"""
	filters = {"docstatus": 1, "is_return": 0}
	if company:
		filters["company"] = company

	effective_date = utils.policy_effective_date()
	if new_book_only and effective_date:
		filters["posting_date"] = (">=", effective_date)

	intercompany = utils.intercompany_customers()
	if intercompany:
		filters["customer"] = ("not in", intercompany)

	rows = frappe.get_all(
		"Sales Invoice",
		filters=filters,
		fields=[
			"name",
			"customer",
			"company",
			"posting_date",
			"due_date",
			"base_grand_total",
			"custom_ledger",
			"custom_is_finance_charge",
			"custom_mode_of_payment",
			"custom_order_type",
			"payment_terms_template",
		],
	)
	return {row.name: row for row in rows if not row.custom_is_finance_charge}


def _outstanding_by_invoice(invoice_names: list[str], as_of: str) -> dict[str, float]:
	"""Outstanding per invoice as of a date, straight from the ledger.

	`Sales Invoice.outstanding_amount` is only ever *now*; the CEI needs a
	balance as it stood at the start of the period, so it has to come from
	GL Entry.
	"""
	if not invoice_names:
		return {}

	accounts = receivable_accounts()
	if not accounts:
		return {}

	result: dict[str, float] = {}
	chunk_size = 500
	for start in range(0, len(invoice_names), chunk_size):
		chunk = invoice_names[start : start + chunk_size]
		rows = frappe.db.sql(
			"""
			SELECT against_voucher AS invoice, SUM(debit - credit) AS balance
			FROM `tabGL Entry`
			WHERE is_cancelled = 0
			  AND party_type = 'Customer'
			  AND against_voucher_type = 'Sales Invoice'
			  AND against_voucher IN %(invoices)s
			  AND account IN %(accounts)s
			  AND posting_date <= %(as_of)s
			GROUP BY against_voucher
			""",
			{"invoices": chunk, "accounts": accounts, "as_of": as_of},
			as_dict=True,
		)
		for row in rows:
			result[row.invoice] = flt(row.balance)

	return result


def is_credit_sale(invoice: dict) -> bool:
	"""A sale actually extended on credit — not COD, not a sample.

	Reads the payment mode carried over from the Sales Order, falling back to
	the payment terms template when an invoice was raised directly.
	"""
	if (invoice.get("custom_order_type") or "") in utils.SAMPLE_ORDER_TYPES:
		return False

	mode = invoice.get("custom_mode_of_payment")
	if mode:
		return mode == utils.MODE_TERMS

	template = invoice.get("payment_terms_template")
	if not template or template == "COD":
		return False
	return utils.template_credit_days(template) > 0


# ── the three metrics ────────────────────────────────────────────────────────


def compute_metrics(company: str | None = None, as_of: str | None = None) -> dict:
	as_of = getdate(as_of or nowdate())
	period_start = add_days(as_of, -PERIOD_DAYS)

	invoices = _invoice_scope(company)
	names = list(invoices)

	ending = _outstanding_by_invoice(names, as_of)
	beginning = _outstanding_by_invoice(names, period_start)

	total_ar = flt(sum(value for value in ending.values() if value > 0))

	current_ar = flt(
		sum(
			value
			for name, value in ending.items()
			if value > 0
			and invoices[name].due_date
			and getdate(invoices[name].due_date) >= as_of
		)
	)

	beginning_ar = flt(sum(value for value in beginning.values() if value > 0))

	credit_sales = flt(
		sum(
			flt(invoices[name].base_grand_total)
			for name in names
			if is_credit_sale(invoices[name])
			and period_start < getdate(invoices[name].posting_date) <= as_of
		)
	)

	# Credit AR only, so COD invoices sitting unpaid do not distort DSO.
	credit_ar = flt(
		sum(
			value
			for name, value in ending.items()
			if value > 0 and is_credit_sale(invoices[name])
		)
	)

	dso = flt(credit_ar / credit_sales * PERIOD_DAYS) if credit_sales else 0.0

	denominator = beginning_ar + credit_sales - current_ar
	cei = flt((beginning_ar + credit_sales - total_ar) / denominator * 100) if denominator else 100.0

	legacy_ar = _legacy_ar(company)

	return {
		"as_of": str(as_of),
		"company": company or "Group",
		"total_ar": total_ar,
		"current_ar": current_ar,
		"beginning_ar": beginning_ar,
		"credit_sales": credit_sales,
		"credit_ar": credit_ar,
		"dso": dso,
		"cei": cei,
		"legacy_ar": legacy_ar,
		"period_days": PERIOD_DAYS,
	}


def _legacy_ar(company: str | None = None) -> float:
	"""Pre-policy balances — reported, never a freeze trigger."""
	effective_date = utils.policy_effective_date()
	if not effective_date:
		return 0.0

	filters = {
		"docstatus": 1,
		"outstanding_amount": (">", 0),
		"posting_date": ("<", effective_date),
	}
	if company:
		filters["company"] = company

	intercompany = utils.intercompany_customers()
	if intercompany:
		filters["customer"] = ("not in", intercompany)

	rows = frappe.get_all(
		"Sales Invoice", filters=filters, fields=["outstanding_amount", "conversion_rate"]
	)
	return flt(sum(flt(row.outstanding_amount) * flt(row.conversion_rate or 1) for row in rows))


# ── the daily job ────────────────────────────────────────────────────────────


def evaluate_company_metrics():
	"""Daily — measure, store a snapshot, and freeze or flag for unfreeze."""
	if not utils.require_policy_live("evaluate_company_metrics"):
		return

	settings = utils.get_settings()
	group = compute_metrics()

	per_company = {}
	for company in frappe.get_all("Company", pluck="name"):
		try:
			per_company[company] = compute_metrics(company=company)
		except Exception:
			frappe.log_error(frappe.get_traceback(), f"Metrics failed for {company}")

	breaches = _find_breaches(group, settings)

	_store_live_state(group)
	_append_snapshot(group, per_company, breaches)

	if breaches and not settings.company_freeze_active:
		_freeze(group, breaches)
	elif not breaches and settings.company_freeze_active:
		_flag_eligible_for_unfreeze(group)

	frappe.db.commit()


def _find_breaches(metrics: dict, settings) -> list[str]:
	breaches = []

	cap = flt(settings.total_ar_cap)
	if cap and metrics["total_ar"] > cap:
		breaches.append(
			_("{0}: new-book AR {1} exceeds the {2} cap.").format(
				BREACH_AR,
				utils.fmt_currency(metrics["total_ar"]),
				utils.fmt_currency(cap),
			)
		)

	dso_breach = int(settings.dso_breach_days or 0)
	if dso_breach and metrics["dso"] >= dso_breach:
		breaches.append(
			_("{0}: {1:.1f} days has reached the {2}-day breach level (target {3}).").format(
				BREACH_DSO, metrics["dso"], dso_breach, settings.dso_target_days
			)
		)

	cei_floor = flt(settings.cei_breach_below)
	if cei_floor and metrics["credit_sales"] and metrics["cei"] < cei_floor:
		breaches.append(
			_("{0}: {1:.1f}% is below the {2}% floor (target {3}%).").format(
				BREACH_CEI, metrics["cei"], cei_floor, settings.cei_target
			)
		)

	return breaches


def _store_live_state(metrics: dict):
	settings = frappe.get_single("Credit Policy Settings")
	settings.db_set("current_total_ar", metrics["total_ar"], update_modified=False)
	settings.db_set("current_dso", metrics["dso"], update_modified=False)
	settings.db_set("current_cei", metrics["cei"], update_modified=False)
	settings.db_set("last_metrics_run", now_datetime(), update_modified=False)
	frappe.clear_document_cache("Credit Policy Settings", "Credit Policy Settings")


# ── freeze / unfreeze ────────────────────────────────────────────────────────


def _freeze(metrics: dict, breaches: list[str]):
	reason = " ".join(breaches)

	settings = frappe.get_single("Credit Policy Settings")
	settings.db_set("company_freeze_active", 1, update_modified=False)
	settings.db_set("freeze_reason", reason, update_modified=False)
	settings.db_set("freeze_started_on", now_datetime(), update_modified=False)
	frappe.clear_document_cache("Credit Policy Settings", "Credit Policy Settings")

	frappe.db.set_global(OVERRIDE_KEY, json.dumps({}))

	_notify_freeze(metrics, breaches)


def _notify_freeze(metrics: dict, breaches: list[str]):
	recipients = utils.dedupe_recipients(
		utils.routed_user("managing_director"),
		utils.routed_user("chief_executive_officer"),
		utils.finance_recipients(),
		utils.users_with_role("Sales Manager"),
	)
	if not recipients:
		return

	items = "".join(f"<li>{item}</li>" for item in breaches)
	_sendmail(
		recipients,
		_("CREDIT FREEZE ACTIVE — no new terms exposure"),
		_(
			"""
			<p><b>A company-wide credit freeze is now in effect.</b> No account may add new
			unsecured exposure, good standing included. Existing invoices keep their agreed
			due dates.</p>
			<p><b>Breached:</b></p><ul>{items}</ul>
			<table style="font-size:14px;margin:8px 0;">
				<tr><td style="padding:3px 14px 3px 0;color:#666;">New-book AR</td><td><b>{ar}</b></td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">DSO</td><td>{dso:.1f} days</td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">CEI</td><td>{cei:.1f}%</td></tr>
				<tr><td style="padding:3px 14px 3px 0;color:#666;">Legacy AR (not counted)</td><td>{legacy}</td></tr>
			</table>
			<p style="color:#666;font-size:13px;">Lifting the freeze needs Finance review first,
			then the CEO and the Managing Director together. New orders must be re-typed COD
			or prepaid in the meantime.</p>
			"""
		).format(
			items=items,
			ar=utils.fmt_currency(metrics["total_ar"]),
			dso=metrics["dso"],
			cei=metrics["cei"],
			legacy=utils.fmt_currency(metrics["legacy_ar"]),
		),
	)


def _flag_eligible_for_unfreeze(metrics: dict):
	"""Metrics are back inside threshold — but nothing lifts silently.

	§11 requires Finance to confirm in writing, so the daily job only tells
	them they may.
	"""
	cache_key = f"credit_ar_unfreeze_eligible_{nowdate()}"
	if frappe.cache().get_value(cache_key):
		return
	frappe.cache().set_value(cache_key, 1, expires_in_sec=86400)

	recipients = utils.finance_recipients()
	if not recipients:
		return

	_sendmail(
		recipients,
		_("Credit freeze may now be lifted — Finance confirmation required"),
		_(
			"<p>Every metric is back inside its threshold:</p>"
			"<ul><li>New-book AR {ar}</li><li>DSO {dso:.1f} days</li><li>CEI {cei:.1f}%</li></ul>"
			"<p>The freeze does <b>not</b> lift on its own. Confirm it in writing to release it.</p>"
		).format(
			ar=utils.fmt_currency(metrics["total_ar"]),
			dso=metrics["dso"],
			cei=metrics["cei"],
		),
	)


@frappe.whitelist()
def confirm_unfreeze(notes: str):
	"""Finance lifts the freeze once the metrics are genuinely back."""
	if not utils.has_any_role("Credit Finance", "System Manager"):
		frappe.throw(
			_("Only Credit Finance can confirm an unfreeze."),
			frappe.PermissionError,
			title=_("Not Authorised"),
		)

	if not (notes or "").strip():
		frappe.throw(_("Confirming an unfreeze must be in writing — record the basis."))

	settings = utils.get_settings()
	if not settings.company_freeze_active:
		frappe.throw(_("There is no active freeze."))

	metrics = compute_metrics()
	breaches = _find_breaches(metrics, settings)
	if breaches:
		frappe.throw(
			_("The freeze cannot be lifted while a metric is still breached:<br><br>{0}").format(
				"<br>".join(breaches)
			),
			title=_("Still Breached"),
		)

	_lift_freeze(_("Finance confirmation: {0}").format(notes))
	return {"frozen": 0}


@frappe.whitelist()
def unfreeze_override(reason: str):
	"""The exception path — CEO and Managing Director, together, documented."""
	if not (reason or "").strip():
		frappe.throw(_("An override must record why."))

	settings = utils.get_settings()
	if not settings.company_freeze_active:
		frappe.throw(_("There is no active freeze."))

	md = utils.routed_user("managing_director")
	ceo = utils.routed_user("chief_executive_officer")
	if not md or not ceo:
		frappe.throw(
			_(
				"An override needs both the Managing Director and the Chief Executive "
				"Officer to be set in Credit Policy Settings."
			),
			title=_("Routing Incomplete"),
		)

	user = frappe.session.user
	if user not in (md, ceo) and "System Manager" not in frappe.get_roles():
		frappe.throw(
			_("Only the Managing Director and the CEO can override a credit freeze."),
			frappe.PermissionError,
			title=_("Not Authorised"),
		)

	signoffs = _get_signoffs()
	signoffs[user] = {"on": str(now_datetime()), "reason": reason}
	frappe.db.set_global(OVERRIDE_KEY, json.dumps(signoffs))

	have_md = md in signoffs
	have_ceo = ceo in signoffs

	if not (have_md and have_ceo):
		waiting = ceo if have_md else md
		_create_signoff_todo(waiting, reason)
		return {
			"frozen": 1,
			"signed": list(signoffs),
			"waiting_on": waiting,
			"message": _("Recorded. The freeze lifts once {0} also signs off.").format(waiting),
		}

	reasons = " | ".join(f"{who}: {data['reason']}" for who, data in signoffs.items())
	_lift_freeze(_("CEO + MD override — {0}").format(reasons), override=True)
	return {"frozen": 0, "signed": list(signoffs)}


def _get_signoffs() -> dict:
	raw = frappe.db.get_global(OVERRIDE_KEY)
	if not raw:
		return {}
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		return {}


def _create_signoff_todo(user: str, reason: str):
	frappe.get_doc(
		{
			"doctype": "ToDo",
			"allocated_to": user,
			"description": _("Credit freeze override awaiting your sign-off: {0}").format(reason),
			"priority": "High",
			"status": "Open",
		}
	).insert(ignore_permissions=True)


def _lift_freeze(basis: str, override: bool = False):
	settings = frappe.get_single("Credit Policy Settings")
	previous_reason = settings.freeze_reason

	settings.db_set("company_freeze_active", 0, update_modified=False)
	settings.db_set("freeze_reason", None, update_modified=False)
	settings.db_set("freeze_started_on", None, update_modified=False)
	frappe.clear_document_cache("Credit Policy Settings", "Credit Policy Settings")

	frappe.db.set_global(OVERRIDE_KEY, json.dumps({}))

	# The exception register: overrides are logged where they can be found later.
	frappe.get_doc(
		{
			"doctype": "Comment",
			"comment_type": "Info",
			"reference_doctype": "Credit Policy Settings",
			"reference_name": "Credit Policy Settings",
			"content": _("Credit freeze lifted by {0}. {1}{2}").format(
				frappe.utils.get_fullname(frappe.session.user),
				basis,
				_(" [OVERRIDE — metrics were still breached]") if override else "",
			),
		}
	).insert(ignore_permissions=True)

	recipients = utils.dedupe_recipients(
		utils.routed_user("managing_director"),
		utils.routed_user("chief_executive_officer"),
		utils.finance_recipients(),
		utils.users_with_role("Sales Manager"),
	)
	if recipients:
		_sendmail(
			recipients,
			_("Credit freeze lifted"),
			_(
				"<p>The company-wide credit freeze has been lifted by <b>{0}</b>.</p>"
				"<p>Basis: {1}</p><p>Previous reason: {2}</p>{3}"
			).format(
				frappe.utils.get_fullname(frappe.session.user),
				frappe.utils.escape_html(basis),
				frappe.utils.escape_html(previous_reason or _("not recorded")),
				_(
					"<p style='color:#b91c1c;'><b>This was an override — the metrics had not "
					"returned inside their thresholds.</b></p>"
				)
				if override
				else "",
			),
		)


# ── snapshots ────────────────────────────────────────────────────────────────


def _append_snapshot(group: dict, per_company: dict, breaches: list[str]):
	"""Daily trend data, kept as JSON rather than a new DocType."""
	history = get_metrics_history()

	today = str(getdate(nowdate()))
	history = [row for row in history if row.get("as_of") != today]
	history.append(
		{
			"as_of": today,
			"total_ar": group["total_ar"],
			"legacy_ar": group["legacy_ar"],
			"dso": group["dso"],
			"cei": group["cei"],
			"credit_sales": group["credit_sales"],
			"breaches": breaches,
			"by_company": {
				name: {
					"total_ar": row["total_ar"],
					"legacy_ar": row["legacy_ar"],
					"dso": row["dso"],
					"cei": row["cei"],
				}
				for name, row in per_company.items()
			},
		}
	)

	cutoff = str(add_days(getdate(nowdate()), -SNAPSHOT_RETENTION_DAYS))
	history = [row for row in history if row.get("as_of", "") >= cutoff]

	frappe.db.set_global(SNAPSHOT_KEY, json.dumps(history))


@frappe.whitelist()
def get_metrics_history() -> list[dict]:
	raw = frappe.db.get_global(SNAPSHOT_KEY)
	if not raw:
		return []
	try:
		return json.loads(raw)
	except (ValueError, TypeError):
		return []


@frappe.whitelist()
def get_current_metrics():
	"""Live figures for the workspace cards, without waiting for the scheduler."""
	settings = utils.get_settings()
	metrics = compute_metrics()
	metrics["freeze_active"] = int(settings.company_freeze_active or 0)
	metrics["freeze_reason"] = settings.freeze_reason
	metrics["total_ar_cap"] = flt(settings.total_ar_cap)
	metrics["dso_target"] = settings.dso_target_days
	metrics["dso_breach"] = settings.dso_breach_days
	metrics["cei_target"] = settings.cei_target
	metrics["cei_breach_below"] = settings.cei_breach_below
	metrics["breaches"] = _find_breaches(metrics, settings)
	return metrics


def _sendmail(recipients, subject, message):
	try:
		frappe.sendmail(recipients=recipients, subject=subject, message=message)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Credit metrics notification failed")
