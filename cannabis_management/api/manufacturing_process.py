"""Backend API for the Manufacturing Process page — a 5-step guided wizard for
one production "run" (one Manufacture-type Material Request) at a time:
create the request, release it to Work Orders + Job Cards, transfer material
to WIP, run the operations (per-sub-operation timers), then record output.

Every endpoint returns human-readable labels (item name, project, operation,
status) as primary identifiers. Document IDs are included as secondary data
for backend linking but never surfaced as the primary UI label.
"""
import json

import frappe
from frappe import _
from frappe.utils import flt, now_datetime, get_datetime

from cannabis_management.doc_hooks.job_card import MICRON_OPERATIONS
from cannabis_management.overrides.mr_run_status import work_order_done


# ── 1. Dashboard ──────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard(company=None):
    filters_mr = {"material_request_type": "Manufacture"}
    filters_jc = {}
    if company:
        filters_mr["company"] = company
        filters_jc["company"] = company

    # Only Material Requests still awaiting fulfillment — excludes Draft,
    # Cancelled, and anything already past the Pending stage.
    mrs = frappe.get_all(
        "Material Request",
        # Released runs move to In Progress / Completed (overrides/mr_run_status)
        # and stay listed -- a finished run's card shows collapsed.
        filters={**filters_mr, "status": ["in", ["Pending", "In Progress", "Completed"]]},
        fields=[
            "name", "docstatus", "company", "custom_project", "custom_routing",
            "set_warehouse", "transaction_date", "status",
        ],
        order_by="creation desc",
        limit=50,
    )

    mr_names = [m.name for m in mrs]
    mr_items_map = {}
    mr_fg_map = {}

    if mr_names:
        for row in frappe.get_all(
            "Material Request Item",
            filters={"parent": ["in", mr_names]},
            fields=["parent", "item_code", "item_name", "qty", "uom"],
        ):
            mr_items_map.setdefault(row.parent, []).append(row)

        for row in frappe.get_all(
            "Finished Goods Detail",
            filters={"parent": ["in", mr_names]},
            fields=["parent", "item", "operation", "expected_yield_",
                     "finished_qty_grams"],
        ):
            mr_fg_map.setdefault(row.parent, []).append(row)

        # Count linked Work Orders per MR
        wo_counts = {}
        for row in frappe.get_all(
            "Work Order",
            filters={"material_request": ["in", mr_names], "docstatus": ["!=", 2]},
            fields=["material_request", "count(name) as cnt"],
            group_by="material_request",
        ):
            wo_counts[row.material_request] = row.cnt

    # Resolve project names in bulk
    project_ids = list(set(m.custom_project for m in mrs if m.custom_project))
    project_name_map = {}
    if project_ids:
        for p in frappe.get_all("Project", filters={"name": ["in", project_ids]}, fields=["name", "project_name"]):
            project_name_map[p.name] = p.project_name

    for m in mrs:
        m["items"] = mr_items_map.get(m.name, [])
        m["finished_goods"] = mr_fg_map.get(m.name, [])
        m["work_order_count"] = wo_counts.get(m.name, 0) if mr_names else 0
        m["project_name"] = project_name_map.get(m.custom_project, m.custom_project or "")
        # Primary label: first item name
        first_item = m["items"][0] if m["items"] else None
        m["primary_label"] = first_item["item_name"] if first_item else m.name
        m["primary_qty"] = f"{first_item['qty']} {first_item['uom']}" if first_item else ""

    # Active Job Cards (Open, Work In Progress, Material Transferred)
    active_statuses = ["Open", "Work In Progress", "Material Transferred"]
    job_cards = frappe.get_all(
        "Job Card",
        filters={**filters_jc, "status": ["in", active_statuses], "docstatus": ["<", 2]},
        fields=[
            "name", "work_order", "production_item", "operation", "workstation",
            "status", "for_quantity", "total_completed_qty", "total_time_in_mins",
            "posting_date", "docstatus", "custom_sub_op_total_cost",
        ],
        order_by="creation desc",
        limit=50,
    )

    # Enrich with item name, project, and WO production_item name
    if job_cards:
        wo_names = list(set(jc.work_order for jc in job_cards if jc.work_order))
        wo_data = {}
        if wo_names:
            for wo in frappe.get_all(
                "Work Order",
                filters={"name": ["in", wo_names]},
                fields=["name", "production_item", "item_name", "project",
                         "material_request", "status as wo_status",
                         "qty", "produced_qty"],
            ):
                wo_data[wo.name] = wo

        jc_project_ids = list(set(wo.get("project", "") for wo in wo_data.values() if wo.get("project")))
        jc_project_name_map = {}
        if jc_project_ids:
            for p in frappe.get_all("Project", filters={"name": ["in", jc_project_ids]}, fields=["name", "project_name"]):
                jc_project_name_map[p.name] = p.project_name

        for jc in job_cards:
            wo = wo_data.get(jc.work_order, {})
            jc["item_name"] = frappe.db.get_value("Item", jc.production_item, "item_name") or jc.production_item
            proj_id = wo.get("project", "")
            jc["project"] = jc_project_name_map.get(proj_id, proj_id)
            jc["project_id"] = proj_id
            jc["material_request"] = wo.get("material_request", "")
            jc["wo_status"] = wo.get("wo_status", "")
            jc["wo_qty"] = flt(wo.get("qty", 0))
            jc["wo_produced_qty"] = flt(wo.get("produced_qty", 0))

    # Recently completed JCs (last 24h)
    completed_today = frappe.db.count("Job Card", {
        "status": "Completed",
        "modified": [">=", frappe.utils.add_days(frappe.utils.today(), -1)],
    })

    return {
        "material_requests": mrs,
        "job_cards": job_cards,
        "stats": {
            "pending_mrs": len([m for m in mrs if m.docstatus == 0]),
            "submitted_mrs": len([m for m in mrs if m.docstatus == 1]),
            "active_job_cards": len(job_cards),
            "completed_today": completed_today,
        },
    }


# ── 2. Run Detail (one Material Request, the wizard's single source of truth) ──

LBS_TO_GRAM = 453.592


@frappe.whitelist()
def get_run_detail(material_request):
    """Everything the 5-step Run wizard needs for one Material Request in a
    single round trip: the MR header, its raw materials + finished-goods
    targets, every linked Work Order with its Job Cards (each carrying full
    sub-operation timer + micron state via `_job_card_full_detail`), which
    step the wizard should show (`current_step`/`active_work_order`), and the
    live scoreboard numbers.

    A run's steps 3-5 (transfer, run operations, finish) are scoped to one
    Work Order at a time — `active_work_order` is the first one (by creation
    order, i.e. routing sequence) that isn't fully produced yet. Once every
    Work Order is fully produced, `complete` is true.
    """
    if not frappe.db.exists("Material Request", material_request):
        frappe.throw(_("Material Request not found."))

    mr = frappe.get_doc("Material Request", material_request)

    items = [{
        "item_code": d.item_code,
        "item_name": d.item_name,
        "qty": flt(d.qty),
        "uom": d.uom,
        "warehouse": d.warehouse,
    } for d in mr.items]

    finished_goods = [{
        "item": d.item,
        "item_name": frappe.db.get_value("Item", d.item, "item_name") or d.item,
        "operation": d.operation,
        "expected_yield_": flt(d.expected_yield_),
        "finished_qty_grams": flt(d.finished_qty_grams),
        "finished_qty_pounds": flt(d.get("finished_qty_pounds")),
        "source_warehouse": d.get("source_warehouse"),
        "wip_warehouse": d.get("wip_warehouse"),
        "target_warehouse": d.get("target_warehouse"),
    } for d in mr.get("custom_finished_goods") or []]

    work_orders = frappe.get_all(
        "Work Order",
        filters={"material_request": mr.name, "docstatus": ["!=", 2]},
        fields=[
            "name", "production_item", "item_name", "status", "docstatus",
            "qty", "produced_qty", "material_transferred_for_manufacturing",
            "project", "process_loss_qty",
        ],
        order_by="creation asc",
    )

    for wo in work_orders:
        wo["qty"] = flt(wo["qty"])
        wo["produced_qty"] = flt(wo["produced_qty"])
        wo["material_transferred_for_manufacturing"] = flt(wo["material_transferred_for_manufacturing"])
        wo["process_loss_qty"] = flt(wo["process_loss_qty"])
        # What each card button shows once its step is done.
        wo["done"] = work_order_done(frappe._dict(wo))
        wo["transferred"] = wo["qty"] > 0 and wo["material_transferred_for_manufacturing"] >= wo["qty"]
        wo["manufacture_entry"] = frappe.db.get_value(
            "Stock Entry",
            {"work_order": wo["name"], "purpose": "Manufacture", "docstatus": 1},
            "name",
        )
        wo["tiering_entry"] = frappe.db.get_value(
            "Conversion Entry",
            {"custom_work_order": wo["name"], "docstatus": 1},
            "name",
        )

        jc_names = frappe.get_all(
            "Job Card",
            filters={"work_order": wo["name"], "docstatus": ["!=", 2]},
            pluck="name",
            order_by="creation asc",
        )
        wo["job_cards"] = [_job_card_full_detail(name) for name in jc_names]

    project_name = ""
    if mr.custom_project:
        project_name = frappe.db.get_value("Project", mr.custom_project, "project_name") or mr.custom_project

    current_step, active_wo, complete = _resolve_run_step(mr, work_orders)

    return {
        "material_request": {
            "name": mr.name,
            "docstatus": mr.docstatus,
            "status": mr.status,
            "company": mr.company,
            "project": mr.custom_project,
            "project_name": project_name,
            "routing": mr.custom_routing,
            "set_warehouse": mr.set_warehouse,
            "transaction_date": mr.transaction_date,
        },
        "items": items,
        "finished_goods": finished_goods,
        "work_orders": work_orders,
        "current_step": current_step,
        "active_work_order": active_wo["name"] if active_wo else None,
        "complete": complete,
        "scoreboard": _build_scoreboard(items, finished_goods, work_orders),
    }


def _resolve_run_step(mr, work_orders):
    """Where the wizard should land: MR draft -> 1; submitted with no Work
    Orders yet -> 2; else scoped to the first not-yet-fully-produced Work
    Order -> 3 (needs transfer), 4 (operations still running) or 5 (ready to
    record output / already complete)."""
    if mr.docstatus == 0:
        return 1, None, False
    if not work_orders:
        return 2, None, False

    active_wo = next((wo for wo in work_orders if not wo.get("done")), None)
    if not active_wo:
        return 5, None, True

    if active_wo["material_transferred_for_manufacturing"] < active_wo["qty"]:
        return 3, active_wo, False

    jcs = active_wo["job_cards"]
    all_done = bool(jcs) and all(jc["status"] == "Completed" for jc in jcs)
    return (5 if all_done else 4), active_wo, False


def _build_scoreboard(items, finished_goods, work_orders):
    grams_in = sum(flt(d["qty"]) * LBS_TO_GRAM for d in items)
    fg_by_item = {fg["item"]: fg for fg in finished_goods if fg.get("item")}

    fg_rows = []
    for wo in work_orders:
        fg = fg_by_item.get(wo["production_item"])
        produced = wo["produced_qty"]
        fg_rows.append({
            "item": wo["production_item"],
            "item_name": wo["item_name"],
            "produced": produced,
            "target_qty": wo["qty"],
            "expected_yield": flt(fg["expected_yield_"]) if fg else None,
            "yield_pct": (produced / grams_in * 100) if grams_in else 0,
        })

    return {
        "grams_in": grams_in,
        "finished_goods": fg_rows,
        "total_cost": sum(flt(jc["total_cost"]) for wo in work_orders for jc in wo["job_cards"]),
        "total_time_mins": sum(flt(jc["total_time_in_mins"]) for wo in work_orders for jc in wo["job_cards"]),
    }


# ── 3. Create Material Request ────────────────────────────────────────────────

@frappe.whitelist()
def create_material_request(payload):
    if isinstance(payload, str):
        payload = json.loads(payload)

    company = payload.get("company")
    project = payload.get("project")
    items = payload.get("items") or []
    fg_rows = payload.get("finished_goods") or []
    routing = payload.get("routing")
    warehouse = payload.get("warehouse")
    schedule_date = payload.get("schedule_date") or frappe.utils.today()
    transaction_date = payload.get("transaction_date") or frappe.utils.today()

    if not company:
        frappe.throw(_("Company is required."))
    if not items:
        frappe.throw(_("At least one raw material item is required."))

    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Manufacture"
    mr.company = company
    mr.custom_project = project
    mr.custom_routing = routing
    mr.set_warehouse = warehouse
    mr.transaction_date = transaction_date
    mr.schedule_date = schedule_date

    for row in items:
        item_code = row.get("item_code")
        if not item_code:
            continue
        stock_uom = frappe.db.get_value("Item", item_code, "stock_uom") or "Nos"
        mr.append("items", {
            "item_code": item_code,
            "qty": flt(row.get("qty")) or 1,
            "uom": stock_uom,
            "stock_uom": stock_uom,
            "conversion_factor": 1,
            "warehouse": row.get("warehouse") or warehouse,
            "schedule_date": schedule_date,
        })

    for row in fg_rows:
        if not row.get("operation"):
            continue
        mr.append("custom_finished_goods", {
            "item": row.get("item"),
            "operation": row.get("operation"),
            "expected_yield_": flt(row.get("expected_yield_", row.get("expected_yield"))),
            "finished_qty_grams": flt(row.get("finished_qty_grams")),
            "finished_qty_pounds": flt(row.get("finished_qty_pounds")),
            "source_warehouse": row.get("source_warehouse"),
            "wip_warehouse": row.get("wip_warehouse"),
            "target_warehouse": row.get("target_warehouse"),
        })

    mr.insert()

    if payload.get("submit"):
        mr.submit()

    frappe.db.commit()
    return {"name": mr.name, "docstatus": mr.docstatus}


# ── 4. Create Work Orders from MR (dedup-aware) ──────────────────────────────

@frappe.whitelist()
def create_work_orders(material_request):
    from cannabis_management.api.manufacturing import create_work_orders_from_mr

    wo_names = create_work_orders_from_mr(material_request) or []

    # Auto-create Job Cards for each new WO
    jc_names = []
    for wo_name in wo_names:
        jcs = _create_job_cards_for_wo(wo_name)
        jc_names.extend(jcs)

    return {
        "work_orders": wo_names,
        "job_cards": jc_names,
    }


def _create_job_cards_for_wo(work_order):
    wo = frappe.get_doc("Work Order", work_order)
    created = []

    for op_row in wo.operations:
        # Dedup: check if JC already exists for this WO + operation
        existing = frappe.db.exists("Job Card", {
            "work_order": wo.name,
            "operation": op_row.operation,
            "docstatus": ["!=", 2],
        })
        if existing:
            continue

        pending_qty = flt(wo.qty) - flt(op_row.completed_qty)
        if pending_qty <= 0:
            continue

        jc = frappe.new_doc("Job Card")
        jc.work_order = wo.name
        jc.production_item = wo.production_item
        jc.operation = op_row.operation
        jc.workstation = op_row.workstation
        jc.workstation_type = op_row.workstation_type or ""
        jc.for_quantity = pending_qty
        jc.wip_warehouse = wo.wip_warehouse
        jc.company = wo.company
        jc.bom_no = wo.bom_no
        jc.project = wo.project
        jc.batch = wo.project  # inventory dimension

        jc.flags.ignore_permissions = True
        jc.insert()
        created.append(jc.name)

    frappe.db.commit()
    return created


# ── 5. Material Transfer Preview & Execute ────────────────────────────────────

@frappe.whitelist()
def get_transfer_preview(work_order):
    wo = frappe.get_doc("Work Order", work_order)

    # Check if transfer already done
    existing_transfer = frappe.db.exists("Stock Entry", {
        "work_order": wo.name,
        "purpose": "Material Transfer for Manufacture",
        "docstatus": 1,
    })

    rows = []
    for d in wo.required_items:
        rows.append({
            "item_code": d.item_code,
            "item_name": d.item_name,
            "from_warehouse": d.source_warehouse or wo.source_warehouse,
            "to_warehouse": wo.wip_warehouse,
            "qty": flt(d.required_qty) - flt(d.transferred_qty),
            "uom": frappe.db.get_value("Item", d.item_code, "stock_uom") or "Nos",
            "transferred_qty": flt(d.transferred_qty),
            "required_qty": flt(d.required_qty),
        })

    return {
        "work_order": wo.name,
        "item_name": wo.item_name,
        "project": wo.project,
        "already_transferred": bool(existing_transfer),
        "rows": [r for r in rows if r["qty"] > 0],
    }


@frappe.whitelist()
def execute_transfer(work_order):
    from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry

    # make_stock_entry() returns stock_entry.as_dict() — a plain frappe._dict,
    # not a live Document, so it has no working .insert()/.submit()/.flags.
    # frappe.get_doc() rebuilds an actual (unsaved) Stock Entry doc from it.
    se = frappe.get_doc(make_stock_entry(work_order, "Material Transfer for Manufacture"))
    se.flags.ignore_permissions = True
    se.insert()
    se.submit()
    frappe.db.commit()

    return {"name": se.name, "docstatus": se.docstatus}


# ── 6. Job Card timer/micron state (embedded per Work Order in get_run_detail) ──

def _resolve_sub_operations(jc):
    """Sub-step names for one Job Card's operation, from the master Operation
    doctype's own Sub Operation table (Operation.sub_operations) — that's the
    only place ERPNext's data model actually stores per-operation sub-steps.
    `BOM Operation` rows are the BOM's top-level operations (e.g. "Hash
    Processing", "Rosin Pressing") and never carry sub-steps themselves, so
    they aren't consulted here.
    Returns plain {operation, time_in_mins} dicts — no timing/cost data,
    that's layered on separately by whoever calls this (_job_card_full_detail
    enriches it live; start_timer just needs the name list to validate against).
    """
    if not jc.operation:
        return []
    op_sub_ops = frappe.get_all(
        "Sub Operation",
        filters={"parent": jc.operation},
        fields=["operation", "time_in_mins"],
        order_by="idx asc",
    )
    return [{"operation": s.operation, "time_in_mins": s.time_in_mins} for s in op_sub_ops]


def _job_card_full_detail(jc):
    """Full per-Job-Card state for the wizard: base fields, per-sub-operation
    timer status (Step 4), and micron data (Step 5, for Wash/Press
    operations — `doc_hooks.job_card.validate` requires these rows before a
    Job Card of that operation can be marked Completed).
    """
    if isinstance(jc, str):
        jc = frappe.get_doc("Job Card", jc)

    item_name = frappe.db.get_value("Item", jc.production_item, "item_name") or jc.production_item
    sub_operations = _resolve_sub_operations(jc)
    assigned = _get_assignments(jc)

    employee_names = {}
    for tl in jc.time_logs:
        if tl.employee and tl.employee not in employee_names:
            employee_names[tl.employee] = frappe.db.get_value("Employee", tl.employee, "employee_name") or tl.employee

    time_logs = []
    for tl in jc.time_logs:
        time_logs.append({
            "idx": tl.idx,
            "operation": tl.operation or "",
            "employee": tl.employee or "",
            "employee_name": employee_names.get(tl.employee, "") if tl.employee else "",
            "workstation": tl.get("custom_workstation") or "",
            "ended": 1 if tl.get("custom_ended") else 0,
            "from_time": str(tl.from_time) if tl.from_time else None,
            "to_time": str(tl.to_time) if tl.to_time else None,
            "time_in_mins": flt(tl.time_in_mins),
            "completed_qty": flt(tl.completed_qty),
            "cost": flt(tl.get("custom_sub_op_cost")),
        })

    # Active timer: last time log with from_time but no to_time
    active_timer = None
    for tl in reversed(time_logs):
        if tl["from_time"] and not tl["to_time"]:
            active_timer = tl
            break

    # Roll each sub-operation's own time/cost/qty up from the matching time
    # log rows (a row's `operation` is the sub-operation it was timed under —
    # see start_timer), so each sub-step gets its own live status instead of
    # only the whole Job Card having one.
    if sub_operations:
        by_op = {}
        for tl in time_logs:
            op = tl["operation"] or jc.operation
            agg = by_op.setdefault(op, {"mins": 0.0, "cost": 0.0, "qty": 0.0, "running": False, "ended": False, "last": None})
            agg["last"] = tl
            if tl["ended"]:
                agg["ended"] = True
            agg["mins"] += tl["time_in_mins"]
            agg["cost"] += tl["cost"]
            agg["qty"] += tl["completed_qty"]
            if tl["from_time"] and not tl["to_time"]:
                agg["running"] = True

        for so in sub_operations:
            agg = by_op.get(so["operation"], {})
            so["total_mins"] = flt(agg.get("mins"))
            so["total_cost"] = flt(agg.get("cost"))
            so["completed_qty"] = flt(agg.get("qty"))
            last = agg.get("last") or {}
            so["ended"] = bool(agg.get("ended")) and not agg.get("running")
            so["employee"] = last.get("employee") or ""
            so["employee_name"] = last.get("employee_name") or ""
            so["workstation"] = last.get("workstation") or ""
            so["default_workstation"] = _default_workstation(jc, so["operation"])
            so["assigned_employee"] = assigned.get(so["operation"], "")
            so["assigned_employee_name"] = _employee_name(so["assigned_employee"])
            if agg.get("running"):
                so["status"] = "active"
            elif agg.get("mins"):
                so["status"] = "done"
            else:
                so["status"] = "pending"

    micron_rows = []
    for row in jc.get("custom_micron_collection_detail") or []:
        micron_rows.append({
            "item": row.item,
            "item_name": frappe.db.get_value("Item", row.item, "item_name") if row.item else "",
            "micron_size": row.micron_size,
            "grams_collected": flt(row.grams_collected),
            "quality_grade": row.quality_grade or "",
            "collected_by": row.collected_by or "",
            "collected_by_name": frappe.db.get_value("Employee", row.collected_by, "employee_name") if row.collected_by else "",
            "notes": row.notes or "",
        })

    return {
        "name": jc.name,
        "production_item": jc.production_item,
        "item_name": item_name,
        "operation": jc.operation,
        "workstation": jc.workstation,
        "status": jc.status,
        "for_quantity": flt(jc.for_quantity),
        "total_completed_qty": flt(jc.total_completed_qty),
        "total_time_in_mins": flt(jc.total_time_in_mins),
        "total_cost": flt(jc.get("custom_sub_op_total_cost")),
        "docstatus": jc.docstatus,
        "work_order": jc.work_order,
        "sub_operations": sub_operations,
        "active_timer": active_timer,
        "time_logs": time_logs,
        "micron_rows": micron_rows,
        "last_employee": next((tl["employee"] for tl in reversed(time_logs) if tl["employee"]), ""),
        "last_employee_name": next((tl["employee_name"] for tl in reversed(time_logs) if tl["employee"]), ""),
        "default_workstation": jc.workstation or _default_workstation(jc, jc.operation),
        "assigned_employee": assigned.get(jc.operation or "", ""),
        "assigned_employee_name": _employee_name(assigned.get(jc.operation or "", "")),
        "is_micron_op": jc.operation in MICRON_OPERATIONS,
    }


# ── 7. Timer Controls ────────────────────────────────────────────────────────

def _default_workstation(jc, operation):
    """Workstation pre-filled in the Start popup — same resolution order as
    doc_hooks.job_card.calculate_sub_op_costs: the (sub-)operation's own
    Workstation, then the Job Card's."""
    ws = frappe.db.get_value("Operation", operation, "workstation") if operation else None
    return ws or jc.workstation or ""


def _get_assignments(jc):
    """Sub-operation (or the Job Card's own operation) -> assigned Employee."""
    raw = jc.get("custom_assigned_employees")
    if not raw:
        return {}
    if isinstance(raw, str):
        try:
            raw = json.loads(raw)
        except ValueError:
            return {}
    return raw if isinstance(raw, dict) else {}


def _employee_name(employee):
    if not employee:
        return ""
    return frappe.db.get_value("Employee", employee, "employee_name") or employee


@frappe.whitelist()
def assign_employee(job_card, employee=None, operation=None):
    """Assign To: remember who should run this (sub-)operation.

    Start pre-fills its Employee with this. Passing no employee clears it.
    """
    jc = frappe.get_doc("Job Card", job_card)
    # Same access as start_timer: anyone who can run the page can assign.
    if jc.docstatus != 0:
        frappe.throw(_("Job Card must be a Draft to assign an employee."))

    operation = operation or jc.operation
    sub_op_names = [s["operation"] for s in _resolve_sub_operations(jc)]
    if sub_op_names and operation not in sub_op_names:
        frappe.throw(_("Select a valid sub-operation: {0}").format(", ".join(sub_op_names)))

    if employee and not frappe.db.exists("Employee", {"name": employee, "status": "Active"}):
        frappe.throw(_("Employee {0} is not active.").format(employee))

    assigned = _get_assignments(jc)
    if employee:
        assigned[operation] = employee
    else:
        assigned.pop(operation, None)
    jc.db_set("custom_assigned_employees", json.dumps(assigned) if assigned else None)

    return {"operation": operation, "employee": employee or "", "employee_name": _employee_name(employee)}


@frappe.whitelist()
def get_default_employee():
    return frappe.db.get_value("Employee", {"user_id": frappe.session.user, "status": "Active"}, "name") or ""


@frappe.whitelist()
def start_timer(job_card, operation=None, employee=None, from_time=None, workstation=None):
    jc = frappe.get_doc("Job Card", job_card)

    if jc.docstatus != 0:
        frappe.throw(_("Job Card must be a Draft to start a timer."))

    # Check no active timer already running
    for tl in jc.time_logs:
        if tl.from_time and not tl.to_time:
            frappe.throw(_("A timer is already running. Pause it first."))

    # When this Job Card has sub-operations, every timer must be started
    # against one of them by name — that's what lets each sub-step accrue
    # its own time/cost instead of everything landing under the parent
    # operation.
    sub_op_names = [s["operation"] for s in _resolve_sub_operations(jc)]
    if sub_op_names and operation not in sub_op_names:
        frappe.throw(_("Select a valid sub-operation to start: {0}").format(", ".join(sub_op_names)))

    if not employee:
        employee = frappe.db.get_value("Employee", {"user_id": frappe.session.user}, "name")

    jc.append("time_logs", {
        "from_time": get_datetime(from_time) if from_time else now_datetime(),
        "operation": operation or jc.operation,
        # None, never "": core's "employee is busy on another workstation"
        # check matches this value against other cards' rows, and "" would
        # match every other card that has a blank employee too.
        "employee": employee or None,
        "custom_workstation": workstation or _default_workstation(jc, operation or jc.operation),
    })

    if jc.status == "Open":
        jc.status = "Work In Progress"

    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "started", "job_card_status": jc.status}


@frappe.whitelist()
def pause_timer(job_card, to_time=None):
    jc = frappe.get_doc("Job Card", job_card)

    paused = False
    for tl in jc.time_logs:
        if tl.from_time and not tl.to_time:
            tl.to_time = get_datetime(to_time) if to_time else now_datetime()
            from_dt = get_datetime(tl.from_time)
            to_dt = get_datetime(tl.to_time)
            if to_dt < from_dt:
                frappe.throw(_("'To' must be after the time it was started."))
            tl.time_in_mins = flt((to_dt - from_dt).total_seconds() / 60, 2)
            paused = True
            break

    if not paused:
        frappe.throw(_("No active timer to pause."))

    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "paused"}


@frappe.whitelist()
def end_sub_operation(job_card, operation=None, to_time=None, completed_qty=None):
    """End a (sub-)operation: closes its running time log (at `to_time`,
    default now) if one is open, and flags the operation's latest time log
    as ended so the page shows View instead of Resume — kept on the Job Card,
    so it survives a reload. `completed_qty` (asked when this is the Job
    Card's last timer to end) lands on that time log's Completed Qty."""
    jc = frappe.get_doc("Job Card", job_card)
    if jc.docstatus != 0:
        frappe.throw(_("Job Card must be a Draft to end an operation."))
    operation = operation or jc.operation

    rows = [tl for tl in jc.time_logs if (tl.operation or jc.operation) == operation]
    if not rows:
        frappe.throw(_("{0} has not been started yet.").format(operation))

    for tl in rows:
        if tl.from_time and not tl.to_time:
            tl.to_time = get_datetime(to_time) if to_time else now_datetime()
            from_dt = get_datetime(tl.from_time)
            to_dt = get_datetime(tl.to_time)
            if to_dt < from_dt:
                frappe.throw(_("'To' must be after the time it was started."))
            tl.time_in_mins = flt((to_dt - from_dt).total_seconds() / 60, 2)

    rows[-1].custom_ended = 1
    if completed_qty not in (None, ""):
        if flt(completed_qty) < 0:
            frappe.throw(_("Completed Qty cannot be negative."))
        rows[-1].completed_qty = flt(completed_qty)

    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "ended"}


@frappe.whitelist()
def update_time_log_row(job_card, idx, from_time, to_time, workstation=None):
    """Manually correct one existing, already-closed time log row's From/To
    and Workstation — used by the "View" popup's editable mode. The
    still-running row (if any) can't be edited here; pause it first. The
    row's cost follows the workstation (doc_hooks.job_card recomputes it on
    save).
    """
    jc = frappe.get_doc("Job Card", job_card)
    idx = int(idx)

    row = next((tl for tl in jc.time_logs if tl.idx == idx), None)
    if not row:
        frappe.throw(_("Time log row not found."))
    if row.from_time and not row.to_time:
        frappe.throw(_("Pause the running timer before editing its time."))

    new_from = get_datetime(from_time)
    new_to = get_datetime(to_time)
    if new_to < new_from:
        frappe.throw(_("'To' must be after 'From'."))

    row.from_time = new_from
    row.to_time = new_to
    if workstation is not None:
        if workstation and not frappe.db.exists("Workstation", workstation):
            frappe.throw(_("Workstation {0} does not exist.").format(workstation))
        row.custom_workstation = workstation or None

    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "updated", "idx": idx}


@frappe.whitelist()
def complete_sub_operation(job_card, completed_qty=0, operation=None):
    jc = frappe.get_doc("Job Card", job_card)

    # Pause any running timer first
    for tl in jc.time_logs:
        if tl.from_time and not tl.to_time:
            tl.to_time = now_datetime()
            from_dt = get_datetime(tl.from_time)
            to_dt = get_datetime(tl.to_time)
            tl.time_in_mins = flt((to_dt - from_dt).total_seconds() / 60, 2)
            if flt(completed_qty):
                tl.completed_qty = flt(completed_qty)
            break

    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "completed"}


# ── 8. Micron Data ────────────────────────────────────────────────────────────

@frappe.whitelist()
def save_micron_data(job_card, rows):
    if isinstance(rows, str):
        rows = json.loads(rows)

    jc = frappe.get_doc("Job Card", job_card)

    # Clear existing and re-add
    jc.set("custom_micron_collection_detail", [])

    for row in rows:
        jc.append("custom_micron_collection_detail", {
            "item": row.get("item"),
            "micron_size": row.get("micron_size"),
            "grams_collected": flt(row.get("grams_collected")),
            "quality_grade": row.get("quality_grade"),
            "collected_by": row.get("collected_by"),
            "notes": row.get("notes"),
        })

    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    frappe.db.commit()

    return {"status": "saved", "row_count": len(rows)}


# ── 9. Complete Job Card → Auto Stock Entry ──────────────────────────────────

@frappe.whitelist()
def complete_job_card(job_card, completed_qty=None):
    jc = frappe.get_doc("Job Card", job_card)

    if jc.docstatus != 0:
        frappe.throw(_("Job Card must be a Draft to complete."))

    # Pause any running timer
    for tl in jc.time_logs:
        if tl.from_time and not tl.to_time:
            tl.to_time = now_datetime()
            from_dt = get_datetime(tl.from_time)
            to_dt = get_datetime(tl.to_time)
            tl.time_in_mins = flt((to_dt - from_dt).total_seconds() / 60, 2)

    # Set completed qty on at least one row
    if completed_qty is not None:
        total_existing = sum(flt(tl.completed_qty) for tl in jc.time_logs)
        if not total_existing and jc.time_logs:
            jc.time_logs[-1].completed_qty = flt(completed_qty)

    jc.status = "Completed"
    jc.flags.ignore_mandatory = True
    jc.save(ignore_permissions=True)
    jc.submit()
    frappe.db.commit()

    # Auto-create Manufacture Stock Entry if all JCs for this WO are done
    se_result = None
    if jc.work_order:
        se_result = _auto_create_manufacture_se(jc.work_order)

    return {
        "status": "completed",
        "job_card": jc.name,
        "stock_entry": se_result,
    }


def _all_job_cards_done(wo):
    for op in wo.operations:
        open_jcs = frappe.db.count("Job Card", {
            "work_order": wo.name,
            "operation": op.operation,
            "status": ["not in", ["Completed", "Cancelled"]],
            "docstatus": ["!=", 2],
        })
        if open_jcs > 0:
            return False
    return True


def _auto_create_manufacture_se(work_order):
    wo = frappe.get_doc("Work Order", work_order)

    if not _all_job_cards_done(wo):
        return {"created": False, "reason": "Not all Job Cards are completed yet."}

    # Check if manufacture SE already exists
    existing = frappe.db.exists("Stock Entry", {
        "work_order": wo.name,
        "purpose": "Manufacture",
        "docstatus": ["!=", 2],
    })
    if existing:
        return {"created": False, "reason": "Manufacture Stock Entry already exists.", "name": existing}

    try:
        from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
        se = frappe.get_doc(make_stock_entry(wo.name, "Manufacture", wo.qty))
        se.flags.ignore_permissions = True
        se.insert()
        frappe.db.commit()
    except Exception as e:
        frappe.db.rollback()
        return {"created": False, "reason": str(e)}

    # Must be submitted, not just inserted — Work Order.produced_qty (what the
    # wizard's step logic and scoreboard read) is only updated by
    # Stock Entry.on_submit -> update_work_order_qty, never by insert alone.
    try:
        se.submit()
        frappe.db.commit()
        return {"created": True, "submitted": True, "name": se.name, "docstatus": se.docstatus}
    except Exception as e:
        frappe.db.rollback()
        return {
            "created": True, "submitted": False, "name": se.name, "docstatus": 0,
            "reason": _("Stock Entry {0} was created as Draft but could not be auto-submitted: {1}").format(se.name, e),
        }


# ── 9b. Manual "Create SKU" — preview + submit the Manufacture Stock Entry ────

@frappe.whitelist()
def get_manufacture_se_preview(work_order):
    """What the 'Create SKU' button shows before committing: the existing
    Manufacture Stock Entry for this Work Order if one's already been made
    (by this or the auto-create-on-last-job-card-complete path), otherwise a
    preview of what would be created — built the same way but never inserted.
    """
    wo = frappe.get_doc("Work Order", work_order)

    existing = frappe.db.get_value(
        "Stock Entry",
        {"work_order": wo.name, "purpose": "Manufacture", "docstatus": ["!=", 2]},
        "name",
    )
    if existing:
        se = frappe.get_doc("Stock Entry", existing)
        return {
            "existing": True,
            "not_ready": False,
            "name": se.name,
            "docstatus": se.docstatus,
            "rows": [{
                "item_code": d.item_code,
                "item_name": d.item_name,
                "qty": flt(d.qty),
                "uom": d.uom,
                "warehouse": d.t_warehouse or d.s_warehouse,
            } for d in se.items],
        }

    if not _all_job_cards_done(wo):
        return {
            "existing": False, "not_ready": True, "name": None, "docstatus": 0, "rows": [],
            "reason": _("Not all Job Cards for {0} are completed yet — finish every operation first.").format(wo.name),
        }

    from erpnext.manufacturing.doctype.work_order.work_order import make_stock_entry
    # Preview-only — read via ["items"], not .items (make_stock_entry returns
    # .as_dict(), where the attribute .items collides with dict.items()).
    se = make_stock_entry(wo.name, "Manufacture", wo.qty)
    return {
        "existing": False,
        "not_ready": False,
        "name": None,
        "docstatus": 0,
        "rows": [{
            "item_code": d.item_code,
            "item_name": d.item_name,
            "qty": flt(d.qty),
            "uom": d.uom,
            "warehouse": d.t_warehouse or d.s_warehouse,
        } for d in se["items"]],
    }


@frappe.whitelist()
def create_manufacture_se(work_order):
    """Manual counterpart to the auto-create in `complete_job_card` — lets the
    user confirm/submit from the preview modal instead of it happening
    silently. Idempotent: submits an existing draft rather than duplicating.
    """
    result = _auto_create_manufacture_se(work_order)
    if not result.get("created") and result.get("name"):
        se = frappe.get_doc("Stock Entry", result["name"])
        if se.docstatus == 0:
            se.flags.ignore_permissions = True
            se.submit()
            frappe.db.commit()
            return {"created": True, "submitted": True, "name": se.name, "docstatus": se.docstatus}
        return {
            "created": False, "submitted": True, "name": se.name, "docstatus": se.docstatus,
            "reason": _("Stock Entry {0} is already submitted.").format(se.name),
        }
    return result


# ── 10. Helpers ───────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_item_stock(item_code, warehouse=None):
    """Actual qty of an item for the Start a Run dialog: in the given
    warehouse (same as Material Request Item.actual_qty) plus the total
    across every warehouse."""
    if not item_code:
        return {"actual_qty": 0, "total_qty": 0, "stock_uom": None}
    total_qty = frappe.db.sql(
        "select coalesce(sum(actual_qty), 0) from `tabBin` where item_code = %s", item_code
    )[0][0]
    actual_qty = flt(frappe.db.get_value(
        "Bin", {"item_code": item_code, "warehouse": warehouse}, "actual_qty"
    )) if warehouse else flt(total_qty)
    return {
        "actual_qty": actual_qty,
        "total_qty": flt(total_qty),
        "stock_uom": frappe.db.get_value("Item", item_code, "stock_uom"),
    }


@frappe.whitelist()
def get_routing_operations(routing):
    if not routing:
        return []
    # Routing's own `operations` table is typed as BOM Operation (ERPNext
    # reuses that child doctype for both) — there is no separate "Routing
    # Detail" doctype.
    return frappe.get_all(
        "BOM Operation",
        filters={"parent": routing, "parenttype": "Routing"},
        fields=["operation", "workstation_type", "workstation", "time_in_mins",
                 "sequence_id"],
        order_by="idx asc",
    )


@frappe.whitelist()
def get_items_for_picker(txt=None, item_group=None):
    filters = {"disabled": 0}
    if item_group:
        filters["item_group"] = item_group

    or_filters = None
    if txt:
        or_filters = [
            ["item_name", "like", f"%{txt}%"],
            ["name", "like", f"%{txt}%"],
        ]

    return frappe.get_all(
        "Item",
        filters=filters,
        or_filters=or_filters,
        fields=["name", "item_name", "item_group", "stock_uom"],
        order_by="item_name asc",
        limit=20,
    )


@frappe.whitelist()
def submit_material_request(material_request):
    mr = frappe.get_doc("Material Request", material_request)
    if mr.docstatus != 0:
        frappe.throw(_("Only Draft Material Requests can be submitted."))
    mr.submit()
    frappe.db.commit()
    return {"name": mr.name, "docstatus": mr.docstatus}


# ── Tiering Product (Rosin Pressing) ─────────────────────────────────────────

TIERING_OPERATION = "Rosin Pressing"


def _tiering_source(work_order):
    """The Rosin Pressing Work Order a Tiering Product run draws from."""
    wo = frappe.get_doc("Work Order", work_order)
    if wo.docstatus != 1:
        frappe.throw(_("Work Order {0} is not submitted.").format(work_order))
    if not frappe.db.exists("Job Card", {"work_order": wo.name, "operation": TIERING_OPERATION}):
        frappe.throw(_("Tiering Product is only for the {0} Work Order.").format(TIERING_OPERATION))
    return wo


def _tiering_sources(wo):
    """What Create Rosin actually produced, with what is still in stock.

    The raw material is the finished goods of the Work Order's submitted
    Manufacture entry -- not wo.production_item, because the micron flow
    replaces that item with the per-micron products (T1 / T2 / T3 ...).
    """
    rows = frappe.db.sql(
        """
        SELECT d.item_code, d.item_name, d.t_warehouse AS warehouse, SUM(d.qty) AS produced_qty
        FROM `tabStock Entry Detail` d
        JOIN `tabStock Entry` se ON se.name = d.parent
        WHERE se.work_order = %s AND se.purpose = 'Manufacture' AND se.docstatus = 1
          AND d.is_finished_item = 1 AND IFNULL(d.t_warehouse, '') != ''
        GROUP BY d.item_code, d.item_name, d.t_warehouse
        ORDER BY MIN(d.idx)
        """,
        wo.name,
        as_dict=True,
    )
    if not rows:
        frappe.throw(_("Create Rosin first: {0} has no submitted Manufacture entry yet.").format(wo.name))
    for r in rows:
        r.produced_qty = flt(r.produced_qty)
        r.available_qty = flt(frappe.db.get_value(
            "Bin", {"item_code": r.item_code, "warehouse": r.warehouse}, "actual_qty"
        ))
        # What this run can tier: what it produced, as far as it is still in
        # stock. The warehouse's stock alone is not it -- other runs' output
        # of the same item sits in the same warehouse (RS00004: 400 g from
        # this run + 510.291 g from another read as 910.291).
        r.tier_qty = flt(min(r.produced_qty, r.available_qty), 3)
        r.stock_uom = frappe.db.get_value("Item", r.item_code, "stock_uom")
    return rows


@frappe.whitelist()
def make_tiering_conversion_entry(work_order):
    """Tiering Product: an unsaved Conversion Entry, opened in its own form.

    Built like make_conversion_entry builds one from a Sales Order: the
    header from the Rosin Pressing Work Order, and one Conversion Entry Item
    row per product its Manufacture entry produced -- that product as Raw
    Material 1, in the warehouse it was produced into, with what is still in
    stock. The Finished Goods, tags and quantities are then filled in on the
    standard Conversion Item table, which applies its own rules. On submit,
    submit_tiering_stock_entries submits the Repack entries it drafts.
    """
    wo, ce = _new_tiering_entry(work_order)
    for src in _tiering_sources(wo):
        if src.tier_qty <= 0:
            continue
        ce.append("items", {
            "conversion_type": "1 to 1",
            "source_warehouse": src.warehouse,
            "target_warehouse": wo.fg_warehouse or src.warehouse,
            "raw_material_1": src.item_code,
            "qty_rm_1": src.tier_qty,
        })
    if not ce.items:
        frappe.throw(_("Nothing left to tier: what {0} produced is no longer in stock.").format(wo.name))
    return ce.as_dict()


def _new_tiering_entry(work_order):
    """The Work Order and a new Conversion Entry header for it."""
    wo = _tiering_source(work_order)
    done = frappe.db.get_value("Conversion Entry", {"custom_work_order": wo.name, "docstatus": 1}, "name")
    if done:
        frappe.throw(_("{0} has already been tiered in {1}.").format(wo.name, done))
    ce = frappe.new_doc("Conversion Entry")
    ce.company = wo.company
    ce.project = wo.project
    ce.posting_date = frappe.utils.nowdate()
    ce.custom_work_order = wo.name
    return wo, ce


def _conversion_counts(conversion_type):
    """"3 to 2" -> (3, 2): raw materials and finished goods the type uses."""
    try:
        rm, fg = (int(x) for x in (conversion_type or "").split(" to "))
    except ValueError:
        return 1, 1
    return max(1, min(rm, 7)), max(1, min(fg, 3))


@frappe.whitelist()
def create_tiering_conversion(work_order, items):
    """Tiering Product, from the page: save and submit the Conversion Entry.

    `items` are Conversion Entry Item rows as filled in on the page's copy of
    the standard Conversion Item table. Only that doctype's own fields are
    taken, and -- as the Conversion Entry form does when the type changes --
    raw materials / finished goods beyond what the conversion type uses are
    cleared, so a leftover value can't slip into the Stock Entry. The entry
    then goes through its normal insert and submit (all of its validations),
    and submit_tiering_stock_entries submits the Repack entries it drafts.
    """
    wo, ce = _new_tiering_entry(work_order)
    items = frappe.parse_json(items) if isinstance(items, str) else (items or [])
    fields = {
        df.fieldname for df in frappe.get_meta("Conversion Entry Item").fields
        if df.fieldtype not in ("Section Break", "Column Break", "Tab Break")
    }
    for row in items:
        values = {k: v for k, v in (row or {}).items() if k in fields}
        if not any(values.get(f) for f in ("raw_material_1", "finished_good_1")):
            continue
        rm_count, fg_count = _conversion_counts(values.get("conversion_type"))
        for n in range(rm_count + 1, 8):
            for f in ("raw_material_{0}", "qty_rm_{0}", "rm_{0}_tag"):
                values.pop(f.format(n), None)
        for n in range(fg_count + 1, 4):
            for f in ("finished_good_{0}", "qty_fg_{0}", "fg_{0}_tag"):
                values.pop(f.format(n), None)
        ce.append("items", values)
    if not ce.items:
        frappe.throw(_("Add at least one row with a Raw Material and a Finished Good."))

    # A run tiers its own output: what Create Rosin made here, as far as it is
    # in stock -- not other runs' rosin that shares the warehouse.
    own = {src.item_code: src for src in _tiering_sources(wo)}
    used = {}
    for row in ce.items:
        for n in range(1, 8):
            code = row.get("raw_material_{0}".format(n))
            if code in own:
                used[code] = flt(used.get(code, 0) + flt(row.get("qty_rm_{0}".format(n))), 3)
    for code, qty in used.items():
        if qty > own[code].tier_qty:
            frappe.throw(
                _("{0}: {1} used, but this run has {2} of it to tier (it produced {3}).").format(
                    code, qty, own[code].tier_qty, own[code].produced_qty
                )
            )

    # Same access as the page's other actions (start_timer, complete_job_card):
    # whoever runs the page can record its output.
    ce.flags.ignore_permissions = True
    ce.insert()
    ce.submit()
    return {
        "conversion_entry": ce.name,
        "stock_entries": frappe.get_all(
            "Stock Entry",
            filters={"custom_conversion_entry_reference": ce.name, "docstatus": 1},
            pluck="name",
            order_by="creation asc",
        ),
    }


def submit_tiering_stock_entries(doc, method=None):
    """Conversion Entry on_submit: a Tiering Product entry submits its stock.

    Conversion Entry's own on_submit drafts one Repack Stock Entry per row
    (and only logs a row that fails). For an entry made by Tiering Product
    (custom_work_order set) those drafts are submitted right here, in the
    same transaction -- if one cannot be, the Conversion Entry is not
    submitted either, so the two never disagree.
    """
    if not doc.get("custom_work_order"):
        return
    drafts = frappe.get_all(
        "Stock Entry",
        filters={"custom_conversion_entry_reference": doc.name, "docstatus": 0},
        pluck="name",
        order_by="creation asc",
    )
    if len(drafts) != len(doc.items):
        frappe.throw(
            _("Only {0} of {1} Stock Entries could be created for {2}. Check the Error Log.").format(
                len(drafts), len(doc.items), doc.name
            )
        )
    for name in drafts:
        se = frappe.get_doc("Stock Entry", name)
        se.flags.ignore_permissions = True
        se.submit()
