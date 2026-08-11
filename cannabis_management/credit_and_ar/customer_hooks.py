"""Customer-side handling for the policy exemption.

Ticking `custom_credit_policy_exempt` carves an account out of this module
entirely. Because the flag is read live by every engine, nothing has to be
migrated when it is toggled — but the account's *displayed* state does need to
follow, so the Red List and the scorecard do not keep showing a hold that is no
longer enforced.
"""

import frappe
from frappe import _

from cannabis_management.credit_and_ar import utils


def validate(doc, method=None):
	_stamp_exemption(doc)


def on_update(doc, method=None):
	previous = doc.get_doc_before_save()
	was_exempt = bool(previous.get("custom_credit_policy_exempt")) if previous else False
	is_exempt = bool(doc.get("custom_credit_policy_exempt"))

	if was_exempt == is_exempt:
		return

	if is_exempt:
		_log(doc, _("Exempted from the Credit &amp; AR policy. Reason: {0}"))
	else:
		_log(doc, _("Returned to the Credit &amp; AR policy."))
		_restore(doc)


def _stamp_exemption(doc):
	"""An exempt account shows as exempt and carries no live hold state.

	The hold fields are cleared rather than left standing: `enforce_hold` already
	ignores exempt accounts, so a lingering "Hard Hold" would be a flag that
	blocks nothing — the worst kind, because people trust it.
	"""
	if not doc.get("custom_credit_policy_exempt"):
		return

	doc.custom_credit_status = utils.STATUS_EXEMPT
	doc.custom_on_hold = 0
	doc.custom_hold_type = utils.HOLD_NONE
	doc.custom_hold_since = None
	doc.custom_active_ar_case = None


def _restore(doc):
	"""Un-exempting hands the account back to the engines."""
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import (
		sync_customer_from_cases,
	)

	sync_customer_from_cases(doc.name)


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
			["custom_credit_policy_exempt", "custom_credit_policy_exempt_reason"],
			as_dict=True,
		)
		or {}
	)
	return {
		"exempt": int(row.get("custom_credit_policy_exempt") or 0),
		"reason": row.get("custom_credit_policy_exempt_reason"),
	}
