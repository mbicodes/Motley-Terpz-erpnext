"""Whitelisted endpoints for the Credit & AR module.

Every endpoint is role-guarded server-side. The client buttons are convenience,
never the control.
"""

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from cannabis_management.credit_and_ar import credit_engine, utils

APPROVER_ROLES = ("Managing Director", "Ops Manager", "System Manager")

TODO_DESCRIPTION = "Approve Terms Sales Order {0} — {1}"


# ── guards ───────────────────────────────────────────────────────────────────


def _get_order(sales_order: str):
	doc = frappe.get_doc("Sales Order", sales_order)
	if utils.resolve_order_type(doc) != utils.ORDER_TYPE_TERMS:
		frappe.throw(
			_("{0} is not a Terms order — no approval is required.").format(sales_order),
			title=_("Not a Terms Order"),
		)
	return doc


def _require_approver():
	if not utils.has_any_role(*APPROVER_ROLES):
		frappe.throw(
			_(
				"Only the Managing Director or the Ops Manager can approve or reject "
				"Terms orders."
			),
			frappe.PermissionError,
			title=_("Not Authorised"),
		)


# ── endpoints ────────────────────────────────────────────────────────────────


@frappe.whitelist()
def request_terms_approval(sales_order: str):
	"""Send a Terms order to the MD and Ops Manager, and block its print."""
	doc = _get_order(sales_order)
	doc.check_permission("write")

	if doc.custom_approval_status == utils.APPROVAL_APPROVED:
		frappe.throw(_("{0} is already approved.").format(sales_order))

	doc.db_set(
		{
			"custom_approval_status": utils.APPROVAL_PENDING,
			"custom_terms_requested_on": now_datetime(),
			"custom_print_blocked": 1,
			"custom_terms_rejection_reason": None,
		},
		update_modified=False,
	)

	approvers = _approver_users()
	_create_todos(doc, approvers)
	_email_approval_request(doc, approvers)

	doc.add_comment(
		"Comment",
		_("Terms approval requested by {0}.").format(frappe.utils.get_fullname(frappe.session.user)),
	)

	return {"status": utils.APPROVAL_PENDING, "notified": approvers}


@frappe.whitelist()
def approve_terms(sales_order: str, notes: str | None = None):
	_require_approver()
	doc = _get_order(sales_order)

	if doc.custom_approval_status == utils.APPROVAL_APPROVED:
		return {"status": utils.APPROVAL_APPROVED}

	doc.db_set(
		{
			"custom_approval_status": utils.APPROVAL_APPROVED,
			"custom_terms_approved_by": frappe.session.user,
			"custom_terms_approved_on": now_datetime(),
			"custom_print_blocked": 0,
			"custom_terms_rejection_reason": None,
		},
		update_modified=False,
	)

	_close_todos(doc)
	_email_decision(doc, approved=True, note=notes)

	doc.add_comment(
		"Comment",
		_("Terms approved by {0}.{1}").format(
			frappe.utils.get_fullname(frappe.session.user),
			f" {frappe.utils.escape_html(notes)}" if notes else "",
		),
	)

	return {"status": utils.APPROVAL_APPROVED}


@frappe.whitelist()
def reject_terms(sales_order: str, reason: str):
	_require_approver()

	if not (reason or "").strip():
		frappe.throw(_("A reason is required to reject a Terms order."))

	doc = _get_order(sales_order)

	doc.db_set(
		{
			"custom_approval_status": utils.APPROVAL_REJECTED,
			"custom_terms_rejection_reason": reason,
			"custom_terms_approved_by": frappe.session.user,
			"custom_terms_approved_on": now_datetime(),
			# Print stays blocked — a rejected Terms order must not leave the building.
			"custom_print_blocked": 1,
		},
		update_modified=False,
	)

	_close_todos(doc)
	_email_decision(doc, approved=False, note=reason)

	doc.add_comment(
		"Comment",
		_("Terms rejected by {0}: {1}").format(
			frappe.utils.get_fullname(frappe.session.user), frappe.utils.escape_html(reason)
		),
	)

	return {"status": utils.APPROVAL_REJECTED}


@frappe.whitelist()
def release_ar_case(case_name: str, release_basis: str, notes: str | None = None):
	"""Lift a hold. Credit Finance only; every basis is verified live."""
	from cannabis_management.credit_and_ar import hold_engine

	return hold_engine.release_case(case_name, release_basis, notes)


@frappe.whitelist()
def raise_manual_case(
	customer: str,
	case_type: str,
	trigger_reason: str,
	trigger_details: str,
	company: str | None = None,
):
	"""Finance or the MD opening a case by hand — suspected fraud, insolvency signs."""
	from cannabis_management.credit_and_ar import hold_engine

	if not utils.has_any_role("Credit Finance", "Managing Director", "System Manager"):
		frappe.throw(
			_("Only Credit Finance or the Managing Director can open an AR Case."),
			frappe.PermissionError,
			title=_("Not Authorised"),
		)

	doc = hold_engine.create_case(
		customer=customer,
		case_type=case_type,
		trigger_reason=trigger_reason,
		trigger_details=trigger_details,
		company=company,
	)
	return {"name": doc.name, "case_type": doc.case_type, "status": doc.status}


@frappe.whitelist()
def refresh_ar_case(case_name: str):
	"""Recompute the live past-due figures on a case."""
	from cannabis_management.credit_and_ar.doctype.ar_case.ar_case import sync_customer_from_cases

	doc = frappe.get_doc("AR Case", case_name)
	doc.check_permission("read")

	snapshot = credit_engine.get_past_due_snapshot(doc.customer)
	frappe.db.set_value(
		"AR Case",
		case_name,
		{
			"past_due_amount": snapshot["past_due_amount"],
			"total_outstanding": snapshot["total_outstanding"],
			"max_days_past_due": snapshot["max_days_past_due"],
		},
		update_modified=False,
	)
	sync_customer_from_cases(doc.customer)
	return snapshot


@frappe.whitelist()
def get_credit_summary(customer: str, sales_order: str | None = None):
	"""Feed the Sales Order sidebar without a second round of queries."""
	summary = credit_engine.get_line_summary(customer, exclude_sales_order=sales_order)
	standing = (
		frappe.db.get_value(
			"Customer",
			customer,
			[
				"custom_credit_status",
				"custom_hold_type",
				"custom_payment_score",
				"custom_score_band",
				"custom_credit_terms_template",
				"custom_terms_valid_until",
			],
			as_dict=True,
		)
		or {}
	)
	summary.update(standing)
	summary["blocker"] = credit_engine.describe_line_blocker(customer)
	summary["freeze_active"] = int(utils.get_settings().company_freeze_active or 0)
	return summary


# ── helpers ──────────────────────────────────────────────────────────────────


def _approver_users() -> list[str]:
	"""The MD and the Ops Manager, falling back to role membership."""
	named = [utils.routed_user("managing_director"), utils.routed_user("ops_manager")]
	users = utils.dedupe_recipients(named)
	if users:
		return users

	return utils.dedupe_recipients(
		utils.users_with_role("Managing Director"), utils.users_with_role("Ops Manager")
	)


def _create_todos(doc, approvers: list[str]):
	for user in approvers:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"reference_type": "Sales Order",
				"reference_name": doc.name,
				"description": TODO_DESCRIPTION.format(doc.name, doc.customer),
				"priority": "High",
				"status": "Open",
			}
		).insert(ignore_permissions=True)


def _close_todos(doc):
	open_todos = frappe.get_all(
		"ToDo",
		filters={
			"reference_type": "Sales Order",
			"reference_name": doc.name,
			"status": "Open",
		},
		pluck="name",
	)
	for name in open_todos:
		frappe.db.set_value("ToDo", name, "status", "Closed", update_modified=False)


def _email_approval_request(doc, approvers: list[str]):
	if not approvers:
		frappe.logger("credit_and_ar").warning(
			f"No approver configured — {doc.name} raised no approval email."
		)
		return

	summary = credit_engine.get_line_summary(doc.customer, exclude_sales_order=doc.name)
	standing = (
		frappe.db.get_value(
			"Customer",
			doc.customer,
			["custom_payment_score", "custom_score_band", "custom_credit_status"],
			as_dict=True,
		)
		or {}
	)

	application = doc.custom_credit_application
	application_html = (
		utils.doc_link("Credit Application", application)
		if application
		else _("<span style='color:#b91c1c;'>No approved credit application on file</span>")
	)

	rows = [
		(_("Customer"), frappe.utils.escape_html(doc.customer)),
		(_("Order Total"), utils.fmt_currency(doc.grand_total, doc.currency)),
		(_("Requested Terms"), frappe.utils.escape_html(doc.payment_terms_template or "")),
		(_("Current Exposure"), utils.fmt_currency(summary["total"], doc.currency)),
		(_("Approved Limit"), utils.fmt_currency(summary["approved_limit"], doc.currency)),
		(_("Available Line"), utils.fmt_currency(summary["available_line"], doc.currency)),
		(
			_("Payment Score"),
			f"{standing.get('custom_payment_score') or _('No score yet')} "
			f"({standing.get('custom_score_band') or _('Insufficient History')})",
		),
		(_("Credit Status"), standing.get("custom_credit_status") or utils.STATUS_COD),
		(_("Credit Application"), application_html),
		(_("Requested By"), frappe.utils.get_fullname(doc.owner)),
	]

	if flt(doc.custom_required_deposit):
		rows.append(
			(
				_("Deposit Required"),
				utils.fmt_currency(doc.custom_required_deposit, doc.currency),
			)
		)

	table = "".join(
		f"<tr><td style='padding:3px 14px 3px 0;color:#666;'>{label}</td>"
		f"<td><b>{value}</b></td></tr>"
		for label, value in rows
	)

	message = _(
		"""
		<p>A <b>Terms</b> Sales Order needs your approval. It cannot be submitted or
		printed until you approve it.</p>
		<table style="font-size:14px;margin:8px 0;">{table}</table>
		<p style="margin-top:16px;">
			<a href="{url}" style="display:inline-block;background:#2563eb;color:#fff;
			   text-decoration:none;padding:9px 18px;border-radius:6px;font-weight:600;">
			   Open Sales Order</a>
		</p>
		<p style="color:#666;font-size:13px;">Open the order and use
		<b>Approve Terms</b> or <b>Reject Terms</b> in the toolbar.</p>
		"""
	).format(table=table, url=frappe.utils.get_url(f"/app/sales-order/{doc.name}"))

	_sendmail(
		approvers,
		_("Terms approval needed — {0} ({1})").format(doc.name, doc.customer),
		message,
		doc,
	)


def _email_decision(doc, approved: bool, note: str | None):
	recipients = utils.dedupe_recipients(doc.owner)
	if not recipients:
		return

	if approved:
		subject = _("Terms approved — {0}").format(doc.name)
		body = _(
			"<p>Sales Order <b>{0}</b> for <b>{1}</b> has been approved on "
			"<b>{2}</b> terms by {3}. It can now be submitted and printed.</p>"
		).format(
			doc.name,
			frappe.utils.escape_html(doc.customer),
			frappe.utils.escape_html(doc.payment_terms_template or ""),
			frappe.utils.get_fullname(frappe.session.user),
		)
	else:
		subject = _("Terms rejected — {0}").format(doc.name)
		body = _(
			"<p>Sales Order <b>{0}</b> for <b>{1}</b> was <b>rejected</b> by {2}.</p>"
			"<p>Reason: {3}</p>"
			"<p>The order remains blocked from submit and print. Re-type it as COD, "
			"or resolve the reason above and request approval again.</p>"
		).format(
			doc.name,
			frappe.utils.escape_html(doc.customer),
			frappe.utils.get_fullname(frappe.session.user),
			frappe.utils.escape_html(note or _("not recorded")),
		)

	if note and approved:
		body += f"<p>{_('Note')}: {frappe.utils.escape_html(note)}</p>"

	body += f"<p>{utils.doc_link('Sales Order', doc.name)}</p>"

	_sendmail(recipients, subject, body, doc)


def _sendmail(recipients, subject, message, doc):
	try:
		frappe.sendmail(
			recipients=recipients,
			subject=subject,
			message=message,
			reference_doctype="Sales Order",
			reference_name=doc.name,
		)
	except Exception:
		frappe.log_error(frappe.get_traceback(), "Terms approval notification failed")
