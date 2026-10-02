"""Inventory Roll Forward: opening + additions - reductions = closing, month by month.

Backs the /app/inventory-roll-forward page. One company at a time, one section
per unit (Pounds, Grams, Units) or per item group, and for every month the
quantity and the stock value of each movement.

Where the numbers come from:
- Value is Stock Ledger Entry.stock_value_difference, so every section's
  closing value is exactly the company's stock value in those items.
- Quantity is Stock Ledger Entry.actual_qty, except for Stock Reconciliation:
  its ledger rows carry actual_qty = 0 on this site, so its movement is read
  from Stock Reconciliation Item.quantity_difference instead.
- Quantities stay in each item's stock UOM. Sections never mix units, which is
  why the item-group view splits a group that holds more than one UOM.
"""

import calendar

import frappe
from frappe import _
from frappe.utils import flt, getdate, nowdate

ROLES = ("System Manager", "Accounts Manager", "Accounts User", "Stock Manager", "Stock User")

# (key, label, sign). Sign is how the row reads on the page: "add" rows show
# what came in, "less" rows what went out (both as positive numbers), and
# "net" rows keep their own sign. Closing = opening + every row's raw movement.
ROWS = [
	("opening", _("Opening Balance"), ""),
	("purchases", _("Purchases"), "add"),
	("receipts", _("Yield / Receipts"), "add"),
	("production", _("Production"), "add"),
	("issued", _("Issued to Production"), "less"),
	("sales", _("Sales"), "less"),
	("adjustments", _("Loss / Adjustments"), "net"),
	("transfers", _("Transfers / Other"), "net"),
	("closing", _("Closing Balance"), ""),
]
MOVEMENTS = [key for key, _label, sign in ROWS if sign]

UNIT_LABELS = {"LBS": _("Pounds (LBS)"), "Gram": _("Grams"), "Nos": _("Units (Nos)")}
UNIT_ORDER = ["LBS", "Gram", "Nos"]

# Which movement row a ledger entry lands on.
ROW_CASE = """
	case
		when sle.voucher_type in ('Purchase Receipt', 'Purchase Invoice') then 'purchases'
		when sle.voucher_type in ('Delivery Note', 'Sales Invoice', 'POS Invoice') then 'sales'
		when sle.voucher_type = 'Stock Reconciliation' then 'adjustments'
		when sle.voucher_type = 'Stock Entry' then
			case
				when se.purpose = 'Material Receipt' then 'receipts'
				when se.purpose = 'Material Issue' then 'adjustments'
				when se.purpose in ('Manufacture', 'Repack') and sle.actual_qty > 0 then 'production'
				when se.purpose in ('Manufacture', 'Repack') then 'issued'
				else 'transfers'
			end
		else 'transfers'
	end
"""
EPSILON = 0.0005


@frappe.whitelist()
def get_filters():
	frappe.only_for(ROLES)
	first = frappe.db.sql("select min(posting_date) from `tabStock Ledger Entry` where is_cancelled = 0")[0][0]
	this_year = getdate(nowdate()).year
	start = getdate(first).year if first else this_year
	# No default company set: the one with the most stock movement.
	busiest = frappe.db.sql(
		"""select company from `tabStock Ledger Entry` where is_cancelled = 0
		   group by company order by count(*) desc limit 1"""
	)
	return {
		"company": frappe.defaults.get_user_default("Company")
		or frappe.db.get_single_value("Global Defaults", "default_company")
		or (busiest[0][0] if busiest else None),
		"years": [str(y) for y in range(this_year, start - 1, -1)],
		"year": str(this_year),
	}


@frappe.whitelist()
def get_roll_forward(company, year, group_by="Unit", item_group=None):
	frappe.only_for(ROLES)
	if not company:
		frappe.throw(_("Pick a company."))
	year = int(year)
	today = getdate(nowdate())
	last_month = 12 if year < today.year else (today.month if year == today.year else 0)

	args = {
		"company": company,
		"start": f"{year}-01-01",
		"end": f"{year}-12-31",
	}
	item_cond = ""
	if item_group:
		args["item_groups"] = tuple(frappe.db.get_descendants("Item Group", item_group) + [item_group])
		item_cond = "and i.item_group in %(item_groups)s"

	by_group = group_by == "Item Group"
	key_cols = "i.stock_uom as stock_uom, " + ("i.item_group" if by_group else "''") + " as grp"

	opening = {}
	for r in _movements(key_cols, item_cond, args, before_start=True):
		cell = opening.setdefault(_key(r), [0.0, 0.0])
		cell[0] += flt(r.qty)
		cell[1] += flt(r.val)

	moves = {}
	groups_seen = {}
	for r in _movements(key_cols, item_cond, args, before_start=False):
		key = _key(r)
		cell = moves.setdefault(key, {}).setdefault((int(r.m), r.r), [0.0, 0.0])
		cell[0] += flt(r.qty)
		cell[1] += flt(r.val)

	for r in frappe.db.sql(
		f"""
		select i.stock_uom as uom, i.item_group as item_group
		from `tabStock Ledger Entry` sle join `tabItem` i on i.name = sle.item_code
		where sle.is_cancelled = 0 and sle.company = %(company)s and sle.posting_date <= %(end)s {item_cond}
		group by i.stock_uom, i.item_group
		""",
		args,
		as_dict=True,
	):
		key = (r.uom, r.item_group if by_group else "")
		groups_seen.setdefault(key, set()).add(r.item_group)

	sections = []
	for key in sorted(set(opening) | set(moves), key=_sort_key):
		section = _section(key, opening.get(key, [0.0, 0.0]), moves.get(key, {}), last_month)
		if section:
			section["item_groups"] = sorted(groups_seen.get(key, []))
			sections.append(section)

	return {
		"company": company,
		"currency": frappe.get_cached_value("Company", company, "default_currency"),
		"year": year,
		"months": [{"month": m, "label": calendar.month_abbr[m]} for m in range(1, last_month + 1)],
		"rows": [{"key": k, "label": label, "sign": sign} for k, label, sign in ROWS],
		"sections": sections,
	}


def _movements(key_cols, item_cond, args, before_start):
	"""Quantity and value per section (and per month and row, inside the year)."""
	if before_start:
		date_cond = "< %(start)s"
		sle_group, sr_group = "", ""
		sle_cols, sr_cols = "0 as m, '' as r", "0 as m, '' as r"
	else:
		date_cond = "between %(start)s and %(end)s"
		sle_cols = f"month(sle.posting_date) as m, {ROW_CASE} as r"
		sr_cols = "month(sr.posting_date) as m, 'adjustments' as r"
		sle_group, sr_group = ", m, r", ", m, r"

	rows = frappe.db.sql(
		f"""
		select {key_cols}, {sle_cols},
			sum(case when sle.voucher_type = 'Stock Reconciliation' then 0 else sle.actual_qty end) as qty,
			sum(sle.stock_value_difference) as val
		from `tabStock Ledger Entry` sle
		join `tabItem` i on i.name = sle.item_code
		left join `tabStock Entry` se on sle.voucher_type = 'Stock Entry' and se.name = sle.voucher_no
		where sle.is_cancelled = 0 and sle.company = %(company)s and sle.posting_date {date_cond} {item_cond}
		group by 1, 2{sle_group}
		""",
		args,
		as_dict=True,
	)
	rows += frappe.db.sql(
		f"""
		select {key_cols}, {sr_cols},
			sum(sri.quantity_difference) as qty, 0 as val
		from `tabStock Reconciliation Item` sri
		join `tabStock Reconciliation` sr on sr.name = sri.parent
		join `tabItem` i on i.name = sri.item_code
		where sr.docstatus = 1 and sr.company = %(company)s and sr.posting_date {date_cond} {item_cond}
		group by 1, 2{sr_group}
		""",
		args,
		as_dict=True,
	)
	return rows


def _key(r):
	return (r.stock_uom, r.grp or "")


def _sort_key(key):
	uom, group = key
	rank = UNIT_ORDER.index(uom) if uom in UNIT_ORDER else len(UNIT_ORDER)
	return (rank, uom or "", group)


def _section(key, opening, moves, last_month):
	"""One block of the page: a row per movement, a qty/value pair per month and for the year."""
	uom, group = key
	unit = UNIT_LABELS.get(uom, uom or _("No UOM"))
	title = f"{group} · {unit}" if group else unit

	balance = list(opening)
	months = []
	year_total = {k: [0.0, 0.0] for k in MOVEMENTS}
	for m in range(1, last_month + 1):
		cells = {"opening": list(balance)}
		for k in MOVEMENTS:
			qty, val = moves.get((m, k), [0.0, 0.0])
			cells[k] = [qty, val]
			year_total[k][0] += qty
			year_total[k][1] += val
			balance[0] += qty
			balance[1] += val
		cells["closing"] = list(balance)
		months.append(cells)

	year_cells = {"opening": list(opening), "closing": list(balance), **year_total}
	if all(abs(v) < EPSILON for cell in year_cells.values() for v in cell):
		return None

	def shown(k, cell):
		sign = dict((key, s) for key, _l, s in ROWS)[k]
		factor = -1 if sign == "less" else 1
		return [_round(cell[0] * factor), _round(cell[1] * factor)]

	return {
		"uom": uom,
		"title": title,
		"months": [{k: shown(k, c) for k, c in cells.items()} for cells in months],
		"year": {k: shown(k, c) for k, c in year_cells.items()},
		"active_rows": [k for k in MOVEMENTS if any(abs(v) >= EPSILON for v in year_total[k])],
	}


def _round(v):
	v = round(flt(v), 2)
	return 0.0 if abs(v) < 0.005 else v
