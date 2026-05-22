"""
Patch: create all Motley Terpz custom fields on CRM Lead.
Safe to re-run — skips fields that already exist.
"""
import frappe


def execute():
    if not frappe.db.exists("DocType", "CRM Lead"):
        frappe.logger().info("[crm_fields] CRM Lead doctype not found — skipping (install Frappe CRM first)")
        return
    _create_fields()
    frappe.db.commit()


def _cf(fieldname, fieldtype, label, **kwargs):
    return {"fieldname": fieldname, "fieldtype": fieldtype, "label": label, **kwargs}


def _create_fields():
    dt = "CRM Lead"

    fields = [
        # ── Tab ─────────────────────────────────────────────────────────────
        _cf("custom_motley_tab", "Tab Break", "Motley Terpz",
            insert_after="net_total"),

        # ── Section: Account Info ────────────────────────────────────────────
        _cf("custom_account_info_section", "Section Break", "Account Info",
            insert_after="custom_motley_tab"),

        _cf("custom_relationship_tier", "Select", "Relationship Tier",
            options="AAA\nAA\nA\nFriends & Family\nWIP\nLead",
            reqd=1, in_list_view=1, in_standard_filter=1,
            insert_after="custom_account_info_section"),

        _cf("custom_pipeline", "Select", "Pipeline",
            options="\nFresh Frozen\nRosin / Solventless\nRetail / Distro\nTolling",
            in_list_view=1, in_standard_filter=1,
            insert_after="custom_relationship_tier"),

        _cf("custom_account_owner", "Link", "Account Owner",
            options="User", in_standard_filter=1,
            insert_after="custom_pipeline"),

        _cf("custom_buyer_activity", "Select", "Buyer Activity",
            options="\nConsistent\nInconsistent\nDeposit\nNever Purchased",
            insert_after="custom_account_owner"),

        _cf("custom_col_break_flags", "Column Break", "",
            insert_after="custom_buyer_activity"),

        _cf("custom_cod_only", "Check", "COD Only",
            insert_after="custom_col_break_flags"),

        _cf("custom_no_ocal", "Check", "No-OCAL",
            insert_after="custom_cod_only"),

        _cf("custom_single_source", "Check", "Single Source",
            insert_after="custom_no_ocal"),

        _cf("custom_special_flags", "Small Text", "Special Flags / Notes",
            insert_after="custom_single_source"),

        _cf("custom_clickup_link", "Data", "ClickUp Link",
            insert_after="custom_special_flags"),

        _cf("custom_last_contact_date", "Date", "Last Contact Date",
            insert_after="custom_clickup_link"),

        _cf("custom_next_followup_date", "Date", "Next Follow-up Date",
            insert_after="custom_last_contact_date"),

        # ── Section: Monthly Demand ──────────────────────────────────────────
        _cf("custom_demand_section", "Section Break", "Monthly Demand (lbs)",
            insert_after="custom_next_followup_date"),

        _cf("custom_demand_fresh_frozen", "Float", "Fresh Frozen",
            insert_after="custom_demand_section"),

        _cf("custom_demand_rosin", "Float", "Rosin",
            insert_after="custom_demand_fresh_frozen"),

        _cf("custom_demand_vrr", "Float", "VRR",
            insert_after="custom_demand_rosin"),

        _cf("custom_demand_food_grade", "Float", "Food Grade",
            insert_after="custom_demand_vrr"),

        _cf("custom_demand_bubble", "Float", "Bubble Hash",
            insert_after="custom_demand_food_grade"),

        _cf("custom_demand_col_break", "Column Break", "",
            insert_after="custom_demand_bubble"),

        _cf("custom_demand_cpg", "Float", "CPG",
            insert_after="custom_demand_col_break"),

        _cf("custom_demand_bho", "Float", "BHO",
            insert_after="custom_demand_cpg"),

        _cf("custom_demand_thca", "Float", "THCA",
            insert_after="custom_demand_bho"),

        _cf("custom_demand_trim", "Float", "Trim",
            insert_after="custom_demand_thca"),

        _cf("custom_demand_flower", "Float", "Flower",
            insert_after="custom_demand_trim"),

        # ── Section: ERPNext Live Data ───────────────────────────────────────
        _cf("custom_erpnext_section", "Section Break", "ERPNext — Live Data",
            collapsible=1, insert_after="custom_demand_flower"),

        _cf("custom_erp_customer", "Link", "ERPNext Customer",
            options="Customer", insert_after="custom_erpnext_section"),

        _cf("custom_ar_balance", "Currency", "AR Balance",
            read_only=1, insert_after="custom_erp_customer"),

        _cf("custom_ar_aging_days", "Int", "AR Aging (days)",
            read_only=1, insert_after="custom_ar_balance"),

        _cf("custom_ar_status", "Select", "AR Status",
            options="\nClean\nWatch\nOverdue\nBlocked",
            read_only=1, in_list_view=1, in_standard_filter=1,
            insert_after="custom_ar_aging_days"),

        _cf("custom_erp_col_break", "Column Break", "",
            insert_after="custom_ar_status"),

        _cf("custom_last_invoice_date", "Date", "Last Invoice Date",
            read_only=1, insert_after="custom_erp_col_break"),

        _cf("custom_last_invoice_amount", "Currency", "Last Invoice Amount",
            read_only=1, insert_after="custom_last_invoice_date"),

        _cf("custom_last_payment_date", "Date", "Last Payment Date",
            read_only=1, insert_after="custom_last_invoice_amount"),

        _cf("custom_mtd_revenue", "Currency", "MTD Revenue",
            read_only=1, insert_after="custom_last_payment_date"),

        _cf("custom_trailing_8w_revenue", "Currency", "8-Week Trailing Revenue",
            read_only=1, insert_after="custom_mtd_revenue"),

        _cf("custom_payment_terms", "Data", "Payment Terms",
            read_only=1, insert_after="custom_trailing_8w_revenue"),

        _cf("custom_last_sync", "Datetime", "Last Synced",
            read_only=1, insert_after="custom_payment_terms"),
    ]

    for f in fields:
        if frappe.db.exists("Custom Field", {"dt": dt, "fieldname": f["fieldname"]}):
            continue
        doc = frappe.get_doc({
            "doctype": "Custom Field",
            "dt": dt,
            **f,
        })
        doc.insert(ignore_permissions=True)
        frappe.logger().info(f"[crm_fields] created {f['fieldname']}")
