import frappe
from frappe import _
from frappe.utils import flt


@frappe.whitelist()
def create_work_orders_from_mr(material_request):
    mr = frappe.get_doc("Material Request", material_request)

    if mr.docstatus != 1:
        frappe.throw(_("Material Request must be submitted."))

    if mr.material_request_type != "Manufacture":
        frappe.throw(_("Material Request type must be Manufacture."))

    boms = frappe.get_all(
        "BOM",
        filters={
            "custom_material_request": mr.name,
            "docstatus": 1,
            "is_active": 1,
        },
        fields=["name", "item", "quantity", "uom"],
        order_by="creation asc",
    )

    # Fallback: find BOMs by FG item from custom_finished_goods
    if not boms:
        fg_items = [row.item for row in mr.custom_finished_goods if row.item]
        if fg_items:
            boms = frappe.get_all(
                "BOM",
                filters={
                    "item": ["in", fg_items],
                    "docstatus": 1,
                    "is_active": 1,
                },
                fields=["name", "item", "quantity", "uom"],
                order_by="creation asc",
            )

    if not boms:
        frappe.throw(
            _("No active BOMs found linked to this Material Request. "
              "Submit the MR first to auto-create BOMs.")
        )

    # BOMs that already have a Work Order — skip those, create only missing ones
    existing_wo_boms = set(frappe.get_all(
        "Work Order",
        filters={"material_request": mr.name, "docstatus": ["!=", 2]},
        pluck="bom_no",
    ))

    # Build FG map: qty + warehouses
    fg_map = {}
    for row in mr.custom_finished_goods:
        fg_map[row.item] = {
            "grams": flt(row.finished_qty_grams),
            "pounds": flt(row.finished_qty_pounds),
            "source_warehouse": row.get("source_warehouse"),
            "wip_warehouse": row.get("wip_warehouse"),
            "target_warehouse": row.get("target_warehouse"),
        }

    default_fg_warehouse = frappe.db.get_single_value(
        "Manufacturing Settings", "default_fg_warehouse"
    ) or ""

    # Number of ops in the routing cycle — used to detect when each RM chain restarts
    n_ops = 1
    if mr.custom_routing:
        routing_doc = frappe.get_doc("Routing", mr.custom_routing)
        n_ops = len(routing_doc.operations) or 1

    created = []
    bom_index = 0

    for bom in boms:
        if bom.name in existing_wo_boms:
            frappe.msgprint(
                _("Work Order already exists for BOM {0} — skipping.").format(bom.name),
                alert=True,
            )
            continue

        fg_info = fg_map.get(bom.item, {})
        qty = fg_info.get("grams") or bom.quantity

        wo = frappe.new_doc("Work Order")
        wo.production_item = bom.item
        wo.bom_no = bom.name
        wo.qty = qty
        wo.custom_expected_yield_qty = qty
        wo.company = mr.company
        wo.project = mr.custom_project
        wo.material_request = mr.name
        wo.use_multi_level_bom = 0
        wo.skip_transfer = 0

        # Op 1 of each RM cycle → raw materials from MR.set_warehouse
        # Op 2..N of each cycle → intermediate FG from default_fg_warehouse
        if bom_index % n_ops == 0:
            wo.source_warehouse = fg_info.get("source_warehouse") or mr.set_warehouse or ""
        else:
            wo.source_warehouse = fg_info.get("source_warehouse") or default_fg_warehouse
        wo.wip_warehouse = fg_info.get("wip_warehouse") or ""
        wo.fg_warehouse = fg_info.get("target_warehouse") or ""

        bom_index += 1

        # Populate operations + required items from BOM
        bom_doc = frappe.get_doc("BOM", bom.name)

        for bom_op in bom_doc.operations:
            # Debug: see what's actually in the BOM operation
            frappe.errprint(f"BOM Op: operation={bom_op.operation}, "
                           f"workstation={bom_op.workstation}, "
                           f"workstation_type={bom_op.workstation_type}")

            workstation = bom_op.workstation or ""
            if not workstation and bom_op.workstation_type:
                workstation = frappe.db.get_value(
                    "Workstation",
                    {"workstation_type": bom_op.workstation_type},
                    "name"
                ) or ""
                frappe.errprint(f"Resolved workstation from type '{bom_op.workstation_type}': '{workstation}'")

            # If still empty, the workstation_type might BE the workstation name
            if not workstation and bom_op.workstation_type:
                if frappe.db.exists("Workstation", bom_op.workstation_type):
                    workstation = bom_op.workstation_type
                    frappe.errprint(f"workstation_type IS the workstation: '{workstation}'")

            frappe.errprint(f"Final workstation for WO: '{workstation}'")

            wo.append("operations", {
                "operation": bom_op.operation,
                "workstation_type": bom_op.workstation_type or "",
                "workstation": workstation,
                "time_in_mins": bom_op.time_in_mins or 60,
                "bom": bom.name,
            })

        wo.flags.ignore_permissions = True
        wo.insert()
        wo.submit()

        created.append(wo.name)

        frappe.msgprint(
            _("Work Order <b>{0}</b> created for {1} ({2} {3})").format(
                wo.name, bom.item, qty, bom.uom
            ),
            alert=True,
        )

    frappe.db.commit()
    return created