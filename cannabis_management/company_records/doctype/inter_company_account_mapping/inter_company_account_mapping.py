# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class InterCompanyAccountMapping(Document):
	def validate(self):
		if self.paying_company == self.receiving_company:
			frappe.throw(_("Paying Company and Receiving Company must be different."))

		due_from_company = frappe.db.get_value("Account", self.due_from_account, "company")
		if due_from_company != self.paying_company:
			frappe.throw(
				_("Due From Account {0} must belong to the Paying Company {1}.")
				.format(self.due_from_account, self.paying_company)
			)

		due_to_company = frappe.db.get_value("Account", self.due_to_account, "company")
		if due_to_company != self.receiving_company:
			frappe.throw(
				_("Due To Account {0} must belong to the Receiving Company {1}.")
				.format(self.due_to_account, self.receiving_company)
			)
