import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import cint, flt

from cannabis_management.farm_reports import rules


class FarmDailyReport(Document):
	def validate(self):
		rules.stamp_new(self)
		rules.block_duplicate(self)

		for section in ("left", "middle", "right"):
			rules.clear_unless(self, f"{section}_section_ipm", "Yes", f"{section}_ipm_mixture_details")
		rules.clear_unless(self, "scouted_for_males", "Yes", "males_found")
		rules.clear_unless(self, "males_found", "Yes", "male_photos")
		rules.clear_unless(self, "scouted_for_males", "No", "planned_scouting_date")
		rules.clear_unless(self, "weeds_under_control", "No", "weed_control_plan_date", "weed_control_plan_notes")
		rules.check_not_before_report_date(self, "planned_scouting_date", "weed_control_plan_date")

		self.validate_labor()

	def before_submit(self):
		rules.require_male_photos(self)

	def validate_labor(self):
		if self.flc_workers_on_farm != "Yes":
			self.set("flc_labor", [])
			self.set("activities", [])
			self.total_laborers = 0
			return

		seen = set()
		total = 0
		for row in self.flc_labor:
			if row.flc in seen:
				frappe.throw(_("{0} is listed more than once in FLC Labor.").format(row.flc))
			seen.add(row.flc)
			if cint(row.no_of_laborers) < 1:
				frappe.throw(_("FLC Labor row {0} needs at least 1 laborer.").format(row.idx))
			total += cint(row.no_of_laborers)
		self.total_laborers = total

		assigned = 0
		for row in self.activities:
			if cint(row.no_of_people) < 1:
				frappe.throw(_("Activities row {0} needs at least 1 person.").format(row.idx))
			if flt(row.quantity_completed) < 0:
				frappe.throw(_("Activities row {0} cannot have a negative quantity.").format(row.idx))
			row.uom = row.uom or "Plants"
			row.output_per_person = round(flt(row.quantity_completed) / cint(row.no_of_people), 2)
			assigned += cint(row.no_of_people)
		if assigned > total:
			frappe.throw(
				_("Activities have {0} people but only {1} laborers were on the farm.").format(assigned, total)
			)
