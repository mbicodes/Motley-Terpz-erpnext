import frappe
from frappe.model.document import Document
from frappe.utils import flt

ENHANCED_THRESHOLD = 20000


class CreditAssessment(Document):
    def validate(self):
        # Lines over $20k require the enhanced assessment flag + MD approval.
        self.enhanced_assessment = 1 if flt(self.recommended_line) > ENHANCED_THRESHOLD else self.enhanced_assessment

        if self.status in ("MD Approved", "Live"):
            missing = []
            if not self.active_license_verified:
                missing.append("active license verified")
            if not self.recommended_line:
                missing.append("recommended line")
            if not self.md_approval:
                missing.append("MD approval (Credit Exception Log)")
            if flt(self.recommended_line) > ENHANCED_THRESHOLD and not self.enhanced_assessment:
                missing.append("enhanced assessment (line over $20,000)")
            if missing:
                frappe.throw("Cannot advance to " + self.status + " — missing: " + ", ".join(missing) + ".")

    def on_update(self):
        if self.status == "Live" and not self.applied_to_profile:
            self.apply_to_profile()

    def apply_to_profile(self):
        from cannabis_management.credit_management.doctype.credit_profile.credit_profile import get_or_create
        profile = get_or_create(self.customer)
        profile.status = "Credit Approved"
        profile.approved_line = self.recommended_line
        profile.term = self.recommended_term
        profile.credit_score = self.credit_score or profile.credit_score
        profile.md_approval_reference = self.md_approval
        profile.save(ignore_permissions=True)
        self.db_set("applied_to_profile", 1)
