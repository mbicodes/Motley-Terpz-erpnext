from frappe.model.document import Document


class Strain(Document):
	def validate(self):
		if not self.metrc_strain_name:
			self.metrc_strain_name = self.strain_name
