import frappe
from frappe.model.document import Document
from frappe.utils import now_datetime


class InventoryVerification(Document):

    def validate(self):
        self._validate_verifier()
        self._calculate_totals()

    def before_submit(self):
        self._validate_verifier()
        self._calculate_totals()
        self._validate_variance_resolved()

    def on_submit(self):
        if self.approved_for_inventory:
            self.db_set("approved_by", frappe.session.user)
            self.db_set("approved_date", now_datetime())

    # ------------------------------------------------------------------

    def _validate_verifier(self):
        """Ensure verifier ≠ wash/press tech on the source batch."""
        source_tech = None
        if self.verification_type == "Bubble Hash" and self.source_batch_ref_wash:
            source_tech = frappe.db.get_value(
                "Wash Batch", self.source_batch_ref_wash, "wash_tech"
            )
        elif self.verification_type == "Rosin" and self.source_batch_ref_press:
            source_tech = frappe.db.get_value(
                "Press Batch", self.source_batch_ref_press, "press_tech"
            )

        if source_tech and self.verified_by == source_tech:
            frappe.throw(
                "The Verifier cannot be the same person who performed the wash/press. "
                "A second person must verify.",
                title="Verification Conflict"
            )

    def _calculate_totals(self):
        sys_total = 0.0
        phys_total = 0.0
        for row in self.metrc_packages or []:
            sys_total += float(row.system_weight_g or 0)
            phys_total += float(row.verified_weight_g or 0)
            row.variance_g = round(float(row.system_weight_g or 0) - float(row.verified_weight_g or 0), 2)

        self.system_total_g = round(sys_total, 2)
        self.physical_total_g = round(phys_total, 2)
        self.variance_g = round(sys_total - phys_total, 2)
        self.variance_pct = round((self.variance_g / sys_total * 100) if sys_total else 0, 2)

    def _validate_variance_resolved(self):
        if abs(float(self.variance_g or 0)) > 0.01 and not self.variance_resolution:
            frappe.throw(
                "A variance exists between system and physical weight. "
                "Please provide a variance resolution before submitting.",
                title="Variance Not Resolved"
            )
