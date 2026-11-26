"""Page reports for the Toll Processing workspace: /app/toll-stock-on-hand and /app/toll-job-yield-summary.

The pages show the two Script Reports in the Sales Operation Board look; the numbers come from the reports' own
execute() so the page and the standard report never disagree.
"""
import json

import frappe
from frappe import _
from frappe.utils import cint, flt

from cannabis_management.toll.constants import CUSTOMER_GROUP, ITEM_BH, ITEM_FF, ITEM_GROUP, ITEM_ROSIN, VIEW_ROLES, WH_GROUP

REPORT_ROLES = VIEW_ROLES | {"Stock User", "Stock Manager"}
REPORTS = {
	"Toll Stock On Hand": "cannabis_management.cannabis_management.report.toll_stock_on_hand.toll_stock_on_hand",
	"Toll Job Yield Summary": "cannabis_management.cannabis_management.report.toll_job_yield_summary.toll_job_yield_summary",
}


def _check(report):
	if report not in REPORTS:
		frappe.throw(_("Unknown report {0}.").format(report))
	if not (set(frappe.get_roles()) & REPORT_ROLES):
		frappe.throw(_("You are not allowed to open {0}.").format(report), frappe.PermissionError)


@frappe.whitelist()
def get_options(report):
	_check(report)
	g = frappe.db.get_value("Warehouse", WH_GROUP, ["lft", "rgt"], as_dict=True)
	return {
		"customers": frappe.get_all("Customer", filters={"customer_group": CUSTOMER_GROUP}, fields=["name", "customer_name"], order_by="customer_name"),
		"warehouses": frappe.get_all("Warehouse", filters={"lft": [">=", g.lft], "rgt": ["<=", g.rgt], "is_group": 0}, pluck="name", order_by="name") if g else [],
		"items": frappe.get_all("Item", filters={"item_group": ITEM_GROUP}, pluck="name", order_by="name"),
	}


@frappe.whitelist()
def get_report(report, filters=None):
	_check(report)
	f = frappe._dict(json.loads(filters) if isinstance(filters, str) else (filters or {}))
	module = frappe.get_module(REPORTS[report])
	columns, data = module.execute(f)[:2]
	data = [dict(r) for r in data]
	kpis = _stock_kpis(data) if report == "Toll Stock On Hand" else _yield_kpis(data)
	return {"columns": columns, "data": data, "kpis": kpis}


def _stock_kpis(rows):
	qty = lambda item: sum(flt(r.get("qty")) for r in rows if r.get("item_code") == item)
	days = [cint(r.get("days")) for r in rows if r.get("days") is not None]
	return [
		{"label": _("Fresh Frozen on hand"), "value": qty(ITEM_FF), "unit": "lbs", "precision": 1},
		{"label": _("Bubble Hash on hand"), "value": qty(ITEM_BH), "unit": "g", "precision": 0},
		{"label": _("Rosin on hand"), "value": qty(ITEM_ROSIN), "unit": "g", "precision": 0},
		{"label": _("Jobs holding stock"), "value": len({r.get("toll_job") for r in rows if r.get("toll_job")}), "precision": 0,
			"sub": (lambda n: _("1 client") if n == 1 else _("{0} clients").format(n))(len({r.get("customer") for r in rows if r.get("customer")}))},
		{"label": _("Oldest material"), "value": max(days) if days else 0, "unit": _("days"), "precision": 0,
			"cls": "attn" if days and max(days) > 30 else ""},
	]


def _yield_kpis(rows):
	total = rows[-1] if rows and rows[-1].get("customer") == _("Total") else {}
	jobs = total.get("jobs") if "jobs" in total else len(rows) - (1 if total else 0)
	return [
		{"label": _("FF washed"), "value": flt(total.get("ff_washed_lbs")), "unit": "lbs", "precision": 1,
			"sub": _("1 job") if jobs == 1 else _("{0} jobs").format(jobs)},
		{"label": _("Wash yield"), "value": flt(total.get("wash_yield")), "unit": "%", "precision": 2,
			"sub": _("{0} g bubble hash").format(frappe.format_value(flt(total.get("bh_grams")), {"fieldtype": "Float", "precision": 0}))},
		{"label": _("Press yield"), "value": flt(total.get("press_yield")), "unit": "%", "precision": 1,
			"sub": _("{0} g rosin").format(frappe.format_value(flt(total.get("rosin_grams")), {"fieldtype": "Float", "precision": 0}))},
		{"label": _("Returned to clients"), "value": flt(total.get("returned_grams")), "unit": "g", "precision": 0},
		{"label": _("Invoiced"), "value": flt(total.get("invoiced_amount")), "currency": 1, "cls": "good" if flt(total.get("invoiced_amount")) else ""},
		{"label": _("Revenue per lb"), "value": flt(total.get("revenue_per_lb")), "currency": 1},
	]
