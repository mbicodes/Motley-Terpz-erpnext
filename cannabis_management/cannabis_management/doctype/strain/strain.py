# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

from frappe.model.document import Document


class Strain(Document):
	def validate(self):
		# METRC strain name defaults to the strain name when left blank.
		if not self.metrc_strain_name:
			self.metrc_strain_name = self.strain_name
