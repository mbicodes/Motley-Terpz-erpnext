import frappe
from frappe.model.document import Document
from frappe.utils import flt


class FarmProductionBatch(Document):
    def recalculate_rollups(self):
        propagation_cost = flt(
            frappe.db.sql(
                """
                SELECT COALESCE(SUM(total_labor_cost), 0)
                FROM `tabCloning Batch`
                WHERE linked_harvest = %s AND docstatus = 1
                """,
                (self.name,),
            )[0][0]
        )

        labor_cost = 0
        if frappe.db.exists("DocType", "Farm Labor Session"):
            labor_cost = flt(
                frappe.db.sql(
                    """
                    SELECT COALESCE(SUM(
                        CASE
                            WHEN task_type = 'Bucking' THEN total_assembly_cost
                            ELSE total_cost
                        END
                    ), 0)
                    FROM `tabFarm Labor Session`
                    WHERE linked_harvest = %s AND docstatus = 1
                    """,
                    (self.name,),
                )[0][0]
            )

        plant_batch_input_costs = 0
        if frappe.db.exists("DocType", "Plant Batch"):
            plant_batch_input_costs = flt(
                frappe.db.sql(
                    """
                    SELECT COALESCE(SUM(total_input_cost), 0)
                    FROM `tabPlant Batch`
                    WHERE linked_harvest = %s AND docstatus = 1
                    """,
                    (self.name,),
                )[0][0]
            )

        revenue_to_date = flt(
            frappe.db.sql(
                """
                SELECT COALESCE(SUM(grand_total), 0)
                FROM `tabSales Invoice`
                WHERE custom_linked_harvest = %s AND docstatus = 1
                """,
                (self.name,),
            )[0][0]
        )

        self.propagation_cost = propagation_cost
        self.labor_cost = labor_cost
        self.costs_to_date = propagation_cost + labor_cost + plant_batch_input_costs
        self.revenue_to_date = revenue_to_date
        self.gross_profit = revenue_to_date - self.costs_to_date
        self.net_to_date = self.gross_profit

        self.db_update()


def update_linked_harvest(doc, method=None):
    harvest_name = doc.get("linked_harvest") or doc.get("custom_linked_harvest")
    if not harvest_name:
        return

    frappe.get_doc("Farm Production Batch", harvest_name).recalculate_rollups()
