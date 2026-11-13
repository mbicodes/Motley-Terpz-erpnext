import frappe
from frappe.model.document import Document


class ProjectTrackerSettings(Document):
	def on_update(self):
		# thresholds and groups change every figure on the page
		from cannabis_management.project_tracker_hooks import bump_cache

		bump_cache()
