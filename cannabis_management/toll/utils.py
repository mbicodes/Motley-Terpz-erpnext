"""Toll Job quantities, activity and status, recalculated from the submitted stock documents.

`update_toll_job_status(toll_job)` is the single place that sets them. It runs after every submit or cancel of a
Stock Entry / Delivery Note / Sales Invoice linked to a Toll Job, and after the board changes the queued flag.
The activity table is rebuilt from the documents each time, so it can never drift from the ledger.
"""
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, flt, get_datetime, getdate

from cannabis_management.toll.constants import (
	ITEM_BH,
	ITEM_FF,
	ITEM_ROSIN,
	LB_TO_G,
	STEP_RANK,
	WH_INBOUND,
	WH_OUTPUT,
	WH_WIP,
)

QTY_FIELDS = (
	"ff_received_lbs", "ff_washed_lbs", "ff_balance_lbs", "bh_grams", "wash_yield", "bh_pressed_grams", "rosin_grams",
	"press_yield", "bh_wip_grams", "bh_output_grams", "rosin_output_grams", "returned_bh_grams", "returned_rosin_grams",
)
EPS = 1e-6


def se_step(purpose, rows):
	"""Board step of a toll Stock Entry from its rows (dicts with item_code, s_warehouse, t_warehouse)."""
	ins = {r["item_code"] for r in rows if r.get("s_warehouse") and not r.get("t_warehouse")}
	if purpose == "Material Receipt":
		return "Receive"
	if purpose == "Material Transfer":
		return "Move to Output"
	if ITEM_FF in ins:
		return "Wash"
	if ITEM_BH in ins:
		return "Press"
	return purpose or "Stock Entry"


def stock_docs(toll_job):
	"""Submitted toll Stock Entries and Delivery Notes of a job, oldest first, with their rows."""
	se_rows = frappe.db.sql(
		"""select se.name, se.purpose, se.posting_date, se.posting_time, se.creation, se.remarks,
			se.washer, se.wash_notes, se.press_notes,
			d.item_code, d.transfer_qty as qty, d.s_warehouse, d.t_warehouse
		from `tabStock Entry` se join `tabStock Entry Detail` d on d.parent = se.name
		where se.toll_job = %s and se.docstatus = 1 order by se.posting_date, se.posting_time, se.creation, d.idx""",
		toll_job, as_dict=True)
	dn_rows = frappe.db.sql(
		"""select dn.name, dn.posting_date, dn.posting_time, dn.creation, dn.outbound_manifest, dn.outbound_tags,
			dn.driver_name, i.item_code, i.stock_qty as qty, i.warehouse
		from `tabDelivery Note` dn join `tabDelivery Note Item` i on i.parent = dn.name
		where dn.toll_job = %s and dn.docstatus = 1 order by dn.posting_date, dn.posting_time, dn.creation, i.idx""",
		toll_job, as_dict=True)

	docs = {}
	for r in se_rows:
		d = docs.setdefault(("Stock Entry", r.name), frappe._dict(doctype="Stock Entry", name=r.name, purpose=r.purpose,
			posting_date=r.posting_date, posting_time=r.posting_time, creation=r.creation, remarks=r.remarks,
			washer=r.washer, wash_notes=r.wash_notes, press_notes=r.press_notes, rows=[]))
		d.rows.append(r)
	for r in dn_rows:
		d = docs.setdefault(("Delivery Note", r.name), frappe._dict(doctype="Delivery Note", name=r.name, purpose="Return",
			posting_date=r.posting_date, posting_time=r.posting_time, creation=r.creation, manifest=r.outbound_manifest,
			tags=r.outbound_tags, driver=r.driver_name, rows=[]))
		d.rows.append(r)
	for d in docs.values():
		d.step = "Return" if d.doctype == "Delivery Note" else se_step(d.purpose, d.rows)
	return sorted(docs.values(), key=lambda d: (getdate(d.posting_date), str(d.posting_time), get_datetime(d.creation)))


def compute(toll_job):
	"""Quantities and activity rows of a job from its submitted documents."""
	docs = stock_docs(toll_job)
	net = defaultdict(float)  # (item, warehouse) -> balance moved by this job's documents
	q = defaultdict(float)
	activity = []
	for d in docs:
		inp = defaultdict(float)
		out = defaultdict(float)
		for r in d.rows:
			qty = flt(r.qty)
			if d.doctype == "Delivery Note":
				net[(r.item_code, r.warehouse)] -= qty
				q["returned_bh_grams" if r.item_code == ITEM_BH else "returned_rosin_grams"] += qty
				out[r.item_code] += qty
				continue
			if r.s_warehouse:
				net[(r.item_code, r.s_warehouse)] -= qty
			if r.t_warehouse:
				net[(r.item_code, r.t_warehouse)] += qty
			if r.s_warehouse and not r.t_warehouse:
				inp[r.item_code] += qty
			elif r.t_warehouse and not r.s_warehouse:
				out[r.item_code] += qty
			else:  # transfer
				inp[r.item_code] += qty
				out[r.item_code] += qty

		if d.step == "Receive":
			q["ff_received_lbs"] += out[ITEM_FF]
		elif d.step == "Wash":
			q["ff_washed_lbs"] += inp[ITEM_FF]
			q["bh_grams"] += out[ITEM_BH]
		elif d.step == "Press":
			q["bh_pressed_grams"] += inp[ITEM_BH]
			q["rosin_grams"] += out[ITEM_ROSIN]
		activity.append(activity_row(d, inp, out))

	q["ff_balance_lbs"] = net[(ITEM_FF, WH_INBOUND)]
	q["bh_wip_grams"] = net[(ITEM_BH, WH_WIP)]
	q["bh_output_grams"] = net[(ITEM_BH, WH_OUTPUT)]
	q["rosin_output_grams"] = net[(ITEM_ROSIN, WH_OUTPUT)]
	q["wash_yield"] = q["bh_grams"] / (q["ff_washed_lbs"] * LB_TO_G) * 100 if q["ff_washed_lbs"] > EPS else 0
	q["press_yield"] = q["rosin_grams"] / q["bh_pressed_grams"] * 100 if q["bh_pressed_grams"] > EPS else 0
	for k in QTY_FIELDS:
		q[k] = flt(q[k], 4 if k.endswith("yield") else 3)
		if abs(q[k]) < 0.0005:
			q[k] = 0
	return q, activity, docs


def _qty(v, uom):
	return "{0} {1}".format(frappe.format_value(flt(v, 3), {"fieldtype": "Float", "precision": 3 if uom == "lbs" else 0}), uom)


def activity_row(d, inp, out):
	row = frappe._dict(step=d.step, posting_date=d.posting_date, reference_doctype=d.doctype, reference_name=d.name)
	if d.step == "Receive":
		row.update(output_qty=out[ITEM_FF], output_uom="lbs", remarks=d.remarks)
	elif d.step == "Wash":
		row.update(input_qty=inp[ITEM_FF], input_uom="lbs", output_qty=out[ITEM_BH], output_uom="g Bubble Hash",
			remarks=" · ".join(x for x in (d.washer and _("Washer: {0}").format(d.washer), d.wash_notes) if x))
	elif d.step == "Press":
		row.update(input_qty=inp[ITEM_BH], input_uom="g Bubble Hash", output_qty=out[ITEM_ROSIN], output_uom="g Rosin",
			remarks=d.press_notes)
	elif d.step == "Move to Output":
		row.update(input_qty=inp[ITEM_BH], input_uom="g Bubble Hash", output_qty=out[ITEM_BH], output_uom="g Bubble Hash",
			remarks=_("Toll WIP to Toll Output"))
	elif d.step == "Return":
		parts = []
		if out[ITEM_BH]:
			parts.append(_("{0} g Bubble Hash").format(frappe.format_value(out[ITEM_BH], {"fieldtype": "Float", "precision": 0})))
		if out[ITEM_ROSIN]:
			parts.append(_("{0} g Rosin").format(frappe.format_value(out[ITEM_ROSIN], {"fieldtype": "Float", "precision": 0})))
		row.update(output_qty=out[ITEM_BH] + out[ITEM_ROSIN], output_uom="g", metrc_tags=d.tags,
			remarks=" · ".join(x for x in (", ".join(parts), d.manifest and _("Manifest {0}").format(d.manifest),
				d.driver and _("Driver {0}").format(d.driver)) if x))
	return row


def invoice_state(sales_invoice):
	if not sales_invoice:
		return None
	return frappe.db.get_value("Sales Invoice", sales_invoice, "docstatus")


def derive_status(job, si_docstatus=None):
	"""Status from the stored quantities (spec 'Status logic'). `job` is a Toll Job doc or dict."""
	g = lambda k: flt(job.get(k))
	if job.get("status") == "Cancelled":
		return "Cancelled"
	if job.get("sales_invoice") and cint(si_docstatus) == 1:
		return "Invoiced"
	if g("ff_balance_lbs") > EPS or g("ff_received_lbs") <= EPS:
		return "Queued for Wash" if cint(job.get("queued_for_wash")) else "Received"
	if g("bh_wip_grams") > EPS:
		return "Pressed" if g("bh_pressed_grams") > EPS else "Washed"
	if g("bh_output_grams") + g("rosin_output_grams") > EPS:
		return "Ready to Return"
	if g("returned_bh_grams") + g("returned_rosin_grams") > EPS:
		return "Returned"
	return "Ready to Return"


def billable_qty(job):
	basis = job.get("rate_basis")
	if basis == "Per Gram Output":
		return flt(job.get("returned_bh_grams")) + flt(job.get("returned_rosin_grams"))
	if basis == "Flat per Job":
		return 1
	return flt(job.get("ff_washed_lbs"))


def update_toll_job_status(toll_job):
	"""Recalculate every quantity field, the activity table, billing and the status of one Toll Job, and save it."""
	if not toll_job or not frappe.db.exists("Toll Job", toll_job):
		return None
	job = frappe.get_doc("Toll Job", toll_job)
	q, activity, _docs = compute(toll_job)
	job.update(q)
	job.set("toll_job_activity", [])
	for a in activity:
		job.append("toll_job_activity", a)
	if job.sales_invoice and not frappe.db.exists("Sales Invoice", job.sales_invoice):
		job.sales_invoice = None
	job.status = derive_status(job, invoice_state(job.sales_invoice))
	job.flags.ignore_permissions = True
	job.flags.from_status_update = True
	job.save()
	return job


def step_of(doc):
	"""Step of a linked document (for rule 9)."""
	if doc.doctype == "Delivery Note":
		return "Return"
	if doc.doctype == "Sales Invoice":
		return "Invoice"
	return se_step(doc.purpose, [r.as_dict() for r in doc.items])


def later_step(doc):
	"""Name of a submitted document of the same Toll Job that is a later step than `doc`, if any."""
	rank = STEP_RANK.get(step_of(doc), 0)
	for d in stock_docs(doc.toll_job):
		if d.name != doc.name and STEP_RANK.get(d.step, 0) > rank:
			return d.name
	if doc.doctype != "Sales Invoice" and rank < STEP_RANK["Invoice"]:
		si = frappe.db.get_value("Sales Invoice", {"toll_job": doc.toll_job, "docstatus": 1}, "name")
		if si:
			return si
	return None


# ---------------------------------------------------------------- cancel / delete

def batch_state(batch):
	"""(live ledger entries, qty) of a batch: entries of submitted, not cancelled stock documents."""
	a = frappe.db.sql("""select count(*), coalesce(sum(sbe.qty), 0) from `tabSerial and Batch Entry` sbe
		join `tabSerial and Batch Bundle` sabb on sabb.name = sbe.parent
		where sbe.batch_no = %s and sabb.docstatus = 1 and ifnull(sabb.is_cancelled, 0) = 0""", batch)[0]
	b = frappe.db.sql("""select count(*), coalesce(sum(actual_qty), 0) from `tabStock Ledger Entry`
		where batch_no = %s and is_cancelled = 0 and ifnull(serial_and_batch_bundle, '') = ''""", batch)[0]
	return int(a[0] or 0) + int(b[0] or 0), flt(a[1]) + flt(b[1])


def job_batches(toll_job):
	return frappe.get_all("Batch", filters={"toll_job": toll_job}, pluck="name", order_by="name")


def cancel_stock_docs(toll_job):
	"""Cancel every submitted Delivery Note / Stock Entry of a job, last step first (so rule 9 holds)."""
	docs = sorted(stock_docs(toll_job), reverse=True,
		key=lambda d: (STEP_RANK.get(d.step, 0), getdate(d.posting_date), str(d.posting_time), get_datetime(d.creation)))
	for d in docs:
		doc = frappe.get_doc(d.doctype, d.name)
		doc.flags.ignore_permissions = True
		doc.cancel()
	return [d.name for d in docs]


def cleanup_batches(toll_job):
	"""Batches of a cancelled job: an empty batch (no live ledger entry) is deleted, any other one is disabled."""
	deleted, disabled = [], []
	for b in job_batches(toll_job):
		live, qty = batch_state(b)
		if live:
			frappe.db.set_value("Batch", b, "disabled", 1)
			disabled.append((b, qty))
			continue
		for f in ("batch", "bh_batch", "rosin_batch"):
			if frappe.db.get_value("Toll Job", toll_job, f) == b:
				frappe.db.set_value("Toll Job", toll_job, f, None, update_modified=False)
		# force: only cancelled (reversed) stock rows still name the batch
		frappe.delete_doc("Batch", b, ignore_permissions=True, force=True)
		deleted.append(b)
	return deleted, disabled
