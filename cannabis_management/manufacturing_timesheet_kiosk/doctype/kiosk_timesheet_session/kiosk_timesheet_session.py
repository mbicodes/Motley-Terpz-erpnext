# Copyright (c) 2026, Cannabis Management and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class KioskTimesheetSession(Document):
	def validate(self):
		if self.status == "Running":
			duplicate = frappe.db.exists(
				"Kiosk Timesheet Session",
				{
					"employee": self.employee,
					"status": "Running",
					"name": ["!=", self.name],
				},
			)
			if duplicate:
				frappe.throw(
					frappe._(
						"Employee {0} already has an open kiosk session ({1})."
					).format(self.employee, duplicate)
				)
