import frappe
from frappe import _
from frappe.utils import validate_email_address

from crm.fcrm.doctype.crm_lead.crm_lead import CRMLead


class CMCRMLead(CRMLead):
	def validate_email(self):
		if not self.email:
			return

		if not self.flags.ignore_email_validation:
			validate_email_address(self.email, throw=True)

		if self.email == self.lead_owner:
			frappe.throw(_("Lead Owner cannot be same as the Lead Email Address"))
