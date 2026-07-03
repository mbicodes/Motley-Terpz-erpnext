# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class ReconciliationRecord(Document):
	def validate(self):
		self.variance = frappe.utils.flt(self.source_balance) - frappe.utils.flt(self.target_balance)
		if self.variance and self.status in ("Approved", "Locked") and not frappe.utils.strip_html(self.variance_explanation or "").strip():
			frappe.throw(
				_("A Variance Explanation is required before a reconciliation with a non-zero variance can be {0}.").format(_(self.status))
			)
