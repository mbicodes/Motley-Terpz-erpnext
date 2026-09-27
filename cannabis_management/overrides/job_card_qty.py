"""Job Card overrides.

Let a Job Card submit when the run did not land on the planned quantity.

Core refuses to submit a Job Card unless Total Completed Qty (plus process
loss) equals Qty to Manufacture exactly:

    The Total Completed Qty (718.0) must be equal to Qty to Manufacture (680.388)

A wash or press run is measured, not dispensed -- the bags come off the line
at whatever they weigh. The planned figure is the BOM's expectation, and the
operator records what actually came out, over or under. Blocking the submit
only pushes people into editing the plan to match the result, which loses the
variance that the yield reporting is built on.

Every other check in core's validate_job_card stays: a stopped Work Order is
still refused, time logs are still required, and Manufacturing Settings'
"enforce time logs" is still honoured.

Let an employee run timers on several operations at once.

Core refuses a timer whose employee already has an overlapping time log on
another Job Card, or who "is currently working on another workstation".
Operators here start one operation and move on to the next while the first
is still running, so neither check applies to employee time logs. The
Manufacturing Process page still refuses starting the same operation twice.
"""

from erpnext.manufacturing.doctype.job_card.job_card import JobCard


class CMJobCard(JobCard):
	def validate_job_card(self):
		"""Core reads for_quantity in this method for one purpose only -- the
		equality check -- and guards it with `if self.for_quantity`. Blanking
		the field for the duration skips exactly that check and leaves the
		rest of the method running unmodified, so it keeps working when core
		changes the checks around it. The value is put back before anything
		else can see it; this runs in on_submit, after the row is written, so
		nothing persists the blank."""
		planned_qty = self.for_quantity
		self.for_quantity = 0
		try:
			super().validate_job_card()
		finally:
			self.for_quantity = planned_qty

	def get_time_logs(self, args, doctype, open_job_cards=None):
		"""An employee may run timers on several operations at once, so their
		own time logs on other Job Cards never count as an overlap. Without an
		employee the core workstation-capacity check still applies."""
		if args.get("employee"):
			return []
		return super().get_time_logs(args, doctype, open_job_cards=open_job_cards)

	def get_open_job_cards(self, employee, workstation=None):
		"""Core uses this only to refuse an employee who "is currently working
		on another workstation"; working on several at once is allowed here."""
		return []
