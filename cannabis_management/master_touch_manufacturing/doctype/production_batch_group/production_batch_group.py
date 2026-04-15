import frappe
from frappe.model.document import Document
from frappe.utils import flt

LBS_TO_GRAMS = 453.592
BUBBLE_YIELD_THRESHOLD_PCT = 2.5  # minimum acceptable yield %


class ProductionBatchGroup(Document):

    def before_save(self):
        self._convert_lbs_to_grams()
        self._rollup_yields()
        self._rollup_costs()

    def _convert_lbs_to_grams(self):
        if self.ff_weight_received_lbs:
            self.ff_weight_received_g = round(self.ff_weight_received_lbs * LBS_TO_GRAMS, 2)

    def _rollup_yields(self):
        """
        Sum yields from linked Wash Batches and Press Batches.
        Note: wash_batches and press_batches child tables here are link tables
        (they store references). We query the actual Wash/Press Batch docs for totals.
        """
        bubble_g = 0.0
        rosin_g = 0.0

        wash_batches = frappe.get_all(
            "Wash Batch",
            filters={"production_batch_group": self.name, "docstatus": 1},
            fields=["total_bubble_yield_g"],
        )
        for wb in wash_batches:
            bubble_g += flt(wb.total_bubble_yield_g)

        press_batches = frappe.get_all(
            "Press Batch",
            filters={"production_batch_group": self.name, "docstatus": 1},
            fields=["total_rosin_yield_g"],
        )
        for pb in press_batches:
            rosin_g += flt(pb.total_rosin_yield_g)

        self.total_bubble_yield_g = round(bubble_g, 2)
        self.total_rosin_yield_g = round(rosin_g, 2)

        ff_g = self.ff_weight_received_g or 0
        self.ff_to_bubble_yield_pct = round((bubble_g / ff_g * 100) if ff_g else 0, 2)
        self.bubble_to_rosin_yield_pct = round((rosin_g / bubble_g * 100) if bubble_g else 0, 2)

    def _rollup_costs(self):
        """Pull costs from the linked Work Order once it has actual costs."""
        if not self.work_order_ref:
            return
        wo = frappe.db.get_value(
            "Work Order",
            self.work_order_ref,
            ["actual_operating_cost", "total_operating_cost"],
            as_dict=True,
        )
        if wo:
            self.total_overhead_cost = flt(wo.actual_operating_cost)


