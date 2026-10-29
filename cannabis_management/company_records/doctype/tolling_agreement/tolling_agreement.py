import frappe
from frappe import _
from frappe.model.document import Document


class TollingAgreement(Document):
	def validate(self):
		for run in self.tolling_runs:
			if frappe.utils.flt(run.input_qty):
				run.actual_yield_pct = frappe.utils.flt(run.output_qty) / frappe.utils.flt(run.input_qty) * 100
			else:
				run.actual_yield_pct = 0
