"""Stop Work — warning, hard hold, immediate hold, and release.

Two clocks run here:

* a **daily sweep** that raises warnings and hard holds from the age and size of
  past-due balances, and cures cases once the customer is current;
* **event-driven immediate holds** for returned payments, broken promises,
  expired licenses and limit breaches, which cannot wait for tomorrow.

The daily sweep only ever moves cases it could have created itself. A case a
human released or defaulted is never quietly reopened or cured by a scheduler.
"""

import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import credit_engine, utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
	AUTO_MANAGED_STATUSES,
	HOLDING_TYPES,
	INACTIVE_STATUSES,
	STATUS_ACTIVE,
	STATUS_CURED,
	STATUS_DEFAULTED,
	STATUS_OPEN,
	STATUS_RELEASED,
	TYPE_HARD_HOLD,
	TYPE_IMMEDIATE_HOLD,
	TYPE_PAYMENT_PLAN,
	TYPE_WARNING,
	sync_customer_from_cases,
)

# Gate 1 — the document types a hold stops. Quotation is deliberately absent:
# quoting a delinquent customer costs nothing and keeps the conversation alive.
GATE_1_DOCTYPES = ("Sales Order", "Delivery Note", "Work Order", "Stock Entry")

PRODUCTION_STOCK_ENTRY_PURPOSES = ("Material Transfer for Manufacture", "Manufacture")


# ── daily sweep ──────────────────────────────────────────────────────────────


def evaluate_customer_credit_status():
	"""Raise, upgrade and cure past-due cases across the whole customer book."""
	if not utils.require_policy_live("evaluate_customer_credit_status"):
		return

	settings = utils.get_settings()
	hard_hold_days = int(settings.hard_hold_days or 0)
	hard_hold_amount = flt(settings.hard_hold_amount)
	warning_enabled = int(settings.warning_enabled or 0)

	customers = frappe.get_all(
		"Customer",
		filters={
			"disabled": 0,
			"custom_is_intercompany": 0,
			"custom_credit_policy_exempt": 0,
		},
		pluck="name",
	)

	for customer in customers:
		try:
			_evaluate_one(customer, hard_hold_days, hard_hold_amount, warning_enabled)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), f"Credit status evaluation failed for {customer}"
			)

	frappe.db.commit()


def _evaluate_one(customer, hard_hold_days, hard_hold_amount, warning_enabled):
	snapshot = credit_engine.get_past_due_snapshot(customer)
	past_due = flt(snapshot["past_due_amount"])
	max_days = int(snapshot["max_days_past_due"])

	case = _get_auto_case(customer)

	if past_due <= 0:
		if case:
			_cure(case, snapshot)
		return

	# Whichever trigger comes first applies.
	breach_by_days = hard_hold_days and max_days > hard_hold_days
	breach_by_amount = hard_hold_amount and past_due >= hard_hold_amount

	if breach_by_days or breach_by_amount:
		reason = "Past Due Days" if breach_by_days else "Past Due Amount"
		details = (
			_("{0} past due, oldest invoice {1} days overdue. Threshold: {2} days / {3}.").format(
				utils.fmt_currency(past_due),
				max_days,
				hard_hold_days,
				utils.fmt_currency(hard_hold_amount),
			)
		)
		_raise_or_upgrade(customer, TYPE_HARD_HOLD, reason, details, snapshot, case)
		return

	if warning_enabled:
		details = _("{0} past due, oldest invoice {1} days overdue.").format(
			utils.fmt_currency(past_due), max_days
		)
		_raise_or_upgrade(customer, TYPE_WARNING, "Past Due Days", details, snapshot, case)


def _get_auto_case(customer):
	"""The live case the sweep is allowed to touch: one it could have raised."""
	rows = frappe.get_all(
		"AR Case",
		filters={
			"customer": customer,
			"case_type": ("in", [TYPE_WARNING, TYPE_HARD_HOLD]),
			"status": ("in", AUTO_MANAGED_STATUSES),
		},
		fields=["name", "case_type", "status"],
		order_by="opened_on desc",
		limit=1,
	)
	return rows[0] if rows else None


def _raise_or_upgrade(customer, case_type, reason, details, snapshot, case):
	if case and case.case_type == case_type:
		_refresh(case.name, snapshot, details)
		return

	if case and case.case_type == TYPE_WARNING and case_type == TYPE_HARD_HOLD:
		doc = frappe.get_doc("AR Case", case.name)
		doc.case_type = TYPE_HARD_HOLD
		doc.status = STATUS_ACTIVE
		doc.trigger_reason = reason
		doc.trigger_details = details
		doc.flags.ignore_role_guards = True
		doc.save(ignore_permissions=True)
		doc.add_comment("Info", _("Escalated from Warning to Hard Hold. {0}").format(details))
		_notify_case(doc, escalated=True)
		return

	if case and case.case_type == TYPE_HARD_HOLD and case_type == TYPE_WARNING:
		# Still past due, just under the hard-hold threshold now. Do not
		# downgrade a hold automatically — Finance releases holds, not the clock.
		_refresh(case.name, snapshot, details)
		return

	create_case(
		customer=customer,
		case_type=case_type,
		trigger_reason=reason,
		trigger_details=details,
		snapshot=snapshot,
	)


def _refresh(case_name, snapshot, details):
	frappe.db.set_value(
		"AR Case",
		case_name,
		{
			"past_due_amount": snapshot["past_due_amount"],
			"total_outstanding": snapshot["total_outstanding"],
			"max_days_past_due": snapshot["max_days_past_due"],
			"trigger_details": details,
		},
		update_modified=False,
	)


def _cure(case, snapshot):
	doc = frappe.get_doc("AR Case", case.name)
	doc.status = STATUS_CURED
	doc.past_due_amount = 0
	doc.total_outstanding = snapshot["total_outstanding"]
	doc.max_days_past_due = 0
	doc.flags.ignore_role_guards = True
	doc.save(ignore_permissions=True)
	doc.add_comment("Info", _("Past due cleared — case cured automatically."))
	sync_customer_from_cases(doc.customer)


# ── case creation ────────────────────────────────────────────────────────────


def create_case(
	customer: str,
	case_type: str,
	trigger_reason: str,
	trigger_details: str,
	snapshot: dict | None = None,
	company: str | None = None,
	notify: bool = True,
):
	"""Create an AR Case and push the resulting hold onto the customer.

	The single choke point for every case in the system — daily sweep, event
	triggers and the manual endpoint all come through here, so the exemption
	only has to be enforced once.
	"""
	if utils.is_policy_exempt(customer):
		frappe.logger("credit_and_ar").info(
			f"{customer} is exempt from the Credit & AR policy — no {case_type} case raised."
		)
		return None

	snapshot = snapshot or credit_engine.get_past_due_snapshot(customer)

	doc = frappe.new_doc("AR Case")
	doc.customer = customer
	doc.company = company or _company_of(customer)
	doc.case_type = case_type
	doc.status = STATUS_ACTIVE if case_type in HOLDING_TYPES else STATUS_OPEN
	doc.trigger_reason = trigger_reason
	doc.trigger_details = trigger_details
	doc.past_due_amount = snapshot["past_due_amount"]
	doc.total_outstanding = snapshot["total_outstanding"]
	doc.max_days_past_due = snapshot["max_days_past_due"]
	doc.flags.ignore_role_guards = True
	doc.insert(ignore_permissions=True)

	if notify:
		_notify_case(doc)

	return doc


def _company_of(customer: str) -> str | None:
	"""The company the customer most recently traded with."""
	rows = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1},
		fields=["company"],
		order_by="posting_date desc",
		limit=1,
	)
	if rows:
		return rows[0].company
	return frappe.defaults.get_user_default("Company")


def raise_immediate_hold(customer: str, trigger_reason: str, trigger_details: str, **kwargs):
	"""An immediate hold, unless one is already standing for the same reason."""
	if utils.is_policy_exempt(customer):
		return None

	existing = frappe.get_all(
		"AR Case",
		filters={
			"customer": customer,
			"case_type": TYPE_IMMEDIATE_HOLD,
			"trigger_reason": trigger_reason,
			"status": ("not in", INACTIVE_STATUSES),
		},
		pluck="name",
	)
	if existing:
		frappe.db.set_value(
			"AR Case", existing[0], "trigger_details", trigger_details, update_modified=False
		)
		return frappe.get_doc("AR Case", existing[0])

	return create_case(
		customer=customer,
		case_type=TYPE_IMMEDIATE_HOLD,
		trigger_reason=trigger_reason,
		trigger_details=trigger_details,
		**kwargs,
	)


# ── event-driven triggers ────────────────────────────────────────────────────


def on_payment_entry_cancel(doc, method=None):
	"""A returned payment is an immediate hold — an ordinary correction is not.

	The difference is the explicit flag on the Payment Entry, ticked by Finance
	before cancelling. Inferring a bounce from any cancellation would fire holds
	on routine re-keying.
	"""
	if doc.payment_type != "Receive" or doc.party_type != "Customer" or not doc.party:
		return
	if not doc.get("custom_is_returned_payment"):
		return
	if utils.is_policy_exempt(doc.party):
		return

	frappe.db.set_value(
		"Customer",
		doc.party,
		"custom_returned_payment_count",
		flt(frappe.db.get_value("Customer", doc.party, "custom_returned_payment_count")) + 1,
		update_modified=False,
	)

	raise_immediate_hold(
		customer=doc.party,
		trigger_reason="Returned Payment",
		trigger_details=_("Payment Entry {0} for {1} was returned. {2}").format(
			doc.name,
			utils.fmt_currency(doc.paid_amount),
			doc.get("custom_return_reason") or "",
		),
		company=doc.company,
	)


def on_sales_invoice_submit(doc, method=None):
	"""§7 — a limit breach at invoicing is an immediate hold."""
	if not doc.customer or doc.is_return:
		return
	if utils.is_policy_exempt(doc.customer):
		return

	limit = credit_engine.get_approved_limit(doc.customer)
	if limit <= 0:
		return

	exposure = credit_engine.get_current_exposure(doc.customer)
	if exposure <= limit:
		return

	raise_immediate_hold(
		customer=doc.customer,
		trigger_reason="Limit Breach",
		trigger_details=_("Group exposure {0} exceeds the approved limit {1} after {2}.").format(
			utils.fmt_currency(exposure), utils.fmt_currency(limit), doc.name
		),
		company=doc.company,
	)


def check_broken_promises():
	"""Daily — a promise to pay that passed without payment is an immediate hold."""
	if not utils.require_policy_live("check_broken_promises"):
		return

	today = getdate(nowdate())
	cases = frappe.get_all(
		"AR Case",
		filters={
			"promise_to_pay_date": ("<", today),
			"promise_kept": 0,
			"status": ("not in", INACTIVE_STATUSES),
		},
		fields=["name", "customer", "promise_to_pay_date", "promise_to_pay_amount"],
	)

	for case in cases:
		if utils.is_policy_exempt(case.customer):
			continue
		snapshot = credit_engine.get_past_due_snapshot(case.customer)
		if flt(snapshot["past_due_amount"]) <= 0:
			frappe.db.set_value("AR Case", case.name, "promise_kept", 1, update_modified=False)
			continue

		frappe.db.set_value(
			"Customer",
			case.customer,
			"custom_broken_ptp_count",
			flt(frappe.db.get_value("Customer", case.customer, "custom_broken_ptp_count")) + 1,
			update_modified=False,
		)
		# Clear the promise so the same broken promise is not counted twice.
		frappe.db.set_value(
			"AR Case", case.name, "promise_to_pay_date", None, update_modified=False
		)

		raise_immediate_hold(
			customer=case.customer,
			trigger_reason="Broken Promise to Pay",
			trigger_details=_("Promised {0} by {1}; nothing received.").format(
				utils.fmt_currency(case.promise_to_pay_amount),
				frappe.format(case.promise_to_pay_date, {"fieldtype": "Date"}),
			),
		)

	frappe.db.commit()


def check_license_expiry():
	"""Daily — warn at T-30 and T-7, hold once the license has actually expired."""
	if not utils.require_policy_live("check_license_expiry"):
		return

	today = getdate(nowdate())

	expired = frappe.get_all(
		"Customer",
		filters={
			"disabled": 0,
			"custom_credit_policy_exempt": 0,
			"custom_license_expiry": ("<", today),
			"custom_credit_status": ("!=", utils.STATUS_COD),
		},
		fields=["name", "custom_license_expiry"],
	)
	for row in expired:
		raise_immediate_hold(
			customer=row.name,
			trigger_reason="Expired License",
			trigger_details=_("License expired on {0}.").format(
				frappe.format(row.custom_license_expiry, {"fieldtype": "Date"})
			),
		)

	for days in (30, 7):
		target = add_days(today, days)
		upcoming = frappe.get_all(
			"Customer",
			filters={
				"disabled": 0,
				"custom_credit_policy_exempt": 0,
				"custom_license_expiry": target,
			},
			fields=["name", "custom_license_expiry"],
		)
		if upcoming:
			_notify_license_expiry(upcoming, days)

	frappe.db.commit()


# ── Gate 1 ───────────────────────────────────────────────────────────────────


def _customer_of(doc) -> str | None:
	"""Find the customer a document ultimately serves."""
	if doc.get("customer"):
		return doc.customer

	if doc.doctype == "Work Order":
		if doc.get("sales_order"):
			return frappe.db.get_value("Sales Order", doc.sales_order, "customer")
		return None

	if doc.doctype == "Stock Entry":
		if doc.get("work_order"):
			sales_order = frappe.db.get_value("Work Order", doc.work_order, "sales_order")
			if sales_order:
				return frappe.db.get_value("Sales Order", sales_order, "customer")
		if doc.get("sales_order_no"):
			return frappe.db.get_value("Sales Order", doc.sales_order_no, "customer")
		return None

	return None


def _is_exempt(doc) -> bool:
	"""Samples never carry credit risk, so a hold does not stop them."""
	if doc.doctype in ("Sales Order", "Delivery Note"):
		return utils.resolve_order_type(doc) == utils.ORDER_TYPE_SAMPLE

	if doc.doctype == "Stock Entry":
		return doc.get("purpose") not in PRODUCTION_STOCK_ENTRY_PURPOSES

	return False


def enforce_hold(doc, method=None):
	"""Block outbound and production work for a held customer.

	Wired to before_submit on Sales Order, Delivery Note, Work Order and
	production Stock Entries. Quotation is deliberately never gated.
	"""
	if _is_exempt(doc):
		return

	customer = _customer_of(doc)
	if not customer:
		return

	if utils.is_policy_exempt(customer):
		return

	hold_type = frappe.db.get_value("Customer", customer, "custom_hold_type")
	if hold_type not in utils.BLOCKING_HOLDS:
		return

	case = frappe.db.get_value("Customer", customer, "custom_active_ar_case")
	case_link = f" ({utils.doc_link('AR Case', case)})" if case else ""

	frappe.throw(
		_(
			"<b>Stop Work.</b> {0} is on <b>{1}</b>{2}.<br><br>"
			"No product moves and no production starts until Credit Finance releases "
			"the hold. Quotations are still allowed."
		).format(frappe.bold(customer), hold_type, case_link),
		title=_("Customer On Hold"),
	)


# ── release ──────────────────────────────────────────────────────────────────


def release_case(case_name: str, release_basis: str, notes: str | None = None):
	"""Lift a hold. Credit Finance only, and every basis is verified live."""
	if not utils.has_any_role("Credit Finance", "System Manager"):
		frappe.throw(
			_("Only Credit Finance can release a hold."),
			frappe.PermissionError,
			title=_("Not Authorised"),
		)

	doc = frappe.get_doc("AR Case", case_name)

	if doc.status in INACTIVE_STATUSES:
		frappe.throw(_("{0} is already {1}.").format(case_name, doc.status))

	_verify_release_basis(doc, release_basis, notes)

	doc.status = STATUS_RELEASED
	doc.release_basis = release_basis
	doc.release_notes = notes
	doc.released_by = frappe.session.user
	doc.released_on = now_datetime()
	doc.flags.from_release_api = True
	doc.flags.ignore_role_guards = True
	doc.save(ignore_permissions=True)

	doc.add_comment(
		"Info",
		_("Hold released by {0} on the basis of <b>{1}</b>. {2}").format(
			frappe.utils.get_fullname(frappe.session.user),
			release_basis,
			frappe.utils.escape_html(notes or ""),
		),
	)

	sync_customer_from_cases(doc.customer)
	_notify_release(doc)

	return {"status": STATUS_RELEASED, "customer_hold": _current_hold(doc.customer)}


def _verify_release_basis(doc, release_basis: str, notes: str | None):
	if release_basis == "Paid in Full":
		snapshot = credit_engine.get_past_due_snapshot(doc.customer)
		if flt(snapshot["past_due_amount"]) > 0.01:
			frappe.throw(
				_(
					"{0} still shows <b>{1}</b> past due, so the hold cannot be released as "
					"Paid in Full."
				).format(
					frappe.bold(doc.customer),
					utils.fmt_currency(snapshot["past_due_amount"]),
				),
				title=_("Still Past Due"),
			)
		return

	if release_basis == "Current on Approved Plan":
		plan = frappe.get_all(
			"AR Case",
			filters={
				"customer": doc.customer,
				"case_type": TYPE_PAYMENT_PLAN,
				"status": ("not in", INACTIVE_STATUSES),
			},
			fields=["name", "md_ratified", "missed_installments"],
			limit=1,
		)
		if not plan:
			frappe.throw(
				_("{0} has no active payment plan.").format(frappe.bold(doc.customer)),
				title=_("No Plan"),
			)
		if not plan[0].md_ratified:
			frappe.throw(
				_("Payment plan {0} has not been ratified by the Managing Director.").format(
					plan[0].name
				),
				title=_("Plan Not Ratified"),
			)
		if int(plan[0].missed_installments or 0) > 0:
			frappe.throw(
				_("Payment plan {0} has {1} missed installment(s) — the customer is not current.").format(
					plan[0].name, plan[0].missed_installments
				),
				title=_("Plan In Default"),
			)
		return

	if release_basis == "MD Exception":
		if not (notes or "").strip():
			frappe.throw(
				_("An MD exception must record the reason and who approved it."),
				title=_("Reason Required"),
			)
		_log_md_exception(doc, notes)
		return

	frappe.throw(_("{0} is not a valid release basis.").format(release_basis))


def _log_md_exception(doc, notes: str):
	"""The exception register: a durable, searchable record on the case."""
	doc.add_comment(
		"Info",
		_("<b>MD EXCEPTION</b> — hold released outside the normal basis by {0}. {1}").format(
			frappe.utils.get_fullname(frappe.session.user), frappe.utils.escape_html(notes)
		),
	)

	recipients = utils.dedupe_recipients(
		utils.routed_user("managing_director"),
		utils.routed_user("chief_executive_officer"),
		utils.finance_recipients(),
	)
	if recipients:
		_sendmail(
			recipients,
			_("MD exception used to release a hold — {0}").format(doc.customer),
			_(
				"<p><b>{0}</b> released the hold on <b>{1}</b> under an MD exception, "
				"outside Paid in Full or Current on Approved Plan.</p><p>Reason: {2}</p><p>{3}</p>"
			).format(
				frappe.utils.get_fullname(frappe.session.user),
				frappe.utils.escape_html(doc.customer),
				frappe.utils.escape_html(notes),
				utils.doc_link("AR Case", doc.name),
			),
		)


def _current_hold(customer: str):
	return frappe.db.get_value(
		"Customer", customer, ["custom_hold_type", "custom_on_hold", "custom_credit_status"], as_dict=True
	)


# ── notifications ────────────────────────────────────────────────────────────


def _notify_case(doc, escalated: bool = False):
	sales_owner = _sales_owner(doc.customer)

	if doc.case_type == TYPE_WARNING:
		recipients = utils.dedupe_recipients(
			utils.finance_recipients(), utils.routed_user("collections_officer")
		)
		subject = _("Warning raised — {0}").format(doc.customer)
	elif doc.case_type == TYPE_HARD_HOLD:
		recipients = utils.dedupe_recipients(
			utils.finance_recipients(),
			utils.routed_user("collections_officer"),
			utils.routed_user("ops_manager"),
			sales_owner,
		)
		subject = _("Hard hold — {0}").format(doc.customer)
	else:
		recipients = utils.dedupe_recipients(
			utils.finance_recipients(), utils.routed_user("managing_director"), sales_owner
		)
		subject = _("Immediate hold — {0}").format(doc.customer)

	if not recipients:
		return

	verb = _("escalated to") if escalated else _("raised:")
	message = _(
		"""
		<p>Stop-work case {verb} <b>{case_type}</b> for <b>{customer}</b>.</p>
		<table style="font-size:14px;margin:8px 0;">
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Trigger</td><td><b>{reason}</b></td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Detail</td><td>{details}</td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Past Due</td><td><b>{past_due}</b></td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Oldest Invoice</td><td>{days} days</td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Total Outstanding</td><td>{total}</td></tr>
		</table>
		<p>{link}</p>
		"""
	).format(
		verb=verb,
		case_type=doc.case_type,
		customer=frappe.utils.escape_html(doc.customer),
		reason=frappe.utils.escape_html(doc.trigger_reason or ""),
		details=frappe.utils.escape_html(doc.trigger_details or ""),
		past_due=utils.fmt_currency(doc.past_due_amount),
		days=doc.max_days_past_due,
		total=utils.fmt_currency(doc.total_outstanding),
		link=utils.doc_link("AR Case", doc.name),
	)

	if doc.case_type in HOLDING_TYPES:
		message += _(
			"<p style='color:#b91c1c;'>No product moves and no production starts for this "
			"customer until Credit Finance releases the hold.</p>"
		)

	_sendmail(recipients, subject, message, doc)


def _notify_release(doc):
	recipients = utils.dedupe_recipients(
		_sales_owner(doc.customer), utils.routed_user("ops_manager"), utils.finance_recipients()
	)
	if not recipients:
		return

	_sendmail(
		recipients,
		_("Hold released — {0}").format(doc.customer),
		_(
			"<p>The hold on <b>{0}</b> has been released by {1} on the basis of "
			"<b>{2}</b>. Normal work can resume.</p><p>{3}</p>"
		).format(
			frappe.utils.escape_html(doc.customer),
			frappe.utils.get_fullname(doc.released_by),
			doc.release_basis,
			utils.doc_link("AR Case", doc.name),
		),
		doc,
	)


def _notify_license_expiry(customers, days):
	recipients = utils.finance_recipients()
	if not recipients:
		return

	rows = "".join(
		"<li><b>{0}</b> — expires {1}</li>".format(
			frappe.utils.escape_html(row.name),
			frappe.format(row.custom_license_expiry, {"fieldtype": "Date"}),
		)
		for row in customers
	)
	_sendmail(
		recipients,
		_("Customer licenses expiring in {0} days").format(days),
		_(
			"<p>The following customer licenses expire in {0} days. An expired license "
			"puts the account on immediate hold.</p><ul>{1}</ul>"
		).format(days, rows),
	)


def _sales_owner(customer: str) -> str | None:
	"""Whoever last raised a Sales Order for this customer."""
	rows = frappe.get_all(
		"Sales Order",
		filters={"customer": customer, "docstatus": ("<", 2)},
		fields=["owner"],
		order_by="creation desc",
		limit=1,
	)
	return rows[0].owner if rows else None


def _sendmail(recipients, subject, message, doc=None):
	try:
		kwargs = {"recipients": recipients, "subject": subject, "message": message}
		if doc is not None:
			kwargs["reference_doctype"] = doc.doctype
			kwargs["reference_name"] = doc.name
		frappe.sendmail(**kwargs)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "AR Case notification failed")
