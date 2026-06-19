import frappe
from frappe import _


# ---------------------------------------------------------------------------
# Micron table auto-detection
# cannabis_management app mein table name alag ho sakta hai.
# Yeh function runtime pe sahi table dhundta hai.
# ---------------------------------------------------------------------------
MICRON_TABLE_CANDIDATES = [
    "tabJob Card Micron Detail",          # original guess
    "tabJob Card Micron",                 # shorter variant
    "tabCannabis Job Card Micron Detail", # cannabis_ prefix variant
    "tabCannabis Micron Detail",          # pure cannabis variant
    "tabMicron Detail",                   # minimal name
]

_micron_table_cache = {}  # cached per-site


def get_micron_table():
    """Return the first existing micron child table name, or None."""
    site = frappe.local.site
    if site in _micron_table_cache:
        return _micron_table_cache[site]

    existing = frappe.db.sql(
        "SELECT TABLE_NAME FROM information_schema.TABLES "
        "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME LIKE %s",
        ("%micron%",),
        as_list=True,
    )
    found_tables = [row[0] for row in existing]

    # Priority: use candidate order, fall back to first found
    chosen = None
    for candidate in MICRON_TABLE_CANDIDATES:
        if candidate in found_tables:
            chosen = candidate
            break

    if not chosen and found_tables:
        chosen = found_tables[0]

    _micron_table_cache[site] = chosen
    return chosen


def execute(filters=None):
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        # L1 — Material Request
        {"label": _("Material Request No."), "fieldname": "material_request",
         "fieldtype": "Link", "options": "Material Request", "width": 180},
        {"label": _("MR Date"), "fieldname": "mr_date",
         "fieldtype": "Date", "width": 110},
        {"label": _("Project / Batch"), "fieldname": "batch",
         "fieldtype": "Link", "options": "Project", "width": 130},
        {"label": _("Raw Material Item"), "fieldname": "raw_material",
         "fieldtype": "Link", "options": "Item", "width": 160},
        {"label": _("Raw Material Qty (LBS)"), "fieldname": "rm_qty",
         "fieldtype": "Float", "width": 140},
        # L2 — BOM
        {"label": _("BOM Number"), "fieldname": "bom_no",
         "fieldtype": "Link", "options": "BOM", "width": 150},
        {"label": _("BOM Raw Material Cost"), "fieldname": "bom_rm_cost",
         "fieldtype": "Currency", "width": 160},
        # L3 — Work Order
        {"label": _("Work Order No."), "fieldname": "work_order",
         "fieldtype": "Link", "options": "Work Order", "width": 170},
        {"label": _("WO Status"), "fieldname": "wo_status",
         "fieldtype": "Data", "width": 110},
        {"label": _("Finished Item"), "fieldname": "finished_item",
         "fieldtype": "Link", "options": "Item", "width": 150},
        {"label": _("Planned Qty to Manufacture"), "fieldname": "planned_qty",
         "fieldtype": "Float", "width": 170},
        {"label": _("Actual Manufactured Qty"), "fieldname": "actual_qty",
         "fieldtype": "Float", "width": 160},
        {"label": _("Yield %"), "fieldname": "yield_pct",
         "fieldtype": "Percent", "width": 90},
        {"label": _("Source Warehouse"), "fieldname": "source_warehouse",
         "fieldtype": "Link", "options": "Warehouse", "width": 150},
        {"label": _("WIP Warehouse"), "fieldname": "wip_warehouse",
         "fieldtype": "Link", "options": "Warehouse", "width": 140},
        {"label": _("Target Warehouse (FG)"), "fieldname": "fg_warehouse",
         "fieldtype": "Link", "options": "Warehouse", "width": 160},
        # L4 — Material Transfer
        {"label": _("Transfer Stock Entry No."), "fieldname": "transfer_entry",
         "fieldtype": "Link", "options": "Stock Entry", "width": 180},
        {"label": _("Transfer Date"), "fieldname": "transfer_date",
         "fieldtype": "Date", "width": 120},
        {"label": _("RM Qty Transferred"), "fieldname": "rm_transferred_qty",
         "fieldtype": "Float", "width": 150},
        {"label": _("Remaining Qty to Transfer"), "fieldname": "remaining_transfer_qty",
         "fieldtype": "Float", "width": 170},
        # L5 — Job Card
        {"label": _("Job Card No."), "fieldname": "job_card",
         "fieldtype": "Link", "options": "Job Card", "width": 160},
        {"label": _("Operation"), "fieldname": "operation",
         "fieldtype": "Link", "options": "Operation", "width": 140},
        {"label": _("Workstation"), "fieldname": "workstation",
         "fieldtype": "Link", "options": "Workstation", "width": 140},
        {"label": _("Sub-Operations"), "fieldname": "sub_operations",
         "fieldtype": "Data", "width": 160},
        {"label": _("Actual Start Time"), "fieldname": "actual_start",
         "fieldtype": "Datetime", "width": 150},
        {"label": _("Actual End Time"), "fieldname": "actual_end",
         "fieldtype": "Datetime", "width": 150},
        {"label": _("Total Working Hours"), "fieldname": "total_hours",
         "fieldtype": "Float", "width": 150},
        {"label": _("Employee"), "fieldname": "employee",
         "fieldtype": "Data", "width": 160},
        {"label": _("JC Actual Produced Qty"), "fieldname": "jc_produced_qty",
         "fieldtype": "Float", "width": 160},
        # L6 — Micron Analysis
        {"label": _("Micron Size"), "fieldname": "micron_size",
         "fieldtype": "Data", "width": 110},
        {"label": _("Finished Product (per Micron)"), "fieldname": "micron_item",
         "fieldtype": "Link", "options": "Item", "width": 200},
        {"label": _("Grams Collected"), "fieldname": "grams_collected",
         "fieldtype": "Float", "width": 130},
        {"label": _("Quality Grade"), "fieldname": "quality_grade",
         "fieldtype": "Data", "width": 120},
        {"label": _("Production Distribution %"), "fieldname": "distribution_pct",
         "fieldtype": "Percent", "width": 170},
        # L7 — Finished Goods
        {"label": _("Manufacture Stock Entry No."), "fieldname": "manufacture_entry",
         "fieldtype": "Link", "options": "Stock Entry", "width": 200},
        {"label": _("Produced Qty in SE"), "fieldname": "se_produced_qty",
         "fieldtype": "Float", "width": 150},
        {"label": _("FG Warehouse"), "fieldname": "fg_warehouse_se",
         "fieldtype": "Link", "options": "Warehouse", "width": 140},
        {"label": _("Production Date"), "fieldname": "production_date",
         "fieldtype": "Date", "width": 130},
        # L8 — Costing
        {"label": _("Raw Material Cost (Actual)"), "fieldname": "rm_actual_cost",
         "fieldtype": "Currency", "width": 180},
        {"label": _("Labour Cost"), "fieldname": "labour_cost",
         "fieldtype": "Currency", "width": 130},
        {"label": _("Machine / Workstation Cost"), "fieldname": "machine_cost",
         "fieldtype": "Currency", "width": 180},
        {"label": _("Additional Costs (Overhead)"), "fieldname": "additional_costs",
         "fieldtype": "Currency", "width": 180},
        {"label": _("Total Manufacturing Cost"), "fieldname": "total_mfg_cost",
         "fieldtype": "Currency", "width": 180},
        {"label": _("Cost Per Unit"), "fieldname": "cost_per_unit",
         "fieldtype": "Currency", "width": 130},
        # L9 — Variance
        {"label": _("Planned Quantity"), "fieldname": "planned_qty_var",
         "fieldtype": "Float", "width": 140},
        {"label": _("Qty Variance"), "fieldname": "qty_variance",
         "fieldtype": "Float", "width": 120},
        {"label": _("Yield Variance %"), "fieldname": "yield_variance_pct",
         "fieldtype": "Percent", "width": 140},
        {"label": _("Cost Variance"), "fieldname": "cost_variance",
         "fieldtype": "Currency", "width": 130},
        {"label": _("Material Consumption Variance"), "fieldname": "material_variance",
         "fieldtype": "Float", "width": 210},
    ]


def get_filters_conditions(filters):
    conditions = ["mr.docstatus = 1"]
    params = {}

    if filters.get("from_date"):
        conditions.append("mr.transaction_date >= %(from_date)s")
        params["from_date"] = filters["from_date"]
    if filters.get("to_date"):
        conditions.append("mr.transaction_date <= %(to_date)s")
        params["to_date"] = filters["to_date"]
    if filters.get("custom_project"):
        conditions.append("mr.custom_project = %(custom_project)s")
        params["custom_project"] = filters["custom_project"]
    if filters.get("work_order"):
        conditions.append("wo.name = %(work_order)s")
        params["work_order"] = filters["work_order"]
    if filters.get("finished_item"):
        conditions.append("wo.production_item = %(finished_item)s")
        params["finished_item"] = filters["finished_item"]
    if filters.get("wo_status"):
        conditions.append("wo.status = %(wo_status)s")
        params["wo_status"] = filters["wo_status"]
    if filters.get("raw_material"):
        conditions.append("mri.item_code = %(raw_material)s")
        params["raw_material"] = filters["raw_material"]

    return " AND ".join(conditions), params


def get_micron_join(micron_table):
    """
    Build the LEFT JOIN clause and SELECT fields for the micron table.
    If table not found → return empty strings so report still loads.
    """
    if not micron_table:
        select_part = (
            "NULL AS micron_size, NULL AS micron_item, "
            "NULL AS grams_collected, NULL AS quality_grade, NULL AS micron_name"
        )
        join_part = ""
        group_field = ""
    else:
        select_part = (
            f"jcm.micron_size      AS micron_size,\n"
            f"            jcm.item             AS micron_item,\n"
            f"            jcm.grams_collected  AS grams_collected,\n"
            f"            jcm.quality_grade    AS quality_grade,\n"
            f"            jcm.name             AS micron_name"
        )
        join_part = (
            f"LEFT JOIN `{micron_table}` AS jcm ON jcm.parent = jc.name"
        )
        group_field = ", jcm.name"
    return select_part, join_part, group_field


def get_data(filters=None):
    if not filters:
        filters = {}

    conditions, params = get_filters_conditions(filters)

    # Detect micron table at runtime — safe even if table missing
    micron_table = get_micron_table()
    micron_select, micron_join, micron_group = get_micron_join(micron_table)

    if not micron_table:
        frappe.log_error(
            "Manufacturing Traceability Report: No micron child table found in DB. "
            "Micron columns (L6) will be empty. "
            "Run: SELECT TABLE_NAME FROM information_schema.TABLES WHERE TABLE_NAME LIKE '%micron%'; "
            "to find the correct table name.",
            "Micron Table Not Found"
        )

    raw_rows = frappe.db.sql(
        f"""
        SELECT
            -- L1
            mr.name                         AS material_request,
            mr.transaction_date             AS mr_date,
            mr.custom_project                      AS batch,
            mri.item_code                   AS raw_material,
            mri.qty                         AS rm_qty,

            -- L2
            bom.name                        AS bom_no,
            bom.raw_material_cost           AS bom_rm_cost,

            -- L3
            wo.name                         AS work_order,
            wo.status                       AS wo_status,
            wo.production_item              AS finished_item,
            wo.qty                          AS planned_qty,
            wo.produced_qty                 AS actual_qty,
            wo.source_warehouse             AS source_warehouse,
            wo.wip_warehouse                AS wip_warehouse,
            wo.fg_warehouse                 AS fg_warehouse,
            wo.actual_operating_cost        AS machine_cost,
            wo.planned_operating_cost       AS planned_operating_cost,

            -- L4
            se_t.name                       AS transfer_entry,
            se_t.posting_date               AS transfer_date,
            se_t.total_outgoing_value       AS rm_actual_cost,
            SUM(sed_t.qty)                  AS rm_transferred_qty,

            -- L5
            jc.name                         AS job_card,
            jc.operation                    AS operation,
            jc.workstation                  AS workstation,
            jc.actual_start_date            AS actual_start,
            jc.actual_end_date              AS actual_end,
            jc.total_time_in_mins           AS total_time_in_mins,
            jc.hour_rate                    AS hour_rate,
            jc.total_completed_qty          AS jc_produced_qty,
            GROUP_CONCAT(DISTINCT jc.operation SEPARATOR ', ') AS sub_operations,
            GROUP_CONCAT(DISTINCT jct.employee  SEPARATOR ', ') AS employee,

            -- L6 (micron — dynamic)
            {micron_select},

            -- L7
            se_m.name                       AS manufacture_entry,
            se_m.fg_completed_qty           AS se_produced_qty,
            se_m.posting_date               AS production_date,
            se_m.total_additional_costs     AS additional_costs,
            sed_m.t_warehouse               AS fg_warehouse_se,

            -- BOM item qty for material variance
            bom_item.qty                    AS bom_item_qty_per_unit

        FROM `tabMaterial Request`         AS mr
        JOIN `tabMaterial Request Item`    AS mri  ON mri.parent          = mr.name
        JOIN `tabWork Order`               AS wo   ON wo.material_request  = mr.name
        LEFT JOIN `tabBOM`                 AS bom  ON bom.name             = wo.bom_no
                                                   AND bom.docstatus       = 1

        LEFT JOIN `tabStock Entry`         AS se_t
               ON se_t.work_order  = wo.name
              AND se_t.purpose     = 'Material Transfer for Manufacture'
              AND se_t.docstatus   = 1
        LEFT JOIN `tabStock Entry Detail`  AS sed_t
               ON sed_t.parent     = se_t.name
              AND sed_t.s_warehouse IS NOT NULL

        LEFT JOIN `tabJob Card`            AS jc   ON jc.work_order        = wo.name
        LEFT JOIN `tabJob Card Operation`  AS jco  ON jco.parent           = jc.name
        LEFT JOIN `tabJob Card Time Log`   AS jct  ON jct.parent           = jc.name

        {micron_join}

        LEFT JOIN `tabStock Entry`         AS se_m
               ON se_m.work_order  = wo.name
              AND se_m.purpose     = 'Manufacture'
              AND se_m.docstatus   = 1
        LEFT JOIN `tabStock Entry Detail`  AS sed_m
               ON sed_m.parent     = se_m.name
              AND sed_m.is_finished_item = 1

        LEFT JOIN `tabBOM Item`            AS bom_item
               ON bom_item.parent    = bom.name
              AND bom_item.item_code  = mri.item_code
              AND bom_item.docstatus  = 1

        WHERE {conditions}

        GROUP BY
            mr.name, mri.name, wo.name, bom.name,
            se_t.name, jc.name, se_m.name, sed_m.name{micron_group}

        ORDER BY mr.transaction_date DESC, mr.name, wo.name
        """,
        params,
        as_dict=True,
    )

    # ---------------------------------------------------------------
    # POST-PROCESSING
    # ---------------------------------------------------------------
    jc_grams_total = {}
    for row in raw_rows:
        jc = row.get("job_card") or ""
        grams = row.get("grams_collected") or 0
        jc_grams_total[jc] = jc_grams_total.get(jc, 0) + grams

    result = []
    for row in raw_rows:
        planned_qty            = row.get("planned_qty") or 0
        actual_qty             = row.get("actual_qty") or 0
        rm_qty                 = row.get("rm_qty") or 0
        rm_transferred         = row.get("rm_transferred_qty") or 0
        total_time_in_mins     = row.get("total_time_in_mins") or 0
        hour_rate              = row.get("hour_rate") or 0
        rm_actual_cost         = row.get("rm_actual_cost") or 0
        machine_cost           = row.get("machine_cost") or 0
        additional_costs       = row.get("additional_costs") or 0
        bom_item_qty_per_unit  = row.get("bom_item_qty_per_unit") or 0
        grams_collected        = row.get("grams_collected") or 0
        jc_key                 = row.get("job_card") or ""
        planned_operating_cost = row.get("planned_operating_cost") or 0

        total_hours       = round(total_time_in_mins / 60.0, 4) if total_time_in_mins else 0
        labour_cost       = round(hour_rate * total_hours, 4)
        total_mfg_cost    = rm_actual_cost + labour_cost + machine_cost + additional_costs

        yield_pct             = round(actual_qty / planned_qty * 100, 2) if planned_qty > 0 else 0
        remaining_transfer    = rm_qty - rm_transferred
        cost_per_unit         = round(total_mfg_cost / actual_qty, 4) if actual_qty > 0 else 0
        qty_variance          = planned_qty - actual_qty
        yield_variance_pct    = round((actual_qty - planned_qty) / planned_qty * 100, 2) if planned_qty > 0 else 0
        cost_variance         = machine_cost - planned_operating_cost
        material_variance     = rm_transferred - (bom_item_qty_per_unit * planned_qty)
        total_grams           = jc_grams_total.get(jc_key, 0)
        distribution_pct      = round(grams_collected / total_grams * 100, 2) if total_grams > 0 else 0

        result.append({
            "material_request":       row.get("material_request"),
            "mr_date":                row.get("mr_date"),
            "batch":                  row.get("batch"),
            "raw_material":           row.get("raw_material"),
            "rm_qty":                 rm_qty,
            "bom_no":                 row.get("bom_no"),
            "bom_rm_cost":            row.get("bom_rm_cost"),
            "work_order":             row.get("work_order"),
            "wo_status":              row.get("wo_status"),
            "finished_item":          row.get("finished_item"),
            "planned_qty":            planned_qty,
            "actual_qty":             actual_qty,
            "yield_pct":              yield_pct,
            "source_warehouse":       row.get("source_warehouse"),
            "wip_warehouse":          row.get("wip_warehouse"),
            "fg_warehouse":           row.get("fg_warehouse"),
            "transfer_entry":         row.get("transfer_entry"),
            "transfer_date":          row.get("transfer_date"),
            "rm_transferred_qty":     rm_transferred,
            "remaining_transfer_qty": remaining_transfer,
            "job_card":               row.get("job_card"),
            "operation":              row.get("operation"),
            "workstation":            row.get("workstation"),
            "sub_operations":         row.get("sub_operations"),
            "actual_start":           row.get("actual_start"),
            "actual_end":             row.get("actual_end"),
            "total_hours":            total_hours,
            "employee":               row.get("employee"),
            "jc_produced_qty":        row.get("jc_produced_qty"),
            "micron_size":            row.get("micron_size"),
            "micron_item":            row.get("micron_item"),
            "grams_collected":        grams_collected,
            "quality_grade":          row.get("quality_grade"),
            "distribution_pct":       distribution_pct,
            "manufacture_entry":      row.get("manufacture_entry"),
            "se_produced_qty":        row.get("se_produced_qty"),
            "fg_warehouse_se":        row.get("fg_warehouse_se"),
            "production_date":        row.get("production_date"),
            "rm_actual_cost":         rm_actual_cost,
            "labour_cost":            labour_cost,
            "machine_cost":           machine_cost,
            "additional_costs":       additional_costs,
            "total_mfg_cost":         total_mfg_cost,
            "cost_per_unit":          cost_per_unit,
            "planned_qty_var":        planned_qty,
            "qty_variance":           qty_variance,
            "yield_variance_pct":     yield_variance_pct,
            "cost_variance":          cost_variance,
            "material_variance":      material_variance,
        })

    return result