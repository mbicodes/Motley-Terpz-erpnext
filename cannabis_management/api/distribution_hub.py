import frappe
from frappe.utils import flt

from cannabis_management.api.jamie import get_hemet_storage_lbs

SALES_ORDER_STAGE_FIELD = "custom_logistic_status"
NOT_SET_LABEL = "Not Set"

PIPELINE_STAGES = [
    NOT_SET_LABEL,
    "Need to Schedule",
    "Scheduled",
    "Order Preparing",
    "Order Prepared",
    "Order Staged",
    "Order Closed Out",
]

DISTRO_WAREHOUSES = ["Hemet TSBC - TSBC", "Hemet - TSBC", "Hemet - MT", "Don Perico - MT"]

WAREHOUSE_CAPACITY_LBS = {
    "Hemet TSBC - TSBC": 54000,
}


def _warehouse_lbs(warehouse):
    row = frappe.db.sql(
        """
        SELECT ROUND(SUM(
            CASE
                WHEN i.stock_uom = 'LBS' THEN b.actual_qty
                WHEN i.stock_uom = 'Gram' THEN b.actual_qty / 453.592
                ELSE 0
            END
        ), 1) AS lbs
        FROM `tabBin` b
        JOIN `tabItem` i ON i.name = b.item_code
        WHERE b.warehouse = %s
        """,
        (warehouse,),
        as_dict=True,
    )
    return flt(row[0].lbs) if row else 0


@frappe.whitelist()
def get_meta():
    companies = frappe.db.sql(
        """
        SELECT DISTINCT company FROM `tabSales Order`
        WHERE company IS NOT NULL AND company != ''
        ORDER BY company
        """,
        pluck=True,
    )
    return {"companies": companies}


@frappe.whitelist()
def get_pipeline(company=None):
    stages = []
    for stage in PIPELINE_STAGES:
        stage_filters = {"docstatus": ["<", 2]}
        if company:
            stage_filters["company"] = company
        if stage == NOT_SET_LABEL:
            stage_filters[SALES_ORDER_STAGE_FIELD] = ["in", ["", None]]
        else:
            stage_filters[SALES_ORDER_STAGE_FIELD] = stage
        count = frappe.db.count("Sales Order", filters=stage_filters)
        stages.append({"label": stage, "count": count})

    order_filters = {"docstatus": ["<", 2]}
    if company:
        order_filters["company"] = company

    rows = frappe.get_all(
        "Sales Order",
        filters=order_filters,
        fields=[
            "name",
            "customer",
            "customer_address as bill_to",
            "custom_pickup_or_dropoff as pickup_dropoff",
            "delivery_date as requested",
            f"{SALES_ORDER_STAGE_FIELD} as stage",
            "custom_notes_for_logistics as notes",
        ],
        order_by="delivery_date asc",
        limit_page_length=50,
    )
    for row in rows:
        row.stage = row.stage or NOT_SET_LABEL

    return {"stages": stages, "orders": rows}


@frappe.whitelist()
def get_manifests(company=None):
    filters = {"docstatus": ["<", 2]}
    if company:
        filters["company"] = company

    dns = frappe.get_all(
        "Delivery Note",
        filters=filters,
        fields=["name", "customer", "total_qty", "total_net_weight",
                 "custom_manifest", "custom_shipment", "status"],
        order_by="modified desc",
        limit_page_length=50,
    )

    result = []
    for dn in dns:
        result.append({
            "manifest_no": dn.custom_manifest.rsplit("/", 1)[-1] if dn.custom_manifest else "--",
            "dn_ref": dn.name,
            "customer": dn.customer,
            "items_count": int(dn.total_qty or 0),
            "weight": f"{flt(dn.total_net_weight, 2)} kg" if dn.total_net_weight else "--",
            "shipment_ref": dn.custom_shipment or "--",
            "status": dn.status,
        })
    return result


@frappe.whitelist()
def get_storage_gauge():
    warehouse = "Hemet TSBC - TSBC"
    capacity = WAREHOUSE_CAPACITY_LBS[warehouse]
    current_lbs = flt(get_hemet_storage_lbs())
    percent = round((current_lbs / capacity) * 100, 1) if capacity else 0
    return {
        "warehouse": warehouse,
        "percent": min(percent, 100),
        "current_qty": current_lbs,
        "capacity": capacity,
    }


@frappe.whitelist()
def get_bin_utilization():
    result = []
    for wh in DISTRO_WAREHOUSES:
        lbs = _warehouse_lbs(wh)
        capacity = WAREHOUSE_CAPACITY_LBS.get(wh)
        percent = round((lbs / capacity) * 100, 1) if capacity else None
        result.append({
            "warehouse": wh,
            "capacity_label": f"~{int(lbs):,} lbs" if lbs else "No stock",
            "percent": min(percent, 100) if percent is not None else None,
        })
    return result

SHORTCUT_CANDIDATES = [
    {"icon": "D", "label": "Delivery Note", "sub": "New / List", "kind": "dt",
     "dt": "Delivery Note", "route": ["List", "Delivery Note"]},
    {"icon": "T", "label": "Delivery Trip", "sub": "New / List", "kind": "dt",
     "dt": "Delivery Trip", "route": ["List", "Delivery Trip"]},
    {"icon": "P", "label": "Pick List", "sub": "New / List", "kind": "dt",
     "dt": "Pick List", "route": ["List", "Pick List"]},
    {"icon": "K", "label": "Packing Slip", "sub": "New / List", "kind": "dt",
     "dt": "Packing Slip", "route": ["List", "Packing Slip"]},
    {"icon": "S", "label": "Sales Order", "sub": "List", "kind": "dt",
     "dt": "Sales Order", "route": ["List", "Sales Order"]},
    {"icon": "W", "label": "Warehouse", "sub": "List", "kind": "dt",
     "dt": "Warehouse", "route": ["List", "Warehouse"]},
    {"icon": "R", "label": "Stock Balance Logistic", "sub": "Report", "kind": "rpt",
     "report": "Stock Balance Logistic", "route": ["query-report", "Stock Balance Logistic"]},
    {"icon": "R", "label": "Warehouse Wise Stock Balance", "sub": "Report", "kind": "rpt",
     "report": "Warehouse Wise Stock Balance", "route": ["query-report", "Warehouse Wise Stock Balance"]},
]


@frappe.whitelist()
def get_shortcuts():
    result = []
    for s in SHORTCUT_CANDIDATES:
        if s.get("dt") and not frappe.db.exists("DocType", s["dt"]):
            continue
        if s.get("report") and not frappe.db.exists("Report", s["report"]):
            continue
        result.append({k: v for k, v in s.items() if k not in ("dt", "report")})
    return result
