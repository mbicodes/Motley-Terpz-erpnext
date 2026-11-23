import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt, getdate

from cannabis_management.time_clock.time_off import (
	approver_for,
	balances,
	employee_of,
	is_hr,
	notify_new,
	weekdays,
)


class TimeOffRequest(Document):
	def validate(self):
		hr = is_hr()
		if self.is_new():
			self.status = "Pending"
			self.employee = self.employee or employee_of()
			if self.employee and not hr and self.employee != employee_of():
				frappe.throw(_("You can only request time off for yourself."), frappe.PermissionError)
		else:
			before = self.get_doc_before_save()
			if before and self.status != before.status:
				frappe.throw(_("Use the Approve, Deny or Cancel buttons to change the status."))
			if before and before.status != "Pending" and not hr:
				frappe.throw(_("Only a pending request can be changed. Cancel it and make a new one."))
		if not self.employee:
			frappe.throw(_("Your user is not linked to an active Employee. Ask HR to link it."))

		self.employee_user = frappe.db.get_value("Employee", self.employee, "user_id")
		if getdate(self.to_date) < getdate(self.from_date):
			frappe.throw(_("To date cannot be before From date."))
		if not 0 < flt(self.hours_per_day) <= 24:
			frappe.throw(_("Hours per day must be between 0 and 24."))
		days = weekdays(self.from_date, self.to_date)
		if not days:
			frappe.throw(_("These dates are only a weekend. Pick at least one weekday."))
		self.total_hours = flt(days * flt(self.hours_per_day), 2)
		if self.is_new():
			self.approver = approver_for(self.employee)

		overlap = frappe.db.get_value(self.doctype, {
			"employee": self.employee, "name": ["!=", self.name or ""],
			"status": ["in", ["Pending", "Approved", "Taken"]],
			"from_date": ["<=", self.to_date], "to_date": [">=", self.from_date]}, "name")
		if overlap:
			frappe.throw(_("These dates overlap request {0}.").format(overlap))

		if self.status == "Pending":
			# shortcut: a request crossing Dec 31 counts all its hours in the start year; split if that matters
			left = balances(self.employee, getdate(self.from_date).year)["types"][self.leave_type]["available"]
			if self.total_hours > left:
				frappe.throw(_("You have {0} hrs of {1} left; this request needs {2} hrs.").format(
					left, self.leave_type, self.total_hours))

	def after_insert(self):
		if self.approver:
			# the approver may have no HR role: sharing lets them open and decide this one request
			frappe.share.add_docshare(self.doctype, self.name, self.approver, write=1,
				flags={"ignore_share_permission": True})
		notify_new(self)
