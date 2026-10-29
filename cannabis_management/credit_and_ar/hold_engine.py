import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, now_datetime, nowdate

from cannabis_management.credit_and_ar import credit_engine, utils
from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
	STATUS_ACTIVE,
	STATUS_CLOSED,
	get_active_case,
	sync_customer_from_cases,
)

GATE_1_DOCTYPES = ("Sales Order", "Delivery Note", "Work Order", "Stock Entry")

PRODUCTION_STOCK_ENTRY_PURPOSES = ("Material Transfer for Manufacture", "Manufacture")

AR_HOLD_THRESHOLD = 400_000

DEFAULT_HARD_HOLD_DAYS = 5
DEFAULT_HARD_HOLD_AMOUNT = 1_000


def evaluate_customer_credit_status():
	if not utils.require_policy_live("evaluate_customer_credit_status"):
		return

	settings = utils.get_settings()
	hard_hold_days = int(settings.hard_hold_days or 0) or DEFAULT_HARD_HOLD_DAYS
	hard_hold_amount = flt(settings.hard_hold_amount) or DEFAULT_HARD_HOLD_AMOUNT

	customers = frappe.get_all(
		"Customer",
		filters={
			"disabled": 0,
			"custom_is_intercompany": 0,
			"custom_credit_status": ("!=", utils.STATUS_EXEMPT),
		},
		pluck="name",
	)

	for customer in customers:
		try:
			_evaluate_one(customer, hard_hold_days, hard_hold_amount)
		except Exception:
			frappe.log_error(
				frappe.get_traceback(), f"Credit status evaluation failed for {customer}"
			)

	frappe.db.commit()


def _evaluate_one(customer, hard_hold_days, hard_hold_amount):
	snapshot = credit_engine.get_past_due_snapshot(customer)
	past_due = flt(snapshot["past_due_amount"])
	max_days = int(snapshot["max_days_past_due"])

	breach_by_days = bool(hard_hold_days) and past_due > 0 and max_days > hard_hold_days
	breach_by_amount = bool(hard_hold_amount) and past_due > 0 and past_due >= hard_hold_amount
	if utils.ar_cap_enabled():
		new_ar = credit_engine.get_customer_new_ar(customer)
		breach_by_ar_total = new_ar >= AR_HOLD_THRESHOLD
	else:
		new_ar = 0.0
		breach_by_ar_total = False
	available_line = credit_engine.get_available_line(customer)
	approved_limit = credit_engine.get_approved_limit(customer)
	breach_by_limit = approved_limit > 0 and available_line <= 0

	if breach_by_days or breach_by_amount or breach_by_ar_total or breach_by_limit:
		if breach_by_days:
			internal_reason = "Past Due Days"
		elif breach_by_amount:
			internal_reason = "Past Due Amount"
		elif breach_by_ar_total:
			internal_reason = "AR Threshold Breach"
		else:
			internal_reason = "Limit Breach"
		details = _details_for_breach(
			internal_reason, past_due, max_days, hard_hold_days, hard_hold_amount,
			new_ar, available_line,
		)
		ensure_active_case(customer, internal_reason, details, snapshot)
		return

	case = get_active_case(customer)

	if case:
		if past_due <= 0 and not case.resolution:
			_cure(case, snapshot)
		else:
			_refresh(case.name, snapshot, _details_for_still_past_due(past_due, max_days))
		return

	if past_due <= 0:
		_clear_warning(customer)
		return

	frappe.db.set_value(
		"Customer", customer, "custom_credit_status", utils.STATUS_WARNING, update_modified=False
	)


def _details_for_breach(
	internal_reason, past_due, max_days, hard_hold_days, hard_hold_amount, new_ar,
	available_line,
):
	if internal_reason in ("Past Due Days", "Past Due Amount"):
		return _(
			"{0} — {1} past due, oldest invoice {2} days overdue. Threshold: {3} days / {4}."
		).format(
			internal_reason,
			utils.fmt_currency(past_due),
			max_days,
			hard_hold_days,
			utils.fmt_currency(hard_hold_amount),
		)
	if internal_reason == "AR Threshold Breach":
		return _(
			"AR Threshold Breach — {0} of new AR (invoiced {1} onward) across the credit "
			"group exceeds the {2} ceiling. Legacy AR is excluded."
		).format(
			utils.fmt_currency(new_ar),
			frappe.utils.formatdate(utils.new_ar_start_date()),
			utils.fmt_currency(AR_HOLD_THRESHOLD),
		)
	return _("Limit Breach — exposure exceeds the approved credit line by {0}.").format(
		utils.fmt_currency(abs(available_line))
	)


def _details_for_still_past_due(past_due, max_days):
	return _("{0} past due, oldest invoice {1} days overdue.").format(
		utils.fmt_currency(past_due), max_days
	)


def _clear_warning(customer):
	current = frappe.db.get_value("Customer", customer, "custom_credit_status")
	if current != utils.STATUS_WARNING:
		return
	has_line = credit_engine.get_active_credit_application(customer)
	frappe.db.set_value(
		"Customer",
		customer,
		"custom_credit_status",
		utils.STATUS_TERMS_APPROVED if has_line else utils.STATUS_COD,
		update_modified=False,
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
	doc.status = STATUS_CLOSED
	doc.past_due_amount = 0
	doc.total_outstanding = snapshot["total_outstanding"]
	doc.max_days_past_due = 0
	doc.flags.ignore_role_guards = True
	doc.save(ignore_permissions=True)
	doc.add_comment("Info", _("Past due cleared — case closed automatically."))
	sync_customer_from_cases(doc.customer)


def ensure_active_case(
	customer: str,
	internal_reason: str,
	trigger_details: str,
	snapshot: dict | None = None,
	notify: bool = True,
	trigger_reason: str | None = None,
):
	if utils.is_policy_exempt(customer):
		frappe.logger("credit_and_ar").info(
			f"{customer} is exempt from the Credit & AR policy — no case raised."
		)
		return None

	snapshot = snapshot or credit_engine.get_past_due_snapshot(customer)

	existing = get_active_case(customer)
	if existing:
		_refresh(existing.name, snapshot, trigger_details)
		doc = frappe.get_doc("AR Case", existing.name)
		doc.add_comment(
			"Info", _("Additional trigger — {0}: {1}").format(internal_reason, trigger_details)
		)
		return doc

	return _create_case(
		customer, internal_reason, trigger_details, snapshot, notify=notify, trigger_reason=trigger_reason
	)


def _create_case(customer, internal_reason, trigger_details, snapshot, notify=True, trigger_reason=None):
	doc = frappe.new_doc("AR Case")
	doc.customer = customer
	doc.status = STATUS_ACTIVE
	doc.trigger_reason = (
		trigger_reason if trigger_reason is not None
		else utils.HOLD_REASON_BY_TRIGGER.get(internal_reason, "")
	)
	doc.trigger_details = trigger_details
	doc.past_due_amount = snapshot["past_due_amount"]
	doc.total_outstanding = snapshot["total_outstanding"]
	doc.max_days_past_due = snapshot["max_days_past_due"]
	doc.flags.ignore_role_guards = True
	doc.insert(ignore_permissions=True)

	if notify:
		_notify_case(doc)

	return doc


def create_manual_case(customer: str, trigger_reason: str, trigger_details: str):
	if utils.is_policy_exempt(customer):
		frappe.logger("credit_and_ar").info(
			f"{customer} is exempt from the Credit & AR policy — no case raised."
		)
		return None

	snapshot = credit_engine.get_past_due_snapshot(customer)
	doc = frappe.new_doc("AR Case")
	doc.customer = customer
	doc.status = STATUS_ACTIVE
	doc.trigger_reason = trigger_reason
	doc.trigger_details = trigger_details
	doc.past_due_amount = snapshot["past_due_amount"]
	doc.total_outstanding = snapshot["total_outstanding"]
	doc.max_days_past_due = snapshot["max_days_past_due"]
	doc.flags.ignore_role_guards = True
	doc.insert(ignore_permissions=True)

	_notify_case(doc)
	return doc


def raise_immediate_hold(customer: str, trigger_reason: str, trigger_details: str):
	return ensure_active_case(customer, trigger_reason, trigger_details)


def on_payment_entry_cancel(doc, method=None):
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
	)


def on_sales_invoice_submit(doc, method=None):
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
	)


def check_broken_promises():
	if not utils.require_policy_live("check_broken_promises"):
		return

	today = getdate(nowdate())
	cases = frappe.get_all(
		"AR Case",
		filters={
			"promise_to_pay_date": ("<", today),
			"promise_kept": 0,
			"status": STATUS_ACTIVE,
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
	if not utils.require_policy_live("check_license_expiry"):
		return

	today = getdate(nowdate())

	expired = frappe.get_all(
		"Customer",
		filters={
			"disabled": 0,
			"custom_credit_status": ("!=", utils.STATUS_EXEMPT),
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
				"custom_credit_status": ("!=", utils.STATUS_EXEMPT),
				"custom_license_expiry": target,
			},
			fields=["name", "custom_license_expiry"],
		)
		if upcoming:
			_notify_license_expiry(upcoming, days)

	frappe.db.commit()


def _customer_of(doc) -> str | None:
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
	if doc.doctype == "Sales Order":
		return utils.resolve_order_type(doc) in (utils.ORDER_TYPE_SAMPLE, utils.ORDER_TYPE_COD)

	if doc.doctype == "Delivery Note":
		return _delivery_note_is_exempt(doc)

	if doc.doctype == "Stock Entry":
		return doc.get("purpose") not in PRODUCTION_STOCK_ENTRY_PURPOSES

	return False


def _delivery_note_is_exempt(doc) -> bool:
	orders = sorted(
		{
			row.get("against_sales_order")
			for row in (doc.get("items") or [])
			if row.get("against_sales_order")
		}
	)
	if not orders:
		return False

	rows = frappe.get_all(
		"Sales Order",
		filters={"name": ["in", orders]},
		fields=["name", "custom_sales_order_type", "custom_mode_of_payment"],
	)
	if len(rows) != len(orders):
		return False

	return all(
		utils.resolve_order_type(row) in (utils.ORDER_TYPE_SAMPLE, utils.ORDER_TYPE_COD)
		for row in rows
	)


def enforce_hold(doc, method=None):
	if _is_exempt(doc):
		return

	customer = _customer_of(doc)
	if not customer:
		return

	if utils.is_policy_exempt(customer):
		return

	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import get_hold_type

	hold_type = get_hold_type(customer)
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


def release_case(case_name: str, release_basis: str, notes: str | None = None):
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import RESOLUTION_RELEASE

	if not utils.has_any_role("Credit Finance", "System Manager"):
		frappe.throw(
			_("Only Credit Finance can release a hold."),
			frappe.PermissionError,
			title=_("Not Authorised"),
		)

	doc = frappe.get_doc("AR Case", case_name)

	if doc.status == STATUS_CLOSED:
		frappe.throw(_("{0} is already Closed.").format(case_name))

	_verify_release_basis(doc, release_basis, notes)

	doc.status = STATUS_CLOSED
	doc.resolution = RESOLUTION_RELEASE
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

	return {"status": STATUS_CLOSED, "customer_hold": _current_hold(doc.customer)}


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
				"outside Paid in Full.</p><p>Reason: {2}</p><p>{3}</p>"
			).format(
				frappe.utils.get_fullname(frappe.session.user),
				frappe.utils.escape_html(doc.customer),
				frappe.utils.escape_html(notes),
				utils.doc_link("AR Case", doc.name),
			),
		)


def _current_hold(customer: str):
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import get_hold_type

	data = frappe.db.get_value(
		"Customer", customer, ["custom_credit_status"], as_dict=True
	) or frappe._dict()
	data["custom_hold_type"] = get_hold_type(customer)
	return data


def _notify_case(doc):
	sales_owner = _sales_owner(doc.customer)

	recipients = utils.dedupe_recipients(
		utils.finance_recipients(),
		utils.routed_user("collections_officer"),
		utils.routed_user("ops_manager"),
		sales_owner,
	)
	if not recipients:
		return

	subject = _("Hard hold — {0}").format(doc.customer)
	message = _(
		"""
		<p>Stop-work case raised for <b>{customer}</b>.</p>
		<table style="font-size:14px;margin:8px 0;">
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Trigger</td><td><b>{reason}</b></td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Detail</td><td>{details}</td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Past Due</td><td><b>{past_due}</b></td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Oldest Invoice</td><td>{days} days</td></tr>
			<tr><td style="padding:3px 14px 3px 0;color:#666;">Total Outstanding</td><td>{total}</td></tr>
		</table>
		<p style='color:#b91c1c;'>No product moves and no production starts for this
		customer until Credit Finance releases the hold.</p>
		<p>{link}</p>
		"""
	).format(
		customer=frappe.utils.escape_html(doc.customer),
		reason=frappe.utils.escape_html(doc.trigger_reason or ""),
		details=frappe.utils.escape_html(doc.trigger_details or ""),
		past_due=utils.fmt_currency(doc.past_due_amount),
		days=doc.max_days_past_due,
		total=utils.fmt_currency(doc.total_outstanding),
		link=utils.doc_link("AR Case", doc.name),
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
