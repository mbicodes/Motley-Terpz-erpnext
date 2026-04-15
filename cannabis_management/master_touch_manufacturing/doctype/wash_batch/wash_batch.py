import frappe
from frappe.model.document import Document
from cannabis_management.master_touch_manufacturing.utils.slack import (
    alert_wash_batch_submitted,
    alert_low_yield,
)

BUBBLE_YIELD_THRESHOLD_PCT = 2.5


class WashBatch(Document):

    def validate(self):
        self._calculate_yield()
        self._check_yield_threshold()

    def before_submit(self):
        self._calculate_yield()
        self._check_yield_threshold()

    def on_submit(self):
        self._notify_slack()

    # ------------------------------------------------------------------

    def _calculate_yield(self):
        total = sum(flt(row.grams_collected) for row in (self.wash_details or []))
        self.total_bubble_yield_g = round(total, 2)
        ff_g = flt(self.ff_input_g)
        self.yield_pct = round((total / ff_g * 100) if ff_g else 0, 2)

    def _check_yield_threshold(self):
        if not self.yield_pct:
            return
        if self.yield_pct < BUBBLE_YIELD_THRESHOLD_PCT:
            if not self.supervisor_approved:
                frappe.throw(
                    f"Wash yield is {self.yield_pct:.2f}% — below the minimum {BUBBLE_YIELD_THRESHOLD_PCT}%. "
                    f"A Lab Supervisor must tick 'Supervisor Approved' and provide a reason before submitting.",
                    title="Low Yield Block"
                )
            if not self.yield_variance_reason:
                frappe.throw(
                    "Please provide a reason for the low yield in 'Low Yield Reason' field.",
                    title="Low Yield Reason Required"
                )

    def _notify_slack(self):
        try:
            lbs = flt(self.ff_input_g) / 453.592
            pbg = frappe.db.get_value(
                "Production Batch Group", self.production_batch_group, "batch_name"
            ) or self.production_batch_group
            alert_wash_batch_submitted(self.name, pbg, round(lbs, 2))

            if self.yield_pct and self.yield_pct < BUBBLE_YIELD_THRESHOLD_PCT:
                alert_low_yield(self.name, "Wash Batch", self.yield_pct, BUBBLE_YIELD_THRESHOLD_PCT)
        except Exception:
            pass  # Never block submission on Slack failure


def flt(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
