"""Toll Job Yield Summary: per job or per customer, FF washed, BH and rosin made, yields, returns and revenue."""
import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.toll.constants import LB_TO_G

SUMS = ("ff_received_lbs", "ff_washed_lbs", "bh_grams", "bh_pressed_grams", "rosin_grams", "returned_grams", "invoiced_amount")


def execute(filters=None):
	f = frappe._dict(filters or {})
	by_customer = f.group_by == "Customer"
	return columns(by_customer), data(f, by_customer)


def columns(by_customer):
	cols = [{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180}]
	if by_customer:
		cols.append({"label": _("Jobs"), "fieldname": "jobs", "fieldtype": "Int", "width": 60})
	else:
		cols += [
			{"label": _("Toll Job"), "fieldname": "toll_job", "fieldtype": "Link", "options": "Toll Job", "width": 120},
			{"label": _("Strain"), "fieldname": "strain", "fieldtype": "Data", "width": 140},
			{"label": _("Return Type"), "fieldname": "return_type", "fieldtype": "Data", "width": 100},
			{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
			{"label": _("Received"), "fieldname": "received_date", "fieldtype": "Date", "width": 95},
		]
	cols += [
		{"label": _("FF Received (lbs)"), "fieldname": "ff_received_lbs", "fieldtype": "Float", "precision": 2, "width": 110},
		{"label": _("FF Washed (lbs)"), "fieldname": "ff_washed_lbs", "fieldtype": "Float", "precision": 2, "width": 110},
		{"label": _("Bubble Hash (g)"), "fieldname": "bh_grams", "fieldtype": "Float", "precision": 0, "width": 110},
		{"label": _("Wash Yield %"), "fieldname": "wash_yield", "fieldtype": "Percent", "precision": 2, "width": 95},
		{"label": _("BH Pressed (g)"), "fieldname": "bh_pressed_grams", "fieldtype": "Float", "precision": 0, "width": 105},
		{"label": _("Rosin (g)"), "fieldname": "rosin_grams", "fieldtype": "Float", "precision": 0, "width": 90},
		{"label": _("Press Yield %"), "fieldname": "press_yield", "fieldtype": "Percent", "precision": 1, "width": 95},
		{"label": _("Returned (g)"), "fieldname": "returned_grams", "fieldtype": "Float", "precision": 0, "width": 100},
		{"label": _("Invoiced Amount"), "fieldname": "invoiced_amount", "fieldtype": "Currency", "width": 120},
		{"label": _("Revenue per lb"), "fieldname": "revenue_per_lb", "fieldtype": "Currency", "width": 110},
	]
	return cols


def _yields(r):
	r.wash_yield = flt(r.bh_grams) / (flt(r.ff_washed_lbs) * LB_TO_G) * 100 if flt(r.ff_washed_lbs) else 0
	r.press_yield = flt(r.rosin_grams) / flt(r.bh_pressed_grams) * 100 if flt(r.bh_pressed_grams) else 0
	r.revenue_per_lb = flt(r.invoiced_amount) / flt(r.ff_washed_lbs) if flt(r.ff_washed_lbs) else 0
	return r


def data(f, by_customer):
	filters = {}
	if f.from_date and f.to_date:
		filters["received_date"] = ["between", [f.from_date, f.to_date]]
	elif f.from_date:
		filters["received_date"] = [">=", f.from_date]
	elif f.to_date:
		filters["received_date"] = ["<=", f.to_date]
	if f.customer:
		filters["customer"] = f.customer
	if not f.include_cancelled:
		filters["status"] = ["!=", "Cancelled"]
	jobs = frappe.get_all("Toll Job", filters=filters, order_by="received_date, name", fields=[
		"name as toll_job", "customer", "strain", "return_type", "status", "received_date", "ff_received_lbs", "ff_washed_lbs",
		"bh_grams", "bh_pressed_grams", "rosin_grams", "returned_bh_grams", "returned_rosin_grams"])
	if not jobs:
		return []
	inv = {}
	for r in frappe.db.sql("""select toll_job, sum(base_net_total) as amt from `tabSales Invoice`
			where docstatus = 1 and toll_job in %(j)s group by toll_job""", {"j": [j.toll_job for j in jobs]}, as_dict=True):
		inv[r.toll_job] = flt(r.amt)
	for j in jobs:
		j.returned_grams = flt(j.returned_bh_grams) + flt(j.returned_rosin_grams)
		j.invoiced_amount = inv.get(j.toll_job, 0)
		_yields(j)
	if not by_customer:
		total = frappe._dict(customer=_("Total"), toll_job=None)
		for k in SUMS:
			total[k] = sum(flt(j[k]) for j in jobs)
		return jobs + [_yields(total)]
	groups = {}
	for j in jobs:
		g = groups.setdefault(j.customer, frappe._dict(customer=j.customer, jobs=0, **{k: 0 for k in SUMS}))
		g.jobs += 1
		for k in SUMS:
			g[k] += flt(j[k])
	out = [_yields(g) for g in sorted(groups.values(), key=lambda g: g.customer)]
	total = frappe._dict(customer=_("Total"), jobs=sum(g.jobs for g in out), **{k: sum(flt(g[k]) for g in out) for k in SUMS})
	return out + [_yields(total)]
