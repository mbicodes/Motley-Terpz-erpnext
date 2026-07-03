# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document


class OnboardingPacket(Document):
	DEFAULT_CHECKLIST = [
		"State Cannabis License",
		"Business License/Seller's Permit",
		"Resale Certificate",
		"Signed W-9",
		"Certificate of Insurance",
		"Voided Check",
		"Signed Contract",
	]

	def before_insert(self):
		if not self.checklist:
			for document_name in self.DEFAULT_CHECKLIST:
				self.append("checklist", {"document_name": document_name, "required": 1})
