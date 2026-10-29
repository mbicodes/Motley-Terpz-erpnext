import frappe
from frappe import _

from cannabis_management.mt_dispatch import flow, gates, stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import get_company_settings, team_flags


@frappe.whitelist()
def act(sales_order, action, expected_stage=None, payload=None):
	return flow.transition(sales_order, action, expected_stage, payload, source="ERP")


@frappe.whitelist()
def board(sales_order):
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")

	cfg = get_company_settings(so.company)
	if not cfg:
		return {"enabled": False}

	current = so.get(flow.STAGE_FIELD)
	held = team_flags(frappe.session.user, cfg)
	is_admin = frappe.session.user == "Administrator"

	applies, paid, required, short = payment_status(so, cfg)
	unpaid = bool(applies and short)

	actions = []
	for action, t in flow.TRANSITIONS.items():
		if current not in t.from_stages:
			continue
		if t.flags and not is_admin and not (held & set(t.flags)):
			continue
		if action == "release" and unpaid and not is_admin:
			continue
		if action in ("release_override", "record_payment") and not unpaid:
			continue
		actions.append(
			{
				"action": action,
				"label": t.label,
				"reason_required": t.reason_required,
				"to": t.resolve_to(so),
				"blocked": blocked_reason(so, cfg, action, t, is_admin),
			}
		)

	notes = []
	if not any(row.approver for row in cfg.team or []):
		notes.append(_("No approver is set for {0}, so no order can be released.").format(so.company))

	return {
		"enabled": True,
		"stage": current,
		"actions": actions,
		"notes": notes,
		"is_admin": is_admin,
		"payment": {
			"gated": applies,
			"paid": paid,
			"required": required,
			"short": short,
		},
	}


def blocked_reason(so, cfg, action, t, is_admin=False):
	if is_admin:
		if action in ("upload_manifest", "release", "release_override") and not gates.draft_delivery_note(so.name):
			return _("No draft Delivery Note for this order.")
		return None
	try:
		if action == "upload_manifest":
			if not gates.draft_delivery_note(so.name):
				return _("No draft Delivery Note for this order.")
			return None
		for guard in t.guards:
			guard(so, cfg, None)
	except gates.GateError as e:
		return frappe.utils.strip_html(str(e))
	return None


@frappe.whitelist()
def stage_counts(company=None):
	filters = {"docstatus": 1, "custom_logistic_status": ["in", stages.ALL_STAGES]}
	if company:
		filters["company"] = company

	rows = frappe.get_all(
		"Sales Order",
		filters=filters,
		fields=["custom_logistic_status as stage", "count(name) as n"],
		group_by="custom_logistic_status",
	)
	counts = {r.stage: r.n for r in rows}
	return [{"stage": s, "count": counts.get(s, 0)} for s in stages.ALL_STAGES]
