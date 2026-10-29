from erpnext.manufacturing.doctype.job_card.job_card import JobCard


class CMJobCard(JobCard):
	def validate_job_card(self):
		planned_qty = self.for_quantity
		self.for_quantity = 0
		try:
			super().validate_job_card()
		finally:
			self.for_quantity = planned_qty

	def get_time_logs(self, args, doctype, open_job_cards=None):
		if args.get("employee"):
			return []
		return super().get_time_logs(args, doctype, open_job_cards=open_job_cards)

	def get_open_job_cards(self, employee, workstation=None):
		return []
