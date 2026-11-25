"""doc_events for the toll flow: validations 1-9 of the build spec, and the Toll Job refresh on submit / cancel.

Every check returns at once for documents that have no toll item, no toll warehouse and no Toll Job, so normal
MTM documents only pay for one warehouse lookup.
"""
import frappe
from frappe import _
from frappe.utils import flt

from cannabis_management.toll.constants import ITEM_GROUP, ITEM_SVC, WH_GROUP
from cannabis_management.toll.utils import later_step, update_toll_job_status

TOLL_DOC_EVENTS = {
	"Stock Entry": {
		"validate": ["cannabis_management.toll.events.validate_stock_doc"],
		"before_cancel": ["cannabis_management.toll.events.before_cancel"],
		"on_submit": ["cannabis_management.toll.events.refresh_job"],
		"on_cancel": ["cannabis_management.toll.events.refresh_job"],
	},
	"Delivery Note": {
		"validate": ["cannabis_management.toll.events.validate_stock_doc"],
		"before_cancel": ["cannabis_management.toll.events.before_cancel"],
		"on_submit": ["cannabis_management.toll.events.refresh_job"],
		"on_cancel": ["cannabis_management.toll.events.refresh_job"],
	},
	"Sales Invoice": {
		"validate": ["cannabis_management.toll.events.validate_sales_invoice"],
		"on_submit": ["cannabis_management.toll.events.sales_invoice_on_submit"],
		"on_cancel": ["cannabis_management.toll.events.sales_invoice_on_cancel"],
		"on_trash": ["cannabis_management.toll.events.sales_invoice_on_trash"],
	},
}


def extend_doc_events(doc_events):
	"""Append (never replace) the toll handlers, like mt_dispatch / project tracker do."""
	for doctype, events in TOLL_DOC_EVENTS.items():
		target = doc_events.setdefault(doctype, {})
		for event, handlers in events.items():
			existing = target.get(event, [])
			if isinstance(existing, str):
				existing = [existing]
			target[event] = list(existing) + [h for h in handlers if h not in existing]
	return doc_events


def toll_warehouses():
	"""Warehouses under Toll Warehouses - MTM (the group included). Cached per request."""
	if getattr(frappe.local, "_toll_warehouses", None) is None:
		g = frappe.db.get_value("Warehouse", WH_GROUP, ["lft", "rgt"], as_dict=True)
		frappe.local._toll_warehouses = set(frappe.get_all(
			"Warehouse", filters={"lft": [">=", g.lft], "rgt": ["<=", g.rgt]}, pluck="name")) if g else set()
	return frappe.local._toll_warehouses


def is_toll_item(item_code):
	return bool(item_code) and frappe.get_cached_value("Item", item_code, "item_group") == ITEM_GROUP


def _row_warehouses(doc, row):
	if doc.doctype == "Stock Entry":
		return [w for w in (row.s_warehouse, row.t_warehouse) if w]
	return [w for w in (row.get("warehouse"), row.get("target_warehouse")) if w]


def validate_stock_doc(doc, method=None):
	whs = toll_warehouses()
	toll_rows = []
	for row in doc.get("items") or []:
		if not row.item_code:
			continue
		row_whs = _row_warehouses(doc, row)
		if is_toll_item(row.item_code):
			if any(w not in whs for w in row_whs):  # rule 1
				frappe.throw(_("Row #{0}: Toll items can only be moved within Toll warehouses.").format(row.idx))
			toll_rows.append(row)
		elif whs and any(w in whs for w in row_whs) and frappe.get_cached_value("Item", row.item_code, "is_stock_item"):
			frappe.throw(_("Row #{0}: Toll warehouses are reserved for customer-owned material.").format(row.idx))  # rule 2

	if not toll_rows:
		return
	if not doc.get("toll_job"):  # rule 3
		frappe.throw(_("Please link a Toll Job to move customer-owned material."))
	job = frappe.db.get_value("Toll Job", doc.toll_job, ["customer", "status"], as_dict=True)
	if not job:
		frappe.throw(_("Toll Job {0} does not exist.").format(doc.toll_job))
	if job.status == "Cancelled":
		frappe.throw(_("Toll Job {0} is cancelled.").format(doc.toll_job))
	for row in toll_rows:
		batch = row.get("batch_no")
		if not batch or frappe.db.get_value("Batch", batch, "toll_job") != doc.toll_job:  # rule 4
			frappe.throw(_("Row #{0}: Batch {1} does not belong to Toll Job {2}.").format(row.idx, batch or _("(empty)"), doc.toll_job))
		rate = row.basic_rate if doc.doctype == "Stock Entry" else row.rate
		if flt(rate) or not row.get("allow_zero_valuation_rate"):  # rule 5
			frappe.throw(_("Row #{0}: Customer-owned material must be moved at zero value.").format(row.idx))
	if doc.doctype == "Delivery Note" and doc.customer != job.customer:  # rule 6
		frappe.throw(_("This material belongs to {0}, not {1}.").format(job.customer, doc.customer))


def before_cancel(doc, method=None):
	"""Rule 9: undo the steps of a job from the last one backwards."""
	if not doc.get("toll_job"):
		return
	later = later_step(doc)
	if later:
		frappe.throw(_("Cancel the later step ({0}) first.").format(later))


def refresh_job(doc, method=None):
	if doc.get("toll_job"):
		update_toll_job_status(doc.toll_job)


def validate_sales_invoice(doc, method=None):
	has_svc = any(r.item_code == ITEM_SVC for r in doc.get("items") or [])
	if not has_svc and not doc.get("toll_job"):
		return
	if has_svc and not doc.get("toll_job"):  # rule 8
		frappe.throw(_("Please link a Toll Job to invoice toll processing."))
	if doc.toll_job and doc.docstatus == 1:
		other = frappe.db.get_value("Sales Invoice",
			{"toll_job": doc.toll_job, "docstatus": 1, "name": ["!=", doc.name]}, "name")
		if other:
			frappe.throw(_("This Toll Job is already invoiced on {0}.").format(other))


def sales_invoice_on_submit(doc, method=None):
	if not doc.get("toll_job"):
		return
	frappe.db.set_value("Toll Job", doc.toll_job, "sales_invoice", doc.name, update_modified=False)
	update_toll_job_status(doc.toll_job)


def sales_invoice_on_cancel(doc, method=None):
	if not doc.get("toll_job"):
		return
	if frappe.db.get_value("Toll Job", doc.toll_job, "sales_invoice") == doc.name:
		frappe.db.set_value("Toll Job", doc.toll_job, "sales_invoice", None, update_modified=False)
	update_toll_job_status(doc.toll_job)


def sales_invoice_on_trash(doc, method=None):
	if doc.get("toll_job") and frappe.db.get_value("Toll Job", doc.toll_job, "sales_invoice") == doc.name:
		frappe.db.set_value("Toll Job", doc.toll_job, "sales_invoice", None)
