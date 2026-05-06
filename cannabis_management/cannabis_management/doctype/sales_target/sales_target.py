import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate


class SalesTarget(Document):
    def validate(self):
        self.validate_dates()
        self.calculate_target_units()

    def validate_dates(self):
        if getdate(self.start_date) > getdate(self.end_date):
            frappe.throw(_("Start Date cannot be after End Date"))

    def calculate_target_units(self):
        if flt(self.avg_sale_price) <= 0:
            frappe.throw(_("Avg Sale Price must be greater than zero"))
        self.target_units = flt(self.target_revenue) / flt(self.avg_sale_price)