import frappe
from frappe import _
from frappe.utils import validate_email_address

from crm.fcrm.doctype.crm_lead.crm_lead import CRMLead


class CMCRMLead(CRMLead):
	def validate_email(self):
		# Same checks as core, minus has_gravatar(): core calls it on every save
		# of any lead with an email and no image -- nearly all of them -- and it
		# is a blocking request to gravatar.com with a 5s timeout. It cost ~0.25s
		# per save when measured and up to 5s when gravatar is slow, for an
		# avatar almost no lead has.
		if not self.email:
			return

		if not self.flags.ignore_email_validation:
			validate_email_address(self.email, throw=True)

		if self.email == self.lead_owner:
			frappe.throw(_("Lead Owner cannot be same as the Lead Email Address"))
