"""Every Block Kit payload the app sends: one builder per message and modal.

Nothing here talks to Slack or writes anything. Builders take a Sales Order
(and its company settings) and return plain dicts, which keeps them testable
and keeps the button rules in one place.

Button values carry {"so": name, "stage": current} so a click that lands
after someone else moved the order is recognised as stale.
"""

import json

import frappe
from frappe.utils import flt, fmt_money, format_date, format_datetime, get_url, now_datetime, strip_html, time_diff_in_seconds

from cannabis_management.mt_dispatch import gates, stages
from cannabis_management.mt_dispatch.payments import payment_status

MAX_SLACK_ROWS = 3          # Conversion rows the Slack form takes
MAX_SLACK_RAW = 3           # raw materials per row on the Slack form
MAX_SLACK_FINISHED = 3
MAX_DN_LINES = 20
# Imported rather than restated, so the modal can never offer a micron the
# builder would not store.
from cannabis_management.mt_dispatch.builders import MICRON_FIELDS  # noqa: E402

# action_id -> (label, style). Buttons that open a modal are marked in MODAL_ACTIONS.
BUTTONS = {
	"mt:flag_conversion": ("Needs conversion", None),
	"mt:start_preparing": ("Start preparing", "primary"),
	"mt:new_conversion": ("New conversion", None),
	"mt:mark_prepared": ("Mark prepared", "primary"),
	"mt:create_dn": ("Create Delivery Note", "primary"),
	"mt:upload_manifest": ("Upload manifest", "primary"),
	"mt:record_payment": ("Record payment", None),
	"mt:release": ("Release", "primary"),
	"mt:override": ("Override release", "danger"),
	"mt:hold": ("Hold", None),
	"mt:resume": ("Resume", "primary"),
	"mt:delivered": ("Delivered / picked up", "primary"),
}

MODAL_ACTIONS = {
	"mt:new_conversion": "mt_conversion",
	"mt:create_dn": "mt_delivery_note",
	"mt:upload_manifest": "mt_manifest",
	"mt:record_payment": "mt_payment",
	"mt:override": "mt_override",
	"mt:hold": "mt_hold",
	"mt:delivered": "mt_delivered",
}

# Buttons that run a transition straight away, and the transition they run.
DIRECT_ACTIONS = {
	"mt:flag_conversion": "flag_conversion",
	"mt:start_preparing": "start_preparing",
	"mt:mark_prepared": "mark_prepared",
	"mt:release": "release",
	"mt:resume": "resume",
}

# Where each stage-changing button takes the order, for the status dropdown.
# record_payment and new_conversion do not change the stage, so they are not here.
# Dropdown value for a stage no step of the order leads to right now.
UNREACHABLE_STATUS = "mt:unreachable"

BUTTON_TARGET = {
	"mt:flag_conversion": stages.AWAITING_CONVERSION,
	"mt:start_preparing": stages.PREPARING,
	"mt:mark_prepared": stages.PREPARED,
	"mt:create_dn": stages.DN_READY,
	"mt:upload_manifest": stages.AWAITING_RELEASE,
	"mt:release": stages.RELEASED,
	"mt:override": stages.RELEASED,
	"mt:delivered": stages.CLOSED_OUT,
	"mt:hold": stages.ON_HOLD,
	"mt:resume": None,  # back to wherever the hold came from
}

STAGE_EMOJI = {
	stages.RECEIVED: ":inbox_tray:",
	stages.AWAITING_CONVERSION: ":arrows_counterclockwise:",
	stages.PREPARING: ":package:",
	stages.PREPARED: ":white_check_mark:",
	stages.DN_READY: ":page_facing_up:",
	stages.AWAITING_RELEASE: ":hourglass_flowing_sand:",
	stages.RELEASED: ":truck:",
	stages.CLOSED_OUT: ":checkered_flag:",
	stages.ON_HOLD: ":double_vertical_bar:",
	stages.CANCELLED: ":x:",
}

# Who owns each stage -- drives App Home and reminders.
STAGE_OWNER = {
	stages.RECEIVED: stages.FULFILLMENT,
	stages.AWAITING_CONVERSION: stages.FULFILLMENT,
	stages.PREPARING: stages.FULFILLMENT,
	stages.PREPARED: stages.COMPLIANCE,
	stages.DN_READY: stages.COMPLIANCE,
	stages.AWAITING_RELEASE: stages.APPROVER,
	stages.RELEASED: stages.DISPATCH,
	stages.ON_HOLD: stages.APPROVER,
}


# ── small helpers ────────────────────────────────────────────────────────────


def txt(text):
	return {"type": "plain_text", "text": str(text)[:150], "emoji": True}


def md(text):
	return {"type": "mrkdwn", "text": str(text)[:3000]}


def section(text, accessory=None):
	block = {"type": "section", "text": md(text)}
	if accessory:
		block["accessory"] = accessory
	return block


def context(text):
	return {"type": "context", "elements": [md(text)]}


def divider():
	return {"type": "divider"}


def value_for(so, extra=None):
	value = {"so": so.name, "stage": so.get("custom_logistic_status")}
	if extra:
		value.update(extra)
	return json.dumps(value, separators=(",", ":"))


def button(action_id, so, label=None, style=None, extra=None):
	default_label, default_style = BUTTONS.get(action_id, (action_id, None))
	b = {
		"type": "button",
		"action_id": action_id,
		"text": txt(label or default_label),
		"value": value_for(so, extra),
	}
	if style or default_style:
		b["style"] = style or default_style
	return b


def erp_url(doctype, name):
	return get_url(f"/app/{frappe.scrub(doctype).replace('_', '-')}/{name}")


def open_erp_button(so):
	return {"type": "button", "action_id": "mt:open_erp", "text": txt("Open in ERP"), "url": erp_url("Sales Order", so.name)}


def money(amount, so):
	return fmt_money(flt(amount), currency=so.get("currency"))


def short_name(name):
	"""SAL-ORD-2026-00563 -> 00563."""
	return (name or "").rsplit("-", 1)[-1]


# ── facts about an order ─────────────────────────────────────────────────────


def sales_rep_user(so):
	"""The ERP user behind the order's first sales person, else its owner."""
	for row in so.get("sales_team") or []:
		employee = frappe.db.get_value("Sales Person", row.sales_person, "employee")
		user = employee and frappe.db.get_value("Employee", employee, "user_id")
		if user:
			return user
	return so.owner


def order_facts(so, cfg):
	applies, paid, required, short = payment_status(so, cfg)
	dn = gates.delivery_notes_for(so.name)
	dn_name = dn[0] if dn else None
	manifest_no, manifest_file = None, None
	if dn_name:
		manifest_no, manifest_file = frappe.db.get_value(
			"Delivery Note", dn_name, ["custom_metrc_manifest_number", "custom_manifest"]
		)
	return frappe._dict(
		applies=applies,
		paid=paid,
		required=required,
		short=short,
		outstanding=max(flt(required) - flt(paid), 0),
		dn=dn_name,
		manifest_no=manifest_no,
		manifest_file=manifest_file,
		# Not "items": on a frappe._dict that name is the dict method.
		line_count=len(so.items or []),
		units=flt(so.get("total_qty")),
		mode=so.get("custom_mode_of_payment") or "—",
		pickup=(so.get("custom_pickup_or_dropoff") or "").upper() or "—",
	)


def item_lines(so, limit=15):
	"""One line per order line: name, code and quantity."""
	lines = []
	for row in (so.items or [])[:limit]:
		name = row.item_name or row.item_code
		code_part = f" (`{row.item_code}`)" if name != row.item_code else ""
		lines.append(f"\u2022 *{name}*{code_part} \u2014 {flt(row.qty):g} {row.uom or row.stock_uom or ''}".rstrip())
	extra = len(so.items or []) - limit
	if extra > 0:
		lines.append(f"\u2026 and {extra} more line(s) in the ERP")
	return "\n".join(lines) or "\u2014"


def payment_line(so, facts):
	if not facts.applies:
		return "Payment gate: not applicable ({0})".format(facts.mode)
	if facts.short:
		return ":red_circle: Paid {0} of {1}. *{2} outstanding.*".format(
			money(facts.paid, so), money(facts.required, so), money(facts.short, so)
		)
	return ":large_green_circle: Paid in full ({0}).".format(money(facts.paid, so))


# ── stage buttons ────────────────────────────────────────────────────────────


def stage_action_ids(so, cfg, facts=None):
	"""The buttons valid for an order right now, in display order."""
	stage = so.get("custom_logistic_status")
	facts = facts or order_facts(so, cfg)
	ids = []
	if stage == stages.RECEIVED:
		if cfg.conversions_enabled:
			ids.append("mt:flag_conversion")
		ids.append("mt:start_preparing")
	elif stage == stages.AWAITING_CONVERSION:
		ids.append("mt:new_conversion")
	elif stage == stages.PREPARING:
		if cfg.conversions_enabled:
			ids.append("mt:new_conversion")
		ids.append("mt:mark_prepared")
	elif stage == stages.PREPARED:
		ids.append("mt:create_dn")
	elif stage == stages.DN_READY:
		ids.append("mt:upload_manifest")
	elif stage == stages.AWAITING_RELEASE:
		if facts.applies and facts.short:
			ids += ["mt:record_payment", "mt:override"]
		else:
			ids.append("mt:release")
	elif stage == stages.RELEASED:
		ids.append("mt:delivered")
	elif stage == stages.ON_HOLD:
		ids.append("mt:resume")

	if stage not in stages.TERMINAL_STAGES and stage != stages.ON_HOLD:
		if facts.applies and facts.short and "mt:record_payment" not in ids:
			ids.append("mt:record_payment")
		ids.append("mt:hold")
	return ids


def status_select(so, action_ids, show_current=False):
	"""A Logistic Status dropdown listing every stage.

	A stage one of this order's steps leads to runs that step, as its button
	would. Any other stage is listed too, so the whole flow is visible, and
	picking it only explains where the order can go from here
	(UNREACHABLE_STATUS); the gates are never skipped.

	With show_current the order's own stage is the selected option, so the
	dropdown doubles as the status display. Picking it again does nothing.
	"""
	options = []
	stage = so.get("custom_logistic_status")
	current = stage or "No stage"

	def value(a, **extra):
		return json.dumps({"so": so.name, "stage": stage, "a": a, **extra}, separators=(",", ":"))

	if show_current:
		options.append(option(current, value("")))

	reachable = {}
	for action_id in action_ids:
		if action_id not in BUTTON_TARGET:
			continue
		target = BUTTON_TARGET[action_id] or so.get("custom_hold_from_stage") or "previous stage"
		reachable.setdefault(target, action_id)

	for target in list(stages.ALL_STAGES) + [t for t in reachable if t not in stages.ALL_STAGES]:
		if target == stage or target == stages.CANCELLED:
			continue  # Cancelled comes from cancelling the Sales Order itself
		action_id = reachable.get(target)
		if action_id:
			label = f"{target} ({BUTTONS[action_id][0]})" if action_id == "mt:override" else target
			options.append(option(label, value(action_id)))
		else:
			options.append(option(target, value(UNREACHABLE_STATUS, to=target)))
	if not options or (show_current and len(options) == 1):
		return None
	select = {
		"type": "static_select",
		"action_id": "mt:set_status",
		"placeholder": txt("Change logistic status"),
		"options": options,
	}
	if show_current:
		select["initial_option"] = options[0]
	return select


def status_section(so, cfg, facts=None):
	"""*Logistic Status* with a dropdown that shows the stage and changes it."""
	stage = so.get("custom_logistic_status") or "\u2014"
	select = None
	if stage not in stages.TERMINAL_STAGES:
		select = status_select(so, stage_action_ids(so, cfg, facts), show_current=True)
	return section(f"{STAGE_EMOJI.get(stage, '')} *Logistic Status:* {stage}", select)


def stage_actions_block(so, cfg, facts=None, block_id="stage_actions"):
	ids = stage_action_ids(so, cfg, facts)
	elements = [button(a, so) for a in ids]
	elements.append(open_erp_button(so))
	return {"type": "actions", "block_id": block_id, "elements": elements[:25]}


# ── messages ─────────────────────────────────────────────────────────────────


def conversion_mentions(cfg):
	"""Who "Needs conversion" tags: the company's Conversion Mention IDs, else
	its fulfillment group, else its fulfillment members one by one."""
	ids = [i.strip() for i in (cfg.get("conversion_mention") or "").split(",") if i.strip()]
	if ids:
		return [f"<!subteam^{i}>" if i.startswith("S") else f"<@{i}>" for i in ids]
	group = cfg.get("fulfillment_group_id") or ""
	if group.startswith("S"):
		return [f"<!subteam^{group}>"]
	from cannabis_management.mt_dispatch.slack import identity

	return [identity.mention(row.user) for row in cfg.get("team") or [] if row.get("fulfillment")]


def thread_parent(so, cfg):
	"""The order's first message, in the #conversions-motley layout: what the
	warehouse is short of, tagged, with the order's stage and buttons below."""
	facts = order_facts(so, cfg)
	stage = so.get("custom_logistic_status") or "—"
	rep = sales_rep_user(so)
	check = stock_check(so, cfg)
	header = ":red_circle: Conversion required" if check.need else ":package: New order"
	text = f"{header.split(' ', 1)[1]} · {so.name} · {so.customer_name or so.customer}"
	details = "*Sales Order:* <{0}|{1}>\n*Customer:* {2}\n*Warehouse:* {3}\n*Delivery date:* {4} \u00b7 {5}".format(
		erp_url("Sales Order", so.name), so.name, so.customer_name or so.customer,
		", ".join(check.warehouses) or "\u2014",
		format_date(so.delivery_date) if so.delivery_date else "\u2014", facts.pickup,
	)
	note = strip_html(so.get("custom_notes_for_logistics") or "").strip()
	if note:
		details += f"\n*Logistics note:* {note[:500]}"
	if so.get("amended_from"):
		details += f"\n*Amended from:* {so.amended_from}"
	blocks = [
		{"type": "header", "text": txt(header)},
		section(details),
		divider(),
	]
	if check.need:
		mention = " ".join(conversion_mentions(cfg))
		blocks.append(section((f"{mention} " if mention else "") + ":warning: *Needs conversion*\n" + "\n".join(check.need)))
		if check.ok:
			blocks.append(section("*Items OK*\n" + "\n".join(check.ok[:10])))
	else:
		blocks.append(section("*Items*\n" + item_lines(so)))
	blocks.append(divider())
	blocks.append(
		context(
			f"{facts.mode} \u00b7 {facts.pickup} \u00b7 Delivery {format_date(so.delivery_date) if so.delivery_date else '\u2014'} "
			f"\u00b7 Rep {frappe.db.get_value('User', rep, 'full_name') or rep}"
		)
	)
	blocks.append(status_section(so, cfg, facts))
	if so.get("custom_hold_reason") and stage == stages.ON_HOLD:
		blocks.append(context(f":double_vertical_bar: On hold: {so.custom_hold_reason}"))
	if stage in stages.TERMINAL_STAGES:
		blocks.append(context("This thread is closed."))
		blocks.append({"type": "actions", "block_id": "stage_actions", "elements": [open_erp_button(so)]})
	else:
		blocks.append(stage_actions_block(so, cfg, facts))
	return text, blocks


def stage_update(so, cfg, line, mentions=None, with_buttons=True):
	"""A thread reply: who did what, who acts next, and the next-step buttons."""
	body = line
	if mentions:
		body += "\n" + " ".join(mentions)
	blocks = [section(body)]
	if with_buttons and so.get("custom_logistic_status") not in stages.TERMINAL_STAGES:
		blocks.append(stage_actions_block(so, cfg, block_id="next_actions"))
	return line, blocks


def approval_dm(so, cfg, released_by=None):
	facts = order_facts(so, cfg)
	manifest_file = (
		f"<{get_url(facts.manifest_file)}|file>" if facts.manifest_file else "no file"
	)
	lines = [
		f"*Release request* · <{erp_url('Sales Order', so.name)}|{so.name}> · {so.customer_name or so.customer}",
		f"Delivery Note: {facts.dn or '—'} · Manifest: {facts.manifest_no or '—'} ({manifest_file})",
		f"Total {money(facts.required, so)} · Paid {money(facts.paid, so)} · Outstanding {money(facts.outstanding, so)}",
		payment_line(so, facts),
	]
	blocks = [section("\n".join(lines))]
	stage = so.get("custom_logistic_status")

	if released_by:
		blocks.append(context(f":truck: Released by {released_by}."))
	elif stage != stages.AWAITING_RELEASE:
		blocks.append(context(f"No longer awaiting release. Now at {stage}."))
	else:
		if facts.applies and facts.short:
			elements = [button("mt:override", so), button("mt:hold", so)]
		else:
			elements = [button("mt:release", so), button("mt:hold", so)]
		elements.append(open_erp_button(so))
		blocks.append({"type": "actions", "block_id": "approval_actions", "elements": elements})
	return f"Release request {so.name}", blocks


def dispatch_post(so, cfg):
	facts = order_facts(so, cfg)
	address = (so.get("shipping_address") or so.get("address_display") or "").replace("<br>", ", ")
	address = frappe.utils.strip_html(address).strip(", ") or "—"
	window = format_date(so.delivery_date) if so.delivery_date else "—"
	drivers = f"<!subteam^{cfg.drivers_group_id}> " if cfg.get("drivers_group_id") else ""
	text = f"{facts.pickup} · {so.name} · {so.customer_name or so.customer}"
	blocks = [
		section(
			f"{drivers}*{facts.pickup}* · <{erp_url('Sales Order', so.name)}|{so.name}> · {so.customer_name or so.customer}\n"
			f"Address: {address}\nWindow: {window} · Manifest {facts.manifest_no or '—'} · {facts.line_count} lines"
		),
		section("*Items*\n" + item_lines(so)),
	]
	if so.get("custom_logistic_status") == stages.RELEASED:
		blocks.append({"type": "actions", "block_id": "dispatch_actions", "elements": [button("mt:delivered", so)]})
	else:
		blocks.append(context(f"Now at {so.get('custom_logistic_status')}."))
	return text, blocks


def exception_post(so, cfg, title, detail, show_resume=False):
	text = f"{title} · {so.name}"
	blocks = [
		section(
			f":warning: *{title}* · <{erp_url('Sales Order', so.name)}|{so.name}> · {so.customer_name or so.customer}\n{detail}"
		)
	]
	if show_resume and so.get("custom_logistic_status") == stages.ON_HOLD:
		blocks.append({"type": "actions", "block_id": "exception_actions", "elements": [button("mt:resume", so)]})
	return text, blocks


# ── thread notes: things that happen around an order ─────────────────────────

INVOICE_VERBS = {"invoice_created": "created", "invoice_submitted": "submitted", "invoice_cancelled": "cancelled"}

# Conversion Entry Item (item field, qty field) pairs: raw materials in, finished goods out.
CE_SOURCE_PAIRS = [(f"raw_material_{n}", f"qty_rm_{n}") for n in range(1, 8)]
CE_TARGET_PAIRS = [(f"finished_good_{n}", f"qty_fg_{n}") for n in range(1, 4)]
# Slack allows 50 blocks a message; one per row plus the header stays well under.
MAX_CE_ROWS = 20


def event_note(so, what, ref, who, extra=None):
	"""(text, blocks) for a thread note, or (None, None) for an unknown kind."""
	extra = extra or {}
	at = format_datetime(now_datetime(), "d MMM HH:mm")

	if what in INVOICE_VERBS:
		verb = INVOICE_VERBS[what]
		head = ":x: *Invoice cancelled*" if what == "invoice_cancelled" else ":receipt: *Order billed*"
		line = f"{head} · Sales Invoice <{erp_url('Sales Invoice', ref)}|{ref}> {verb} by {who} · {at}"
		total = frappe.db.get_value("Sales Invoice", ref, ["grand_total", "currency"], as_dict=True)
		if total:
			line += f" · {fmt_money(flt(total.grand_total), currency=total.currency)}"
		return f"{ref} {verb} · {so.name}", [section(line)]

	if what == "dn_created":
		line = f":page_facing_up: *Delivery Note* <{erp_url('Delivery Note', ref)}|{ref}> created by {who} · {at}"
		return f"{ref} created · {so.name}", [section(line)]

	if what in ("conversion_submitted", "conversion_cancelled"):
		return conversion_note(so, ref, what, who, at)

	if what == "so_changed":
		changes = "\n".join(
			f"• *{label}:* {old or '—'} → {new or '—'}" for label, old, new in extra.get("changes") or []
		)
		return f"{so.name} changed", [section(f":pencil2: {who} changed the order · {at}\n{changes}")]

	return None, None


def conversion_note(so, ce_name, what, who, at):
	"""Which conversion, who did it, and what it turned into what."""
	ce = frappe.get_doc("Conversion Entry", ce_name)
	total = frappe.db.count("Conversion Entry", {"sales_order": so.name, "docstatus": ["<", 2]})
	done = frappe.db.count("Conversion Entry", {"sales_order": so.name, "docstatus": 1})
	cancelled = what == "conversion_cancelled"
	verb = "cancelled" if cancelled else "submitted"
	head = (
		f"{':x:' if cancelled else ':arrows_counterclockwise:'} *Conversion* "
		f"<{erp_url('Conversion Entry', ce.name)}|{ce.name}> {verb} by {who} · {at} · {done} of {total} submitted"
	)
	if ce.get("amended_from"):
		head += f"\nAmends {ce.amended_from}"
	blocks = [section(head)]

	rows = ce.get("items") or []
	for idx, row in enumerate(rows[:MAX_CE_ROWS], 1):
		source = _ce_lines(row, CE_SOURCE_PAIRS, row.source_warehouse)
		target = _ce_lines(row, CE_TARGET_PAIRS, row.target_warehouse)
		kind = f" · {row.conversion_type}" if row.get("conversion_type") else ""
		blocks.append(
			section(
				f"*Row {idx}*{kind}\n:package: *From*\n" + ("\n".join(source) or "—")
				+ "\n:dart: *To*\n" + ("\n".join(target) or "—")
			)
		)
	if len(rows) > MAX_CE_ROWS:
		blocks.append(context(f"… and {len(rows) - MAX_CE_ROWS} more row(s) in the ERP"))
	return f"{ce.name} {verb} · {so.name}", blocks


def _ce_lines(row, pairs, warehouse):
	lines = []
	for item_field, qty_field in pairs:
		item_code = row.get(item_field)
		qty = flt(row.get(qty_field))
		if not item_code or qty <= 0:
			continue
		item_name, uom = frappe.db.get_value("Item", item_code, ["item_name", "stock_uom"]) or (item_code, "")
		name = f"*{item_name}* (`{item_code}`)" if item_name and item_name != item_code else f"`{item_code}`"
		lines.append(f"• {name} — {qty:g} {uom or ''} · {warehouse or '—'}")
	return lines


# ── stock check: does the order need a conversion? ───────────────────────────


def stock_check(so, cfg=None):
	"""Per item and warehouse: what the order needs against what the Bin holds.

	The same arithmetic as the existing #conversions-motley hook
	(overrides/sales_invoice_hooks.py) -- stock_qty summed per item, compared
	with Bin.actual_qty -- but per company and per line warehouse rather than
	one hardcoded MTM warehouse.
	"""
	need, ok, warehouses = [], [], []
	totals = {}
	fixed = (cfg or {}).get("conversion_check_warehouse")
	for row in so.items or []:
		if not row.item_code:
			continue
		warehouse = fixed or row.warehouse or so.get("set_warehouse")
		key = (row.item_code, warehouse)
		entry = totals.setdefault(key, {"label": row.item_name or row.item_code, "uom": row.stock_uom or "", "required": 0.0})
		entry["required"] += flt(row.stock_qty or row.qty)
		if warehouse and warehouse not in warehouses:
			warehouses.append(warehouse)

	for (item_code, warehouse), e in totals.items():
		available = flt(frappe.db.get_value("Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty")) if warehouse else 0.0
		shortage = max(0.0, e["required"] - available)
		name = f"*{e['label']}* (`{item_code}`)" if e["label"] != item_code else f"`{item_code}`"
		if shortage > 0:
			need.append(
				f"\u2022 {name} \u2014 need *{shortage:.2f} {e['uom']}* (required {e['required']:.2f}, available {available:.2f})"
			)
		else:
			ok.append(f"\u2022 {name} \u2014 ok ({e['required']:.2f} {e['uom']})")
	return frappe._dict(need=need, ok=ok, warehouses=warehouses)


def conversion_check(so, cfg, fulfillment_mentions=None, extra_mentions=None):
	"""The stock check as a thread reply, in the #conversions-motley layout.

	post.on_transition only sends it when something is short.
	"""
	check = stock_check(so, cfg)
	header = ":red_circle: Conversion required" if check.need else ":large_green_circle: No conversion required"
	blocks = [
		{"type": "header", "text": txt(header)},
		section(
			"*Sales Order:* <{0}|{1}>\n*Customer:* {2}\n*Warehouse:* {3}".format(
				erp_url("Sales Order", so.name), so.name, so.customer_name or so.customer,
				", ".join(check.warehouses) or "\u2014",
			)
		),
		divider(),
	]
	if check.need:
		mention = " ".join(fulfillment_mentions if fulfillment_mentions is not None else conversion_mentions(cfg))
		blocks.append(section((f"{mention} " if mention else "") + ":warning: *Needs conversion*\n" + "\n".join(check.need)))
	if check.ok:
		if check.need:
			blocks.append(divider())
		blocks.append(section("*Items OK*\n" + "\n".join(check.ok[:10])))
	if extra_mentions:
		blocks.append(context("FYI " + " ".join(extra_mentions)))
	if so.get("custom_logistic_status") not in stages.TERMINAL_STAGES:
		blocks.append(stage_actions_block(so, cfg, block_id="next_actions"))
	return f"{so.name} inventory check \u00b7 {header.split(' ', 1)[1]}", blocks


# ── modals ───────────────────────────────────────────────────────────────────


def _modal(callback_id, title, blocks, meta, submit="Submit"):
	view = {
		"type": "modal",
		"callback_id": callback_id,
		"title": txt(title[:24]),
		"close": txt("Cancel"),
		"private_metadata": json.dumps(meta, separators=(",", ":")),
		"blocks": blocks[:100],
		"notify_on_close": True,
	}
	if submit:
		view["submit"] = txt(submit)
	return view


def _meta(so, **extra):
	return {"so": so.name, "stage": so.get("custom_logistic_status"), **extra}


def input_block(block_id, label, element, optional=False, hint=None, dispatch=False):
	block = {"type": "input", "block_id": block_id, "label": txt(label), "element": element, "optional": optional}
	if hint:
		block["hint"] = txt(hint)
	if dispatch:
		block["dispatch_action"] = True
	return block


def option(label, value):
	return {"text": txt(str(label)[:75]), "value": str(value)[:150]}


def static_select(action_id, options, initial=None, placeholder="Choose"):
	el = {"type": "static_select", "action_id": action_id, "placeholder": txt(placeholder), "options": options[:100]}
	if initial:
		match = next((o for o in el["options"] if o["value"] == initial), None)
		if match:
			el["initial_option"] = match
	return el


def external_select(action_id, placeholder="Type to search", min_query_length=2):
	return {
		"type": "external_select",
		"action_id": action_id,
		"placeholder": txt(placeholder),
		"min_query_length": min_query_length,
	}


def number_input(action_id, initial=None, decimal=True, min_value=None):
	el = {"type": "number_input", "action_id": action_id, "is_decimal_allowed": decimal}
	if initial is not None:
		el["initial_value"] = str(initial)
	if min_value is not None:
		el["min_value"] = str(min_value)
	return el


def warehouse_options(company):
	names = frappe.get_all(
		"Warehouse", filters={"company": company, "is_group": 0, "disabled": 0}, pluck="name", order_by="name", limit=100
	)
	return [option(n, n) for n in names]


def conversion_modal(so, cfg, rows=1, microns=False):
	"""Up to three conversion rows; each takes 1–3 raw materials and 1–3 finished goods."""
	rows = max(1, min(int(rows or 1), MAX_SLACK_ROWS))
	warehouses = warehouse_options(so.company)
	blocks = [
		section(f"Conversion for *{so.name}* · {so.customer_name or so.customer}"),
		input_block("posting_date", "Posting date", {"type": "datepicker", "action_id": "value", "initial_date": frappe.utils.nowdate()}),
	]
	for r in range(1, rows + 1):
		blocks.append(divider())
		blocks.append(section(f"*Row {r}*"))
		blocks.append(input_block(f"r{r}_src", "Source warehouse", static_select("value", warehouses, cfg.default_source_warehouse)))
		blocks.append(input_block(f"r{r}_tgt", "Target warehouse", static_select("value", warehouses, cfg.default_target_warehouse)))
		for n in range(1, MAX_SLACK_RAW + 1):
			blocks.append(
				input_block(
					f"r{r}_rm{n}", f"Raw material {n}", external_select("mt:item_or_tag", "Item or Metric Tag"),
					optional=n > 1,
				)
			)
			blocks.append(input_block(f"r{r}_rmq{n}", f"Raw material {n} qty", number_input("value", min_value=0), optional=n > 1))
		for n in range(1, MAX_SLACK_FINISHED + 1):
			blocks.append(
				input_block(f"r{r}_fg{n}", f"Finished good {n}", external_select("mt:item", "Item"), optional=n > 1)
			)
			blocks.append(input_block(f"r{r}_fgq{n}", f"Finished good {n} qty", number_input("value", min_value=0), optional=n > 1))
		if microns:
			for grams_field, _check, _flag, label in MICRON_FIELDS:
				blocks.append(
					input_block(
						f"r{r}_{grams_field}", f"Row {r} {label} (g)",
						number_input("value", min_value=0), optional=True,
					)
				)

	extra = []
	if rows < MAX_SLACK_ROWS:
		extra.append({"type": "button", "action_id": "mt:conv_add_row", "text": txt("Add row")})
	extra.append(
		{
			"type": "checkboxes",
			"action_id": "mt:conv_microns",
			"options": [option("Add microns", "microns")],
			**({"initial_options": [option("Add microns", "microns")]} if microns else {}),
		}
	)
	extra.append(
		{
			"type": "button",
			"action_id": "mt:open_erp",
			"text": txt("More rows? Open ERP form"),
			"url": conversion_erp_url(so),
		}
	)
	blocks.append(divider())
	blocks.append({"type": "actions", "block_id": "conv_controls", "elements": extra})
	blocks.append(
		input_block(
			"submit_mode",
			"When I submit",
			{
				"type": "radio_buttons",
				"action_id": "value",
				"options": [option("Save and submit", "submit"), option("Save draft", "draft")],
				"initial_option": option("Save and submit", "submit"),
			},
		)
	)
	return _modal("mt_conversion", "New conversion", blocks, _meta(so, rows=rows, microns=int(bool(microns))))


def conversion_erp_url(so):
	from urllib.parse import urlencode

	return get_url(
		"/app/conversion-entry/new?"
		+ urlencode({"sales_order": so.name, "company": so.company, "customer": so.customer})
	)


def delivery_note_modal(so, cfg):
	lines = so.items or []
	if len(lines) > MAX_DN_LINES:
		return _modal(
			"mt_delivery_note",
			"Delivery Note",
			[
				section(
					f"*{so.name}* has {len(lines)} lines. Slack takes up to {MAX_DN_LINES}. "
					"Create this Delivery Note from the ERP form."
				),
				{"type": "actions", "elements": [open_erp_button(so)]},
			],
			_meta(so, erp_only=1),
			submit=None,
		)

	blocks = [section(f"Delivery Note for *{so.name}* · {so.customer_name or so.customer}")]
	for row in lines:
		warehouse = row.warehouse or so.get("set_warehouse")
		tags = gates.tags_with_stock(row.item_code, warehouse) if warehouse else []
		blocks.append(divider())
		blocks.append(section(f"*{row.item_code}* · {row.item_name or ''}\nQty {flt(row.qty):g} {row.uom or ''} · {warehouse or 'no warehouse'}"))
		if tags:
			options = [option(f"{t.tag_code or t.muid} ({flt(t.qty):g})", t.muid) for t in tags]
			blocks.append(
				input_block(
					f"line_{row.name}",
					"Metric Tag",
					static_select("value", options, tags[0].muid if len(tags) == 1 else None, "Pick a tag"),
					optional=not cfg.require_muid_on_dn,
				)
			)
		else:
			blocks.append(context("No Metric Tag holds stock of this item here."))
	return _modal("mt_delivery_note", "Delivery Note", blocks, _meta(so), submit="Create draft")


def manifest_modal(so, cfg):
	blocks = [
		section(f"Metrc manifest for *{so.name}*"),
		input_block(
			"manifest_file",
			"Manifest file",
			{"type": "file_input", "action_id": "value", "filetypes": ["pdf", "png", "jpg", "jpeg"], "max_files": 1},
			hint="PDF, PNG or JPG, 20 MB max.",
		),
		input_block(
			"manifest_number",
			"Manifest number",
			{"type": "plain_text_input", "action_id": "value", "min_length": 10, "max_length": 10},
			hint="10 digits.",
		),
	]
	return _modal("mt_manifest", "Upload manifest", blocks, _meta(so))


def payment_modal(so, cfg):
	facts = order_facts(so, cfg)
	modes = [option(m, m) for m in frappe.get_all("Mode of Payment", filters={"enabled": 1}, pluck="name", limit=100)]
	blocks = [
		section(f"Payment for *{so.name}* · Outstanding {money(facts.outstanding, so)}"),
		input_block("amount", "Amount", number_input("value", initial=flt(facts.outstanding, 2) or None, min_value=0.01)),
		input_block("mode_of_payment", "Mode of payment", static_select("value", modes, cfg.default_mode_of_payment)),
		input_block("reference_no", "Reference no", {"type": "plain_text_input", "action_id": "value"}, optional=True),
		input_block("reference_date", "Date", {"type": "datepicker", "action_id": "value", "initial_date": frappe.utils.nowdate()}),
		input_block(
			"photo", "Photo", {"type": "file_input", "action_id": "value", "filetypes": ["pdf", "png", "jpg", "jpeg"], "max_files": 1},
			optional=True,
		),
	]
	return _modal("mt_payment", "Record payment", blocks, _meta(so))


def override_modal(so, cfg):
	facts = order_facts(so, cfg)
	blocks = [
		section(f"Release *{so.name}* with {money(facts.outstanding, so)} outstanding."),
		input_block(
			"reason", "Reason",
			{"type": "plain_text_input", "action_id": "value", "multiline": True, "min_length": 15},
			hint="At least 15 characters. Posted to the exceptions channel.",
		),
	]
	return _modal("mt_override", "Override release", blocks, _meta(so), submit="Release")


def hold_modal(so, cfg):
	blocks = [
		section(f"Put *{so.name}* on hold at {so.get('custom_logistic_status')}."),
		input_block("reason", "Reason", {"type": "plain_text_input", "action_id": "value", "multiline": True}),
	]
	return _modal("mt_hold", "Hold order", blocks, _meta(so), submit="Hold")


def delivered_modal(so, cfg):
	blocks = [
		section(f"Confirm *{so.name}* delivered or picked up."),
		input_block(
			"photo", "Signed manifest photo",
			{"type": "file_input", "action_id": "value", "filetypes": ["pdf", "png", "jpg", "jpeg"], "max_files": 1},
			optional=True,
		),
		input_block("note", "Note", {"type": "plain_text_input", "action_id": "value", "multiline": True}, optional=True),
	]
	return _modal("mt_delivered", "Confirm delivery", blocks, _meta(so), submit="Confirm")


MODAL_BUILDERS = {
	"mt_conversion": conversion_modal,
	"mt_delivery_note": delivery_note_modal,
	"mt_manifest": manifest_modal,
	"mt_payment": payment_modal,
	"mt_override": override_modal,
	"mt_hold": hold_modal,
	"mt_delivered": delivered_modal,
}


# ── commands and home ────────────────────────────────────────────────────────


def age_in_stage(so_name):
	at = frappe.db.get_value(
		"Dispatch Stage Log", {"parent": so_name, "parenttype": "Sales Order"}, "at", order_by="idx desc"
	)
	if not at:
		return "—"
	seconds = max(time_diff_in_seconds(now_datetime(), at), 0)
	hours = int(seconds // 3600)
	if hours >= 24:
		return f"{hours // 24}d {hours % 24}h"
	return f"{hours}h {int(seconds % 3600 // 60)}m"


def order_card(so, cfg, thread_link=None):
	facts = order_facts(so, cfg)
	stage = so.get("custom_logistic_status") or "—"
	owner = STAGE_OWNER.get(stage, "—")
	lines = [
		f"*<{erp_url('Sales Order', so.name)}|{so.name}>* · {so.customer_name or so.customer} · {so.company}",
		f"{STAGE_EMOJI.get(stage, '')} *{stage}* · owner: {owner} · in stage {age_in_stage(so.name)}",
		f"Owed {money(facts.required, so)} · Paid {money(facts.paid, so)}",
	]
	if thread_link:
		lines.append(f"<{thread_link}|Open thread>")
	return [section("\n".join(lines))]


def home_view(sections):
	"""sections: [(company, [(stage, [row, ...]), ...]), ...] where row is
	(so, age, action_id or None)."""
	blocks = [{"type": "header", "text": txt("Your dispatch queue")}]
	if not sections:
		blocks.append(section("Nothing waiting on you. :tada:"))
	for company, stage_rows in sections:
		blocks.append(divider())
		blocks.append({"type": "header", "text": txt(company)})
		if not stage_rows:
			blocks.append(context("Nothing waiting."))
		for stage, rows in stage_rows:
			blocks.append(context(f"{STAGE_EMOJI.get(stage, '')} *{stage}* · {len(rows)}"))
			for so, age, action_id in rows:
				accessory = button(action_id, so) if action_id else None
				blocks.append(
					section(
						f"<{erp_url('Sales Order', so.name)}|{short_name(so.name)}> · {so.customer_name or so.customer} · {age}",
						accessory,
					)
				)
				if len(blocks) >= 98:
					blocks.append(context("More orders than fit here. Use /board."))
					return {"type": "home", "blocks": blocks[:100]}
	return {"type": "home", "blocks": blocks[:100]}
