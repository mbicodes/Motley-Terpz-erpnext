import frappe
from erpnext.stock.doctype.material_request.material_request import MaterialRequest
from frappe.custom.doctype.property_setter.property_setter import make_property_setter
from frappe.utils import flt

IN_PROGRESS = "In Progress"
COMPLETED = "Completed"


def install():
	options = frappe.get_meta("Material Request").get_field("status").options.split("\n")
	missing = [s for s in (IN_PROGRESS, COMPLETED) if s not in options]
	if missing:
		_add_options(options + missing)

	for name in frappe.get_all(
		"Work Order",
		filters={"docstatus": 1, "material_request": ("is", "set")},
		pluck="material_request",
		distinct=True,
	):
		sync(name)


def _add_options(options):
	make_property_setter(
		"Material Request",
		"status",
		"options",
		"\n".join(options),
		"Text",
		validate_fields_for_doctype=False,
	)


def work_order_done(wo):
	return wo.status == "Completed" or (
		flt(wo.qty) > 0 and flt(wo.produced_qty) + flt(wo.process_loss_qty) >= flt(wo.qty)
	)


def run_status(mr):
	if mr.material_request_type != "Manufacture" or mr.docstatus != 1:
		return None
	if mr.status in ("Stopped", "Cancelled"):
		return None
	work_orders = frappe.get_all(
		"Work Order",
		filters={"material_request": mr.name, "docstatus": 1},
		fields=["name", "status", "qty", "produced_qty", "process_loss_qty"],
	)
	if not work_orders:
		return None
	return COMPLETED if all(work_order_done(wo) for wo in work_orders) else IN_PROGRESS


def sync(material_request):
	if not material_request or not frappe.db.exists("Material Request", material_request):
		return
	mr = frappe.get_doc("Material Request", material_request)
	status = run_status(mr)
	if status and mr.status != status:
		mr.db_set("status", status, update_modified=False)


def on_work_order_change(doc, method=None):
	sync(doc.material_request)


def on_stock_entry_change(doc, method=None):
	if doc.purpose == "Manufacture" and doc.work_order:
		sync(frappe.db.get_value("Work Order", doc.work_order, "material_request"))


class CMMaterialRequest(MaterialRequest):
	def set_status(self, update=False, status=None, update_modified=True):
		super().set_status(update=update, status=status, update_modified=update_modified)
		run = run_status(self)
		if run and self.status != run:
			self.status = run
			if update:
				self.db_set("status", run, update_modified=update_modified)
