"""Whitelisted entry points: the Sales Order form's stage buttons, and the
lookups the pickers need. The Slack layer calls flow.transition() directly
after frappe.set_user(), so it does not come through here.
"""

import frappe
from frappe import _

from cannabis_management.mt_dispatch import flow, gates, stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import get_company_settings, team_flags


@frappe.whitelist()
def act(sales_order, action, expected_stage=None, payload=None):
	"""Run one transition as the logged-in user."""
	return flow.transition(sales_order, action, expected_stage, payload, source="ERP")


@frappe.whitelist()
def board(sales_order):
	"""Everything the form needs to draw its buttons: current stage, what this
	user may do from here, and the payment position."""
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
		# Same rule as the Slack buttons: Release only when paid, the override
		# only when not. Payment is only worth offering while money is owed.
		if action == "release" and unpaid:
			continue
		if action in ("release_override", "record_payment") and not unpaid:
			continue
		actions.append(
			{"action": action, "label": t.label, "reason_required": t.reason_required, "to": t.resolve_to(so)}
		)

	return {
		"enabled": True,
		"stage": current,
		"actions": actions,
		"payment": {
			"gated": applies,
			"paid": paid,
			"required": required,
			"short": short,
		},
	}


@frappe.whitelist()
def tag_options(item_code, warehouse):
	"""Metric Tags holding stock of this item here, for the picker."""
	return gates.tags_with_stock(item_code, warehouse)


@frappe.whitelist()
def line_tag_options(sales_order):
	"""Tag choices per Sales Order line, for the Delivery Note form."""
	so = frappe.get_doc("Sales Order", sales_order)
	so.check_permission("read")

	out = {}
	for row in so.items:
		warehouse = row.warehouse or so.set_warehouse
		out[row.name] = {
			"item_code": row.item_code,
			"qty": row.qty,
			"warehouse": warehouse,
			"tags": gates.tags_with_stock(row.item_code, warehouse) if warehouse else [],
		}
	return out


@frappe.whitelist()
def stage_counts(company=None):
	"""Open orders per stage. Backs /board and the workspace number cards."""
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
