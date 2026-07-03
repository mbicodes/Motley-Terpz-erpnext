# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class CompanyContract(Document):
	def validate(self):
		if self.effective_date and self.expiry_date and frappe.utils.getdate(self.expiry_date) < frappe.utils.getdate(self.effective_date):
			frappe.throw(_("Expiry Date cannot be before Effective Date."))
