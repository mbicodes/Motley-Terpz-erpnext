"""App Home: each person's own queue.

Grouped by company, then by the stages that person's team flags own at that
company. Each row carries the one button that moves the order forward.
"""

import frappe

from cannabis_management.mt_dispatch import stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import team_flags
from cannabis_management.mt_dispatch.slack import blocks, client, identity

ROWS_PER_STAGE = 15

# flag -> stages it owns
OWNED = {
	stages.FULFILLMENT: [stages.RECEIVED, stages.AWAITING_CONVERSION, stages.PREPARING],
	stages.COMPLIANCE: [stages.PREPARED, stages.DN_READY],
	stages.APPROVER: [stages.AWAITING_RELEASE, stages.ON_HOLD],
	stages.FINANCE: [stages.AWAITING_RELEASE],
	stages.DISPATCH: [stages.RELEASED],
}

FORWARD = {
	stages.RECEIVED: "mt:start_preparing",
	stages.AWAITING_CONVERSION: "mt:new_conversion",
	stages.PREPARING: "mt:mark_prepared",
	stages.PREPARED: "mt:create_dn",
	stages.DN_READY: "mt:upload_manifest",
	stages.RELEASED: "mt:delivered",
	stages.ON_HOLD: "mt:resume",
}


def enabled_settings():
	return [
		frappe.get_cached_doc("Dispatch Company Settings", name)
		for name in frappe.get_all("Dispatch Company Settings", filters={"enabled": 1}, pluck="name", order_by="name")
	]


def forward_action(so, cfg, flags):
	stage = so.get("custom_logistic_status")
	if stage != stages.AWAITING_RELEASE:
		return FORWARD.get(stage)
	applies, _paid, _required, short = payment_status(so, cfg)
	if applies and short:
		if stages.FINANCE in flags:
			return "mt:record_payment"
		return "mt:override" if "can_override" in flags else None
	return "mt:release" if stages.APPROVER in flags else None


def build(user):
	sections = []
	for cfg in enabled_settings():
		flags = team_flags(user, cfg)
		if not flags:
			continue
		owned = []
		for flag in flags:
			for stage in OWNED.get(flag, []):
				if stage not in owned:
					owned.append(stage)
		owned.sort(key=stages.ALL_STAGES.index)

		stage_rows = []
		for stage in owned:
			names = frappe.get_all(
				"Sales Order",
				filters={"company": cfg.company, "docstatus": 1, "custom_logistic_status": stage},
				pluck="name",
				order_by="modified asc",
				limit=ROWS_PER_STAGE,
			)
			rows = []
			for name in names:
				so = frappe.get_doc("Sales Order", name)
				# Finance only cares about Awaiting Release orders that still owe money.
				if stage == stages.AWAITING_RELEASE and flags & {stages.APPROVER} == set() and stages.FINANCE in flags:
					applies, _p, _r, short = payment_status(so, cfg)
					if not (applies and short):
						continue
				rows.append((so, blocks.age_in_stage(name), forward_action(so, cfg, flags)))
			if rows:
				stage_rows.append((stage, rows))
		sections.append((cfg.company, stage_rows))
	return blocks.home_view(sections)


def publish(slack_user, user=None):
	user = user or identity.erp_user_for(slack_user)
	if not user:
		view = {"type": "home", "blocks": [blocks.section(identity.NOT_LINKED)]}
	else:
		view = build(user)
	client.views_publish(slack_user, view)


def on_app_home_opened(slack_user):
	publish(slack_user)
