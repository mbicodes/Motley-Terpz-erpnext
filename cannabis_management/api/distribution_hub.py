# =================== DISTRIBUTION HUB - BACKEND API ===================
# Yeh file apne custom Frappe app ke andar rakhein, misal ke taur par:
#   your_app/your_app/distribution_hub/api.py
# Aur JS file (distribution_hub.js) ke top par APP_MODULE = "your_app.distribution_hub" set karein.
#
# IMPORTANT / ASSUMPTIONS (apne actual DocType/Field names se match karke adjust karein):
#   - "Sales Order"    -> pipeline ke orders (custom field "distro_stage" Select field
#                          jisme values: Pending in Sales Pipeline, Need to Schedule,
#                          Scheduled, Preparing, Prepared, Staged, Closed Out)
#   - "Delivery Note"  -> manifests (custom field "metrc_transport_tag")
#   - "Warehouse"      -> storage gauge + bin utilization (custom field "confirmed_capacity_lbs")
#   - "Bin"             -> actual stock qty per warehouse (Frappe stock doctype)
#   - "Company"         -> company selector (Motley / TSBC filter)
#
# Agar in fields ke naam alag hain to sirf neeche "FIELD MAP" section update kar dein —
# baaki query logic same rahega.

import frappe
from frappe import _
from frappe.utils import flt


# ---------------------------------------------------------------------------
# FIELD MAP -- apne DocType/field names yahan match karein
# ---------------------------------------------------------------------------
SALES_ORDER_STAGE_FIELD = "distro_stage"          # Select field on Sales Order
SALES_ORDER_LOGISTICS_FIELD = "logistics_status"  # Small Text / Select field
DN_METRC_FIELD = "metrc_transport_tag"             # Data field on Delivery Note
WAREHOUSE_CAPACITY_FIELD = "confirmed_capacity_lbs"  # Float field on Warehouse

DISTRO_WAREHOUSES = ["Hemet Distro", "Hemet-MT", "Don Perico", "Motley HQ Distro"]

PIPELINE_STAGES = [
    "Pending in Sales Pipeline",
    "Need to Schedule",
    "Scheduled",
    "Preparing",
    "Prepared",
    "Staged",
    "Closed Out",
]


# ---------------------------------------------------------------------------
# Meta (used only to populate the company filter dropdown in the pipeline section)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_meta():
    companies = frappe.get_all(
        "Company",
        filters={"name": ["in", ["Motley Logistics", "TSBC Logistics"]]},
        pluck="name",
    ) or ["Motley Logistics", "TSBC Logistics"]

    return {"companies": companies}


# ---------------------------------------------------------------------------
# 7-stage pipeline: stage counts + order rows
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_pipeline(company=None):
    filters = {}
    if company:
        filters["company"] = company

    stages = []
    for stage in PIPELINE_STAGES:
        stage_filters = dict(filters)
        stage_filters[SALES_ORDER_STAGE_FIELD] = stage
        count = frappe.db.count("Sales Order", filters=stage_filters)
        stages.append({"label": stage, "count": count})

    order_filters = dict(filters)
    order_filters[SALES_ORDER_STAGE_FIELD] = ["is", "set"]

    rows = frappe.get_all(
        "Sales Order",
        filters=order_filters,
        fields=[
            "name",
            "customer",
            "customer_address as bill_to",
            "delivery_date as requested",
            f"{SALES_ORDER_STAGE_FIELD} as stage",
            f"{SALES_ORDER_LOGISTICS_FIELD} as logistics_status",
            "set_warehouse as pickup_dropoff",
        ],
        order_by="delivery_date asc",
        limit_page_length=50,
    )

    return {"stages": stages, "orders": rows}


# ---------------------------------------------------------------------------
# Manifests (Delivery Note + METRC tag)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_manifests(company=None):
    filters = {"docstatus": ["<", 2]}
    if company:
        filters["company"] = company

    dns = frappe.get_all(
        "Delivery Note",
        filters=filters,
        fields=["name", "customer", "total_qty", "net_weight", DN_METRC_FIELD, "status"],
        order_by="modified desc",
        limit_page_length=50,
    )

    result = []
    for dn in dns:
        result.append({
            "manifest_no": f"MFT-{dn.name[-4:]}",
            "dn_ref": dn.name,
            "customer": dn.customer,
            "items_count": int(dn.total_qty or 0),
            "weight": f"{flt(dn.net_weight, 2)} kg" if dn.net_weight else "--",
            "metrc_tag": dn.get(DN_METRC_FIELD),
            "status": dn.status,
        })
    return result


# ---------------------------------------------------------------------------
# Storage gauge: Hemet Distro utilization % vs confirmed capacity
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_storage_gauge(warehouse="Hemet Distro"):
    capacity = frappe.db.get_value("Warehouse", warehouse, WAREHOUSE_CAPACITY_FIELD) or 0

    total_qty = frappe.db.sql(
        """
        SELECT COALESCE(SUM(actual_qty), 0)
        FROM `tabBin`
        WHERE warehouse = %s
        """,
        (warehouse,),
    )[0][0]

    percent = round((flt(total_qty) / flt(capacity)) * 100, 1) if capacity else 0
    return {"warehouse": warehouse, "percent": min(percent, 100), "current_qty": total_qty, "capacity": capacity}


# ---------------------------------------------------------------------------
# Bin utilization across all distro warehouses
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_bin_utilization():
    result = []
    for wh in DISTRO_WAREHOUSES:
        capacity = frappe.db.get_value("Warehouse", wh, WAREHOUSE_CAPACITY_FIELD) or 0
        total_qty = frappe.db.sql(
            """
            SELECT COALESCE(SUM(actual_qty), 0)
            FROM `tabBin`
            WHERE warehouse = %s
            """,
            (wh,),
        )[0][0]
        percent = round((flt(total_qty) / flt(capacity)) * 100, 1) if capacity else 0
        result.append({
            "warehouse": wh,
            "capacity_label": f"~{int(total_qty):,} lbs" if total_qty else "No stock",
            "percent": min(percent, 100),
        })
    return result


# ---------------------------------------------------------------------------
# Shortcuts grid (static config — link these to real Frappe routes)
# ---------------------------------------------------------------------------
@frappe.whitelist()
def get_shortcuts():
    return [
        {"icon": "L", "label": "Delivery Note", "sub": "New / List", "kind": "dt",
         "route": ["List", "Delivery Note"]},
        {"icon": "L", "label": "Pick List", "sub": "New / List", "kind": "dt",
         "route": ["List", "Pick List"]},
        {"icon": "L", "label": "Sales Order (Distro)", "sub": "List", "kind": "dt",
         "route": ["List", "Sales Order"]},
        {"icon": "R", "label": "Sean Stock Balance", "sub": "Custom Report", "kind": "rpt",
         "is_new": True, "route": ["query-report", "Sean Stock Balance"]},
        {"icon": "R", "label": "Stock Balance Logistic", "sub": "Custom Report", "kind": "rpt",
         "is_new": True, "route": ["query-report", "Stock Balance Logistic"]},
        {"icon": "D", "label": "Storage Gauge", "sub": "Dashboard", "kind": "dash",
         "route": ["dashboard-view", "Storage Gauge"]},
        {"icon": "P", "label": "METRC Transport", "sub": "Custom Page", "kind": "pg",
         "route": ["metrc-transport"]},
        {"icon": "P", "label": "Bin Reorg Console", "sub": "Custom Page", "kind": "pg",
         "route": ["bin-reorg-console"]},
        {"icon": "F", "label": "Sean Expense Tracker", "sub": "Custom Form", "kind": "form",
         "route": ["List", "Sean Expense Tracker"]},
        {"icon": "R", "label": "Delivery Note Register", "sub": "Report", "kind": "rpt",
         "route": ["query-report", "Delivery Note Register"]},
        {"icon": "R", "label": "OTIF / Return Rate", "sub": "Query Report", "kind": "rpt",
         "route": ["query-report", "OTIF / Return Rate"]},
    ]