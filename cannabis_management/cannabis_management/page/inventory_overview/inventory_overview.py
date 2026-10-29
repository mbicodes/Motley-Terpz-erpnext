import re

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

FRESH_FROZEN = ("Fresh Frozen", "Fresh Frozen - BHO", "Fresh Frozen - SHO")

FREEZERS = ["Freezer - MTM", "Freezer 2 - MTM", "Freezer 3 - MTM", "Freezer 4 - MTM"]

NATURES = ["Natures Lab - MTM"]

ALL_GROUPS = "*"

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
	 "label": "Fresh Frozen", "reserved": False, "batch": True},

	{"key": "ff_freezers",
	 "title": "Fresh Frozen Sitting in Freezers - Freezer 1-4 warehouse",
	 "warehouses": FREEZERS, "groups": list(FRESH_FROZEN),
	 "label": "Fresh Frozen", "reserved": False, "split_by_warehouse": True,
	 "batch": True},

	{"key": "natures", "title": "Nature's Lab - MTM",
	 "warehouses": NATURES, "groups": ALL_GROUPS, "reserved": False,
	 "split_by_batch": True, "show_uom": True, "show_type": True},
]


def _require_access():
	if not set(PAGE_ROLES) & set(frappe.get_roles()):
		frappe.throw(_("You are not permitted to view the Inventory Overview."),
		             frappe.PermissionError)


def _strain(item_name, item_code, groups):
	name = (item_name or item_code or "").strip()
	if " - " not in name:
		return name

	head, _sep, tail = name.rpartition(" - ")
	candidates = set()
	for g in list(groups) + list(TIERS):
		candidates.add(g.lower())
		candidates.add(g.replace("Tier ", "T").lower())
		for word in g.split():
			if len(word) > 2:
				candidates.add(word.lower())

	return head.strip() if tail.strip().lower() in candidates else name


def _group_condition(groups):
	return "" if groups == ALL_GROUPS else "AND i.item_group IN %(groups)s"


def _batch_sort_key(label):
	m = re.search(r"(\d+)\s*$", label or "")
	return (label == NO_BATCH, re.sub(r"\d+\s*$", "", label or "").lower(), int(m.group(1)) if m else 0)


def _bin_rows(warehouses, groups):
	if not groups or not warehouses:
		return []
	return frappe.db.sql(
		"""
		SELECT b.item_code, i.item_name, i.item_group, i.stock_uom, b.warehouse,
		       b.actual_qty, {reserved} AS reserved_qty
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		WHERE b.warehouse IN %(warehouses)s
		  {group_condition}
		  AND i.disabled = 0
		  AND b.actual_qty > 0
		ORDER BY i.item_name, b.warehouse
		""".format(reserved=RESERVED_SQL, group_condition=_group_condition(groups)),
		{"warehouses": tuple(warehouses), "groups": tuple(groups)}, as_dict=True)


def _batch_split(warehouses, groups):
	if not groups or not warehouses:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT sle.item_code, sle.warehouse, sle.project, SUM(sle.actual_qty) AS qty
		FROM `tabStock Ledger Entry` sle
		JOIN `tabItem` i ON i.name = sle.item_code
		WHERE sle.warehouse IN %(warehouses)s
		  {group_condition}
		  AND sle.is_cancelled = 0
		GROUP BY sle.item_code, sle.warehouse, sle.project
		HAVING ROUND(SUM(sle.actual_qty), 6) > 0
		ORDER BY qty DESC
		""".format(group_condition=_group_condition(groups)),
		{"warehouses": tuple(warehouses), "groups": tuple(groups)}, as_dict=True)

	out = {}
	for r in rows:
		out.setdefault((r.item_code, r.warehouse), []).append((r.project or NO_BATCH, flt(r.qty)))
	return out


def _project_names(projects):
	projects = [p for p in set(projects) if p and p != NO_BATCH]
	if not projects:
		return {}
	return {name: (label or "").strip() or name for name, label in frappe.get_all(
		"Project", filters={"name": ["in", projects]},
		fields=["name", "project_name"], as_list=True)}


def _rows_for(warehouses, groups, show_batch=False):
	bins = _bin_rows(warehouses, groups)
	batches = _batch_split(warehouses, groups) if show_batch else {}
	out = []

	for b in bins:
		on_hand = flt(b.actual_qty)
		reserved = flt(b.reserved_qty)
		parts = batches.get((b.item_code, b.warehouse)) or [(NO_BATCH, on_hand)]

		total = sum(q for _p, q in parts) or on_hand
		scale = min(1.0, on_hand / total) if total else 0

		for project, qty in parts:
			share = flt(qty * scale, 3)
			if share <= 0:
				continue
			out.append({
				"strain": _strain(b.item_name, b.item_code,
				                  [b.item_group] if groups == ALL_GROUPS else groups),
				"item_code": b.item_code,
				"item_name": b.item_name,
				"item_group": b.item_group,
				"warehouse": b.warehouse,
				"uom": b.stock_uom,
				"source_batch": project,
				"qty": share,
				"reserved_qty": flt(reserved * (share / on_hand), 3) if on_hand else 0,
			})

	names = _project_names(r["source_batch"] for r in out) if show_batch else {}
	for r in out:
		r["available"] = flt(r["qty"] - r["reserved_qty"], 3)
		r["source_batch"] = names.get(r["source_batch"], r["source_batch"]) if show_batch else ""
	return out


@frappe.whitelist()
def get_overview():
	_require_access()
	blocks = []
	for cfg in BLOCKS:
		groups = cfg["groups"]
		show_batch = bool(cfg.get("batch"))
		sections = []
		if groups is None:
			for tier in TIERS:
				sections.append({"label": tier,
				                 "rows": _rows_for(cfg["warehouses"], [tier], show_batch)})
		elif cfg.get("split_by_warehouse"):
			for wh in cfg["warehouses"]:
				sections.append({"label": wh, "rows": _rows_for([wh], groups, show_batch)})
		elif cfg.get("split_by_batch"):
			by_batch = {}
			for r in _rows_for(cfg["warehouses"], groups, True):
				by_batch.setdefault(r["source_batch"], []).append(r)
			for label in sorted(by_batch, key=_batch_sort_key):
				sections.append({"label": label, "batch": False, "rows": by_batch[label]})
		else:
			sections.append({"label": cfg.get("label") or ", ".join(groups),
			                 "rows": _rows_for(cfg["warehouses"], groups, show_batch)})

		for s in sections:
			s.setdefault("batch", show_batch)
			s["total_qty"] = flt(sum(r["qty"] for r in s["rows"]), 3)
			s["total_available"] = flt(sum(r["available"] for r in s["rows"]), 3)

		blocks.append({
			"key": cfg["key"], "title": cfg["title"],
			"warehouses": cfg["warehouses"],
			"multi_warehouse": (len(cfg["warehouses"]) > 1
			                    and not cfg.get("split_by_warehouse")),
			"reserved": cfg["reserved"],
			"batch": show_batch,
			"show_uom": bool(cfg.get("show_uom")),
			"show_type": bool(cfg.get("show_type")),
			"sections": sections,
			"total_qty": flt(sum(s["total_qty"] for s in sections), 3),
		})

	return {"blocks": blocks, "as_of": nowdate()}
