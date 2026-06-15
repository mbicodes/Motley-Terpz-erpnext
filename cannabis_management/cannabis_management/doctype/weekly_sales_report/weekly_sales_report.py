import frappe
from frappe.model.document import Document


class WeeklySalesReport(Document):
	def before_save(self):
		# Once acknowledged, lock all snapshot fields — only acknowledgment_notes may change
		if not self.is_new() and self.is_acknowledged:
			original = frappe.get_doc("Weekly Sales Report", self.name)
			locked_fields = [
				"week_start", "week_end", "total_orders", "total_order_value",
				"total_invoiced", "total_collected", "total_outstanding",
				"acknowledged_by", "acknowledged_at", "is_acknowledged",
			]
			for f in locked_fields:
				if getattr(self, f) != getattr(original, f):
					frappe.throw(
						f"Field '{f}' cannot be changed after a Weekly Sales Report has been acknowledged.",
						title="Report Locked"
					)
