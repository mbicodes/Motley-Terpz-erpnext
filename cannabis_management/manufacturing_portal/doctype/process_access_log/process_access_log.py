import frappe
from frappe.model.document import Document


class ProcessAccessLog(Document):
	"""Append-only audit trail. Written only by cannabis_management.manufacturing_portal.access.

	No `create` permission is granted to any role — rows are inserted with
	ignore_permissions so the log cannot be forged through the UI or the REST API,
	and `in_create` stops anyone editing a row after the fact.
	"""

	pass
