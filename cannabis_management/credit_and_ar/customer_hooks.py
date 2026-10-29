import frappe
from frappe import _

from cannabis_management.credit_and_ar import customer_contact_rules, utils


def validate(doc, method=None):
	_stamp_exemption(doc)
	customer_contact_rules.validate_customer(doc)


def on_update(doc, method=None):
	previous = doc.get_doc_before_save()
	was_exempt = (previous.get("custom_credit_status") == utils.STATUS_EXEMPT) if previous else False
	is_exempt = doc.get("custom_credit_status") == utils.STATUS_EXEMPT

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
	if doc.get("custom_credit_status") != utils.STATUS_EXEMPT:
		return

	doc.custom_hold_since = None
	doc.custom_active_ar_case = None


def _restore(doc):
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
		sync_customer_from_cases,
	)

	sync_customer_from_cases(doc.name)


def _clear_native_credit_limit(doc):
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
