"""Toll Job: one intake of one strain from one toll client.

Not submittable. Quantities, activity and status are written only by
cannabis_management.toll.utils.update_toll_job_status from the linked stock documents.
"""
import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from cannabis_management.toll.constants import CUSTOMER_GROUP
from cannabis_management.toll.utils import batch_state, billable_qty, derive_status, invoice_state, job_batches


class TollJob(Document):
	def validate(self):
		if self.is_new() or self.has_value_changed("customer"):
			if frappe.db.get_value("Customer", self.customer, "customer_group") != CUSTOMER_GROUP:
				frappe.throw(_("Customer {0} is not in the {1} customer group.").format(self.customer, CUSTOMER_GROUP))
		if not self.is_new():
			before = self.get_doc_before_save()
			if before and flt(before.ff_washed_lbs) > 0:
				for f in ("customer", "return_type"):
					if before.get(f) != self.get(f) and not self.flags.from_status_update:
						frappe.throw(_("{0} cannot be changed after the first wash.").format(self.meta.get_label(f)))
		if self.promised_return_date and self.received_date and getdate(self.promised_return_date) < getdate(self.received_date):
			frappe.throw(_("Promised Return Date cannot be before the Received Date."))
		self.billable_qty = flt(billable_qty(self), 3)
		self.amount = flt(self.billable_qty * flt(self.rate), 2)
		if not self.flags.from_status_update and not self.is_new():
			self.status = derive_status(self, invoice_state(self.sales_invoice))

	def on_trash(self):
		"""Delete a job with no submitted documents: its cancelled stock documents and its empty batches go with it.
		A batch that still holds stock is never deleted, and then the job is not deleted either."""
		live = frappe.get_all("Stock Entry", filters={"toll_job": self.name, "docstatus": 1}, pluck="name")
		live += frappe.get_all("Delivery Note", filters={"toll_job": self.name, "docstatus": 1}, pluck="name")
		live += frappe.get_all("Sales Invoice", filters={"toll_job": self.name, "docstatus": 1}, pluck="name")
		if live:
			frappe.throw(_("Toll Job {0} has submitted documents ({1}). Use Cancel Job first, then delete it.").format(
				self.name, ", ".join(live)))
		cancelled_si = frappe.get_all("Sales Invoice", filters={"toll_job": self.name, "docstatus": 2}, pluck="name")
		if cancelled_si:
			frappe.throw(_("Cancelled Sales Invoice {0} is linked to {1}. Delete the invoice first.").format(
				", ".join(cancelled_si), self.name))
		for b in job_batches(self.name):
			n, qty = batch_state(b)
			if n:
				frappe.throw(_("Batch {0} is not empty ({1} in stock entries that are not cancelled), so it is not deleted and {2} cannot be deleted.").format(
					b, frappe.format_value(qty, {"fieldtype": "Float", "precision": 3}), self.name))
		for si in frappe.get_all("Sales Invoice", filters={"toll_job": self.name, "docstatus": 0}, pluck="name"):
			frappe.delete_doc("Sales Invoice", si, ignore_permissions=True)
		for dt in ("Delivery Note", "Stock Entry"):  # cancelled ones: their ledger entries are already reversed
			for n in frappe.get_all(dt, filters={"toll_job": self.name, "docstatus": 2}, pluck="name"):
				frappe.delete_doc(dt, n, ignore_permissions=True)
		for b in job_batches(self.name):
			frappe.delete_doc("Batch", b, ignore_permissions=True, force=True)
