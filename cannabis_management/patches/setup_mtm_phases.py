"""
MTM Setup Patch — Phases 10, 11, 15

Run once via bench migrate (registered in patches.txt).
Also callable directly:
    bench --site erp.alltechvirtual.com execute \
        "cannabis_management.patches.setup_mtm_phases.execute"

Creates:
    Phase 10 — Quality Inspection Templates (Bubble Hash QI, Rosin QI)
    Phase 11 — WIP sub-accounts (1411–1414) + Employee custom fields
               + Item Group default account mappings
    Phase 15 — TSBC Ranch customer record + Toll Service item in Motley Terpz
"""

import frappe
from frappe.utils import today


def execute():
    frappe.flags.in_patch = True
    try:
        _create_qi_templates()
        _create_batch_cost_field()
        _create_wip_accounts()
        _create_employee_custom_fields()
        _map_item_group_accounts()
        _setup_intercompany_customers()
        _create_si_pbg_field()
        _create_toll_service_item()
        frappe.db.commit()
        print("MTM setup patch completed successfully.")
    finally:
        frappe.flags.in_patch = False


# ── Phase 10: Quality Inspection Templates ─────────────────────────────────────

def _create_qi_templates():
    """Create Bubble Hash QI and Rosin QI templates."""

    bubble_readings = [
        {"specification": "Net Weight (g)",   "min_value": 0,   "max_value": 9999, "numeric": 1, "value": ""},
        {"specification": "Moisture Content", "min_value": 0,   "max_value": 15,   "numeric": 1, "value": ""},
        {"specification": "Color Grade",      "min_value": 0,   "max_value": 0,    "numeric": 0, "value": ""},
        {"specification": "Contamination",    "min_value": 0,   "max_value": 0,    "numeric": 0, "value": "None"},
        {"specification": "METRC Tag Match",  "min_value": 0,   "max_value": 0,    "numeric": 0, "value": ""},
    ]

    rosin_readings = [
        {"specification": "Net Weight (g)",   "min_value": 0,   "max_value": 9999, "numeric": 1, "value": ""},
        {"specification": "Color Grade",      "min_value": 0,   "max_value": 0,    "numeric": 0, "value": ""},
        {"specification": "Consistency",      "min_value": 0,   "max_value": 0,    "numeric": 0, "value": ""},
        {"specification": "Terpene Aroma",    "min_value": 0,   "max_value": 0,    "numeric": 0, "value": "Acceptable"},
        {"specification": "METRC Tag Match",  "min_value": 0,   "max_value": 0,    "numeric": 0, "value": ""},
    ]

    for template_name, readings in [
        ("Bubble Hash QI", bubble_readings),
        ("Rosin QI",        rosin_readings),
    ]:
        if frappe.db.exists("Quality Inspection Template", template_name):
            print(f"  -- QI Template '{template_name}' already exists")
            continue

        tmpl = frappe.new_doc("Quality Inspection Template")
        tmpl.quality_inspection_template_name = template_name
        for r in readings:
            tmpl.append("item_quality_inspection_parameter", r)
        tmpl.insert(ignore_permissions=True)
        print(f"  +  QI Template '{template_name}' created")


# ── Phase 11: WIP Accounts ─────────────────────────────────────────────────────

def _create_wip_accounts():
    """Create MTM-specific WIP sub-accounts under Stock Assets."""
    company = "Motley Terpz"
    abbr = "MT"
    parent = f"Stock Assets - {abbr}"

    accounts = [
        ("1411", "WIP - Fresh Frozen Processing"),
        ("1412", "WIP - Bubble Hash Production"),
        ("1413", "WIP - Rosin Production"),
        ("1414", "WIP - Toll Manufacturing"),
    ]

    for number, label in accounts:
        # ERPNext builds name as: "{account_number} - {account_name} - {abbr}"
        full_name = f"{number} - {label} - {abbr}"
        if frappe.db.exists("Account", full_name):
            print(f"  -- Account '{full_name}' already exists")
            continue

        acc = frappe.new_doc("Account")
        acc.account_name = label          # number is stored separately; ERPNext prepends it
        acc.account_number = number
        acc.parent_account = parent
        acc.company = company
        acc.account_type = "Stock"
        acc.root_type = "Asset"
        acc.is_group = 0
        acc.insert(ignore_permissions=True)
        print(f"  +  Account '{full_name}' created")


# ── Phase 11: Employee Custom Fields ──────────────────────────────────────────

def _create_batch_cost_field():
    """Add custom_cost_per_gram to Batch for Phase 9 cost stamping."""
    if frappe.db.exists("Custom Field", {"dt": "Batch", "fieldname": "custom_cost_per_gram"}):
        print("  -- Custom Field Batch.custom_cost_per_gram already exists")
        return
    cf = frappe.new_doc("Custom Field")
    cf.dt = "Batch"
    cf.fieldname = "custom_cost_per_gram"
    cf.label = "Cost per Gram"
    cf.fieldtype = "Currency"
    cf.insert_after = "custom_net_weight_g"
    cf.read_only = 1
    cf.insert(ignore_permissions=True)
    print("  +  Custom Field Batch.custom_cost_per_gram created")


def _create_employee_custom_fields():
    """Add default_workstation and hourly_wage_rate to Employee."""
    fields = [
        {
            "fieldname": "custom_default_workstation",
            "label": "Default Workstation",
            "fieldtype": "Link",
            "options": "Workstation",
            "insert_after": "department",
        },
        {
            "fieldname": "custom_hourly_wage_rate",
            "label": "Hourly Wage Rate",
            "fieldtype": "Currency",
            "insert_after": "custom_default_workstation",
        },
    ]

    for f in fields:
        if frappe.db.exists("Custom Field", {"dt": "Employee", "fieldname": f["fieldname"]}):
            print(f"  -- Custom Field Employee.{f['fieldname']} already exists")
            continue

        cf = frappe.new_doc("Custom Field")
        cf.dt = "Employee"
        cf.fieldname = f["fieldname"]
        cf.label = f["label"]
        cf.fieldtype = f["fieldtype"]
        cf.options = f.get("options", "")
        cf.insert_after = f.get("insert_after", "")
        cf.insert(ignore_permissions=True)
        print(f"  +  Custom Field Employee.{f['fieldname']} created")


# ── Phase 11: Item Group → Account Mappings ───────────────────────────────────

_GROUP_ACCOUNT_MAP = {
    "Fresh Frozen":        "1411 - WIP - Fresh Frozen Processing - MT",
    "Fresh Frozen - SHO":  "1411 - WIP - Fresh Frozen Processing - MT",
    "Fresh Frozen - BHO":  "1411 - WIP - Fresh Frozen Processing - MT",
    "Primes":              "1412 - WIP - Bubble Hash Production - MT",
    "Subprimes":           "1412 - WIP - Bubble Hash Production - MT",
    "Full Spec":           "1412 - WIP - Bubble Hash Production - MT",
    "Food Grade":          "1412 - WIP - Bubble Hash Production - MT",
    "Rosin":               "1413 - WIP - Rosin Production - MT",
}

def _map_item_group_accounts():
    """Set expense_account on Item Group defaults for Motley Terpz."""
    company = "Motley Terpz"

    for group_name, expense_acct in _GROUP_ACCOUNT_MAP.items():
        if not frappe.db.exists("Item Group", group_name):
            continue
        # Check if the account actually exists before linking
        if not frappe.db.exists("Account", expense_acct):
            continue

        ig = frappe.get_doc("Item Group", group_name)

        # Find or create the Item Group Default row for this company
        existing_row = None
        for row in ig.get("item_group_defaults") or []:
            if row.company == company:
                existing_row = row
                break

        if existing_row:
            if existing_row.expense_account == expense_acct:
                print(f"  -- Item Group '{group_name}' account already mapped")
                continue
            existing_row.expense_account = expense_acct
        else:
            ig.append("item_group_defaults", {
                "company": company,
                "expense_account": expense_acct,
            })

        ig.save(ignore_permissions=True)
        print(f"  +  Item Group '{group_name}' mapped to {expense_acct}")


# ── Phase 15: Inter-company setup — TSBC Ranch customer + Toll Service item ───

def _setup_intercompany_customers():
    """Ensure TSBC Ranch exists as a Customer in Motley Terpz for toll billing."""
    if frappe.db.exists("Customer", "TSBC Ranch"):
        print("  -- Customer 'TSBC Ranch' already exists")
        return

    cust = frappe.new_doc("Customer")
    cust.customer_name = "TSBC Ranch"
    cust.customer_group = "Commercial"
    cust.territory = "All Territories"
    cust.customer_type = "Company"
    cust.is_internal_customer = 1
    cust.represents_company = "TSBC Ranch"
    cust.insert(ignore_permissions=True)
    print("  +  Customer 'TSBC Ranch' created (internal, represents TSBC Ranch company)")


def _create_si_pbg_field():
    """Add custom_production_batch_group to Sales Invoice for toll invoice linking."""
    if frappe.db.exists("Custom Field", {"dt": "Sales Invoice", "fieldname": "custom_production_batch_group"}):
        print("  -- Custom Field Sales Invoice.custom_production_batch_group already exists")
        return
    cf = frappe.new_doc("Custom Field")
    cf.dt = "Sales Invoice"
    cf.fieldname = "custom_production_batch_group"
    cf.label = "Production Batch Group"
    cf.fieldtype = "Link"
    cf.options = "Production Batch Group"
    cf.insert_after = "company"
    cf.insert(ignore_permissions=True)
    print("  +  Custom Field Sales Invoice.custom_production_batch_group created")


def _create_toll_service_item():
    """Create a non-stock service item used on Toll Fee Sales Invoices."""
    item_code = "toll-processing-fee"
    if frappe.db.exists("Item", item_code):
        print(f"  -- Item '{item_code}' already exists")
        return

    item = frappe.new_doc("Item")
    item.item_code = item_code
    item.item_name = "Toll Processing Fee"
    item.item_group = "Services"
    item.stock_uom = "Gram"
    item.is_stock_item = 0
    item.is_sales_item = 1
    item.is_purchase_item = 0
    item.description = "Per-gram toll processing fee charged to third-party customers."
    item.insert(ignore_permissions=True, set_name=item_code)
    print(f"  +  Item '{item_code}' created")
