"""Whitelisted API of the Toll Processing Board (/app/toll-processing-board).

Every method runs in the request's single DB transaction: an error anywhere rolls the whole call back, so a
Receive with three rows creates all three Toll Jobs or none. Board users never open the stock forms; the methods
check the user's roles and then create the documents with ignore_permissions.
"""
import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate, nowtime

from cannabis_management.toll.constants import (
	CANCEL_ROLES,
	COMPANY,
	CUSTOMER_GROUP,
	INCOME_ACCOUNT,
	INVOICE_ROLES,
	ITEM_BH,
	ITEM_FF,
	ITEM_ROSIN,
	ITEM_SVC,
	LB_TO_G,
	LOCATIONS,
	PRODUCE_ROLES,
	RATE_BASES,
	RETURN_EXPENSE_ACCOUNT,
	RETURN_TYPES,
	UOM_FF,
	UOM_G,
	VIEW_ROLES,
	WH_INBOUND,
	WH_OUTPUT,
	WH_WIP,
)
from cannabis_management.toll.utils import EPS, billable_qty, cancel_stock_docs, cleanup_batches, update_toll_job_status

JOB_FIELDS = [
	"name", "status", "customer", "customer_name", "strain", "return_type", "priority", "received_date",
	"promised_return_date", "physical_location", "queued_for_wash", "batch", "inbound_manifest",
	"ff_received_lbs", "ff_washed_lbs", "ff_balance_lbs", "bh_grams", "wash_yield", "bh_pressed_grams", "rosin_grams",
	"press_yield", "bh_wip_grams", "bh_output_grams", "rosin_output_grams", "returned_bh_grams", "returned_rosin_grams",
	"rate_basis", "rate", "billable_qty", "amount", "sales_invoice", "modified",
]


# ---------------------------------------------------------------- helpers

def _roles():
	return set(frappe.get_roles())


def _require(roles, action):
	if not (_roles() & roles):
		frappe.throw(_("You are not allowed to {0}.").format(action), frappe.PermissionError)


def _parse(v):
	if isinstance(v, str):
		try:
			return json.loads(v)
		except ValueError:
			return v
	return v


def _job(name, lock=True):
	if not name or not frappe.db.exists("Toll Job", name):
		frappe.throw(_("Toll Job {0} does not exist.").format(name or ""))
	if lock:  # one action at a time per job: a second click waits here and then sees the new balance
		frappe.db.sql("select name from `tabToll Job` where name = %s for update", name)
	job = frappe.get_doc("Toll Job", name)
	if job.status == "Cancelled":
		frappe.throw(_("Toll Job {0} is cancelled.").format(name))
	return job


def _date(value, label, not_before=None, not_before_label=None):
	d = getdate(value or nowdate())
	if d > getdate(nowdate()):
		frappe.throw(_("{0} cannot be in the future.").format(label))
	if not_before and d < getdate(not_before):
		frappe.throw(_("{0} cannot be before the {1} ({2}).").format(
			label, not_before_label, frappe.format_value(getdate(not_before), {"fieldtype": "Date"})))
	return d


def _posting(doc, d):
	"""Today posts at the current time; a back-dated step posts at the end of that day, so it lands after the
	earlier steps of the same day."""
	doc.set_posting_time = 1
	doc.posting_date = d
	doc.posting_time = nowtime() if getdate(d) == getdate(nowdate()) else "23:59:59"


def _ensure_batch(job, item_code, suffix=""):
	"""One batch per job and item (ERPNext ties a batch to one item): TJ-2026-0001, TJ-2026-0001-BH, TJ-2026-0001-RO."""
	field = {ITEM_FF: "batch", ITEM_BH: "bh_batch", ITEM_ROSIN: "rosin_batch"}[item_code]
	if job.get(field):
		return job.get(field)
	batch_id = job.name + suffix
	if not frappe.db.exists("Batch", batch_id):
		b = frappe.get_doc({
			"doctype": "Batch", "batch_id": batch_id, "item": item_code, "manufacturing_date": job.received_date,
			"toll_job": job.name, "toll_customer": job.customer, "strain": job.strain,
			"reference_doctype": "Toll Job", "reference_name": job.name,
		})
		b.flags.ignore_permissions = True
		b.insert()
	job.db_set(field, batch_id, update_modified=False)
	return batch_id


def _se_row(item_code, qty, uom, batch, s_wh=None, t_wh=None, finished=False):
	return {
		"item_code": item_code, "qty": flt(qty, 3), "transfer_qty": flt(qty, 3), "uom": uom, "stock_uom": uom,
		"conversion_factor": 1, "s_warehouse": s_wh, "t_warehouse": t_wh, "batch_no": batch,
		"use_serial_batch_fields": 1, "basic_rate": 0, "valuation_rate": 0, "allow_zero_valuation_rate": 1,
		"set_basic_rate_manually": 1 if t_wh and not s_wh else 0, "is_finished_item": 1 if finished else 0,
	}


def _submit_se(job, purpose, d, rows, remarks, **fields):
	se = frappe.new_doc("Stock Entry")
	se.stock_entry_type = purpose
	se.purpose = purpose
	se.company = job.company or COMPANY
	_posting(se, d)
	se.toll_job = job.name
	se.remarks = remarks
	se.update(fields)
	for r in rows:
		se.append("items", r)
	se.flags.ignore_permissions = True
	se.insert()
	se.submit()
	return se


def _last_posting(toll_job, purpose=None):
	"""Posting date of the job's latest submitted stock entry (of one purpose)."""
	r = frappe.db.sql("""select max(posting_date) from `tabStock Entry` where toll_job = %s and docstatus = 1
		and (%s is null or purpose = %s)""", (toll_job, purpose, purpose))
	return r[0][0] if r and r[0][0] else None


def _fmt(n, d=0):
	return frappe.format_value(flt(n, d), {"fieldtype": "Float", "precision": d})


def _result(job_name, message):
	return {"message": message, "job": job_card(job_name)}


# ---------------------------------------------------------------- read

@frappe.whitelist()
def get_context():
	_require(VIEW_ROLES, _("open the Toll Processing Board"))
	r = _roles()
	washers = frappe.get_all("Workstation", filters={"name": ["like", "%wash%"]}, pluck="name", order_by="name")
	return {
		"customers": frappe.get_all("Customer", filters={"customer_group": CUSTOMER_GROUP, "disabled": 0},
			fields=["name", "customer_name"], order_by="customer_name"),
		"washers": washers,
		"locations": list(LOCATIONS),
		"rate_bases": list(RATE_BASES),
		"return_types": list(RETURN_TYPES),
		"customer_group": CUSTOMER_GROUP,
		"lb_to_g": LB_TO_G,
		"today": nowdate(),
		"can": {"produce": bool(r & PRODUCE_ROLES), "invoice": bool(r & INVOICE_ROLES), "cancel": bool(r & CANCEL_ROLES),
			"edit": bool(r & PRODUCE_ROLES)},
	}


def _filters_sql(f):
	cond, vals = ["status != 'Cancelled'"], {}
	if not cint(f.get("show_closed")):
		cond.append("status != 'Invoiced'")
	if f.get("customer"):
		cond.append("customer = %(customer)s")
		vals["customer"] = f["customer"]
	if f.get("strain"):
		cond.append("strain like %(strain)s")
		vals["strain"] = "%" + f["strain"].strip() + "%"
	if f.get("return_type"):
		cond.append("return_type = %(return_type)s")
		vals["return_type"] = f["return_type"]
	if f.get("from_date"):
		cond.append("received_date >= %(from_date)s")
		vals["from_date"] = f["from_date"]
	if f.get("to_date"):
		cond.append("received_date <= %(to_date)s")
		vals["to_date"] = f["to_date"]
	if f.get("name"):
		cond.append("name = %(name)s")
		vals["name"] = f["name"]
	return " and ".join(cond), vals


def _cards(where, vals, limit=500):
	jobs = frappe.db.sql(
		"select {0} from `tabToll Job` where {1} order by (priority = 'Rush') desc, received_date, name limit {2}".format(
			", ".join("`{0}`".format(f) for f in JOB_FIELDS), where, cint(limit)), vals, as_dict=True)
	if not jobs:
		return []
	names = [j.name for j in jobs]
	inv = {d.name: d for d in frappe.get_all("Sales Invoice",
		filters={"name": ["in", [j.sales_invoice for j in jobs if j.sales_invoice] or [""]]},
		fields=["name", "docstatus", "grand_total"])}
	dns = {}
	for d in frappe.db.sql("""select toll_job, name from `tabDelivery Note` where docstatus = 1 and toll_job in %(n)s
			order by posting_date, creation""", {"n": names}, as_dict=True):
		dns[d.toll_job] = d.name
	today = getdate(nowdate())
	for j in jobs:
		si = inv.get(j.sales_invoice)
		j.invoice_status = None if not si else ("Submitted" if si.docstatus == 1 else "Cancelled" if si.docstatus == 2 else "Draft")
		j.delivery_note = dns.get(j.name)
		j.overdue = bool(j.promised_return_date and getdate(j.promised_return_date) < today
			and j.status not in ("Returned", "Invoiced"))
		for k in ("received_date", "promised_return_date", "modified"):
			j[k] = str(j[k]) if j[k] else None
	return jobs


def job_card(name):
	where, vals = _filters_sql({"name": name, "show_closed": 1})
	rows = _cards(where, vals, 1)
	return rows[0] if rows else None


@frappe.whitelist()
def get_board_data(filters=None):
	_require(VIEW_ROLES, _("open the Toll Processing Board"))
	f = _parse(filters) or {}
	where, vals = _filters_sql(f)
	jobs = _cards(where, vals)
	counts = {}
	for j in jobs:
		counts[j.status] = counts.get(j.status, 0) + 1
	kpis = {
		"ff_on_hand_lbs": flt(sum(flt(j.ff_balance_lbs) for j in jobs), 3),
		"bh_wip_grams": flt(sum(flt(j.bh_wip_grams) for j in jobs), 3),
		"output_ready_grams": flt(sum(flt(j.bh_output_grams) + flt(j.rosin_output_grams) for j in jobs), 3),
		"overdue": sum(1 for j in jobs if j.overdue),
		"uninvoiced_returned": sum(1 for j in jobs if j.status == "Returned"),
	}
	return {"jobs": jobs, "kpis": kpis, "counts": counts, "today": nowdate()}


# ---------------------------------------------------------------- receive / queue / edit

@frappe.whitelist()
def create_toll_client(customer_name):
	"""A new client from the Receive dialog: a normal Customer in the Toll Clients group."""
	_require(PRODUCE_ROLES, _("receive toll material"))
	customer_name = (customer_name or "").strip()
	if not customer_name:
		frappe.throw(_("Enter the client name."))
	existing = frappe.db.get_value("Customer", {"customer_name": customer_name}, ["name", "customer_group"], as_dict=True)
	if existing:
		if existing.customer_group != CUSTOMER_GROUP:
			frappe.throw(_("Customer {0} already exists in the {1} group. Ask accounts to move it to {2}.").format(
				existing.name, existing.customer_group, CUSTOMER_GROUP))
		return existing.name
	c = frappe.get_doc({"doctype": "Customer", "customer_name": customer_name, "customer_group": CUSTOMER_GROUP,
		"customer_type": "Company"})
	c.flags.ignore_permissions = True
	c.insert()
	return c.name


@frappe.whitelist()
def receive_material(header, rows):
	"""Per row: Toll Job, its FF batch and a submitted Material Receipt into Toll Inbound. Returns the job names."""
	_require(PRODUCE_ROLES, _("receive toll material"))
	h = frappe._dict(_parse(header) or {})
	rows = [frappe._dict(r) for r in (_parse(rows) or []) if r]
	if not h.customer:
		frappe.throw(_("Select the customer."))
	if frappe.db.get_value("Customer", h.customer, "customer_group") != CUSTOMER_GROUP:
		frappe.throw(_("Customer {0} is not in the {1} group.").format(h.customer, CUSTOMER_GROUP))
	if not rows:
		frappe.throw(_("Add at least one strain."))
	d = _date(h.received_date, _("Received Date"))
	if h.promised_return_date and getdate(h.promised_return_date) < d:
		frappe.throw(_("Promised Return Date cannot be before the Received Date."))
	if h.rate_basis and h.rate_basis not in RATE_BASES:
		frappe.throw(_("Unknown Rate Basis {0}.").format(h.rate_basis))
	for i, r in enumerate(rows, 1):
		if not (r.strain or "").strip() or flt(r.ff_lbs) <= 0:
			frappe.throw(_("Row {0}: enter a strain and FF pounds greater than zero.").format(i))
		if r.return_type not in RETURN_TYPES:
			frappe.throw(_("Row {0}: select the Return Type.").format(i))

	made = []
	for r in rows:
		job = frappe.get_doc({
			"doctype": "Toll Job", "company": COMPANY, "customer": h.customer, "strain": r.strain.strip(),
			"return_type": r.return_type, "priority": h.priority or "Normal", "received_date": d,
			"promised_return_date": h.promised_return_date or None, "physical_location": h.physical_location or None,
			"inbound_manifest": h.inbound_manifest, "inbound_tags": (r.inbound_tag or "").strip(),
			"rate_basis": h.rate_basis or RATE_BASES[0], "rate": flt(h.rate), "status": "Received",
		})
		job.flags.ignore_permissions = True
		job.insert()
		batch = _ensure_batch(job, ITEM_FF)
		remarks = _("Toll receipt from {0}, strain {1}, manifest {2}").format(
			job.customer_name or job.customer, job.strain, h.inbound_manifest or "-")
		_submit_se(job, "Material Receipt", d, [_se_row(ITEM_FF, r.ff_lbs, UOM_FF, batch, t_wh=WH_INBOUND)], remarks)
		made.append(job.name)
	return {"jobs": made, "message": _("Received {0} toll job{1}: {2}.").format(
		len(made), "" if len(made) == 1 else "s", ", ".join(made))}


@frappe.whitelist()
def set_queued(toll_job, queued):
	_require(PRODUCE_ROLES, _("plan toll washes"))
	job = _job(toll_job)
	if job.status not in ("Received", "Queued for Wash"):
		frappe.throw(_("Only received jobs can be queued for wash."))
	job.db_set("queued_for_wash", cint(queued))
	update_toll_job_status(job.name)
	return _result(job.name, _("{0} moved to {1}.").format(job.name, _("Queued for Wash") if cint(queued) else _("Received")))


EDITABLE = ("promised_return_date", "priority", "physical_location", "return_type", "inbound_manifest", "inbound_tags", "notes")


@frappe.whitelist()
def update_job(toll_job, values):
	_require(PRODUCE_ROLES, _("edit toll jobs"))
	job = _job(toll_job)
	v = _parse(values) or {}
	for k in EDITABLE:
		if k in v:
			job.set(k, v[k] or None)
	if "rate" in v or "rate_basis" in v:
		_require(INVOICE_ROLES | PRODUCE_ROLES, _("change toll rates"))
		if v.get("rate_basis"):
			job.rate_basis = v["rate_basis"]
		if "rate" in v:
			job.rate = flt(v["rate"])
	job.flags.ignore_permissions = True
	job.save()
	return _result(job.name, _("{0} saved.").format(job.name))


@frappe.whitelist()
def cancel_toll_job(toll_job):
	"""Cancel a job at any stage before invoicing: its Delivery Notes and Stock Entries are cancelled last step first,
	a draft invoice is deleted, and its batches are deleted when empty or disabled when not."""
	_require(CANCEL_ROLES, _("cancel toll jobs"))
	job = _job(toll_job)
	invoiced = frappe.get_all("Sales Invoice", filters={"toll_job": job.name, "docstatus": 1}, pluck="name")
	if invoiced:
		frappe.throw(_("{0} is invoiced on {1}. Cancel the invoice first, then cancel the job.").format(job.name, ", ".join(invoiced)))
	cancelled = cancel_stock_docs(job.name)
	drafts = frappe.get_all("Sales Invoice", filters={"toll_job": job.name, "docstatus": 0}, pluck="name")
	for si in drafts:
		frappe.delete_doc("Sales Invoice", si, ignore_permissions=True)
	frappe.db.set_value("Toll Job", job.name, {"status": "Cancelled", "sales_invoice": None})
	update_toll_job_status(job.name)
	deleted, disabled = cleanup_batches(job.name)
	parts = [_("{0} cancelled.").format(job.name)]
	if cancelled:
		parts.append(_("Cancelled: {0}.").format(", ".join(cancelled)))
	if drafts:
		parts.append(_("Draft invoice deleted: {0}.").format(", ".join(drafts)))
	if deleted:
		parts.append(_("Empty batches deleted: {0}.").format(", ".join(deleted)))
	if disabled:
		parts.append(_("Batches kept (not empty) and disabled: {0}.").format(", ".join("{0} ({1})".format(b, _fmt(q, 3)) for b, q in disabled)))
	return {"message": " ".join(parts), "cancelled": cancelled, "deleted_batches": deleted, "disabled_batches": [b for b, _q in disabled]}


# ---------------------------------------------------------------- wash / press / move

@frappe.whitelist()
def record_wash(toll_job, wash_date, lbs, bh_grams, washer=None, notes=None):
	_require(PRODUCE_ROLES, _("record washes"))
	job = _job(toll_job)
	lbs, g = flt(lbs, 3), flt(bh_grams, 3)
	if lbs <= 0 or g <= 0:
		frappe.throw(_("Enter FF pounds and bubble hash grams greater than zero."))
	if lbs > flt(job.ff_balance_lbs) + EPS:  # rule 7
		frappe.throw(_("Quantity exceeds the available balance for this Toll Job ({0} lbs).").format(_fmt(job.ff_balance_lbs, 2)))
	d = _date(wash_date, _("Wash Date"), job.received_date, _("Received Date"))
	ff_batch = _ensure_batch(job, ITEM_FF)
	bh_batch = _ensure_batch(job, ITEM_BH, "-BH")
	target = WH_OUTPUT if job.return_type == "Bubble Hash" else WH_WIP
	_submit_se(job, "Repack", d, [
		_se_row(ITEM_FF, lbs, UOM_FF, ff_batch, s_wh=WH_INBOUND),
		_se_row(ITEM_BH, g, UOM_G, bh_batch, t_wh=target, finished=True),
	], _("Toll wash {0}, {1}: {2} lbs FF to {3} g Bubble Hash").format(job.name, job.strain, _fmt(lbs, 3), _fmt(g)),
		wash_date=d, washer=washer, wash_notes=notes)
	pct = g / (lbs * LB_TO_G) * 100
	return _result(job.name, _("Wash recorded for {0}: {1} g Bubble Hash ({2}% yield).").format(job.name, _fmt(g), _fmt(pct, 2)))


@frappe.whitelist()
def record_press(toll_job, press_date, bh_grams, rosin_grams, notes=None):
	_require(PRODUCE_ROLES, _("record presses"))
	job = _job(toll_job)
	if job.return_type not in ("Rosin", "Both"):
		frappe.throw(_("{0} returns Bubble Hash only; nothing is pressed.").format(job.name))
	bh, r = flt(bh_grams, 3), flt(rosin_grams, 3)
	if bh <= 0 or r <= 0:
		frappe.throw(_("Enter bubble hash and rosin grams greater than zero."))
	if bh > flt(job.bh_wip_grams) + EPS:  # rule 7
		frappe.throw(_("Quantity exceeds the available balance for this Toll Job ({0} g in WIP).").format(_fmt(job.bh_wip_grams)))
	if r > bh:
		frappe.throw(_("Rosin cannot be more than the bubble hash pressed."))
	last_wash = _last_posting(job.name, "Repack")
	d = _date(press_date, _("Press Date"), last_wash or job.received_date, _("last wash date"))
	bh_batch = _ensure_batch(job, ITEM_BH, "-BH")
	ro_batch = _ensure_batch(job, ITEM_ROSIN, "-RO")
	_submit_se(job, "Repack", d, [
		_se_row(ITEM_BH, bh, UOM_G, bh_batch, s_wh=WH_WIP),
		_se_row(ITEM_ROSIN, r, UOM_G, ro_batch, t_wh=WH_OUTPUT, finished=True),
	], _("Toll press {0}, {1}: {2} g Bubble Hash to {3} g Rosin").format(job.name, job.strain, _fmt(bh), _fmt(r)),
		press_date=d, press_notes=notes)
	return _result(job.name, _("Press recorded for {0}: {1} g rosin ({2}% yield).").format(job.name, _fmt(r), _fmt(r / bh * 100, 1)))


@frappe.whitelist()
def move_bh_to_output(toll_job, grams, move_date=None):
	_require(PRODUCE_ROLES, _("move bubble hash"))
	job = _job(toll_job)
	g = flt(grams, 3)
	if g <= 0:
		frappe.throw(_("Enter grams greater than zero."))
	if g > flt(job.bh_wip_grams) + EPS:
		frappe.throw(_("Quantity exceeds the available balance for this Toll Job ({0} g in WIP).").format(_fmt(job.bh_wip_grams)))
	d = _date(move_date, _("Date"), job.received_date, _("Received Date"))
	bh_batch = _ensure_batch(job, ITEM_BH, "-BH")
	row = _se_row(ITEM_BH, g, UOM_G, bh_batch, s_wh=WH_WIP, t_wh=WH_OUTPUT)
	_submit_se(job, "Material Transfer", d, [row],
		_("Toll {0}, {1}: {2} g Bubble Hash to Toll Output, returned as bubble hash").format(job.name, job.strain, _fmt(g)))
	return _result(job.name, _("{0} g Bubble Hash moved to Toll Output for {1}.").format(_fmt(g), job.name))


# ---------------------------------------------------------------- return / invoice

@frappe.whitelist()
def return_to_client(toll_job, return_date, manifest=None, driver=None, items=None):
	"""Delivery Note at zero rate from Toll Output: moves the stock and carries the METRC paperwork."""
	_require(PRODUCE_ROLES, _("return toll material"))
	job = _job(toll_job)
	avail = {ITEM_BH: flt(job.bh_output_grams), ITEM_ROSIN: flt(job.rosin_output_grams)}
	lines = []
	for it in _parse(items) or []:
		it = frappe._dict(it)
		if it.item_code not in avail:
			frappe.throw(_("Only Toll Bubble Hash and Toll Rosin can be returned."))
		q = flt(it.qty, 3)
		if q <= 0:
			continue
		if q > avail[it.item_code] + EPS:
			frappe.throw(_("Quantity exceeds the available balance for this Toll Job."))
		lines.append((it.item_code, q, (it.metrc_tag or "").strip()))
	if not lines:
		frappe.throw(_("Enter a return quantity on at least one item."))
	last = _last_posting(job.name)
	d = _date(return_date, _("Return Date"), last or job.received_date, _("last production date"))

	dn = frappe.new_doc("Delivery Note")
	dn.customer = job.customer
	dn.company = job.company or COMPANY
	_posting(dn, d)
	dn.toll_job = job.name
	dn.outbound_manifest = manifest
	dn.driver_name = driver
	dn.outbound_tags = "\n".join(t for _i, _q, t in lines if t)
	dn.ignore_pricing_rule = 1
	for item_code, q, _t in lines:
		batch = _ensure_batch(job, item_code, "-BH" if item_code == ITEM_BH else "-RO")
		dn.append("items", {
			"item_code": item_code, "qty": q, "stock_qty": q, "uom": UOM_G, "stock_uom": UOM_G, "conversion_factor": 1,
			"warehouse": WH_OUTPUT, "batch_no": batch, "use_serial_batch_fields": 1, "allow_zero_valuation_rate": 1,
			"rate": 0, "price_list_rate": 0,
		})
	dn.set_missing_values()
	# MTM has no default COGS account; the zero-value return posts nothing, but ERPNext still wants a P&L account per row
	zero_account = RETURN_EXPENSE_ACCOUNT if frappe.db.exists("Account", RETURN_EXPENSE_ACCOUNT) else None
	for row in dn.items:  # nothing from price lists or pricing rules: the return is at zero
		row.update({"rate": 0, "price_list_rate": 0, "discount_percentage": 0, "discount_amount": 0, "margin_rate_or_amount": 0,
			"allow_zero_valuation_rate": 1, "warehouse": WH_OUTPUT, "uom": UOM_G, "conversion_factor": 1,
			"expense_account": zero_account or row.expense_account})
	dn.remarks = _("Return of customer-owned material, Toll Job {0} ({1})").format(job.name, job.strain)
	dn.flags.ignore_permissions = True
	dn.insert()
	dn.submit()
	return {**_result(job.name, _("Delivery Note {0} created for {1}.").format(dn.name, job.name)), "delivery_note": dn.name}


@frappe.whitelist()
def create_invoice(toll_job, rate_basis=None, rate=None):
	"""Draft service Sales Invoice for a returned job; accounts review and submit it."""
	_require(INVOICE_ROLES, _("create toll invoices"))
	job = _job(toll_job)
	if job.sales_invoice and frappe.db.get_value("Sales Invoice", job.sales_invoice, "docstatus") in (0, 1):
		return {"message": _("{0} already has invoice {1}.").format(job.name, job.sales_invoice),
			"sales_invoice": job.sales_invoice, "job": job_card(job.name)}
	if job.status != "Returned":
		frappe.throw(_("Create the invoice after the material is returned to the client."))
	if rate_basis:
		if rate_basis not in RATE_BASES:
			frappe.throw(_("Unknown Rate Basis {0}.").format(rate_basis))
		job.rate_basis = rate_basis
	if rate is not None:
		job.rate = flt(rate)
	if flt(job.rate) <= 0:
		frappe.throw(_("Enter a rate greater than zero."))
	qty = billable_qty(job)
	if qty <= 0:
		frappe.throw(_("Nothing to bill: the billable quantity is zero."))
	job.flags.ignore_permissions = True
	job.save()

	uom = {"Per lb FF Input": UOM_FF, "Per Gram Output": UOM_G}.get(job.rate_basis, "Nos")
	desc = _("Toll processing — {0}, {1}: {2} lbs FF, {3} g BH, {4} g rosin").format(
		job.name, job.strain, _fmt(job.ff_washed_lbs, 2), _fmt(job.bh_grams), _fmt(job.rosin_grams))
	si = frappe.new_doc("Sales Invoice")
	si.customer = job.customer
	si.company = job.company or COMPANY
	si.toll_job = job.name
	si.update_stock = 0
	si.ignore_pricing_rule = 1
	si.append("items", {"item_code": ITEM_SVC, "qty": flt(qty, 3), "uom": uom, "conversion_factor": 1, "rate": flt(job.rate),
		"description": desc, "income_account": INCOME_ACCOUNT})
	si.set_missing_values()
	for row in si.items:
		row.update({"rate": flt(job.rate), "price_list_rate": flt(job.rate), "discount_percentage": 0, "discount_amount": 0,
			"description": desc, "income_account": INCOME_ACCOUNT, "uom": uom, "conversion_factor": 1, "qty": flt(qty, 3)})
	si.flags.ignore_permissions = True
	si.insert()
	frappe.db.set_value("Toll Job", job.name, "sales_invoice", si.name)
	return {"message": _("Draft invoice {0} created for {1}. Accounts submit it; the job moves to Invoiced then.").format(
		si.name, frappe.format_value(si.grand_total, {"fieldtype": "Currency", "options": "currency"}, si)),
		"sales_invoice": si.name, "job": job_card(job.name)}


@frappe.whitelist()
def get_job_balances(toll_job):
	"""Fresh numbers for a dialog (Return grid, Press default)."""
	_require(VIEW_ROLES, _("open the Toll Processing Board"))
	return job_card(toll_job)


# ---------------------------------------------------------------- Wash / Press Plan Board rows

def plan_board_rows(statuses):
	"""Read-only toll jobs for the Wash Plan Board (Received / Queued) and the Press Plan Board (Washed / Pressed).
	They are listed apart from the plan rows, so the boards' project summaries never include them."""
	try:
		if not frappe.db.table_exists("Toll Job"):
			return []
		rows = frappe.get_all("Toll Job", filters={"status": ["in", list(statuses)]}, order_by="received_date asc, name asc",
			fields=["name", "customer", "customer_name", "strain", "return_type", "status", "priority", "received_date",
				"promised_return_date", "physical_location", "ff_received_lbs", "ff_balance_lbs", "bh_wip_grams"])
	except Exception:
		frappe.log_error(title="Toll rows for plan board")
		return []
	for r in rows:
		r.received_date = str(r.received_date) if r.received_date else None
		r.promised_return_date = str(r.promised_return_date) if r.promised_return_date else None
	rows.sort(key=lambda r: r.priority != "Rush")
	return rows
