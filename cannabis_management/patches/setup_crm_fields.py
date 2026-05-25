"""
Patch: create / update all Motley Terpz custom fields on CRM Lead.
Safe to re-run — skips fields that already exist, updates options/labels
on existing fields via _update_fields().
"""
import frappe


def execute():
    if not frappe.db.exists("DocType", "CRM Lead"):
        frappe.logger().info("[crm_fields] CRM Lead doctype not found — skipping (install Frappe CRM first)")
        return
    _create_fields()
    _update_fields()
    frappe.db.commit()


# ── Helpers ───────────────────────────────────────────────────────────────────

def _cf(fieldname, fieldtype, label, **kwargs):
    return {"fieldname": fieldname, "fieldtype": fieldtype, "label": label, **kwargs}


def _update_cf(fieldname, updates):
    name = frappe.db.get_value("Custom Field", {"dt": "CRM Lead", "fieldname": fieldname}, "name")
    if name:
        frappe.db.set_value("Custom Field", name, updates)


# ── Field definitions ─────────────────────────────────────────────────────────

def _create_fields():
    dt = "CRM Lead"

    fields = [
        # ── Tab ──────────────────────────────────────────────────────────────
        _cf("custom_motley_tab", "Tab Break", "Motley Terpz",
            insert_after="net_total"),

        # ── SECTION A: Identity & Ownership ──────────────────────────────────
        _cf("custom_account_info_section", "Section Break", "Identity & Ownership",
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

        _cf("custom_company", "Select", "Company",
            options="\nTSBC Ranch\nMotley Terpz\nBoth",
            in_standard_filter=1,
            insert_after="custom_account_owner"),

        _cf("custom_revenue_size", "Select", "Revenue Size",
            options="\n$25M+\n$5M+\n$1M+\n$500K+\n$100K+\n<$50K\nUnknown",
            insert_after="custom_company"),

        # ── SECTION B: Activity & Behavior ───────────────────────────────────
        _cf("custom_section_activity", "Section Break", "Activity & Behavior",
            insert_after="custom_revenue_size"),

        _cf("custom_buyer_activity", "Select", "Buyer Activity",
            options="\nConsistent\nInconsistent\nDeposit\nNever Purchased\nCollab\nHave not contacted",
            insert_after="custom_section_activity"),

        _cf("custom_last_contact_date", "Date", "Last Contact Date",
            insert_after="custom_buyer_activity"),

        _cf("custom_next_followup_date", "Date", "Next Follow-up Date",
            insert_after="custom_last_contact_date"),

        _cf("custom_notes", "Long Text", "Notes",
            insert_after="custom_next_followup_date"),

        # ── SECTION C: Flags & Special Handling ──────────────────────────────
        _cf("custom_section_flags", "Section Break", "Flags & Special Handling",
            insert_after="custom_notes"),

        _cf("custom_single_source", "Check", "Single Source",
            insert_after="custom_section_flags"),

        _cf("custom_cod_only", "Check", "COD Only",
            insert_after="custom_single_source"),

        _cf("custom_no_ocal", "Check", "No-OCAL",
            insert_after="custom_cod_only"),

        _cf("custom_col_break_flags", "Column Break", "",
            insert_after="custom_no_ocal"),

        _cf("custom_col_break_flags2", "Column Break", "",
            insert_after="custom_col_break_flags"),

        _cf("custom_account_flags", "Small Text", "Account Flags",
            description="Comma-separated: No-OCAL, COD Only, Custom QC Process, Single Source, Do Not Contact",
            insert_after="custom_col_break_flags2"),

        _cf("custom_clickup_link", "Data", "ClickUp Link",
            insert_after="custom_account_flags"),

        _cf("custom_slack_channel", "Data", "Slack Channel",
            insert_after="custom_clickup_link"),

        # ── SECTION D: Monthly Demand (lbs) ──────────────────────────────────
        _cf("custom_demand_section", "Section Break", "Monthly Demand (lbs)",
            collapsible=1, insert_after="custom_slack_channel"),

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

        _cf("custom_demand_bho", "Float", "BHO / Live Resin",
            insert_after="custom_demand_cpg"),

        _cf("custom_demand_thca", "Float", "THCA",
            insert_after="custom_demand_bho"),

        _cf("custom_demand_trim", "Float", "Trim / Biomass",
            insert_after="custom_demand_thca"),

        _cf("custom_demand_flower", "Float", "Flower / Pre-rolls",
            insert_after="custom_demand_trim"),

        _cf("custom_demand_other", "Long Text", "Other Demand Notes",
            insert_after="custom_demand_flower"),

        # ── SECTION E: ERPNext — Live Data ────────────────────────────────────
        _cf("custom_erpnext_section", "Section Break", "ERPNext — Live Data",
            collapsible=1, insert_after="custom_demand_other"),

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

        _cf("custom_cod_flag", "Check", "COD Flag",
            read_only=1,
            description="Auto-set from Payment Terms nightly",
            insert_after="custom_ar_status"),

        _cf("custom_erp_col_break", "Column Break", "",
            insert_after="custom_cod_flag"),

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


# ── Update existing fields ────────────────────────────────────────────────────

def _update_fields():
    # Rename section "Account Info" → "Identity & Ownership"
    _update_cf("custom_account_info_section", {"label": "Identity & Ownership"})

    # Update buyer activity options to include Collab + Have not contacted
    _update_cf("custom_buyer_activity", {
        "options": "\nConsistent\nInconsistent\nDeposit\nNever Purchased\nCollab\nHave not contacted",
    })

    # Update demand field labels
    _update_cf("custom_demand_bho",    {"label": "BHO / Live Resin"})
    _update_cf("custom_demand_trim",   {"label": "Trim / Biomass"})
    _update_cf("custom_demand_flower", {"label": "Flower / Pre-rolls"})

    # Rename legacy special flags field
    _update_cf("custom_special_flags", {"label": "Internal Notes"})

    # Reposition existing fields
    _update_cf("custom_buyer_activity",      {"insert_after": "custom_section_activity"})
    _update_cf("custom_last_contact_date",   {"insert_after": "custom_buyer_activity"})
    _update_cf("custom_next_followup_date",  {"insert_after": "custom_last_contact_date"})
    _update_cf("custom_single_source",       {"insert_after": "custom_section_flags"})
    _update_cf("custom_cod_only",            {"insert_after": "custom_single_source"})
    _update_cf("custom_no_ocal",             {"insert_after": "custom_cod_only"})
    _update_cf("custom_col_break_flags",     {"insert_after": "custom_no_ocal"})
    _update_cf("custom_clickup_link",        {"insert_after": "custom_account_flags"})
