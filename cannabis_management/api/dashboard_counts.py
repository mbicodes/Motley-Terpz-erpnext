import frappe


@frappe.whitelist(allow_guest=False)
def get_dashboard_counts():
    """Return all stat counts for the CEO Dashboard in a single call."""

    counts = {}

    for company in ["TSBC Ranch", "Motley Terpz"]:
        key = "tsbc" if company == "TSBC Ranch" else "motley"

        # 1) Pending Orders In Sales Pipeline
        counts[key + "_pending"] = frappe.db.count("Sales Order", filters={
            "docstatus": ["<", 2],
            "company": company,
            "billing_status": ["in", ["Not Billed", "Partly Billed"]]
        })

        # 2) Orders — Need to Schedule
        counts[key + "_need_schedule"] = frappe.db.count("Sales Invoice", filters={
            "docstatus": ["<", 2],
            "company": company,
            "custom_logistic_status": ["not in", ["Scheduled"]]
        })

        # 3) Orders @ Distro / @ Lab
        counts[key + "_at_lab"] = frappe.db.count("Sales Invoice", filters={
            "docstatus": ["<", 2],
            "company": company,
            "custom_logistic_status": "Scheduled",
            "custom_sales_stages": "Ready to Go Out"
        })

        # 4) Orders — Ready for Final Close Out
        counts[key + "_closeout"] = frappe.db.count("Sales Invoice", filters={
            "docstatus": ["<", 2],
            "company": company
        })

    return counts