# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class BankFinancialStatementRecord(Document):
	def validate(self):
		if self.account_last4:
			if len(self.account_last4) > 4 or not self.account_last4.isdigit():
				frappe.throw(
					_("Account Last 4 must be at most 4 characters and contain digits only. Never store full account numbers.")
				)
