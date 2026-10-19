"""Backend for the Fulfillment Pipeline page (page/fulfillment_pipeline).

One card per open Sales Order, one column per Logistic Status. Every stage move
goes through flow.set_stage, so the stage log, the order's Slack thread and the
board all see the same move. The board's own drag rules are in _guard(); the
page draws a red drop zone from the same messages, and move_stage re-checks
them server side against fresh data.

Spec: fulfillment_pipeline_mapping.md (sections referenced below).
"""

import json

import frappe
from frappe import _
from frappe.utils import (
	add_days,
	cint,
	flt,
	formatdate,
	get_datetime,
	getdate,
	now_datetime,
	nowdate,
	strip_html,
)

from cannabis_management.mt_dispatch import flow, gates, notify, payments, stages
from cannabis_management.mt_dispatch.settings import get_company_settings
from cannabis_management.mt_dispatch.stages import (
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
)

STAGE_FIELD = flow.STAGE_FIELD

# Section 3. Order Closed Out is never shown; Cancelled is its own tab.
BOARD_STAGES = [
	RECEIVED,
	AWAITING_CONVERSION,
	PREPARING,
	PREPARED,
	DN_READY,
	AWAITING_RELEASE,
	RELEASED,
	ON_HOLD,
]

# Section 1.
VIEW_ROLES = {
	"Fulfilment",
	"Fulfilment - Consolidated",
	"Tori S - Consolidated",
	"Matt Schneider - Consolidated",
	"System Manager",
}
EDIT_ROLES = {
	"Fulfilment",
	"Fulfilment - Consolidated",
	"Tori S - Consolidated",
	"System Manager",
}

CANCELLED_DAYS = 60
# Stages where the shortage result is still written back to
# custom_conversion_required. Once the Delivery Note exists the flag is left
# alone, so stock moving elsewhere later cannot re-flag a shipped order.
WRITE_CONVERSION_FLAG = (RECEIVED, AWAITING_CONVERSION, PREPARING, PREPARED)
GRAM_UOMS = {"gram", "grams", "g", "gm", "gms"}
PULL_SHEET_GAP_ROWS = 7
EPSILON = 0.0005

FIELDS = [
	"name",
	"docstatus",
	"status",
	"customer_name",
	"company",
	"delivery_date",
	"creation",
	"modified",
	"set_warehouse",
	"total_qty",
	"per_billed",
	"advance_paid",
	"grand_total",
	"rounded_total",
	"disable_rounded_total",
	"is_internal_customer",
	STAGE_FIELD,
	"custom_pickup_or_dropoff",
	"custom_mode_of_payment",
	"custom_payment_verified",
	"custom_approval_status",
	"custom_notes_for_logistics",
	"custom_conversion_required",
	"custom_hold_reason",
	"custom_hold_from_stage",
	"custom_pull_sheet",
	"custom_update_ack_on",
	"custom_cancel_reason",
]


# ── access ───────────────────────────────────────────────────────────────────


def can_view(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(frappe.get_roles(user)) & VIEW_ROLES)


def can_edit(user=None):
	user = user or frappe.session.user
	return user == "Administrator" or bool(set(frappe.get_roles(user)) & EDIT_ROLES)


def _require(edit=False):
	if not (can_edit() if edit else can_view()):
		frappe.throw(
			_("Your role can view the Fulfillment Pipeline but not change it.")
			if edit and can_view()
			else _("You don't have access to the Fulfillment Pipeline."),
			frappe.PermissionError,
		)


def _open_so(sales_order, for_update=False):
	"""The order, checked for read access and for being on the board."""
	so = frappe.get_doc("Sales Order", sales_order, for_update=for_update)
	so.check_permission("read")
	if so.docstatus != 1:
		frappe.throw(_("{0} is not a submitted order.").format(so.name))
	if so.get(STAGE_FIELD) in stages.TERMINAL_STAGES:
		frappe.throw(_("{0} is {1} and no longer on the board.").format(so.name, so.get(STAGE_FIELD)))
	return so


# ── reading the board ────────────────────────────────────────────────────────


@frappe.whitelist()
def get_board(view="open"):
	"""Every card for one tab. Section 2 decides which orders show."""
	_require()
	cancelled = view == "cancelled"
	rows = _cancelled_rows() if cancelled else _open_rows()
	cards = _build(rows, cancelled=cancelled)
	return {
		"cards": cards,
		"view": "cancelled" if cancelled else "open",
		"stages": BOARD_STAGES,
		"cancelled_count": len(rows) if cancelled else len(_cancelled_rows(names_only=True)),
		"can_edit": can_edit(),
		"today": nowdate(),
		"now": str(now_datetime()),
	}


@frappe.whitelist()
def get_card(sales_order):
	"""One card, fresh. None when the order is no longer on the open board."""
	_require()
	if not frappe.db.exists("Sales Order", sales_order):
		return None
	rows = _open_rows(name=sales_order)
	cards = _build(rows)
	return cards[0] if cards else None


def _board_companies():
	"""Companies on the dispatch flow. A company with no enabled Dispatch
	Company Settings is not on the flow (see settings.py), so its orders stay
	off the board -- e.g. Motley Terpz, whose open orders all predate June."""
	return frappe.get_all("Dispatch Company Settings", filters={"enabled": 1}, pluck="name") or ["-"]


def _open_rows(name=None):
	filters = [
		["docstatus", "=", 1],
		["company", "in", _board_companies()],
		["status", "not in", ["Completed", "Closed"]],
		[STAGE_FIELD, "not in", [CLOSED_OUT, CANCELLED]],
	]
	if name:
		filters.append(["name", "=", name])
	# get_list, not get_all: a user fenced to one company sees only its orders.
	return frappe.get_list(
		"Sales Order", filters=filters, fields=FIELDS, order_by="creation asc", limit_page_length=0
	)


def _cancelled_rows(names_only=False):
	since = add_days(nowdate(), -CANCELLED_DAYS)
	# A cancelled order that was amended lives on as its amendment, which is
	# on the open board; only orders that really ended belong on this tab.
	superseded = frappe.get_all(
		"Sales Order",
		filters={"amended_from": ["is", "set"], "modified": [">=", since]},
		pluck="amended_from",
	)
	return frappe.get_list(
		"Sales Order",
		filters=[
			["modified", ">=", since],
			["company", "in", _board_companies()],
			["name", "not in", superseded or ["-"]],
		],
		or_filters=[[STAGE_FIELD, "=", CANCELLED], ["docstatus", "=", 2]],
		fields=["name"] if names_only else FIELDS,
		order_by="modified desc",
		limit_page_length=0,
	)


def _build(rows, cancelled=False, write_flags=True):
	if not rows:
		return []
	names = [r.name for r in rows]

	items = frappe.get_all(
		"Sales Order Item",
		filters={"parenttype": "Sales Order", "parent": ["in", names]},
		fields=[
			"parent", "name", "idx", "item_code", "item_name", "qty", "stock_qty", "delivered_qty",
			"conversion_factor", "uom", "stock_uom", "warehouse",
		],
		order_by="parent asc, idx asc",
	)
	items_by_so = {}
	for it in items:
		items_by_so.setdefault(it.parent, []).append(it)

	item_codes = sorted({it.item_code for it in items if it.item_code})
	ctx = frappe._dict(
		stock_items=set(
			frappe.get_all("Item", filters={"name": ["in", item_codes], "is_stock_item": 1}, pluck="name")
		) if item_codes else set(),
		bins=_bins(item_codes),
		reserved=_reservations(item_codes),
		targets=_conversion_targets(names),
		ces=_conversion_entries(names),
		dns=_delivery_notes(names),
		reps=_sales_reps(names),
		logs=_stage_logs(names),
		abbr=dict(frappe.get_all("Company", fields=["name", "abbr"], as_list=True)),
	)
	versions = {} if cancelled else _versions(rows, ctx.logs)

	cards = []
	for r in rows:
		card = _card(r, items_by_so.get(r.name, []), ctx, versions.get(r.name, []), cancelled)
		cards.append(card)
		if write_flags and not cancelled:
			_sync_conversion_flag(r, card)
	return cards


def _bins(item_codes):
	if not item_codes:
		return {}
	return {
		(b.item_code, b.warehouse): flt(b.actual_qty)
		for b in frappe.get_all(
			"Bin", filters={"item_code": ["in", item_codes]}, fields=["item_code", "warehouse", "actual_qty"]
		)
	}


def _reservations(item_codes):
	"""{(item, warehouse): {sales order: qty still reserved}} from open Stock
	Reservation Entries. Section 4: stock held for OTHER orders is not available."""
	if not item_codes:
		return {}
	rows = frappe.db.sql(
		"""
		select item_code, warehouse, voucher_no, sum(reserved_qty - delivered_qty) as qty
		from `tabStock Reservation Entry`
		where docstatus = 1 and voucher_type = 'Sales Order'
		  and status not in ('Delivered', 'Cancelled')
		  and item_code in %(items)s
		group by item_code, warehouse, voucher_no
		""",
		{"items": item_codes},
		as_dict=True,
	)
	out = {}
	for r in rows:
		if flt(r.qty) > 0:
			out.setdefault((r.item_code, r.warehouse), {})[r.voucher_no] = flt(r.qty)
	return out


def _conversion_targets(names):
	"""{so: {item: [target warehouse]}} from submitted Conversion Entries --
	gates.conversion_targets for many orders at once."""
	rows = frappe.db.sql(
		"""
		select ce.sales_order, cei.target_warehouse,
		       cei.finished_good_1, cei.finished_good_2, cei.finished_good_3
		from `tabConversion Entry Item` cei
		join `tabConversion Entry` ce on ce.name = cei.parent
		where ce.sales_order in %(names)s and ce.docstatus = 1 and ifnull(cei.target_warehouse, '') != ''
		""",
		{"names": names},
		as_dict=True,
	)
	out = {}
	for r in rows:
		per_so = out.setdefault(r.sales_order, {})
		for item_code in (r.finished_good_1, r.finished_good_2, r.finished_good_3):
			if item_code and r.target_warehouse not in per_so.setdefault(item_code, []):
				per_so[item_code].append(r.target_warehouse)
	return out


def _conversion_entries(names):
	out = {}
	for r in frappe.get_all(
		"Conversion Entry",
		filters={"sales_order": ["in", names], "docstatus": ["<", 2]},
		fields=["name", "sales_order", "docstatus"],
		order_by="creation desc",
	):
		out.setdefault(r.sales_order, {"draft": [], "submitted": []})[
			"submitted" if r.docstatus == 1 else "draft"
		].append(r.name)
	return out


def _delivery_notes(names):
	rows = frappe.db.sql(
		"""
		select distinct dni.against_sales_order as so, dn.name, dn.docstatus
		from `tabDelivery Note Item` dni
		join `tabDelivery Note` dn on dn.name = dni.parent
		where dni.against_sales_order in %(names)s and dn.docstatus < 2
		order by dn.docstatus desc, dn.creation asc
		""",
		{"names": names},
		as_dict=True,
	)
	out = {}
	for r in rows:
		out.setdefault(r.so, []).append(r)
	return out


def _sales_reps(names):
	out = {}
	for r in frappe.get_all(
		"Sales Team",
		filters={"parenttype": "Sales Order", "parent": ["in", names]},
		fields=["parent", "sales_person"],
		order_by="idx asc",
	):
		out.setdefault(r.parent, r.sales_person)
	return out


def _stage_logs(names):
	out = {}
	for r in frappe.get_all(
		"Dispatch Stage Log",
		filters={"parenttype": "Sales Order", "parent": ["in", names]},
		fields=["parent", "to_stage", "action", "at"],
		order_by="idx asc",
	):
		out.setdefault(r.parent, []).append(r)
	return out


def _entered_at(logs):
	"""Section 5: when the order entered the flow. The first enter_flow row, or
	failing that the first stage move of any kind."""
	for row in logs:
		if row.action == "enter_flow" and row.at:
			return get_datetime(row.at)
	for row in logs:
		if row.at:
			return get_datetime(row.at)
	return None


def _versions(rows, logs):
	since = {}
	for r in rows:
		entered = _entered_at(logs.get(r.name, []))
		if entered:
			since[r.name] = entered
	if not since:
		return {}
	out = {}
	for v in frappe.db.sql(
		"""
		select docname, creation, data from `tabVersion`
		where ref_doctype = 'Sales Order' and docname in %(names)s and creation > %(since)s
		order by creation asc
		""",
		{"names": list(since), "since": min(since.values())},
		as_dict=True,
	):
		if get_datetime(v.creation) > since[v.docname]:
			out.setdefault(v.docname, []).append(v)
	return out


# ── one card ─────────────────────────────────────────────────────────────────


def _unit(uom):
	return "g" if (uom or "").strip().lower() in GRAM_UOMS else (uom or "")


def _qty_text(value, uom):
	unit = _unit(uom)
	return f"{flt(value):g}{(' ' + unit) if unit else ''}"


def _lines(r, its, ctx):
	"""Per (item, warehouse) on the order: what is still to ship, what the
	warehouse can give it, and the gap. Section 4's conversion badge."""
	lines = {}
	so_targets = ctx.targets.get(r.name, {})
	for it in its:
		row_wh = it.warehouse or r.set_warehouse
		need = max(flt(it.qty) - flt(it.delivered_qty), 0) * (flt(it.conversion_factor) or 1)
		# Same rule as gates.delivery_warehouse: goods this order converted
		# ship from the Conversion Entry's target when it holds the quantity.
		wh = row_wh
		for target in so_targets.get(it.item_code, []):
			if ctx.bins.get((it.item_code, target), 0) >= need:
				wh = target
				break
		line = lines.setdefault(
			(it.item_code, wh),
			frappe._dict(
				item_code=it.item_code,
				item_name=it.item_name or it.item_code,
				warehouse=wh,
				row_warehouse=row_wh,
				uom=it.stock_uom,
				ordered=0.0,
				need=0.0,
				is_stock=it.item_code in ctx.stock_items,
			),
		)
		line.ordered += flt(it.stock_qty)
		line.need += need

	out = []
	for (item_code, wh), line in lines.items():
		available = short = None
		if line.is_stock:
			held_for_others = sum(
				q for so_name, q in ctx.reserved.get((item_code, wh), {}).items() if so_name != r.name
			)
			available = ctx.bins.get((item_code, wh), 0) - held_for_others
			short = max(line.need - available, 0) if line.need > EPSILON else 0
		out.append(
			{
				"item_code": item_code,
				"item_name": line.item_name,
				"warehouse": wh,
				"row_warehouse": line.row_warehouse,
				"uom": _unit(line.uom),
				"ordered": flt(line.ordered, 3),
				"need": flt(line.need, 3),
				"available": None if available is None else flt(available, 3),
				"short": flt(short or 0, 3),
				"is_stock": line.is_stock,
			}
		)
	return out


def _stage_at(r, logs):
	current = r.get(STAGE_FIELD)
	at = None
	for row in logs:
		if row.to_stage == current and row.at and row.action != "update_ack":
			at = row.at
	return str(at or r.creation)


def _update_banner(r, its, versions):
	"""Section 5: what changed on the items or the date since the order entered
	the flow and since the last "Got it". Newest first."""
	ack = get_datetime(r.custom_update_ack_on) if r.custom_update_ack_on else None
	rows_by_name = {it.name: it for it in its}
	notes, latest = [], None
	for v in reversed(versions):
		if ack and get_datetime(v.creation) <= ack:
			continue
		found = _diff_notes(v.data, rows_by_name)
		if found:
			notes.extend(found)
			latest = latest or str(v.creation)
	if not notes:
		return None
	return {"note": notes[0], "more": len(notes) - 1, "all": notes[:12], "at": latest}


def _md(value):
	"""A date in the ERP's own format (System Settings), as the board shows it."""
	try:
		return formatdate(getdate(value))
	except Exception:
		return str(value or "-")


def _diff_notes(raw, rows_by_name):
	try:
		data = json.loads(raw or "{}")
	except ValueError:
		return []
	out = []
	for change in data.get("changed") or []:
		if len(change) == 3 and change[0] == "delivery_date":
			out.append(_("Delivery date moved from {0} to {1}").format(_md(change[1]), _md(change[2])))
	for entry in data.get("added") or []:
		if len(entry) == 2 and entry[0] == "items":
			row = entry[1] or {}
			out.append(
				_("Item added: {0} {1}").format(
					row.get("item_name") or row.get("item_code"), _qty_text(row.get("qty"), row.get("uom"))
				)
			)
	for entry in data.get("removed") or []:
		if len(entry) == 2 and entry[0] == "items":
			row = entry[1] or {}
			out.append(_("Item removed: {0}").format(row.get("item_name") or row.get("item_code")))
	for entry in data.get("row_changed") or []:
		if len(entry) != 4 or entry[0] != "items":
			continue
		current = rows_by_name.get(entry[2])
		label = (current.item_name or current.item_code) if current else _("a line")
		uom = current.uom if current else ""
		for field, old, new in entry[3] or []:
			if field == "qty":
				out.append(
					_("Qty on {0} changed {1} to {2}").format(label, _qty_text(old, uom), _qty_text(new, uom))
				)
			elif field == "item_code":
				out.append(_("Item changed from {0} to {1}").format(old, new))
	return out


def _cod_unpaid(r):
	"""COD with money still owed. The cached gate result for dispatch
	companies; computed directly where there is no dispatch record to keep it."""
	if r.custom_mode_of_payment != stages.COD:
		return False
	cfg = get_company_settings(r.company)
	if cfg:
		# Same rule as dispatch's G5: no gate (switched off, internal
		# customer, nothing owed) means nothing to wait for.
		if not payments.payment_gate_applies(r, cfg):
			return False
		return not cint(r.custom_payment_verified)
	if payments.is_internal(r):
		return False
	return payments.required_amount(r) - payments.paid_amount(r) > 0.01


def _card(r, its, ctx, versions, cancelled=False):
	raw_stage = r.get(STAGE_FIELD)
	on_flow = raw_stage in stages.ALL_STAGES
	if cancelled:
		status = CANCELLED
	else:
		# An order with no stage (or a retired one) sits at the entry point.
		status = raw_stage if raw_stage in BOARD_STAGES else RECEIVED

	lines = _lines(r, its, ctx)
	short_count = sum(1 for line in lines if line["short"] > EPSILON)
	ce = ctx.ces.get(r.name, {"draft": [], "submitted": []})
	dns = ctx.dns.get(r.name, [])
	logs = ctx.logs.get(r.name, [])
	units = {line["uom"] for line in lines}

	card = {
		"so": r.name,
		"customer": r.customer_name,
		"company": r.company,
		"co": ctx.abbr.get(r.company) or r.company,
		"due": str(r.delivery_date) if r.delivery_date else None,
		"type": r.custom_pickup_or_dropoff or "",
		"cod": r.custom_mode_of_payment == stages.COD,
		"cod_unpaid": False if cancelled else _cod_unpaid(r),
		"approval": r.custom_approval_status or "",
		"rep": ctx.reps.get(r.name) or "",
		"total_qty": flt(r.total_qty, 3),
		"uom": units.pop() if len(units) == 1 else "",
		"strains": len({it.item_code for it in its if it.item_code}),
		"created": str(r.creation),
		"status": status,
		"raw_status": raw_stage or "",
		"on_flow": on_flow,
		"stage_at": _stage_at(r, logs),
		"hold_reason": r.custom_hold_reason or "",
		"hold_from": r.custom_hold_from_stage or "",
		"cancel_reason": r.custom_cancel_reason or "",
		"note": strip_html(r.custom_notes_for_logistics or "").strip()[:240],
		"pull_sheet": r.custom_pull_sheet or "",
		"lines": lines,
		"needs_conv": short_count > 0,
		"short_count": short_count,
		"conv": "submitted" if ce["submitted"] else ("draft" if ce["draft"] else "none"),
		"conv_draft": ce["draft"][0] if ce["draft"] else None,
		"dn": dns[0].name if dns else None,
		"dn_submitted": bool(dns and dns[0].docstatus == 1),
		"invoiced": flt(r.per_billed) > 0,
		"docstatus": r.docstatus,
		"updated": None if cancelled else _update_banner(r, its, versions),
	}
	card["blocked"] = (
		{stage: _("Cancelled orders are read-only.") for stage in BOARD_STAGES}
		if cancelled
		else {stage: _guard(card, stage) for stage in BOARD_STAGES}
	)
	return card


def _guard(card, to):
	"""Section 6 drag guards. Returns why the move is refused, or ""."""
	if to == card["status"]:
		return ""
	if to == PREPARING and card["needs_conv"] and card["conv"] != "submitted":
		return _("Submit the Conversion Entry before preparing this order.")
	# No pull-sheet rule on Order Prepared: the team drags freely and the
	# card's "Pull sheet" step only shows whether one is filed (user, 2026-10-19).
	if to == DN_READY and not card["dn"]:
		return _("Create the Delivery Note first.")
	if to == RELEASED:
		if card["cod"]:
			if card["cod_unpaid"]:
				return _("COD order: payment must be in the cash ledger before release.")
		elif card["approval"] not in stages.APPROVAL_CLEAR:
			return _("Terms order: credit approval is {0}.").format(card["approval"] or _("not requested"))
	return ""


def _sync_conversion_flag(r, card):
	"""Section 4: keep custom_conversion_required equal to the badge, so list
	view and Slack read the same answer."""
	if r.docstatus != 1 or r.get(STAGE_FIELD) not in WRITE_CONVERSION_FLAG:
		return
	want = 1 if card["needs_conv"] else 0
	if cint(r.custom_conversion_required) != want:
		frappe.db.set_value("Sales Order", r.name, "custom_conversion_required", want, update_modified=False)


def _fresh_card(sales_order):
	"""The card for an order this request already holds a lock on."""
	rows = frappe.get_all("Sales Order", filters={"name": sales_order}, fields=FIELDS)
	cards = _build(rows, write_flags=False)
	return cards[0] if cards else None


# ── actions ──────────────────────────────────────────────────────────────────


def _notify(sales_order, action):
	notify.enqueue(
		"cannabis_management.mt_dispatch.notify.on_transition",
		sales_order=sales_order,
		action=action,
		source="ERP",
		enqueue_after_commit=True,
		queue="short",
	)


def _touch(sales_order):
	"""Redraw this card on every open board (set_stage does this for moves)."""
	frappe.publish_realtime("mt_fulfillment_update", {"sales_order": sales_order}, after_commit=True)


@frappe.whitelist(methods=["POST"])
def move_stage(sales_order, to_stage, reason=None):
	"""Drag a card to a column (section 6)."""
	_require(edit=True)
	if to_stage not in BOARD_STAGES:
		frappe.throw(_("{0} is not a column on the board.").format(to_stage))

	so = _open_so(sales_order, for_update=True)
	current = so.get(STAGE_FIELD)
	if current == to_stage:
		return get_card(so.name)

	reason = (reason or "").strip()
	if to_stage == ON_HOLD and not reason:
		frappe.throw(_("A reason is required to put an order on hold."))

	if to_stage == RELEASED and get_company_settings(so.company):
		# The gate decides on fresh money, never the cached flag alone.
		payments.refresh_payment_status(so.name, notify_approvers=False)

	card = _fresh_card(so.name)
	blocked = _guard(card, to_stage)
	if blocked:
		frappe.throw(blocked, title=_("Can't move {0} to {1}").format(so.name, to_stage))

	if to_stage == ON_HOLD:
		so.db_set({"custom_hold_from_stage": current, "custom_hold_reason": reason}, update_modified=False)
	elif current == ON_HOLD:
		so.db_set({"custom_hold_from_stage": None, "custom_hold_reason": None}, update_modified=False)
	if to_stage == RELEASED:
		so.db_set(
			{"custom_released_by": frappe.session.user, "custom_released_on": now_datetime()},
			update_modified=False,
		)

	flow.set_stage(so, to_stage, "board_move", "ERP", note=reason or None)

	# Slack gets the step it already knows how to post, so a hold still lands
	# in exceptions and a release still posts to dispatch.
	if to_stage == ON_HOLD:
		_notify(so.name, "hold")
	elif current == ON_HOLD:
		_notify(so.name, "resume")
	elif to_stage == RELEASED:
		_notify(so.name, "release")
	else:
		_notify(so.name, "board_move")

	return get_card(so.name)


@frappe.whitelist(methods=["POST"])
def attach_pull_sheet(sales_order, file_url):
	"""The filled sheet, uploaded onto the order, marks the Pull sheet step done."""
	_require(edit=True)
	so = _open_so(sales_order)
	if not file_url or not frappe.db.exists("File", {"file_url": file_url}):
		frappe.throw(_("That upload is no longer available. Try again."))

	from cannabis_management.mt_dispatch.builders import attach_file

	attach_file(file_url, "Sales Order", so.name)
	so.db_set(
		{
			"custom_pull_sheet": file_url,
			"custom_pull_sheet_by": frappe.session.user,
			"custom_pull_sheet_on": now_datetime(),
		},
		update_modified=False,
	)
	_touch(so.name)
	return get_card(so.name)


@frappe.whitelist(methods=["POST"])
def ack_update(sales_order):
	"""Section 5: "Got it" clears the Order Updated banner."""
	_require(edit=True)
	so = _open_so(sales_order)
	so.db_set(
		{"custom_update_ack_on": now_datetime(), "custom_update_ack_by": frappe.session.user},
		update_modified=False,
	)
	current = so.get(STAGE_FIELD)
	flow._append_log(so, current, current, "update_ack", "ERP", None)
	_touch(so.name)
	return get_card(so.name)


@frappe.whitelist(methods=["POST"])
def conversion_action(sales_order):
	"""What "+ Conv." should do: open the existing draft, or start a new one."""
	_require(edit=True)
	so = _open_so(sales_order)
	draft = frappe.db.get_value(
		"Conversion Entry", {"sales_order": so.name, "docstatus": 0}, "name", order_by="creation desc"
	)
	if draft:
		return {"open": draft}
	card = _fresh_card(so.name)
	if not card["needs_conv"]:
		frappe.throw(_("Nothing on {0} is short, so no conversion is needed.").format(so.name))
	return {"new": True}


@frappe.whitelist(methods=["POST"])
def make_conversion_entry(source_name):
	"""A new Conversion Entry for the order's short lines, opened in the form.

	Returned unsaved, like the Sales Order form's own Create > Conversion
	Entry: Conversion Entry's validate requires Raw Material 1 on every row,
	and the raw materials are for the team to pick (Scan Metrc Tag does this),
	so an empty draft cannot be saved. It becomes a draft on the team's first
	save. The order moves to Awaiting Conversion now.
	"""
	_require(edit=True)
	so = _open_so(source_name, for_update=True)
	card = _fresh_card(so.name)
	short_lines = [line for line in card["lines"] if line["short"] > EPSILON]
	if not short_lines:
		frappe.throw(_("Nothing on {0} is short, so no conversion is needed.").format(so.name))

	ce = frappe.new_doc("Conversion Entry")
	ce.company = so.company
	ce.customer = so.customer
	ce.sales_order = so.name
	ce.posting_date = nowdate()
	ce.reasons = "Blending"
	for line in short_lines:
		ce.append(
			"items",
			{
				"finished_good_1": line["item_code"],
				"qty_fg_1": line["short"],
				"source_warehouse": line["row_warehouse"],
				"target_warehouse": line["row_warehouse"],
			},
		)

	so.db_set("custom_conversion_required", 1, update_modified=False)
	if so.get(STAGE_FIELD) == RECEIVED or so.get(STAGE_FIELD) not in stages.ALL_STAGES:
		flow.set_stage(so, AWAITING_CONVERSION, "board_move", "ERP", note=_("Conversion started from the board"))
		_notify(so.name, "flag_conversion")
	else:
		_touch(so.name)
	return ce.as_dict()


@frappe.whitelist(methods=["POST"])
def make_dn(sales_order):
	"""Section 6 "+ DN": a draft Delivery Note from the order, or the one it has."""
	_require(edit=True)
	so = _open_so(sales_order, for_update=True)

	existing = gates.delivery_notes_for(so.name)
	if existing:
		return {"name": existing[0], "existing": True}

	card = _fresh_card(so.name)
	if card["needs_conv"] and card["conv"] != "submitted":
		frappe.throw(_("Short items need a submitted Conversion Entry first."))

	from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

	dn = make_delivery_note(so.name)
	if not dn.items:
		frappe.throw(_("Nothing is left to deliver on {0}.").format(so.name))

	# Ship each line from where its goods are (see gates.delivery_warehouse),
	# as the dispatch flow's own builder does.
	targets = gates.conversion_targets(so.name)
	so_rows = {row.name: row for row in so.items}
	for item in dn.items:
		row = so_rows.get(item.so_detail)
		if row:
			item.warehouse = gates.delivery_warehouse(so, row, targets)
	warehouses = {item.warehouse for item in dn.items}
	if len(warehouses) == 1:
		dn.set_warehouse = warehouses.pop()

	dn.insert()

	# flow.dn_after_insert has already moved a dispatch company's order; this
	# covers the rest (and an order sitting On Hold is left where it is).
	stage = frappe.db.get_value("Sales Order", so.name, STAGE_FIELD)
	if stage in flow.BEFORE_DN or stage not in stages.ALL_STAGES:
		so.set(STAGE_FIELD, stage)
		flow.set_stage(so, DN_READY, "board_move", "ERP", note=_("{0} created from the board").format(dn.name))
		_notify(so.name, "board_move")
	else:
		_touch(so.name)
	return {"name": dn.name}


# ── automatic moves (section 6) ──────────────────────────────────────────────


def on_si_submit(doc, method=None):
	"""A Released order that is now fully invoiced leaves the board."""
	orders = []
	for row in doc.items or []:
		if row.get("sales_order") and row.sales_order not in orders:
			orders.append(row.sales_order)
	for so_name in orders:
		stage, per_billed = frappe.db.get_value("Sales Order", so_name, [STAGE_FIELD, "per_billed"]) or (None, 0)
		if stage != RELEASED or flt(per_billed) < 99.99:
			continue
		so = frappe.get_doc("Sales Order", so_name)
		flow.set_stage(so, CLOSED_OUT, "invoice_close", "System", note=doc.name)
		notify.enqueue(
			"cannabis_management.mt_dispatch.notify.on_transition",
			sales_order=so_name,
			action="invoice_close",
			enqueue_after_commit=True,
			queue="short",
		)


# ── Lab Pull Sheet print format (section 8) ──────────────────────────────────


def _mdy(value):
	if not value:
		return "-"
	d = getdate(value)
	return f"{d.month}/{d.day}/{d.year}"


def lab_pull_sheet(doc):
	"""Jinja method for the "Lab Pull Sheet" print format."""
	so_name = doc.name if hasattr(doc, "name") else doc.get("name")
	rows = frappe.get_all("Sales Order", filters={"name": so_name}, fields=FIELDS)
	short = []
	if rows:
		cards = _build(rows, write_flags=False)
		if cards:
			short = [line["item_name"] for line in cards[0]["lines"] if line["short"] > EPSILON]

	lines, total = [], 0.0
	for it in doc.get("items") or []:
		qty = flt(it.get("stock_qty")) or flt(it.get("qty"))
		total += qty
		lines.append({"item_name": it.get("item_name") or it.get("item_code"), "qty": _qty_text(qty, it.get("stock_uom"))})

	units = {_unit(it.get("stock_uom")) for it in doc.get("items") or []}
	return {
		"date": _mdy(nowdate()),
		"delivery_date": _mdy(doc.get("delivery_date")),
		"rows": lines,
		# Blank rows under each strain, one per extra tag pulled for it.
		"gap_rows": PULL_SHEET_GAP_ROWS,
		"total": _qty_text(total, units.pop() if len(units) == 1 else ""),
		"short": short,
		"order_type": " · ".join(
			p for p in (doc.get("custom_pickup_or_dropoff"), "COD" if doc.get("custom_mode_of_payment") == stages.COD else "Terms") if p
		),
	}
