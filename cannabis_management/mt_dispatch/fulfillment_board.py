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

VIEW_ROLES = {
	"Fulfilment",
	"Fulfilment - Consolidated",
	"Tori S - Consolidated",
	"Matt Schneider - Consolidated",
	"System Manager",
	"Manufacturing Manager",
}
EDIT_ROLES = {
	"Fulfilment",
	"Fulfilment - Consolidated",
	"Tori S - Consolidated",
	"System Manager",
}

CANCELLED_DAYS = 60
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
	so = frappe.get_doc("Sales Order", sales_order, for_update=for_update)
	so.check_permission("read")
	if so.docstatus != 1:
		frappe.throw(_("{0} is not a submitted order.").format(so.name))
	if so.get(STAGE_FIELD) in stages.TERMINAL_STAGES:
		frappe.throw(_("{0} is {1} and no longer on the board.").format(so.name, so.get(STAGE_FIELD)))
	return so


@frappe.whitelist()
def get_board(view="open"):
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
		"can_reserve": _can_reserve(),
		"today": nowdate(),
		"now": str(now_datetime()),
	}


@frappe.whitelist()
def get_card(sales_order):
	_require()
	if not frappe.db.exists("Sales Order", sales_order):
		return None
	rows = _open_rows(name=sales_order)
	cards = _build(rows)
	return cards[0] if cards else None


def _board_companies():
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
	return frappe.get_list(
		"Sales Order", filters=filters, fields=FIELDS, order_by="creation asc", limit_page_length=0
	)


def _cancelled_rows(names_only=False):
	since = add_days(nowdate(), -CANCELLED_DAYS)
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
		row_sre=_sre_by_row(names),
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


def _sre_by_row(names):
	out = {}
	if not names:
		return out
	for r in frappe.db.sql(
		"""
		select voucher_detail_no, warehouse, sum(reserved_qty - delivered_qty) as qty
		from `tabStock Reservation Entry`
		where docstatus = 1 and voucher_type = 'Sales Order' and voucher_no in %(names)s
		  and status not in ('Delivered', 'Cancelled')
		group by voucher_detail_no, warehouse
		""",
		{"names": names},
		as_dict=True,
	):
		if flt(r.qty) > 0:
			out.setdefault(r.voucher_detail_no, {})[r.warehouse] = flt(r.qty)
	return out


def _open_sres(so_name):
	return [
		r
		for r in frappe.get_all(
			"Stock Reservation Entry",
			filters={
				"docstatus": 1,
				"voucher_type": "Sales Order",
				"voucher_no": so_name,
				"status": ["not in", ["Delivered", "Cancelled"]],
			},
			fields=["name", "voucher_detail_no", "warehouse", "reserved_qty", "delivered_qty", "stock_uom"],
			order_by="creation asc",
		)
		if flt(r.reserved_qty) - flt(r.delivered_qty) > EPSILON
	]


def _qty_label(by_unit):
	parts = [_qty_text(q, u) for u, q in by_unit.items() if q > EPSILON]
	return " + ".join(parts) or "0"


def _conversion_targets(names):
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


def _unit(uom):
	return "g" if (uom or "").strip().lower() in GRAM_UOMS else (uom or "")


def _qty_text(value, uom):
	unit = _unit(uom)
	return f"{flt(value):g}{(' ' + unit) if unit else ''}"


def _lines(r, its, ctx):
	lines = {}
	so_targets = ctx.targets.get(r.name, {})
	for it in its:
		row_wh = it.warehouse or r.set_warehouse
		need = max(flt(it.qty) - flt(it.delivered_qty), 0) * (flt(it.conversion_factor) or 1)
		sre = ctx.row_sre.get(it.name) or {}
		wh = row_wh
		if sre:
			wh = max(sre, key=sre.get)
		else:
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
				reserved=0.0,
				misplaced=0.0,
				is_stock=it.item_code in ctx.stock_items,
			),
		)
		line.ordered += flt(it.stock_qty)
		line.need += need
		line.reserved += sre.get(wh, 0)
		line.misplaced += sum(q for w, q in sre.items() if w != wh)

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
				"reserved": flt(line.reserved, 3),
				"misplaced": flt(line.misplaced, 3),
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
	if r.custom_mode_of_payment != stages.COD:
		return False
	cfg = get_company_settings(r.company)
	if cfg:
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
		status = raw_stage if raw_stage in BOARD_STAGES else RECEIVED

	lines = _lines(r, its, ctx)
	short_count = sum(1 for line in lines if line["short"] > EPSILON)
	ce = ctx.ces.get(r.name, {"draft": [], "submitted": []})
	dns = ctx.dns.get(r.name, [])
	logs = ctx.logs.get(r.name, [])
	units = {line["uom"] for line in lines}
	stock_lines = [line for line in lines if line["is_stock"] and line["need"] > EPSILON]
	reserved_by_unit, todo_by_unit, held_by_unit = {}, {}, {}
	for line in stock_lines:
		u = line["uom"]
		reserved_by_unit[u] = reserved_by_unit.get(u, 0) + min(line["reserved"], line["need"])
		todo_by_unit[u] = todo_by_unit.get(u, 0) + max(line["need"] - line["reserved"], 0)
	for line in lines:
		if line["reserved"] + line["misplaced"] > EPSILON:
			held_by_unit[line["uom"]] = held_by_unit.get(line["uom"], 0) + line["reserved"] + line["misplaced"]
	reserved_total = sum(reserved_by_unit.values())
	to_reserve = sum(todo_by_unit.values())
	misplaced_total = sum(line["misplaced"] for line in lines)
	if not stock_lines:
		reserve_state = "n/a"
	elif to_reserve <= EPSILON:
		reserve_state = "full"
	elif reserved_total > EPSILON:
		reserve_state = "partial"
	else:
		reserve_state = "none"

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
		"reserve_state": reserve_state,
		"reserved_total": flt(reserved_total, 3),
		"to_reserve": flt(to_reserve, 3),
		"held_total": flt(sum(held_by_unit.values()), 3),
		"misplaced_total": flt(misplaced_total, 3),
		"reserved_text": _qty_label(reserved_by_unit),
		"to_reserve_text": _qty_label(todo_by_unit),
		"held_text": _qty_label(held_by_unit),
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
	if to == card["status"]:
		return ""
	if to == PREPARING and card["needs_conv"] and card["conv"] != "submitted":
		return _("Submit the Conversion Entry before preparing this order.")
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
	if r.docstatus != 1 or r.get(STAGE_FIELD) not in WRITE_CONVERSION_FLAG:
		return
	want = 1 if card["needs_conv"] else 0
	if cint(r.custom_conversion_required) != want:
		frappe.db.set_value("Sales Order", r.name, "custom_conversion_required", want, update_modified=False)


def _fresh_card(sales_order):
	rows = frappe.get_all("Sales Order", filters={"name": sales_order}, fields=FIELDS)
	cards = _build(rows, write_flags=False)
	return cards[0] if cards else None


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
	frappe.publish_realtime("mt_fulfillment_update", {"sales_order": sales_order}, after_commit=True)


@frappe.whitelist(methods=["POST"])
def move_stage(sales_order, to_stage, reason=None):
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


def _stock_reservation_on():
	if not cint(frappe.db.get_single_value("Stock Settings", "enable_stock_reservation")):
		frappe.throw(_("Stock reservation is switched off in Stock Settings."))


def _can_reserve(ptypes=("create", "submit")):
	return can_edit() and all(frappe.has_permission("Stock Reservation Entry", p) for p in ptypes)


def _require_reserve_rights(ptypes):
	if not _can_reserve(ptypes):
		frappe.throw(
			_("Your roles cannot {0} Stock Reservation Entries. Ask for the Stock User role.").format(
				_(" / ").join(ptypes)
			),
			frappe.PermissionError,
		)


@frappe.whitelist(methods=["POST"])
def reserve_stock(sales_order):
	_require(edit=True)
	_require_reserve_rights(("create", "submit"))
	_stock_reservation_on()
	so = _open_so(sales_order, for_update=True)
	if flt(so.get("per_picked")) > 0:
		frappe.throw(_("{0} has a Pick List. Reserve its stock from the Pick List.").format(so.name))
	card = _fresh_card(so.name)
	if card["needs_conv"] and card["conv"] != "submitted":
		frappe.throw(
			_("{0} is short until its Conversion Entry is submitted. Reserve after that, when the goods are in place.").format(so.name)
		)

	targets = gates.conversion_targets(so.name)
	sres = _open_sres(so.name)
	dn_warehouse = dict(
		frappe.db.sql(
			"""select so_detail, warehouse from `tabDelivery Note Item`
			where against_sales_order = %s and docstatus = 0 and ifnull(so_detail, '') != ''""",
			so.name,
		)
	)
	units = {row.name: _unit(row.stock_uom) for row in so.items}

	def held_by_unit():
		out = {}
		for r in _open_sres(so.name):
			u = units.get(r.voucher_detail_no, _unit(r.stock_uom))
			out[u] = out.get(u, 0) + flt(r.reserved_qty) - flt(r.delivered_qty)
		return out

	before = held_by_unit()
	release, details = [], []
	for row in so.items:
		if not row.item_code or not frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			continue
		cf = flt(row.conversion_factor) or 1
		need = max(flt(row.stock_qty) - flt(row.delivered_qty) * cf, 0)
		ship = dn_warehouse.get(row.name) or gates.delivery_warehouse(so, row, targets, follow_reservation=False)
		mine = [r for r in sres if r.voucher_detail_no == row.name]
		wrong = [r.name for r in mine if r.warehouse != ship]
		held_here = sum(flt(r.reserved_qty) - flt(r.delivered_qty) for r in mine if r.warehouse == ship)
		release += wrong
		open_qty = need - held_here
		if open_qty <= EPSILON:
			continue
		if not row.reserve_stock:
			row.db_set("reserve_stock", 1, update_modified=False)
		details.append({"sales_order_item": row.name, "warehouse": ship, "qty_to_reserve": open_qty / cf})

	if not details and not release:
		frappe.throw(_("Everything still to ship on {0} is already reserved.").format(so.name))
	if release:
		_require_reserve_rights(("cancel",))
		so.cancel_stock_reservation_entries(sre_list=release, notify=False)
	if details:
		so.create_stock_reservation_entries(items_details=details, notify=True)

	after = held_by_unit()
	gained = {u: after.get(u, 0) - before.get(u, 0) for u in set(after) | set(before)}
	_touch(so.name)
	return {
		"card": get_card(so.name),
		"reserved_now": flt(sum(v for v in gained.values() if v > 0), 3),
		"reserved_now_text": _qty_label({u: v for u, v in gained.items() if v > 0}),
		"moved": len(release),
	}


@frappe.whitelist(methods=["POST"])
def unreserve_stock(sales_order):
	_require(edit=True)
	_require_reserve_rights(("cancel",))
	_stock_reservation_on()
	so = _open_so(sales_order, for_update=True)
	sre_list = [r.name for r in _open_sres(so.name)]
	if not sre_list:
		frappe.throw(_("Nothing is reserved for {0}.").format(so.name))
	so.cancel_stock_reservation_entries(sre_list=sre_list, notify=True)
	_touch(so.name)
	return get_card(so.name)


@frappe.whitelist(methods=["POST"])
def conversion_action(sales_order):
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

	stage = frappe.db.get_value("Sales Order", so.name, STAGE_FIELD)
	if stage in flow.BEFORE_DN or stage not in stages.ALL_STAGES:
		so.set(STAGE_FIELD, stage)
		flow.set_stage(so, DN_READY, "board_move", "ERP", note=_("{0} created from the board").format(dn.name))
		_notify(so.name, "board_move")
	else:
		_touch(so.name)
	return {"name": dn.name}


def on_si_submit(doc, method=None):
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


def _mdy(value):
	if not value:
		return "-"
	d = getdate(value)
	return f"{d.month}/{d.day}/{d.year}"


def lab_pull_sheet(doc):
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
		"gap_rows": PULL_SHEET_GAP_ROWS,
		"total": _qty_text(total, units.pop() if len(units) == 1 else ""),
		"short": short,
		"order_type": " · ".join(
			p for p in (doc.get("custom_pickup_or_dropoff"), "COD" if doc.get("custom_mode_of_payment") == stages.COD else "Terms") if p
		),
	}
