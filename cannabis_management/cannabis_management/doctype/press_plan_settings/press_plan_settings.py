import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class PressPlanSettings(Document):
    def validate(self):
        from cannabis_management.cannabis_management.doctype.press_production_plan.press_production_plan import SLOTS, norm

        if len(self.micron_groups) > len(SLOTS):
            frappe.throw(_("The press plan tracks at most {0} micron groups.").format(len(SLOTS)))
        seen = set()
        for g in self.micron_groups:
            k = norm(g.micron_label)
            if not k:
                frappe.throw(_("Micron Groups row {0}: enter the micron.").format(g.idx))
            if k in seen:
                frappe.throw(_("Micron Groups row {0}: {1} is listed twice.").format(g.idx, g.micron_label))
            seen.add(k)
            if not 0 <= flt(g.expected_yield) <= 100:
                frappe.throw(_("Micron Groups row {0}: the expected yield must be between 0% and 100%.").format(g.idx))
        if self.aging_warning_days is not None and self.aging_warning_days < 0:
            frappe.throw(_("Aging Warning cannot be negative."))
