"""The state machine.

Sales Order.custom_logistic_status is written here and nowhere else. Every
move goes through transition(), which locks the row, checks the stage, checks
the caller's authority at that company, runs the gates, performs the effect and
appends an audit row. guard_stage_field rejects any write that skipped it.
"""

import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime

from cannabis_management.mt_dispatch import builders, gates, notify, stages
from cannabis_management.mt_dispatch.gates import GateError, StaleAction
from cannabis_management.mt_dispatch.settings import get_company_settings, is_administrator, require_team_flag
from cannabis_management.mt_dispatch.stages import (  # re-exported for callers
	ALL_STAGES,
	AWAITING_CONVERSION,
	AWAITING_RELEASE,
	CANCELLED,
	CLOSED_OUT,
	DN_READY,
	ON_HOLD,
	PREPARED,
	PREPARING,
	RECEIVED,
	RELEASED,
	TERMINAL_STAGES,
)

STAGE_FIELD = "custom_logistic_status"


class Transition:
	def __init__(
		self,
		action,
		label,
		from_stages,
		to,
		flags=(),
		guards=(),
		effect=None,
		reason_required=False,
	):
		self.action = action
		self.label = label
		self.from_stages = tuple(from_stages)
		self.to = to
		self.flags = tuple(flags)
		self.guards = tuple(guards)
		self.effect = effect
		self.reason_required = reason_required

	def resolve_to(self, so):
		return self.to(so) if callable(self.to) else self.to


# ── effects ──────────────────────────────────────────────────────────────────


def _effect_flag_conversion(so, cfg, payload):
	so.db_set("custom_conversion_required", 1, update_modified=False)


def _effect_hold(so, cfg, payload):
	so.db_set(
		{
			"custom_hold_from_stage": so.get(STAGE_FIELD),
			"custom_hold_reason": (payload or {}).get("reason"),
		},
		update_modified=False,
	)


def _effect_resume(so, cfg, payload):
	so.db_set({"custom_hold_from_stage": None, "custom_hold_reason": None}, update_modified=False)


def _resume_to(so):
	"""Back to wherever the hold came from. Orders held before the field
	existed, or with a stage since removed, land on Order Received."""
	previous = so.get("custom_hold_from_stage")
	return previous if previous in stages.ALL_STAGES else RECEIVED


def _effect_release(so, cfg, payload):
	dn_name = gates.draft_delivery_note(so.name)
	if not dn_name:
		raise GateError(_("No draft Delivery Note to submit for this order."))

	dn = frappe.get_doc("Delivery Note", dn_name)
	dn.submit()

	so.db_set(
		{"custom_released_by": frappe.session.user, "custom_released_on": now_datetime()},
		update_modified=False,
	)
	return dn_name


def _effect_release_override(so, cfg, payload):
	reason = ((payload or {}).get("reason") or "").strip()
	so.db_set("custom_release_override_reason", reason, update_modified=False)
	return _effect_release(so, cfg, payload)


def _effect_mark_delivered(so, cfg, payload):
	file_url = (payload or {}).get("file_url")
	if file_url:
		dn_names = gates.delivery_notes_for(so.name)
		if dn_names:
			builders.attach_file(file_url, "Delivery Note", dn_names[0])


# ── the table ────────────────────────────────────────────────────────────────

NON_TERMINAL = tuple(s for s in stages.ALL_STAGES if s not in TERMINAL_STAGES)

TRANSITIONS = {
	t.action: t
	for t in [
		Transition(
			"flag_conversion", "flag for conversion",
			from_stages=[RECEIVED], to=AWAITING_CONVERSION,
			flags=[stages.FULFILLMENT],
			guards=[lambda so, cfg, p: (
				None if cfg.conversions_enabled
				else _raise(_("Conversions are switched off for {0}.").format(so.company))
			)],
			effect=_effect_flag_conversion,
		),
		Transition(
			"start_preparing", "start preparing",
			from_stages=[RECEIVED], to=PREPARING,
			flags=[stages.FULFILLMENT],
		),
		Transition(
			"create_conversion", "create a Conversion Entry",
			from_stages=[AWAITING_CONVERSION, PREPARING], to=None,
			flags=[stages.FULFILLMENT],
			effect=builders.make_conversion_entry,
		),
		Transition(
			"mark_prepared", "mark prepared",
			from_stages=[PREPARING], to=PREPARED,
			flags=[stages.FULFILLMENT],
			guards=[gates.conversions_complete],
		),
		Transition(
			"create_delivery_note", "create the Delivery Note",
			from_stages=[PREPARED], to=DN_READY,
			flags=[stages.COMPLIANCE],
			guards=[gates.one_delivery_note, gates.tags_set],
			effect=builders.build_delivery_note,
		),
		Transition(
			"upload_manifest", "upload the manifest",
			from_stages=[DN_READY], to=AWAITING_RELEASE,
			flags=[stages.COMPLIANCE],
			guards=[gates.manifest_present],
			effect=builders.attach_manifest,
		),
		Transition(
			"record_payment", "record a payment",
			from_stages=NON_TERMINAL, to=None,
			flags=[stages.FINANCE],
			effect=builders.make_payment_entry,
		),
		Transition(
			"release", "release",
			from_stages=[AWAITING_RELEASE], to=RELEASED,
			flags=[stages.APPROVER],
			guards=[gates.manifest_present, gates.paid],
			effect=_effect_release,
		),
		Transition(
			"release_override", "release with an override",
			from_stages=[AWAITING_RELEASE], to=RELEASED,
			flags=["can_override"],
			guards=[gates.manifest_present],
			effect=_effect_release_override,
			reason_required=True,
		),
		Transition(
			"mark_delivered", "confirm delivery",
			from_stages=[RELEASED], to=CLOSED_OUT,
			flags=[stages.DISPATCH, stages.COMPLIANCE, stages.APPROVER],
			effect=_effect_mark_delivered,
		),
		Transition(
			"hold", "put on hold",
			from_stages=[s for s in NON_TERMINAL if s != ON_HOLD], to=ON_HOLD,
			flags=list(stages.ALL_FLAGS),
			effect=_effect_hold,
			reason_required=True,
		),
		Transition(
			"resume", "resume",
			from_stages=[ON_HOLD], to=_resume_to,
			flags=[stages.APPROVER],
			effect=_effect_resume,
		),
	]
}


def _raise(message):
	raise GateError(message)


# ── the one way in ───────────────────────────────────────────────────────────


def transition(sales_order, action, expected_stage=None, payload=None, source="ERP"):
	"""Move an order, or explain why not.

	Runs as frappe.session.user. Slack handlers call frappe.set_user() first,
	so owner, modified_by and version history all name the real person.
	"""
	t = TRANSITIONS.get(action)
	if not t:
		raise GateError(_("Unknown dispatch action {0}.").format(action))

	payload = _as_dict(payload)

	# for_update takes a row lock, so two approvers clicking Release at the
	# same moment queue up rather than both submitting the Delivery Note.
	so = frappe.get_doc("Sales Order", sales_order, for_update=True)

	cfg = get_company_settings(so.company)
	if not cfg:
		raise GateError(_("{0} is not set up for dispatch.").format(so.company))

	current = so.get(STAGE_FIELD)

	if expected_stage and current != expected_stage:
		raise StaleAction(stale_message(so))

	if current not in t.from_stages:
		raise GateError(_("Can't {0} from {1}.").format(t.label, current or _("no stage")))

	if t.reason_required and not (payload.get("reason") or "").strip():
		raise GateError(_("A reason is required to {0}.").format(t.label))

	require_team_flag(cfg, frappe.session.user, t.flags)

	# Administrator is exempt from the gates, as from the team flags.
	if not is_administrator():
		for guard in t.guards:
			guard(so, cfg, payload)

	# Resolved before the effect runs, not after: `resume` reads its target
	# stage out of custom_hold_from_stage, and its own effect is what clears
	# that field. Any target that depends on document state must be decided
	# from the state the guards just approved.
	to = t.resolve_to(so)

	frappe.flags.mt_dispatch = action
	try:
		result = t.effect(so, cfg, payload) if t.effect else None
		if to:
			set_stage(so, to, action, source, note=payload.get("reason"))
	finally:
		frappe.flags.mt_dispatch = None

	notify.enqueue(
		"cannabis_management.mt_dispatch.notify.on_transition",
		sales_order=so.name,
		action=action,
		source=source,
		enqueue_after_commit=True,
		queue="short",
	)
	return result


def set_stage(so, to, action, source="System", note=None, user=None):
	"""Write the stage and append the audit row. Only transition() and the
	document hooks below call this."""
	previous = so.get(STAGE_FIELD)
	if previous == to and action != "backfill":
		return

	frappe.flags.mt_dispatch = frappe.flags.get("mt_dispatch") or action
	try:
		so.db_set(STAGE_FIELD, to, update_modified=False)
	finally:
		if frappe.flags.get("mt_dispatch") == action:
			frappe.flags.mt_dispatch = None

	so.set(STAGE_FIELD, to)
	_append_log(so, previous, to, action, source, note, user)


def _append_log(so, from_stage, to_stage, action, source, note, user=None):
	last_idx = (
		frappe.db.sql(
			"""select coalesce(max(idx), 0) from `tabDispatch Stage Log`
			   where parent = %s and parenttype = 'Sales Order'""",
			so.name,
		)[0][0]
		or 0
	)
	row = frappe.new_doc("Dispatch Stage Log")
	row.update(
		{
			"parent": so.name,
			"parenttype": "Sales Order",
			"parentfield": "custom_stage_log",
			"idx": last_idx + 1,
			"from_stage": from_stage,
			"to_stage": to_stage,
			"action": action,
			"user": user or frappe.session.user,
			"source": source,
			"at": now_datetime(),
			"note": note,
		}
	)
	row.insert(ignore_permissions=True)


def last_log_row(so):
	rows = frappe.get_all(
		"Dispatch Stage Log",
		filters={"parent": so.name, "parenttype": "Sales Order"},
		fields=["user", "at", "to_stage"],
		order_by="idx desc",
		limit=1,
	)
	return rows[0] if rows else None


def _who_last(so):
	row = last_log_row(so)
	if not row:
		return ""
	name = frappe.db.get_value("User", row.user, "full_name") or row.user
	return _(" by {0} at {1}").format(name, frappe.utils.format_datetime(row.at, "d MMM HH:mm"))


def stale_message(so):
	"""What a late click is told: who got there first."""
	current = so.get(STAGE_FIELD)
	if current == RELEASED:
		return _("Already released{0}.").format(_who_last(so))
	return _("Already moved to {0}{1}.").format(current or _("no stage"), _who_last(so))


def _as_dict(payload):
	if not payload:
		return {}
	if isinstance(payload, str):
		return json.loads(payload)
	return dict(payload)


# ── document hooks ───────────────────────────────────────────────────────────


def guard_stage_field(doc, method=None):
	"""Nothing edits the stage except this module -- for companies on dispatch.

	A company with no enabled Dispatch Company Settings has no buttons to go
	through, so its people set Logistic Status by hand like any other field.
	"""
	if not get_company_settings(doc.company):
		return
	if not doc.has_value_changed(STAGE_FIELD) or frappe.flags.get("mt_dispatch"):
		return
	if is_administrator():
		# Administrator may set the stage by hand; it still goes on the audit
		# trail, and into the order's Slack thread like any other move.
		before = doc.get_doc_before_save()
		_append_log(doc, before.get(STAGE_FIELD) if before else None, doc.get(STAGE_FIELD), "admin_set", "ERP", None)
		notify.enqueue(
			"cannabis_management.mt_dispatch.notify.on_transition",
			sales_order=doc.name,
			action="admin_set",
			source="ERP",
			enqueue_after_commit=True,
			queue="short",
		)
		return
	frappe.throw(
		_("Stage changes go through the dispatch buttons."),
		exc=GateError,
		title=_("Dispatch Flow"),
	)


def enter_flow(so, source="System"):
	"""Put a submitted order on the board, if it is allowed on and isn't already."""
	cfg = get_company_settings(so.company)
	if not cfg:
		return False
	if so.docstatus != 1:
		return False
	# On the board means the flow put it there, not that the field holds a
	# stage: Logistic Status is editable on a draft, so a new order can arrive
	# at submit already reading "Order Received" without ever having entered
	# (no stage log, no Slack thread). Such a value is dropped and the order
	# enters properly below.
	on_board = frappe.db.exists("Dispatch Stage Log", {"parent": so.name, "parenttype": "Sales Order"})
	if on_board and so.get(STAGE_FIELD) in stages.ALL_STAGES:
		return False

	try:
		gates.ready_to_start(so, cfg)
	except GateError:
		return False

	if not on_board:
		so.set(STAGE_FIELD, None)
	set_stage(so, RECEIVED, "enter_flow", source)
	notify.enqueue(
		"cannabis_management.mt_dispatch.notify.on_transition",
		sales_order=so.name,
		action="enter_flow",
		enqueue_after_commit=True,
		queue="short",
	)
	return True


def on_so_submit(doc, method=None):
	enter_flow(doc, source="System")


def on_so_update(doc, method=None):
	"""Covers an order edited the ordinary way after submit.

	This does NOT catch credit approval: credit_and_ar.api.approve_terms
	writes with db_set, which runs no document events at all. That path calls
	on_terms_approved() directly.
	"""
	enter_flow(doc, source="System")


def on_terms_approved(sales_order):
	"""Called by the credit module the moment a Terms order is approved."""
	if not frappe.db.exists("Sales Order", sales_order):
		return
	enter_flow(frappe.get_doc("Sales Order", sales_order), source="System")


def on_so_cancel(doc, method=None):
	cfg = get_company_settings(doc.company)
	if not cfg or doc.get(STAGE_FIELD) not in stages.ALL_STAGES:
		return

	for dn_name in gates.delivery_notes_for(doc.name, docstatus=0):
		frappe.delete_doc("Delivery Note", dn_name, ignore_permissions=True, delete_permanently=False)

	set_stage(doc, CANCELLED, "cancel", "System")
	notify.enqueue(
		"cannabis_management.mt_dispatch.notify.on_transition",
		sales_order=doc.name,
		action="cancel",
		enqueue_after_commit=True,
		queue="short",
	)


def on_conversion_submit(doc, method=None):
	"""The last outstanding conversion moves the order on by itself."""
	_sync_conversion(doc)


def on_conversion_cancel(doc, method=None):
	_sync_conversion(doc)


def _sync_conversion(ce):
	if not ce.get("sales_order"):
		return
	if not frappe.db.exists("Sales Order", ce.sales_order):
		return

	so = frappe.get_doc("Sales Order", ce.sales_order)
	cfg = get_company_settings(so.company)
	if not cfg or so.get(STAGE_FIELD) not in (AWAITING_CONVERSION, PREPARING):
		return

	complete = True
	try:
		gates.conversions_complete(so, cfg)
	except GateError:
		complete = False

	if not complete or so.get(STAGE_FIELD) != AWAITING_CONVERSION:
		# No stage move. The thread still hears about it: events.on_ce_change
		# posts the entry itself -- who, what into what, "2 of 3 submitted".
		return

	set_stage(so, PREPARING, "conversions_done", "System")
	notify.enqueue(
		"cannabis_management.mt_dispatch.notify.on_transition",
		sales_order=so.name,
		action="conversions_done",
		enqueue_after_commit=True,
		queue="short",
	)


def on_dn_cancel(doc, method=None):
	"""A Delivery Note cancelled after release sends the order back to Prepared."""
	for so_name, _cfg in gates._governed_orders(doc):
		so = frappe.get_doc("Sales Order", so_name)
		if so.get(STAGE_FIELD) not in (RELEASED, CLOSED_OUT):
			continue
		set_stage(so, PREPARED, "dn_cancelled", "System")
		notify.enqueue(
			"cannabis_management.mt_dispatch.notify.on_transition",
			sales_order=so_name,
			action="dn_cancelled",
			enqueue_after_commit=True,
			queue="short",
		)


# Stages before the Delivery Note exists, and before it is submitted.
BEFORE_DN = (RECEIVED, AWAITING_CONVERSION, PREPARING, PREPARED)
BEFORE_RELEASE = BEFORE_DN + (DN_READY, AWAITING_RELEASE, ON_HOLD)


def dn_after_insert(doc, method=None):
	"""A note made outside the flow puts its order at Delivery Note Ready."""
	if frappe.flags.get("mt_dispatch"):
		return
	for so_name, _cfg in gates._governed_orders(doc):
		so = frappe.get_doc("Sales Order", so_name)
		if so.get(STAGE_FIELD) in BEFORE_DN:
			set_stage(so, DN_READY, "admin_delivery_note", "ERP")


def dn_on_submit(doc, method=None):
	"""A note submitted outside the flow releases its order."""
	if frappe.flags.get("mt_dispatch"):
		return
	for so_name, _cfg in gates._governed_orders(doc):
		so = frappe.get_doc("Sales Order", so_name)
		if so.get(STAGE_FIELD) not in BEFORE_RELEASE:
			continue
		so.db_set(
			{"custom_released_by": frappe.session.user, "custom_released_on": now_datetime()},
			update_modified=False,
		)
		set_stage(so, RELEASED, "admin_release", "ERP", note=_("{0} submitted by hand").format(doc.name))
		notify.enqueue(
			"cannabis_management.mt_dispatch.notify.on_transition",
			sales_order=so_name,
			action="release",
			enqueue_after_commit=True,
			queue="short",
		)
