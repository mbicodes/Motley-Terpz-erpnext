# Copyright (c) 2026, alltechvirtual.com and contributors
# For license information, please see license.txt

from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint


class DailyReportSettings(Document):
	def validate(self):
		self.time_zone = (self.time_zone or "").strip() or "America/Los_Angeles"
		try:
			ZoneInfo(self.time_zone)
		except (ZoneInfoNotFoundError, ValueError):
			frappe.throw(_("{0} is not a valid time zone. Use a name such as America/Los_Angeles.").format(self.time_zone))
		if not 0 <= cint(self.reminder_hour) <= 23:
			frappe.throw(_("Reminder Hour must be between 0 and 23."))
