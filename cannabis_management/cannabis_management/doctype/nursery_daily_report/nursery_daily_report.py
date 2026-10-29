from frappe.model.document import Document

from cannabis_management.farm_reports import rules


class NurseryDailyReport(Document):
	def validate(self):
		rules.stamp_new(self)
		rules.block_duplicate(self)

		rules.clear_unless(self, "sprays_applied", "Yes", "spray_mixture_details")
		rules.clear_unless(self, "scouted_for_males", "Yes", "males_found")
		rules.clear_unless(self, "males_found", "Yes", "male_photos")
		rules.clear_unless(self, "scouted_for_males", "No", "next_scouting_date")
		rules.clear_unless(
			self, "plants_tagged_per_metrc", "No", "pending_tagging_actions", "promised_completion_date"
		)
		rules.check_not_before_report_date(self, "next_scouting_date", "promised_completion_date")

	def before_submit(self):
		rules.require_male_photos(self)
