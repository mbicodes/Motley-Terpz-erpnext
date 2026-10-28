# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt
"""Inventory Overview — the Physical Inventory Weekly sheet, served live.

One block per section of the sheet, each a warehouse crossed with a set of item
groups. The whole layout is the BLOCKS table below: a block's warehouse, its
groups and whether it shows Reserved are one line each, so a section can be
re-pointed without touching the query underneath.

Two columns in the sheet have no field of their own and are derived:

* Strain Name is the item name. In this data the strain is the name --
  "Moonbow - T1", "ALCATRAZ OG - T1" -- with the tier as a suffix, which is
  stripped for display so the same strain reads the same in every block.
* Source Batch is the Project. Project is this site's batch inventory
  dimension: it sits on Stock Ledger Entry, not on Bin, so a batch's quantity
  is summed from the ledger and capped at what the Bin actually holds. Stock
  posted without a project shows under "(no batch)" rather than vanishing.

Reserved follows ERPNext's own projected_qty on Bin -- Sales Order, Work Order,
subcontract and production-plan commitments -- so it agrees with the inventory
dashboard rather than offering a second opinion.
"""

import frappe
from frappe import _
from frappe.utils import flt, nowdate

PAGE_ROLES = ("System Manager", "Stock Manager", "Stock User",
              "Manufacturing Manager", "Accounts Manager", "Ops Manager")

TIERS = ("Tier 1", "Tier 2", "Tier 3")
NO_BATCH = "(no batch)"

RESERVED_SQL = """(
    COALESCE(b.reserved_qty, 0)
  + COALESCE(b.reserved_qty_for_production, 0)
  + COALESCE(b.reserved_qty_for_sub_contract, 0)
  + COALESCE(b.reserved_qty_for_production_plan, 0)
)"""

# Fresh Frozen is three groups on this site; the sheet treats them as one.
FRESH_FROZEN = ("Fresh Frozen", "Fresh Frozen - BHO", "Fresh Frozen - SHO")

# Freezers 1-4 as the sheet names them. "Freezer 3 - MTM" holds stock in Bin
# but has no Warehouse record of its own, so it is matched by name here rather
# than looked up -- dropping it would hide real inventory.
FREEZERS = ["Freezer - MTM", "Freezer 2 - MTM", "Freezer 3 - MTM", "Freezer 4 - MTM"]

# The sheet's sections, top to bottom. `groups` None means "one sub-table per
# tier"; a list means a single sub-table under `label`.
BLOCKS = [
	{"key": "ready_to_sell", "title": "Ready to Sell Qty - Main Storage Warehouse",
	 "warehouses": ["Main Storage - MTM"], "groups": None, "reserved": True},

	{"key": "fresh_pressed",
	 "title": "Fresh Pressed Inventory (Unreleased Batches) Finished Good - Warehouse",
	 "warehouses": ["Finished Goods - MTM"], "groups": None, "reserved": False},

	{"key": "untiered_fresh_rosin",
	 "title": "Untiered Fresh Pressed Rosin Inventory - Finished Good Warehouse",
	 "warehouses": ["Finished Goods - MTM"], "groups": ["Raw Rosin"],
	 "label": "Raw Rosin", "reserved": False},

	{"key": "hash_pressing", "title": "Bubble Hash Pressing to Rosin - WIP Warehouse",
	 "warehouses": ["Work In Progress - MTM"], "groups": ["Bubble Hash"],
	 "label": "Bubble Hash", "reserved": False},

	{"key": "hash_waiting",
	 "title": "Bubble Hash Waiting to be pressed - Finished Good Warehouse",
	 "warehouses": ["Finished Goods - MTM"], "groups": ["Bubble Hash"],
	 "label": "Bubble Hash", "reserved": False},

	{"key": "ff_washing", "title": "Fresh Frozen Washing - WIP warehouse",
	 "warehouses": ["Work In Progress - MTM"], "groups": list(FRESH_FROZEN),
	 "label": "Fresh Frozen", "reserved": False},

	# Four freezers, four columns. split_by_warehouse gives each its own
	# sub-table, so the column heading names the freezer and the rows inside
	# need no warehouse of their own -- the same shape the tier blocks use.
	{"key": "ff_freezers",
	 "title": "Fresh Frozen Sitting in Freezers - Freezer 1-4 warehouse",
	 "warehouses": FREEZERS, "groups": list(FRESH_FROZEN),
	 "label": "Fresh Frozen", "reserved": False, "split_by_warehouse": True},
]


def _require_access():
	if not set(PAGE_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("You are not permitted to view the Inventory Overview."),
		             frappe.PermissionError)


def _strain(item_name, item_code, groups):
	"""The strain, without the group or tier suffix the item name carries.

	Names arrive as "Moonbow - T1", "Triangle Punch - Rosin",
	"Cherry Gusher - bubble hash" -- the same strain written three ways. The
	suffix is matched case-insensitively against the block's own groups, each
	word of them, and the tier short forms, so one strain reads identically
	wherever it appears.
	"""
	name = (item_name or item_code or "").strip()
	if " - " not in name:
		return name

	head, _sep, tail = name.rpartition(" - ")
	candidates = set()
	for g in list(groups) + list(TIERS):
		candidates.add(g.lower())
		candidates.add(g.replace("Tier ", "T").lower())
		# "Raw Rosin" should also strip a bare "Rosin"
		for word in g.split():
			if len(word) > 2:
				candidates.add(word.lower())

	return head.strip() if tail.strip().lower() in candidates else name


def _bin_rows(warehouses, groups):
	"""Stock on hand across the block's warehouses and item groups."""
	if not groups or not warehouses:
		return []
	return frappe.db.sql(
		"""
		SELECT b.item_code, i.item_name, i.item_group, i.stock_uom, b.warehouse,
		       b.actual_qty, {reserved} AS reserved_qty
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		WHERE b.warehouse IN %(warehouses)s
		  AND i.item_group IN %(groups)s
		  AND i.disabled = 0
		  AND b.actual_qty > 0
		ORDER BY i.item_name, b.warehouse
		""".format(reserved=RESERVED_SQL),
		{"warehouses": tuple(warehouses), "groups": tuple(groups)}, as_dict=True)


def _batch_split(warehouses, groups):
	"""{item_code: [(project, qty), ...]} -- the sheet's Source Batch column.

	Read from the ledger because Project is a dimension there, not a Bin field.
	Capped per item at the Bin quantity, for the same reason the inventory
	dashboard caps it: issues have been posted against projects their receipts
	lack, so a raw ledger sum can exceed or outlive the stock it names.
	"""
	if not groups or not warehouses:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT sle.item_code, sle.warehouse, sle.project, SUM(sle.actual_qty) AS qty
		FROM `tabStock Ledger Entry` sle
		JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.warehouse IN %(warehouses)s
		  AND i.item_group IN %(groups)s
		  AND sle.is_cancelled = 0
		GROUP BY sle.item_code, sle.warehouse, sle.project
		HAVING ROUND(SUM(sle.actual_qty), 6) > 0
		ORDER BY qty DESC
		""",
		{"warehouses": tuple(warehouses), "groups": tuple(groups)}, as_dict=True)

	out = {}
	for r in rows:
		out.setdefault((r.item_code, r.warehouse), []).append((r.project or NO_BATCH, flt(r.qty)))
	return out


def _rows_for(warehouses, groups):
	"""One display row per item, warehouse and batch."""
	bins = _bin_rows(warehouses, groups)
	batches = _batch_split(warehouses, groups)
	out = []

	for b in bins:
		on_hand = flt(b.actual_qty)
		reserved = flt(b.reserved_qty)
		parts = batches.get((b.item_code, b.warehouse)) or [(NO_BATCH, on_hand)]

		# Never let the ledger claim more than the bin holds.
		total = sum(q for _p, q in parts) or on_hand
		scale = min(1.0, on_hand / total) if total else 0

		for project, qty in parts:
			share = flt(qty * scale, 3)
			if share <= 0:
				continue
			out.append({
				"strain": _strain(b.item_name, b.item_code, groups),
				"item_code": b.item_code,
				"item_name": b.item_name,
				"item_group": b.item_group,
				"warehouse": b.warehouse,
				"uom": b.stock_uom,
				"source_batch": project,
				"qty": share,
				# Reserved is a bin-level figure; it is apportioned across the
				# batches of that item in proportion to what each holds.
				"reserved_qty": flt(reserved * (share / on_hand), 3) if on_hand else 0,
			})

	for r in out:
		r["available"] = flt(r["qty"] - r["reserved_qty"], 3)
	return out


@frappe.whitelist()
def get_overview():
	_require_access()
	blocks = []
	for cfg in BLOCKS:
		groups = cfg["groups"]
		sections = []
		if groups is None:
			for tier in TIERS:
				sections.append({"label": tier,
				                 "rows": _rows_for(cfg["warehouses"], [tier])})
		elif cfg.get("split_by_warehouse"):
			# A column per warehouse, listed even when empty: an empty freezer
			# is information, and a column that vanishes moves the others.
			for wh in cfg["warehouses"]:
				sections.append({"label": wh, "rows": _rows_for([wh], groups)})
		else:
			sections.append({"label": cfg.get("label") or ", ".join(groups),
			                 "rows": _rows_for(cfg["warehouses"], groups)})

		for s in sections:
			s["total_qty"] = flt(sum(r["qty"] for r in s["rows"]), 3)
			s["total_available"] = flt(sum(r["available"] for r in s["rows"]), 3)

		blocks.append({
			"key": cfg["key"], "title": cfg["title"],
			"warehouses": cfg["warehouses"],
			# A per-row warehouse column is only needed where a block spans
			# several warehouses without splitting them into columns.
			"multi_warehouse": (len(cfg["warehouses"]) > 1
			                    and not cfg.get("split_by_warehouse")),
			"reserved": cfg["reserved"],
			"sections": sections,
			"total_qty": flt(sum(s["total_qty"] for s in sections), 3),
		})

	return {"blocks": blocks, "as_of": nowdate()}
