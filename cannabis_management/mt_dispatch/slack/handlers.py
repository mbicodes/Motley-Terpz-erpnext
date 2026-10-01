"""The work behind every click, as background jobs, and the modal parsing
the endpoints validate with inline.

Slack wants an answer within three seconds, so endpoints only verify, check
the cheap things and enqueue. The job looks up the ERP user, becomes them with
frappe.set_user() -- so owner, modified_by and version history name the real
person -- and runs flow.transition(). A GateError goes back to whoever clicked
as an ephemeral message; nothing is posted to the channel.
"""

import json

import frappe
from frappe.utils import flt

from cannabis_management.mt_dispatch import builders, flow, gates
from cannabis_management.mt_dispatch.gates import GateError, StaleAction
from cannabis_management.mt_dispatch.settings import get_company_settings, require_team_flag
from cannabis_management.mt_dispatch.slack import blocks, client, identity
from cannabis_management.mt_dispatch.slack.client import SlackError

# modal callback_id -> transition it runs on submit
MODAL_TRANSITION = {
	"mt_conversion": "create_conversion",
	"mt_delivery_note": "create_delivery_note",
	"mt_manifest": "upload_manifest",
	"mt_payment": "record_payment",
	"mt_override": "release_override",
	"mt_hold": "hold",
	"mt_delivered": "mark_delivered",
}

MANIFEST_DIGITS = gates.MANIFEST_DIGITS
MIN_OVERRIDE_REASON = 15


# ── telling the clicker ──────────────────────────────────────────────────────


def tell(slack_user, text, response_url=None, channel=None, thread_ts=None):
	"""Ephemeral to one person: through response_url when there is one, as an
	ephemeral in the source channel next, and as a DM when neither exists
	(App Home clicks and modal submissions)."""
	try:
		if response_url:
			client.respond(response_url, text)
			return
		if channel and not channel.startswith("D"):
			client.post_ephemeral(channel, slack_user, text, thread_ts=thread_ts)
			return
		client.post(client.open_dm(slack_user), text)
	except Exception:
		frappe.log_error(f"MT Dispatch: could not tell {slack_user}: {text}", "MT Dispatch Slack")


def _message(exc):
	return frappe.utils.strip_html(str(exc)) or exc.__class__.__name__


# ── pre-checks run inline, before a modal opens ──────────────────────────────


def precheck(user, sales_order, action, expected_stage):
	"""None when `user` may start `action` on the order now, else why not."""
	if not frappe.db.exists("Sales Order", sales_order):
		return f"{sales_order} no longer exists."
	so = frappe.get_doc("Sales Order", sales_order)
	cfg = get_company_settings(so.company)
	if not cfg:
		return f"{so.company} is not set up for dispatch."
	t = flow.TRANSITIONS[action]
	current = so.get(flow.STAGE_FIELD)
	if expected_stage and current != expected_stage:
		return flow.stale_message(so)
	if current not in t.from_stages:
		return f"Can't {t.label} from {current or 'no stage'}."
	try:
		require_team_flag(cfg, user, t.flags)
	except GateError as e:
		return _message(e)
	return None


# ── jobs ─────────────────────────────────────────────────────────────────────


def run_action(slack_user, action, sales_order, expected_stage=None, payload=None,
			   response_url=None, channel=None, thread_ts=None, files=None, erp_user=None):
	"""Run one transition as the person who clicked."""
	user = erp_user or identity.erp_user_for(slack_user)
	if not user:
		tell(slack_user, identity.NOT_LINKED, response_url, channel, thread_ts)
		return

	frappe.set_user(user)
	payload = dict(payload or {})
	try:
		for key, file_obj in (files or {}).items():
			payload[key] = client.download_to_file(file_obj, *_attach_target(action, sales_order))
		flow.transition(sales_order, action, expected_stage, payload, source="Slack")
		frappe.db.commit()
	except (StaleAction, GateError, frappe.ValidationError, frappe.PermissionError, SlackError) as e:
		frappe.db.rollback()
		frappe.clear_messages()
		tell(slack_user, f":no_entry: {_message(e)}", response_url, channel, thread_ts)
		reset_status(sales_order)
	except Exception as e:
		frappe.db.rollback()
		frappe.log_error(f"MT Dispatch: {action} on {sales_order} by {user}", "MT Dispatch Slack")
		tell(slack_user, f":warning: Something went wrong: {_message(e)}", response_url, channel, thread_ts)
	finally:
		frappe.set_user("Administrator")


def _attach_target(action, sales_order):
	"""Where a Slack upload lands. Manifest and delivery photos belong on the
	Delivery Note; a payment photo is attached to the Payment Entry later."""
	if action in ("upload_manifest", "mark_delivered"):
		dn = gates.draft_delivery_note(sales_order) or next(iter(gates.delivery_notes_for(sales_order)), None)
		if dn:
			return ("Delivery Note", dn)
	return (None, None)


def reset_status(sales_order):
	"""Redraw the thread parent from the ERP, so a status dropdown that was
	picked but did not go through shows the order's real stage again."""
	from cannabis_management.mt_dispatch.slack import post

	try:
		frappe.set_user("Administrator")
		so = frappe.get_doc("Sales Order", sales_order)
		cfg = get_company_settings(so.company)
		if cfg:
			post.refresh_parent(so, cfg)
	except Exception:
		frappe.log_error(f"MT Dispatch: could not reset the status of {sales_order}", "MT Dispatch Slack")


def publish_home(slack_user):
	from cannabis_management.mt_dispatch.slack import home

	home.publish(slack_user)


def say(slack_user, text, response_url=None, channel=None):
	tell(slack_user, text, response_url, channel)


# ── modal state ──────────────────────────────────────────────────────────────


def state_value(values, block_id):
	"""The value of the one element in an input block, whatever its type."""
	element = next(iter((values.get(block_id) or {}).values()), None)
	if not element:
		return None
	kind = element.get("type")
	if kind in ("static_select", "external_select", "radio_buttons"):
		return (element.get("selected_option") or {}).get("value")
	if kind == "datepicker":
		return element.get("selected_date")
	if kind == "file_input":
		return element.get("files") or []
	if kind == "checkboxes":
		return [o.get("value") for o in element.get("selected_options") or []]
	return element.get("value")


def parse_view(callback_id, view):
	"""(errors, payload, files) for a submitted modal.

	errors maps block_id -> message and goes straight back to Slack as
	response_action = errors, so the problem is shown on the right field.
	"""
	values = (view.get("state") or {}).get("values") or {}
	meta = json.loads(view.get("private_metadata") or "{}")
	parser = PARSERS[callback_id]
	errors, payload, files = parser(values, meta)
	return errors, payload, files


def _parse_conversion(values, meta):
	errors, rows = {}, []
	valid_types = builders.conversion_types()
	for r in range(1, int(meta.get("rows") or 1) + 1):
		raw, finished = [], []
		for n in range(1, blocks.MAX_SLACK_RAW + 1):
			picked = state_value(values, f"r{r}_rm{n}")
			qty = flt(state_value(values, f"r{r}_rmq{n}"))
			if picked and qty <= 0:
				errors[f"r{r}_rmq{n}"] = "Enter a quantity above zero."
			if picked:
				raw.append({**_resolve_pick(picked), "qty": qty})
		for n in range(1, blocks.MAX_SLACK_FINISHED + 1):
			picked = state_value(values, f"r{r}_fg{n}")
			qty = flt(state_value(values, f"r{r}_fgq{n}"))
			if picked and qty <= 0:
				errors[f"r{r}_fgq{n}"] = "Enter a quantity above zero."
			if picked:
				finished.append({**_resolve_pick(picked), "qty": qty})

		if not raw and not finished and r > 1:
			continue  # an added row left empty
		if not raw:
			errors[f"r{r}_rm1"] = "Add at least one raw material."
			continue
		if not finished:
			errors[f"r{r}_fg1"] = "Add at least one finished good."
			continue
		conversion_type = f"{len(raw)} to {len(finished)}"
		if conversion_type not in valid_types:
			errors[f"r{r}_rm1"] = f"{conversion_type} is not a conversion type the ERP allows."
		row = {
			"source_warehouse": state_value(values, f"r{r}_src"),
			"target_warehouse": state_value(values, f"r{r}_tgt"),
			"raw_materials": raw,
			"finished_goods": finished,
		}
		for grams_field, _check, _flag, _label in blocks.MICRON_FIELDS:
			v = state_value(values, f"r{r}_{grams_field}")
			if v not in (None, ""):
				row[grams_field] = flt(v)
		rows.append(row)

	payload = {
		"posting_date": state_value(values, "posting_date"),
		"rows": rows,
		"submit": state_value(values, "submit_mode") != "draft",
	}
	return errors, payload, {}


def _resolve_pick(value):
	"""external_select values are item:<code> or tag:<Metric Tag name>."""
	kind, _, name = (value or "").partition(":")
	if kind == "tag":
		item = frappe.db.get_value("Metric Tag", name, "item_code")
		return {"item": item or name, "tag": name}
	return {"item": name or value}


def _parse_delivery_note(values, meta):
	errors, picks = {}, {}
	if meta.get("erp_only"):
		return {"__modal": "This order is created from the ERP form."}, {}, {}
	so = frappe.get_doc("Sales Order", meta["so"])
	cfg = get_company_settings(so.company)
	for row in so.items:
		block_id = f"line_{row.name}"
		tag = state_value(values, block_id)
		if tag:
			available = gates.tag_qty(tag)
			if available < flt(row.qty):
				errors[block_id] = f"This tag holds {available:g}. The line needs {flt(row.qty):g}."
			picks[row.name] = tag
		elif cfg and cfg.require_muid_on_dn:
			errors[block_id] = "Pick a Metric Tag."
	return errors, {"muid": picks}, {}


def _parse_manifest(values, meta):
	errors = {}
	number = (state_value(values, "manifest_number") or "").strip()
	if not (number.isdigit() and len(number) == MANIFEST_DIGITS):
		errors["manifest_number"] = f"The manifest number must be {MANIFEST_DIGITS} digits."
	uploads = state_value(values, "manifest_file") or []
	if not uploads:
		errors["manifest_file"] = "Attach the manifest file."
	elif client.check_upload(uploads[0]):
		errors["manifest_file"] = client.check_upload(uploads[0])
	# G4 checks the payload for a file_url; the job fills it after the download.
	return errors, {"manifest_number": number, "file_url": "pending"}, ({"file_url": uploads[0]} if uploads else {})


def _parse_payment(values, meta):
	errors = {}
	amount = flt(state_value(values, "amount"))
	if amount <= 0:
		errors["amount"] = "Enter an amount greater than zero."
	mode = state_value(values, "mode_of_payment")
	if not mode:
		errors["mode_of_payment"] = "Choose a mode of payment."
	photos = state_value(values, "photo") or []
	files = {}
	if photos:
		problem = client.check_upload(photos[0])
		if problem:
			errors["photo"] = problem
		files["file_url"] = photos[0]
	payload = {
		"amount": amount,
		"mode_of_payment": mode,
		"reference_no": (state_value(values, "reference_no") or "").strip() or None,
		"reference_date": state_value(values, "reference_date"),
	}
	return errors, payload, files


def _parse_override(values, meta):
	reason = (state_value(values, "reason") or "").strip()
	errors = {}
	if len(reason) < MIN_OVERRIDE_REASON:
		errors["reason"] = f"Give a reason of at least {MIN_OVERRIDE_REASON} characters."
	return errors, {"reason": reason}, {}


def _parse_hold(values, meta):
	reason = (state_value(values, "reason") or "").strip()
	return ({"reason": "A reason is required."} if not reason else {}), {"reason": reason}, {}


def _parse_delivered(values, meta):
	errors, files = {}, {}
	photos = state_value(values, "photo") or []
	if photos:
		problem = client.check_upload(photos[0])
		if problem:
			errors["photo"] = problem
		files["file_url"] = photos[0]
	note = (state_value(values, "note") or "").strip()
	# "reason" is what transition() writes into the stage log's note.
	return errors, ({"reason": note} if note else {}), files


PARSERS = {
	"mt_conversion": _parse_conversion,
	"mt_delivery_note": _parse_delivery_note,
	"mt_manifest": _parse_manifest,
	"mt_payment": _parse_payment,
	"mt_override": _parse_override,
	"mt_hold": _parse_hold,
	"mt_delivered": _parse_delivered,
}
