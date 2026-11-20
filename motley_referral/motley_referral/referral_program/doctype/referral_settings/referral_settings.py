import frappe
from frappe import _
from frappe.model.document import Document


class ReferralSettings(Document):
    def validate(self):
        if not 1 <= (self.run_day or 1) <= 28:
            frappe.throw(_("Statement Run Day must be between 1 and 28."))
        seen = set()
        for r in self.eligible_companies:
            if r.company in seen:
                frappe.throw(_("Company {0} is listed twice.").format(r.company))
            seen.add(r.company)
