import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_to_date, get_datetime, now_datetime

# A double-tapped button must not become two punches. Only enforced for portal
# punches — HR correcting history by hand may legitimately need close timestamps.
DEBOUNCE_SECONDS = 60

# Tolerance for a device clock running slightly ahead of the server.
FUTURE_SKEW_MINUTES = 5


class UserCheckin(Document):
	def validate(self):
		self.validate_not_future()
		self.validate_debounce()
		self.validate_alternation()

	def validate_not_future(self):
		if get_datetime(self.time) > add_to_date(now_datetime(), minutes=FUTURE_SKEW_MINUTES):
			frappe.throw(_("A punch cannot be recorded in the future."))

	def validate_debounce(self):
		if self.source != "Portal":
			return

		punch_time = get_datetime(self.time)
		existing = frappe.get_all(
			"User Checkin",
			filters={
				"user": self.user,
				"name": ["!=", self.name or ""],
				"time": [
					"between",
					[
						add_to_date(punch_time, seconds=-DEBOUNCE_SECONDS),
						add_to_date(punch_time, seconds=DEBOUNCE_SECONDS),
					],
				],
			},
			limit=1,
		)
		if existing:
			frappe.throw(
				_("You just punched a moment ago. Please wait a minute before punching again."),
				title=_("Duplicate Punch"),
			)

	def validate_alternation(self):
		"""IN and OUT must alternate relative to the punches on either side.

		Checking both neighbours (rather than only the latest punch) is what lets HR
		insert a forgotten OUT in the middle of history without tripping the rule.
		"""
		previous = self._neighbour("previous")
		if previous and previous.log_type == self.log_type:
			frappe.throw(
				_("The previous punch for {0} at {1} was already {2}.").format(
					frappe.bold(self.user),
					frappe.format(previous.time, {"fieldtype": "Datetime"}),
					frappe.bold(self.log_type),
				),
				title=_("Punches Must Alternate"),
			)

		following = self._neighbour("next")
		if following and following.log_type == self.log_type:
			frappe.throw(
				_("The next punch for {0} at {1} is already {2}.").format(
					frappe.bold(self.user),
					frappe.format(following.time, {"fieldtype": "Datetime"}),
					frappe.bold(self.log_type),
				),
				title=_("Punches Must Alternate"),
			)

	def _neighbour(self, direction):
		operator, order = ("<", "desc") if direction == "previous" else (">", "asc")
		rows = frappe.get_all(
			"User Checkin",
			filters={
				"user": self.user,
				"name": ["!=", self.name or ""],
				"time": [operator, self.time],
			},
			fields=["name", "time", "log_type"],
			order_by=f"time {order}",
			limit=1,
		)
		return rows[0] if rows else None
