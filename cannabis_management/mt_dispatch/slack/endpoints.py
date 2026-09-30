"""The four URLs Slack calls: interact, options, command, events.

All are guest endpoints -- Slack has no ERP session -- so verify() is the
first line of each and nothing runs before it. Each answers inside Slack's
three seconds: buttons enqueue and return an empty 200, modal submissions
validate inline and either return field errors or enqueue and clear, and
buttons that open a modal call views.open inline because the trigger_id
expires in three seconds.
"""

import json
import re

import frappe
from werkzeug.wrappers import Response

from cannabis_management.mt_dispatch import flow, stages
from cannabis_management.mt_dispatch.settings import get_company_settings, team_flags
from cannabis_management.mt_dispatch.slack import blocks, client, handlers, identity
from cannabis_management.mt_dispatch.slack.verify import SlackAuthError, check_team, verify

QUEUE = "short"
MODAL_TO_TRANSITION = {
	"mt:new_conversion": "create_conversion",
	"mt:create_dn": "create_delivery_note",
	"mt:upload_manifest": "upload_manifest",
	"mt:record_payment": "record_payment",
	"mt:override": "release_override",
	"mt:hold": "hold",
	"mt:delivered": "mark_delivered",
}


def _json(data=None, status=200):
	if data is None:
		return Response("", status=status)
	return Response(json.dumps(data), status=status, mimetype="application/json")


def _reject():
	return Response("invalid request", status=401)


def _enqueue(method, **kwargs):
	frappe.enqueue(
		"cannabis_management.mt_dispatch.slack.handlers." + method,
		queue=QUEUE,
		enqueue_after_commit=False,
		**kwargs,
	)


# ── interactivity ────────────────────────────────────────────────────────────


@frappe.whitelist(allow_guest=True, methods=["POST"])
def interact(**kwargs):
	try:
		verify()
		payload = json.loads(frappe.form_dict.get("payload") or "{}")
		check_team((payload.get("team") or {}).get("id") or payload.get("team_id"))
	except (SlackAuthError, ValueError):
		return _reject()

	kind = payload.get("type")
	if kind == "block_actions":
		return _block_actions(payload)
	if kind == "view_submission":
		return _view_submission(payload)
	if kind == "view_closed":
		# A form opened from the status dropdown and then cancelled: put the
		# dropdown back on the order's real stage.
		meta = json.loads((payload.get("view") or {}).get("private_metadata") or "{}")
		if meta.get("so"):
			_enqueue("reset_status", sales_order=meta["so"])
		return _json()
	return _json()


def _source(payload):
	channel = (payload.get("channel") or payload.get("container") or {}).get("id") or (
		payload.get("container") or {}
	).get("channel_id")
	message = payload.get("message") or {}
	return channel, message.get("thread_ts") or message.get("ts")


def _unreachable_status(payload, value, slack_user):
	"""A stage picked that no step leads to from here: say where the order can
	go instead, and put the dropdown back on its real stage."""
	sales_order = value.get("so")
	if not sales_order or not frappe.db.exists("Sales Order", sales_order):
		return _json()
	so = frappe.get_doc("Sales Order", sales_order)
	cfg = get_company_settings(so.company)
	stage = so.get("custom_logistic_status") or "no stage"
	reachable = []
	if cfg:
		for action_id in blocks.stage_action_ids(so, cfg):
			target = blocks.BUTTON_TARGET.get(action_id, "") or so.get("custom_hold_from_stage")
			if target and target not in reachable:
				reachable.append(target)
	text = f":no_entry: {so.name} can't move from *{stage}* to *{value.get('to')}* directly."
	text += f" From {stage} it can move to: {', '.join(reachable)}." if reachable else f" There is no step to take from {stage}."
	channel, _ts = _source(payload)
	_enqueue("say", slack_user=slack_user, text=text, response_url=payload.get("response_url"), channel=channel)
	_enqueue("reset_status", sales_order=sales_order)
	return _json()


def _block_actions(payload):
	action = (payload.get("actions") or [{}])[0]
	action_id = action.get("action_id") or ""
	slack_user = (payload.get("user") or {}).get("id")

	if action_id == "mt:open_erp":
		return _json()
	if action_id in ("mt:conv_add_row", "mt:conv_microns"):
		return _update_conversion_modal(payload, action_id)

	try:
		if action_id == "mt:set_status":
			# The dropdown carries the button it stands for; from here on it
			# is handled exactly as if that button had been clicked.
			value = json.loads((action.get("selected_option") or {}).get("value") or "{}")
			action_id = value.pop("a", "")
			if not action_id:
				return _json()  # re-picked the current stage
			if action_id == blocks.UNREACHABLE_STATUS:
				return _unreachable_status(payload, value, slack_user)
		else:
			value = json.loads(action.get("value") or "{}")
	except ValueError:
		return _json()
	sales_order, expected_stage = value.get("so"), value.get("stage")
	if not sales_order:
		return _json()

	channel, thread_ts = _source(payload)
	response_url = payload.get("response_url")

	if action_id in blocks.DIRECT_ACTIONS:
		_enqueue(
			"run_action",
			slack_user=slack_user,
			action=blocks.DIRECT_ACTIONS[action_id],
			sales_order=sales_order,
			expected_stage=expected_stage,
			response_url=response_url,
			channel=channel,
			thread_ts=thread_ts,
		)
		return _json()

	if action_id in blocks.MODAL_ACTIONS:
		user = identity.erp_user_for(slack_user)
		if not user:
			_enqueue("say", slack_user=slack_user, text=identity.NOT_LINKED, response_url=response_url, channel=channel)
			_enqueue("reset_status", sales_order=sales_order)
			return _json()
		problem = handlers.precheck(user, sales_order, MODAL_TO_TRANSITION[action_id], expected_stage)
		if problem:
			_enqueue("say", slack_user=slack_user, text=f":no_entry: {problem}", response_url=response_url, channel=channel)
			_enqueue("reset_status", sales_order=sales_order)
			return _json()

		so = frappe.get_doc("Sales Order", sales_order)
		cfg = get_company_settings(so.company)
		callback_id = blocks.MODAL_ACTIONS[action_id]
		view = blocks.MODAL_BUILDERS[callback_id](so, cfg)
		meta = json.loads(view["private_metadata"])
		meta.update({"ch": channel, "th": thread_ts})
		view["private_metadata"] = json.dumps(meta, separators=(",", ":"))
		try:
			client.views_open(payload["trigger_id"], view)
		except client.SlackError as e:
			frappe.log_error(f"MT Dispatch: views.open failed: {e}", "MT Dispatch Slack")
	return _json()


def _update_conversion_modal(payload, action_id):
	view = payload.get("view") or {}
	meta = json.loads(view.get("private_metadata") or "{}")
	so = frappe.get_doc("Sales Order", meta["so"])
	cfg = get_company_settings(so.company)
	if not cfg:
		return _json()
	rows, microns = int(meta.get("rows") or 1), bool(int(meta.get("microns") or 0))
	if action_id == "mt:conv_add_row":
		rows = min(rows + 1, blocks.MAX_SLACK_ROWS)
	else:
		microns = not microns
	new_view = blocks.conversion_modal(so, cfg, rows=rows, microns=microns)
	new_meta = json.loads(new_view["private_metadata"])
	new_meta.update({"ch": meta.get("ch"), "th": meta.get("th")})
	new_view["private_metadata"] = json.dumps(new_meta, separators=(",", ":"))
	try:
		client.views_update(view["id"], new_view, view.get("hash"))
	except client.SlackError as e:
		frappe.log_error(f"MT Dispatch: views.update failed: {e}", "MT Dispatch Slack")
	return _json()


def _view_submission(payload):
	view = payload.get("view") or {}
	callback_id = view.get("callback_id")
	if callback_id not in handlers.PARSERS:
		return _json({"response_action": "clear"})

	errors, action_payload, files = handlers.parse_view(callback_id, view)
	if "__modal" in errors:
		return _json({"response_action": "clear"})
	if errors:
		return _json({"response_action": "errors", "errors": errors})

	meta = json.loads(view.get("private_metadata") or "{}")
	_enqueue(
		"run_action",
		slack_user=(payload.get("user") or {}).get("id"),
		action=handlers.MODAL_TRANSITION[callback_id],
		sales_order=meta.get("so"),
		expected_stage=meta.get("stage"),
		payload=action_payload,
		files=files,
		channel=meta.get("ch"),
		thread_ts=meta.get("th"),
	)
	return _json({"response_action": "clear"})


# ── typeahead ────────────────────────────────────────────────────────────────


@frappe.whitelist(allow_guest=True, methods=["POST"])
def options(**kwargs):
	try:
		verify()
		payload = json.loads(frappe.form_dict.get("payload") or "{}")
		check_team((payload.get("team") or {}).get("id"))
	except (SlackAuthError, ValueError):
		return _reject()

	query = (payload.get("value") or "").strip()
	action_id = payload.get("action_id")
	return _json({"options": search_options(action_id, query)})


def search_options(action_id, query, limit=100):
	if len(query) < 2:
		return []
	like = f"%{query}%"
	out = []
	per_kind = limit // 2 if action_id == "mt:item_or_tag" else limit

	if action_id == "mt:item_or_tag":
		for t in frappe.get_all(
			"Metric Tag",
			filters={"status": ["!=", "Empty"]},
			or_filters={"name": ["like", like], "tag_code": ["like", like], "muid": ["like", like]},
			fields=["name", "tag_code", "item_code", "current_qty"],
			limit=per_kind,
		):
			out.append(blocks.option(f"Tag {t.tag_code or t.name} · {t.item_code or '?'} ({t.current_qty or 0:g})", f"tag:{t.name}"))

	for i in frappe.get_all(
		"Item",
		filters={"disabled": 0},
		or_filters={"name": ["like", like], "item_name": ["like", like]},
		fields=["name", "item_name"],
		limit=per_kind,
	):
		label = i.name if i.item_name in (None, "", i.name) else f"{i.name} · {i.item_name}"
		out.append(blocks.option(label, f"item:{i.name}"))
	return out[:limit]


# ── slash commands ───────────────────────────────────────────────────────────


@frappe.whitelist(allow_guest=True, methods=["POST"])
def command(**kwargs):
	try:
		verify()
		check_team(frappe.form_dict.get("team_id"))
	except SlackAuthError:
		return _reject()

	form = frappe.form_dict
	slack_user = form.get("user_id")
	user = identity.erp_user_for(slack_user)
	if not user:
		return _ephemeral(identity.NOT_LINKED)

	name = (form.get("command") or "").lstrip("/")
	text = (form.get("text") or "").strip()
	if name == "order":
		return _cmd_order(user, text)
	if name == "board":
		return _cmd_board(user, text)
	if name == "hold":
		return _cmd_hold(user, slack_user, text, form)
	return _ephemeral("Unknown command.")


def _ephemeral(text, blks=None):
	body = {"response_type": "ephemeral", "text": text}
	if blks:
		body["blocks"] = blks
	return _json(body)


def user_companies(user):
	out = []
	for name in frappe.get_all("Dispatch Company Settings", filters={"enabled": 1}, pluck="name", order_by="name"):
		cfg = get_company_settings(name)
		if cfg and (team_flags(user, cfg) or user == "Administrator"):
			out.append(cfg)
	return out


def resolve_order(text, companies):
	"""Full name, or the numeric tail (00563 or 563), within the user's companies."""
	token = (text or "").split()[0] if text else ""
	if not token:
		return None, "Give an order number, e.g. /order 00563."
	names = [c.company for c in companies]
	if not names:
		return None, "You're not on any company's dispatch team."
	if frappe.db.exists("Sales Order", {"name": token, "company": ["in", names], "docstatus": 1}):
		return token, None
	if not re.fullmatch(r"\d+", token):
		return None, f"No order {token} at your companies."
	tail = token.zfill(5)
	# An amended order keeps the number and gains a suffix: …-00563-1.
	matches = frappe.get_all(
		"Sales Order",
		filters={"company": ["in", names], "docstatus": 1},
		or_filters=[["name", "like", f"%-{tail}"], ["name", "like", f"%-{tail}-%"]],
		pluck="name",
		order_by="creation desc",
		limit=5,
	)
	if not matches:
		return None, f"No order ending {token} at your companies."
	if len(matches) > 1:
		return None, "More than one match: " + ", ".join(matches)
	return matches[0], None


def _cmd_order(user, text):
	name, problem = resolve_order(text, user_companies(user))
	if problem:
		return _ephemeral(problem)
	so = frappe.get_doc("Sales Order", name)
	cfg = get_company_settings(so.company)
	from cannabis_management.mt_dispatch.slack.post import thread_row

	row = thread_row(so.name)
	link = client.permalink(row.channel, row.ts) if row else None
	return _ephemeral(f"{so.name} · {so.get('custom_logistic_status')}", blocks.order_card(so, cfg, link))


def _cmd_board(user, text):
	from cannabis_management.mt_dispatch import reminders

	companies = user_companies(user)
	abbr = (text or "").strip().upper()
	if abbr:
		companies = [c for c in companies if (frappe.db.get_value("Company", c.company, "abbr") or "").upper() == abbr]
		if not companies:
			return _ephemeral(f"No company {abbr} that you're on.")
	if not companies:
		return _ephemeral("You're not on any company's dispatch team.")

	blks = []
	for cfg in companies:
		rows = frappe.get_all(
			"Sales Order",
			filters={"company": cfg.company, "docstatus": 1, "custom_logistic_status": ["in", stages.ALL_STAGES]},
			fields=["custom_logistic_status as stage", "count(name) as n"],
			group_by="custom_logistic_status",
		)
		counts = {r.stage: r.n for r in rows}
		overdue = reminders.overdue_orders(cfg)
		lines = [
			f"{blocks.STAGE_EMOJI.get(s, '')} {s}: *{counts.get(s, 0)}*"
			for s in stages.ALL_STAGES
			if s not in stages.TERMINAL_STAGES
		]
		blks.append({"type": "header", "text": blocks.txt(cfg.company)})
		blks.append(blocks.section("\n".join(lines)))
		if overdue:
			blks.append(
				blocks.section(
					":alarm_clock: *Overdue*\n"
					+ "\n".join(f"{blocks.short_name(n)} · {s} · {m} working min" for n, s, m in overdue[:15])
				)
			)
	return _ephemeral("Dispatch board", blks[:50])


def _cmd_hold(user, slack_user, text, form):
	name, problem = resolve_order(text, user_companies(user))
	if problem:
		return _ephemeral(problem)
	reason = text.split(None, 1)[1].strip() if len(text.split(None, 1)) > 1 else ""
	so = frappe.get_doc("Sales Order", name)
	problem = handlers.precheck(user, name, "hold", None)
	if problem:
		return _ephemeral(f":no_entry: {problem}")

	if not reason:
		cfg = get_company_settings(so.company)
		view = blocks.hold_modal(so, cfg)
		meta = json.loads(view["private_metadata"])
		meta["ch"] = form.get("channel_id")
		view["private_metadata"] = json.dumps(meta, separators=(",", ":"))
		client.views_open(form.get("trigger_id"), view)
		return _json()

	_enqueue(
		"run_action",
		slack_user=slack_user,
		action="hold",
		sales_order=name,
		expected_stage=so.get(flow.STAGE_FIELD),
		payload={"reason": reason},
		response_url=form.get("response_url"),
	)
	return _ephemeral(f"Putting {name} on hold…")


# ── events ───────────────────────────────────────────────────────────────────


@frappe.whitelist(allow_guest=True, methods=["POST"])
def events(**kwargs):
	try:
		verify()
		body = json.loads(frappe.request.get_data(as_text=True) or "{}")
	except (SlackAuthError, ValueError):
		return _reject()

	if body.get("type") == "url_verification":
		return _json({"challenge": body.get("challenge")})

	# Slack retries anything it thinks we were slow on. The first delivery was
	# already handled, so a retry is acknowledged and dropped.
	if frappe.request.headers.get("X-Slack-Retry-Num"):
		return _json()

	try:
		check_team(body.get("team_id"))
	except SlackAuthError:
		return _reject()

	event = body.get("event") or {}
	if event.get("type") == "app_home_opened" and event.get("tab", "home") == "home":
		_enqueue("publish_home", slack_user=event.get("user"))
	return _json()
