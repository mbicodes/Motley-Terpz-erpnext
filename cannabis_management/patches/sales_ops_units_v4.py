# Sales Operation Board v4 (16 Nov 2026):
# 1. Each product line gets the unit the team counts it in, read from its SKUs: the stock unit of the items in its
#    item groups (LBS = lb, Gram = g), or of item groups named after it (Fresh Frozen - SHO, ...). Fresh frozen = lb.
# 2. Volume rows keep their price per lb or per gram (price + price_unit) instead of only per gram.
# 3. Stage colours: the open pipeline becomes one grape ramp from the logo, light to dark as deals and accounts move
#    on; Won is green, Lost red, Dormant amber. Only colours still at their seeded values are changed. Safe to run twice.

import frappe
from frappe.utils import flt

from cannabis_management import sales_ops

UOM_UNIT = {"LBS": "lb", "Gram": "g"}
# validated ordinal ramps (one hue, monotone lightness, light end above 2:1 on white)
DEAL_RAMP = ["#c08ffd", "#ac7be7", "#9868d2", "#8555bd", "#7342a8", "#612e94", "#4f1980"]
LEAD_RAMP = ["#b989f6", "#9666d0", "#7544aa", "#552086"]
GOOD, WARNING, CRITICAL = "#0ca30c", "#fab219", "#d03b3b"
SEEDED = {
	# stage: colour it was seeded with (v2 / v3 patches)
	"Lead": "#6B7280", "Qualified Lead": "#0EA5E9", "Active Customer": "#16A34A", "Recurring Customer": "#0D9488",
	"Dormant Customer": "#CA8A04", "Lost Customer": "#B91C1C",
	"Active Opportunity": "#2563EB", "In Discussion": "#0EA5E9", "Sampling": "#9333EA", "Testing / QC": "#EA580C",
	"Proposal / Quote Sent": "#CA8A04", "Pending Buyer Approval": "#DB2777", "Buyer Ready": "#16A34A",
	"Closed Won": "#166534", "Closed Lost": "#B91C1C",
}


def execute():
	for dt in ("sales_pipeline_product_line", "sales_pipeline_volume", "sales_pipeline_requirement", "sales_pipeline_deal", "sales_pipeline_settings"):
		frappe.reload_doc("cannabis_management", "doctype", dt)
	frappe.flags.in_patch = True
	doc = frappe.get_single("Sales Pipeline Settings")
	set_units(doc)
	recolour(doc)
	doc.flags.ignore_permissions = True
	doc.save()
	sales_ops.clear_settings_memo()
	migrate_volume_prices(sales_ops.get_settings())


def sku_unit(row):
	groups = [g.strip() for g in (row.item_groups or "").replace(",", "\n").splitlines() if g.strip()]
	if not groups:
		groups = frappe.get_all("Item Group", filters={"name": ("like", "%{0}%".format(row.product_line))}, pluck="name")
	if not groups:
		return None
	rows = frappe.db.sql(
		"""select stock_uom, count(*) n from `tabItem` where disabled = 0 and item_group in %s and stock_uom in ('LBS', 'Gram')
		group by stock_uom order by n desc limit 1""", (tuple(groups),))
	return UOM_UNIT.get(rows[0][0]) if rows else None


def set_units(doc):
	for row in doc.product_lines:
		if row.get("unit") and row.unit != "g":
			continue  # chosen by hand
		unit = sku_unit(row) or ("lb" if "fresh frozen" in (row.product_line or "").lower() else "g")
		row.unit = unit


def recolour(doc):
	deal_open = [r for r in doc.stages if r.board == "Deal" and not r.is_closed]
	lead_path = [r for r in doc.stages if r.board == "Lead" and not r.is_closed and r.stage not in ("Dormant Customer",)]
	for rows, ramp in ((deal_open, DEAL_RAMP), (lead_path, LEAD_RAMP)):
		rows = sorted(rows, key=lambda r: r.sort_order)
		for i, r in enumerate(rows):
			step = ramp[round(i * (len(ramp) - 1) / max(1, len(rows) - 1))] if len(rows) > 1 else ramp[0]
			if (r.colour or "").upper() == SEEDED.get(r.stage, "").upper():
				r.colour = step
	for r in doc.stages:
		if (r.colour or "").upper() != SEEDED.get(r.stage, "#").upper():
			continue
		if r.board == "Deal" and r.is_closed:
			r.colour = GOOD if r.is_won else CRITICAL
		elif r.board == "Lead" and r.is_closed:
			r.colour = CRITICAL
		elif r.stage == "Dormant Customer":
			r.colour = WARNING


def migrate_volume_prices(s):
	for r in frappe.get_all(sales_ops.VOLUME, fields=["name", "product_line", "price", "price_unit", "price_per_gram", "uom"]):
		pu = sales_ops.price_unit(s, r.product_line)
		upd = {}
		if not r.price_unit:
			upd["price_unit"] = pu
			if flt(r.price_per_gram) and not flt(r.price):
				upd["price"] = flt(r.price_per_gram) * sales_ops.UNIT_GRAMS[pu]
		allowed = sales_ops.line_units_allowed(s, r.product_line)
		if r.uom not in allowed:
			upd["uom"] = allowed[0]
		if upd:
			frappe.db.set_value(sales_ops.VOLUME, r.name, upd, update_modified=False)
	# totals of every account follow the rows
	for name in frappe.get_all(sales_ops.ACCOUNT, pluck="name"):
		acc = frappe.get_doc(sales_ops.ACCOUNT, name)
		before = (flt(acc.weekly_volume), flt(acc.monthly_demand), flt(acc.monthly_potential))
		acc._apply_volume(s)
		if before != (flt(acc.weekly_volume), flt(acc.monthly_demand), flt(acc.monthly_potential)) or acc.get("volume"):
			for v in acc.volume:
				frappe.db.set_value(sales_ops.VOLUME, v.name, {k: v.get(k) for k in ("uom", "price", "price_unit", "price_per_gram", "weekly_grams", "monthly_grams", "monthly_value")}, update_modified=False)
			frappe.db.set_value(sales_ops.ACCOUNT, name, {"weekly_volume": acc.weekly_volume, "monthly_demand": acc.monthly_demand,
				"monthly_potential": acc.monthly_potential}, update_modified=False)
