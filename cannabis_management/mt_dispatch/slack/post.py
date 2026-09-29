"""Posting: what goes to Slack after each transition.

notify.on_transition resolves the company and hands over here once a bot
token exists. Everything we may need to edit later -- the thread parent, each
approval DM, the dispatch post, exception posts -- is remembered as a
Dispatch Slack Message row on the order, so a later transition can chat.update
it in place.
"""

import time

import frappe
from frappe.utils import flt, format_datetime, now_datetime

from cannabis_management.mt_dispatch import gates, stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import get_company_settings, users_with_flag
from cannabis_management.mt_dispatch.slack import blocks, client, identity
from cannabis_management.mt_dispatch.slack.client import SlackError

THREAD_PARENT = "thread_parent"
APPROVAL_DM = "approval_dm"
DISPATCH_POST = "dispatch_post"
EXCEPTION_POST = "exception_post"

VERBS = {
	"enter_flow": "order received",
	"flag_conversion": "flagged a conversion",
	"start_preparing": "started preparing",
	"create_conversion": "created a Conversion Entry",
	"conversions_done": "all conversions done",
	"conversion_progress": "conversion update",
	"mark_prepared": "marked prepared",
	"create_delivery_note": "created the Delivery Note",
	"upload_manifest": "uploaded the manifest",
	"record_payment": "recorded a payment",
	"release": "released",
	"release_override": "released with an override",
	"mark_delivered": "confirmed delivery",
	"hold": "put on hold",
	"resume": "resumed",
	"cancel": "cancelled the order",
	"dn_cancelled": "cancelled the Delivery Note after release",
	"backfill": "moved onto the dispatch board",
}

SYSTEM_ACTIONS = {"enter_flow", "conversions_done", "conversion_progress", "backfill"}


# ── message rows ─────────────────────────────────────────────────────────────


def message_rows(so_name, kind=None, open_only=False):
	filters = {"parent": so_name, "parenttype": "Sales Order"}
	if kind:
		filters["kind"] = kind
	if open_only:
		filters["closed"] = 0
	return frappe.get_all(
		"Dispatch Slack Message",
		filters=filters,
		fields=["name", "kind", "channel", "ts", "slack_user", "closed"],
		order_by="idx asc",
	)


def thread_row(so_name):
	rows = message_rows(so_name, THREAD_PARENT)
	return rows[0] if rows else None


def add_row(so_name, kind, channel, ts, slack_user=None):
	idx = frappe.db.sql(
		"select coalesce(max(idx), 0) from `tabDispatch Slack Message` where parent=%s and parenttype='Sales Order'",
		so_name,
	)[0][0]
	row = frappe.new_doc("Dispatch Slack Message")
	row.update(
		{
			"parent": so_name,
			"parenttype": "Sales Order",
			"parentfield": "custom_slack_messages",
			"idx": (idx or 0) + 1,
			"kind": kind,
			"channel": channel,
			"ts": ts,
			"slack_user": slack_user,
			"closed": 0,
		}
	)
	row.insert(ignore_permissions=True)
	return row


def close_rows(so_name):
	frappe.db.sql(
		"update `tabDispatch Slack Message` set closed=1 where parent=%s and parenttype='Sales Order'", so_name
	)


# ── audiences ────────────────────────────────────────────────────────────────


def mention_users(users):
	out = []
	for user in users:
		m = identity.mention(user)
		if m not in out:
			out.append(m)
	return out


def fulfillment_mentions(cfg):
	if cfg.get("fulfillment_group_id") and cfg.fulfillment_group_id.startswith("S"):
		return [f"<!subteam^{cfg.fulfillment_group_id}>"]
	return mention_users(users_with_flag(cfg, stages.FULFILLMENT))


def stage_log_users(so_name):
	return [
		u
		for u in frappe.get_all(
			"Dispatch Stage Log",
			filters={"parent": so_name, "parenttype": "Sales Order"},
			pluck="user",
			distinct=True,
		)
		if u and u not in ("Administrator", "Guest")
	]


def mentions_for(action, so, cfg):
	"""Section 9: who the thread reply tags."""
	rep = [blocks.sales_rep_user(so)]
	if action in ("enter_flow", "backfill"):
		return fulfillment_mentions(cfg) + mention_users(users_with_flag(cfg, stages.COMPLIANCE) + rep)
	if action == "flag_conversion":
		return fulfillment_mentions(cfg)
	if action == "mark_prepared":
		return mention_users(users_with_flag(cfg, stages.COMPLIANCE))
	if action == "upload_manifest":
		return mention_users(users_with_flag(cfg, stages.APPROVER))
	if action in ("release", "mark_delivered"):
		return mention_users(rep)
	if action == "release_override":
		return mention_users(rep + users_with_flag(cfg, stages.FINANCE))
	if action in ("hold", "resume"):
		return mention_users(rep + users_with_flag(cfg, stages.APPROVER))
	if action in ("cancel", "dn_cancelled"):
		return mention_users(stage_log_users(so.name))
	return []


# ── thread ───────────────────────────────────────────────────────────────────


def ensure_thread(so, cfg):
	"""The thread parent for an order, posting it the first time."""
	row = thread_row(so.name)
	if row:
		return row
	if not cfg.orders_channel:
		return None
	text, blks = blocks.thread_parent(so, cfg)
	channel, ts = client.post(cfg.orders_channel, text, blks)
	row = add_row(so.name, THREAD_PARENT, channel, ts)
	_link_amendment(so, cfg, channel, ts)
	return row


def _link_amendment(so, cfg, channel, ts):
	"""An amended order's new thread points at the old one, and back."""
	if not so.get("amended_from"):
		return
	old = thread_row(so.amended_from)
	if not old:
		return
	old_link = client.permalink(old.channel, old.ts)
	new_link = client.permalink(channel, ts)
	client.post(channel, f"Amended from {so.amended_from}" + (f" · <{old_link}|old thread>" if old_link else ""), thread_ts=ts)
	client.post(old.channel, f"Amended as {so.name}" + (f" · <{new_link}|new thread>" if new_link else ""), thread_ts=old.ts)


def refresh_parent(so, cfg):
	row = thread_row(so.name)
	if not row:
		return
	text, blks = blocks.thread_parent(so, cfg)
	try:
		client.update(row.channel, row.ts, text, blks)
	except SlackError as e:
		frappe.log_error(f"MT Dispatch: could not update thread for {so.name}: {e}", "MT Dispatch Slack")


def reply(so, cfg, text, blks=None):
	row = ensure_thread(so, cfg)
	if not row:
		return None
	return client.post(row.channel, text, blks, thread_ts=row.ts)


# ── the entry point notify calls ─────────────────────────────────────────────


def on_transition(sales_order, action, users=None, channel=None, **kwargs):
	# Serialise jobs for one order, so two quick transitions never both post a
	# thread parent. The commit comes first on purpose: notify has already
	# read from the database, and under REPEATABLE READ those reads pinned a
	# snapshot from before the lock. Without a fresh transaction the second job
	# waits for the lock and then still cannot see the first job's thread row.
	frappe.db.commit()
	frappe.db.get_value("Sales Order", sales_order, "name", for_update=True)
	so = frappe.get_doc("Sales Order", sales_order)
	cfg = get_company_settings(so.company)
	if not cfg:
		return

	actor = kwargs.get("actor") or frappe.session.user
	stage = so.get("custom_logistic_status")

	row = ensure_thread(so, cfg)
	if not row:
		return
	refresh_parent(so, cfg)

	line = _line(so, action, actor, kwargs)
	# A new order's conversion check is the thread parent itself, so only a
	# conversion flagged later gets it again as a reply.
	if action == "flag_conversion" and blocks.stock_check(so, cfg).need:
		# A new order, or one just flagged for conversion, that the warehouse
		# is short of: show fulfillment what is missing instead of a one-line
		# update. Nothing short means no conversion message -- the ordinary
		# reply below goes out instead.
		others = [] if action == "flag_conversion" else mention_users(
			users_with_flag(cfg, stages.COMPLIANCE) + [blocks.sales_rep_user(so)]
		)
		text, blks = blocks.conversion_check(so, cfg, blocks.conversion_mentions(cfg), others)
		if action == "flag_conversion":
			blks.insert(0, blocks.section(line))
		client.post(row.channel, text, blks, thread_ts=row.ts)
		line = None
	if line:
		# Enter-flow already shows everything on the parent; its reply is the tag list.
		text, blks = blocks.stage_update(
			so, cfg, line, mentions_for(action, so, cfg), with_buttons=action not in ("enter_flow", "backfill")
		)
		client.post(row.channel, text, blks, thread_ts=row.ts)

	if action == "upload_manifest":
		send_approval_dms(so, cfg)
	elif action in ("release", "release_override"):
		post_dispatch(so, cfg)
		refresh_approval_dms(so.name, released_by=identity.full_name(actor))
		if action == "release_override":
			_, _, _, short = payment_status(so, cfg)
			post_exception(
				so, cfg, "Override release",
				f"Released by {identity.mention(actor)} with {blocks.money(short, so)} outstanding.\n"
				f"Reason: {so.get('custom_release_override_reason') or '—'}",
			)
	elif action == "hold":
		post_exception(
			so, cfg, "On hold",
			f"Held by {identity.mention(actor)} at {so.get('custom_hold_from_stage')}.\nReason: {so.get('custom_hold_reason') or '—'}",
			show_resume=True,
		)
		refresh_approval_dms(so.name)
	elif action == "resume":
		refresh_exceptions(so, cfg)
		post_exception(so, cfg, "Resumed", f"Resumed by {identity.mention(actor)}. Back at {stage}.")
		refresh_approval_dms(so.name)
	elif action == "mark_delivered":
		refresh_dispatch(so, cfg)
		close_rows(so.name)
	elif action == "cancel":
		post_exception(so, cfg, "Order cancelled", f"Cancelled by {identity.mention(actor)}. Draft Delivery Note removed.")
		refresh_approval_dms(so.name)
		close_rows(so.name)
	elif action == "dn_cancelled":
		post_exception(
			so, cfg, "Delivery Note cancelled after release",
			f"Cancelled by {identity.mention(actor)}. The order is back at {stage}.",
		)
		refresh_dispatch(so, cfg)

	frappe.db.commit()
	_refresh_homes(cfg)


def _line(so, action, actor, kwargs):
	who = "System" if action in SYSTEM_ACTIONS else identity.full_name(actor)
	at = format_datetime(now_datetime(), "HH:mm")
	if action in ("enter_flow", "backfill"):
		return f"{blocks.STAGE_EMOJI.get(stages.RECEIVED)} New order · {at}"
	if action in ("create_conversion", "conversion_progress", "conversions_done"):
		total = frappe.db.count("Conversion Entry", {"sales_order": so.name, "docstatus": ["<", 2]})
		done = frappe.db.count("Conversion Entry", {"sales_order": so.name, "docstatus": 1})
		if action == "conversions_done":
			return f":white_check_mark: All conversions done ({done} of {total} submitted) · {at}"
		return f"{who} {VERBS[action]} · {done} of {total} submitted · {at}"
	if action == "record_payment":
		_, paid, required, short = payment_status(so, get_company_settings(so.company))
		state = "paid in full" if not short else f"{blocks.money(short, so)} outstanding"
		return f"{who} recorded a payment · {blocks.money(paid, so)} of {blocks.money(required, so)}, {state} · {at}"
	verb = VERBS.get(action, action)
	stage = so.get("custom_logistic_status")
	return f"{who} {verb} · {at} → *{stage}*"


# ── approval DMs ─────────────────────────────────────────────────────────────


def approvers(cfg, include_backup=False):
	users = [row.user for row in cfg.team or [] if row.approver and (include_backup or not row.backup_approver)]
	return users or [row.user for row in cfg.team or [] if row.approver]


def send_approval_dms(so, cfg, users=None):
	already = {r.slack_user for r in message_rows(so.name, APPROVAL_DM)}
	text, blks = blocks.approval_dm(so, cfg)
	for user in users or approvers(cfg):
		slack_id = identity.slack_id_for(user)
		if not slack_id or slack_id in already:
			continue
		try:
			channel = client.open_dm(slack_id)
			channel, ts = client.post(channel, text, blks)
			add_row(so.name, APPROVAL_DM, channel, ts, slack_id)
		except SlackError as e:
			frappe.log_error(f"MT Dispatch: approval DM to {user} failed: {e}", "MT Dispatch Slack")


def refresh_approval_dms(sales_order, released_by=None):
	so = frappe.get_doc("Sales Order", sales_order)
	cfg = get_company_settings(so.company)
	if not cfg:
		return
	if not released_by and so.get("custom_logistic_status") in (stages.RELEASED, stages.CLOSED_OUT):
		released_by = identity.full_name(so.get("custom_released_by")) if so.get("custom_released_by") else None
	text, blks = blocks.approval_dm(so, cfg, released_by=released_by)
	for row in message_rows(so.name, APPROVAL_DM, open_only=True):
		try:
			client.update(row.channel, row.ts, text, blks)
		except SlackError as e:
			frappe.log_error(f"MT Dispatch: approval DM update failed: {e}", "MT Dispatch Slack")


def on_payment_cleared(sales_order):
	"""A COD order that is now paid in full: the DMs grow a Release button."""
	refresh_approval_dms(sales_order)
	so = frappe.get_doc("Sales Order", sales_order)
	cfg = get_company_settings(so.company)
	if cfg:
		refresh_parent(so, cfg)
		frappe.db.commit()
		_refresh_homes(cfg)


# ── dispatch and exceptions ──────────────────────────────────────────────────


def post_dispatch(so, cfg):
	if not cfg.dispatch_channel:
		return
	text, blks = blocks.dispatch_post(so, cfg)
	channel, ts = client.post(cfg.dispatch_channel, text, blks)
	add_row(so.name, DISPATCH_POST, channel, ts)


def refresh_dispatch(so, cfg):
	text, blks = blocks.dispatch_post(so, cfg)
	for row in message_rows(so.name, DISPATCH_POST, open_only=True):
		try:
			client.update(row.channel, row.ts, text, blks)
		except SlackError:
			pass


def post_exception(so, cfg, title, detail, show_resume=False):
	if not cfg.exceptions_channel:
		return
	text, blks = blocks.exception_post(so, cfg, title, detail, show_resume=show_resume)
	channel, ts = client.post(cfg.exceptions_channel, text, blks)
	if show_resume:
		add_row(so.name, EXCEPTION_POST, channel, ts)


def refresh_exceptions(so, cfg):
	"""Hold posts lose their Resume button once the order has moved on."""
	for row in message_rows(so.name, EXCEPTION_POST, open_only=True):
		try:
			client.update(
				row.channel, row.ts, f"Resumed · {so.name}",
				[blocks.section(f":arrow_forward: *{so.name}* resumed. Now at {so.get('custom_logistic_status')}.")],
			)
			frappe.db.set_value("Dispatch Slack Message", row.name, "closed", 1, update_modified=False)
		except SlackError:
			pass


# ── App Home ─────────────────────────────────────────────────────────────────


def _refresh_homes(cfg):
	from cannabis_management.mt_dispatch.slack import home

	for row in cfg.team or []:
		slack_id = frappe.db.get_value("User", row.user, "custom_slack_user_id")
		if slack_id:
			try:
				home.publish(slack_id, row.user)
			except Exception:
				frappe.log_error(f"MT Dispatch: App Home refresh failed for {row.user}", "MT Dispatch Slack")


# ── one-off: threads for orders that were open before go-live ────────────────


def post_open_threads(company, limit=None):
	"""Post a thread for every open order at one company that has none yet.

	Run by hand once the channels are ready:
	bench --site <site> execute cannabis_management.mt_dispatch.slack.post.post_open_threads --kwargs "{'company': 'Master Touch Manufacturing'}"
	"""
	cfg = get_company_settings(company)
	if not cfg:
		print(f"{company} is not enabled for dispatch.")
		return 0
	open_stages = [s for s in stages.ALL_STAGES if s not in stages.TERMINAL_STAGES]
	names = frappe.get_all(
		"Sales Order",
		filters={"company": company, "docstatus": 1, "custom_logistic_status": ["in", open_stages]},
		pluck="name",
		order_by="creation asc",
	)
	posted = 0
	for name in names:
		if thread_row(name):
			continue
		so = frappe.get_doc("Sales Order", name)
		ensure_thread(so, cfg)
		frappe.db.commit()
		posted += 1
		time.sleep(1.1)  # chat.postMessage allows about one message per second per channel
		if limit and posted >= int(limit):
			break
	print(f"{posted} thread(s) posted for {company}.")
	return posted
