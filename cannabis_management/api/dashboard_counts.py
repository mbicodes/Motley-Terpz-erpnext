import frappe


@frappe.whitelist(allow_guest=False)
def get_dashboard_counts():
    counts = {}

    for company in ["TSBC Ranch", "Motley Terpz"]:
        key = "tsbc" if company == "TSBC Ranch" else "motley"

        counts[key + "_pending"] = frappe.db.count("Sales Order", filters={
            "docstatus": ["<", 2],
            "company": company,
            "billing_status": ["in", ["Not Billed", "Partly Billed"]]
        })

        counts[key + "_need_schedule"] = frappe.db.count("Sales Invoice", filters={
            "docstatus": ["<", 2],
            "company": company,
            "custom_logistic_status": ["not in", ["Scheduled"]]
        })

        counts[key + "_at_lab"] = frappe.db.count("Sales Invoice", filters={
            "docstatus": ["<", 2],
            "company": company,
            "custom_logistic_status": "Scheduled",
            "custom_sales_stages": "Ready to Go Out"
        })

        counts[key + "_closeout"] = frappe.db.count("Sales Invoice", filters={
            "docstatus": ["<", 2],
            "company": company
        })

    return counts
