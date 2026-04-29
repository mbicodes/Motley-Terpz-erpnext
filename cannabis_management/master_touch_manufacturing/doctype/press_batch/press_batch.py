import frappe
from frappe.model.document import Document
from cannabis_management.master_touch_manufacturing.utils.slack import (
    alert_press_batch_submitted,
    alert_low_yield,
)

ROSIN_YIELD_THRESHOLD_PCT = 10.0  # minimum acceptable rosin yield from bubble hash


class PressBatch(Document):

    def validate(self):
        self._calculate_yield()

    def before_submit(self):
        self._calculate_yield()
        self._check_discrepancy()
        self._check_yield_threshold()

    def on_submit(self):
        self._notify_slack()

    # ------------------------------------------------------------------

    def _calculate_yield(self):
        total = sum(flt(row.grams_rosin) for row in (self.press_details or []))
        self.total_rosin_yield_g = round(total, 2)
        bh_g = flt(self.bubble_hash_input_g)
        self.yield_pct = round((total / bh_g * 100) if bh_g else 0, 2)
        self.discrepancy_g = round(bh_g - total, 2)

    def _check_discrepancy(self):
        if abs(flt(self.discrepancy_g)) > 0.01:
            if not self.discrepancy_resolved:
                frappe.throw(
                    f"Discrepancy of {self.discrepancy_g:.2f}g — please tick 'Discrepancy Resolved' "
                    "and add notes before submitting.",
                    title="Discrepancy Not Resolved"
                )

    def _check_yield_threshold(self):
        if not self.yield_pct:
            return
        if self.yield_pct < ROSIN_YIELD_THRESHOLD_PCT:
            if not self.supervisor_approved:
                frappe.throw(
                    f"Press yield is {self.yield_pct:.2f}% — below the minimum {ROSIN_YIELD_THRESHOLD_PCT}%. "
                    "A Lab Supervisor must approve before submitting.",
                    title="Low Yield Block"
                )
            if not self.yield_variance_reason:
                frappe.throw(
                    "Please provide a reason for the low yield.",
                    title="Low Yield Reason Required"
                )

    def _notify_slack(self):
        try:
            alert_press_batch_submitted(
                self.name,
                str(self.strain_name),
                flt(self.bubble_hash_input_g)
            )
            if self.yield_pct and self.yield_pct < ROSIN_YIELD_THRESHOLD_PCT:
                alert_low_yield(self.name, "Press Batch", self.yield_pct, ROSIN_YIELD_THRESHOLD_PCT)
        except Exception:
            pass


def flt(value):
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0
