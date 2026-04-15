import frappe
from frappe.model.document import Document


class METRCPackageVerification(Document):

    def validate(self):
        self._calc_variance()

    def _calc_variance(self):
        sys_g = float(self.system_weight_g or 0)
        phys_g = float(self.verified_weight_g or 0)
        self.variance_g = round(sys_g - phys_g, 2)
