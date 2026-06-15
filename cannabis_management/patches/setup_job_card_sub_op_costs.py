"""
Patch: Add custom fields to Job Card Time Log and Job Card for per-sub-operation
operating cost tracking.
Safe to re-run.
"""
import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields


def execute():
    create_custom_fields({
        "Job Card Time Log": [
            {
                "fieldname": "custom_workstation",
                "fieldtype": "Link",
                "options": "Workstation",
                "label": "Workstation",
                "read_only": 1,
                "in_list_view": 1,
                "insert_after": "operation",
                "columns": 2,
            },
            {
                "fieldname": "custom_hour_rate",
                "fieldtype": "Currency",
                "label": "Rate / Hr",
                "read_only": 1,
                "in_list_view": 1,
                "insert_after": "custom_workstation",
                "columns": 2,
            },
            {
                "fieldname": "custom_sub_op_cost",
                "fieldtype": "Currency",
                "label": "Sub-Op Cost",
                "read_only": 1,
                "in_list_view": 1,
                "insert_after": "custom_hour_rate",
                "columns": 2,
            },
        ],
        "Job Card": [
            {
                "fieldname": "custom_sub_op_cost_section",
                "fieldtype": "Section Break",
                "label": "Sub-Operation Costs",
                "insert_after": "total_completed_qty",
                "collapsible": 1,
            },
            {
                "fieldname": "custom_sub_op_total_cost",
                "fieldtype": "Currency",
                "label": "Total Sub-Op Operating Cost",
                "read_only": 1,
                "bold": 1,
                "insert_after": "custom_sub_op_cost_section",
            },
        ],
    }, ignore_validate=True)
    frappe.db.commit()
