"""Toll Stock On Hand: customer-owned material in the Toll warehouses by batch (one batch per Toll Job and item).
Used for physical counts and METRC reconciliation."""
import frappe
from frappe import _
from frappe.utils import date_diff, flt, getdate, nowdate

from cannabis_management.toll.constants import WH_GROUP


def execute(filters=None):
	f = frappe._dict(filters or {})
	return columns(), data(f)


def columns():
	return [
		{"label": _("Customer"), "fieldname": "customer", "fieldtype": "Link", "options": "Customer", "width": 180},
		{"label": _("Toll Job"), "fieldname": "toll_job", "fieldtype": "Link", "options": "Toll Job", "width": 120},
		{"label": _("Strain"), "fieldname": "strain", "fieldtype": "Data", "width": 150},
		{"label": _("Warehouse"), "fieldname": "warehouse", "fieldtype": "Link", "options": "Warehouse", "width": 150},
		{"label": _("Item"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 110},
		{"label": _("Batch"), "fieldname": "batch_no", "fieldtype": "Link", "options": "Batch", "width": 140},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "precision": 3, "width": 100},
		{"label": _("UOM"), "fieldname": "uom", "fieldtype": "Link", "options": "UOM", "width": 70},
		{"label": _("Physical Location"), "fieldname": "physical_location", "fieldtype": "Data", "width": 120},
		{"label": _("Received Date"), "fieldname": "received_date", "fieldtype": "Date", "width": 100},
		{"label": _("Days Since Received"), "fieldname": "days", "fieldtype": "Int", "width": 90},
		{"label": _("Status"), "fieldname": "status", "fieldtype": "Data", "width": 110},
	]


def data(f):
	g = frappe.db.get_value("Warehouse", WH_GROUP, ["lft", "rgt"], as_dict=True)
	if not g:
		return []
	whs = frappe.get_all("Warehouse", filters={"lft": [">=", g.lft], "rgt": ["<=", g.rgt], "is_group": 0}, pluck="name")
	if f.warehouse:
		whs = [w for w in whs if w == f.warehouse]
	if not whs:
		return []
	cond, vals = "", {"whs": whs, "date": f.as_on_date or nowdate()}
	if f.item_code:
		cond += " and sle.item_code = %(item)s"
		vals["item"] = f.item_code
	# batch quantities: from the Serial and Batch Bundle where the entry has one, else from the SLE's own batch_no
	rows = frappe.db.sql(f"""
		select sle.warehouse, sle.item_code, coalesce(sbe.batch_no, sle.batch_no) as batch_no,
			sum(coalesce(sbe.qty, sle.actual_qty)) as qty
		from `tabStock Ledger Entry` sle
		left join `tabSerial and Batch Entry` sbe
			on ifnull(sle.serial_and_batch_bundle, '') != '' and sbe.parent = sle.serial_and_batch_bundle
		where sle.is_cancelled = 0 and sle.warehouse in %(whs)s and sle.posting_date <= %(date)s {cond}
		group by sle.warehouse, sle.item_code, coalesce(sbe.batch_no, sle.batch_no)
		having abs(sum(coalesce(sbe.qty, sle.actual_qty))) > 0.0005""", vals, as_dict=True)
	if not rows:
		return []
	batches = {b.name: b for b in frappe.get_all("Batch", filters={"name": ["in", [r.batch_no for r in rows if r.batch_no] or [""]]},
		fields=["name", "toll_job", "toll_customer", "strain"])}
	jobs = {j.name: j for j in frappe.get_all("Toll Job", filters={"name": ["in", [b.toll_job for b in batches.values() if b.toll_job] or [""]]},
		fields=["name", "customer", "strain", "received_date", "physical_location", "status"])}
	uoms = {i.name: i.stock_uom for i in frappe.get_all("Item", filters={"name": ["in", list({r.item_code for r in rows})]}, fields=["name", "stock_uom"])}
	today = getdate(vals["date"])
	out = []
	for r in rows:
		b = batches.get(r.batch_no) or frappe._dict()
		j = jobs.get(b.toll_job) or frappe._dict()
		row = frappe._dict(customer=j.customer or b.toll_customer, toll_job=b.toll_job, strain=j.strain or b.strain, warehouse=r.warehouse,
			item_code=r.item_code, batch_no=r.batch_no, qty=flt(r.qty, 3), uom=uoms.get(r.item_code), physical_location=j.physical_location,
			received_date=j.received_date, days=date_diff(today, j.received_date) if j.received_date else None, status=j.status)
		if f.customer and row.customer != f.customer:
			continue
		if f.toll_job and row.toll_job != f.toll_job:
			continue
		out.append(row)
	out.sort(key=lambda r: (r.customer or "", r.toll_job or "", r.warehouse, r.item_code))
	return out
