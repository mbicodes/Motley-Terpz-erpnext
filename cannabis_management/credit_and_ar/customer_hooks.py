"""Customer-side handling for the policy exemption.

Setting Credit Status to "Policy Exempt" carves an account out of this module
entirely. It used to be a separate checkbox; the status carries it now, so an
account has one field describing where it stands instead of two that could
disagree with each other.

Because utils.is_policy_exempt reads the status live, nothing has to be migrated
when it changes — but the account's *displayed* state does need to follow, so
the Red List and the scorecard do not keep showing a hold that is no longer
enforced.
"""

import frappe
from frappe import _

from cannabis_management.credit_and_ar import utils


def validate(doc, method=None):
	_stamp_exemption(doc)


def on_update(doc, method=None):
	previous = doc.get_doc_before_save()
	was_exempt = (previous.get("custom_credit_status") == utils.STATUS_EXEMPT) if previous else False
	is_exempt = doc.get("custom_credit_status") == utils.STATUS_EXEMPT

	# Not just on the transition: an account that is already exempt must stay
	# clear of ERPNext's native limit, including one exempted before this ran.
	# The helper no-ops when there is nothing to remove.
	if is_exempt:
		_clear_native_credit_limit(doc)

	if was_exempt != is_exempt:
		if is_exempt:
			_log(doc, _("Exempted from the Credit &amp; AR policy. Reason: {0}"))
		else:
			_log(doc, _("Returned to the Credit &amp; AR policy."))
			_restore(doc)

	_sync_hard_hold_case(doc)


def _sync_hard_hold_case(doc):
	"""An AR Case is opened only for Hard Hold — and whenever Credit Status
	lands on Hard Hold, a case must exist. The engines already pair the two by
	opening the case first and letting it set the status. This is the other
	direction: Credit Status is editable by hand (see customer_layout.py), so a
	human — or any other code path — setting it straight to Hard Hold must open
	the case too, or the status shows Hard Hold while nothing actually enforces
	it (``get_hold_type`` keys off ``custom_active_ar_case``, not this field).
	"""
	if doc.get("custom_credit_status") != utils.STATUS_HARD_HOLD:
		return
	if doc.get("custom_active_ar_case"):
		return
	if utils.is_policy_exempt(doc.name):
		return

	from cannabis_management.credit_and_ar import hold_engine

	hold_engine.ensure_active_case(
		customer=doc.name,
		internal_reason="Manual",
		trigger_details=_("Credit Status set to Hard Hold directly on the Customer record."),
		trigger_reason=doc.get("custom_hold_reason") or "",
	)


def _stamp_exemption(doc):
	"""An exempt account shows as exempt and carries no live hold state.

	The hold fields are cleared rather than left standing: `enforce_hold` already
	ignores exempt accounts, so a lingering "Hard Hold" would be a flag that
	blocks nothing — the worst kind, because people trust it.
	"""
	if doc.get("custom_credit_status") != utils.STATUS_EXEMPT:
		return

	doc.custom_hold_since = None
	doc.custom_active_ar_case = None


def _restore(doc):
	"""Un-exempting hands the account back to the engines."""
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
		sync_customer_from_cases,
	)

	sync_customer_from_cases(doc.name)


def _clear_native_credit_limit(doc):
	"""Drop ERPNext's own Customer Credit Limit rows for an exempt account.

	The module mirrors an approved line onto ERPNext's native Customer Credit
	Limit "for reporting" — but that mirror is not inert. get_credit_limit reads
	the customer's own row regardless of bypass_credit_limit_check, and that flag
	does not mean "never check": it means *do not check at the Sales Order, check
	at the Sales Invoice instead*. So a mirrored row lets the order through and
	then blocks the invoice with ERPNext's own popup — the one that invites Sales
	to email a list of people to raise the limit, which is exactly what the Credit
	Application process exists to prevent.

	An exempt account is outside this module, so the row it planted goes with the
	exemption. Customer Group and Company level limits are ERPNext's own
	configuration and are deliberately left alone.
	"""
	rows = frappe.get_all(
		"Customer Credit Limit",
		filters={"parent": doc.name, "parenttype": "Customer"},
		pluck="name",
	)
	if not rows:
		return

	frappe.db.delete("Customer Credit Limit", {"parent": doc.name, "parenttype": "Customer"})
	frappe.clear_document_cache("Customer", doc.name)
	doc.add_comment(
		"Info",
		_("Native credit limit removed: this account is exempt from the Credit &amp; AR policy."),
	)


def _log(doc, template: str):
	try:
		doc.add_comment(
			"Info",
			template.format(
				frappe.utils.escape_html(doc.get("custom_credit_policy_exempt_reason") or "")
			),
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Credit exemption comment failed")


@frappe.whitelist()
def get_exemption_state(customer: str):
	"""For the form banner."""
	row = (
		frappe.db.get_value(
			"Customer",
			customer,
			["custom_credit_status", "custom_credit_policy_exempt_reason"],
			as_dict=True,
		)
		or {}
	)
	return {
		"exempt": int(row.get("custom_credit_status") == utils.STATUS_EXEMPT),
		"reason": row.get("custom_credit_policy_exempt_reason"),
	}
