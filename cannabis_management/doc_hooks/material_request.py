import frappe
from frappe import _
from frappe.utils import flt

LBS_TO_GRAM = 453.592


def validate(doc, method=None):
    if doc.work_order and not doc.set_warehouse:
        src = frappe.db.get_value("Work Order", doc.work_order, "source_warehouse")
        if src:
            doc.set_warehouse = src


def on_submit(doc, method=None):
    if not doc.custom_finished_goods or not doc.items:
        return

    _create_boms_from_mr(doc)


def _create_boms_from_mr(doc):
    """
    Each RM chains through the full routing sequence.

    Routing: Wash → Press → QC  (3 operations)
    RM items: A, B

    FG grid (must be RM_count × op_count = 6 rows):
      Row 1: D  (Wash)     ← for RM A
      Row 2: E  (Press)
      Row 3: F  (QC)
      Row 4: G  (Wash)     ← for RM B
      Row 5: H  (Press)
      Row 6: I  (QC)

    BOMs created:
      A → D (Wash)
      D → E (Press)
      E → F (QC)
      B → G (Wash)
      G → H (Press)
      H → I (QC)
    """

    # ── Get routing operations in sequence ──
    if not doc.custom_routing:
        frappe.throw(_("Routing is required for Manufacture requests."))

    routing_doc = frappe.get_doc("Routing", doc.custom_routing)
    routing_ops = sorted(routing_doc.operations, key=lambda r: r.idx)

    if not routing_ops:
        frappe.throw(_("Routing '{0}' has no operations.").format(doc.custom_routing))

    n_ops = len(routing_ops)
    n_rms = len(doc.items)
    n_fgs = len(doc.custom_finished_goods)
    expected_fgs = n_rms * n_ops

    if n_fgs != expected_fgs:
        frappe.throw(
            _("Expected {0} Finished Goods rows ({1} raw materials × {2} operations) "
              "but found {3}.").format(expected_fgs, n_rms, n_ops, n_fgs)
        )

    # ── Create BOMs: one chain per RM ──
    fg_rows = list(doc.custom_finished_goods)

    for rm_idx, rm_row in enumerate(doc.items):
        rm_item_code = rm_row.item_code
        rm_uom = frappe.db.get_value("Item", rm_item_code, "stock_uom") or "LBS"

        # This RM's FG slice
        fg_slice = fg_rows[rm_idx * n_ops : (rm_idx + 1) * n_ops]

        # Track the input item for chaining
        input_item = rm_item_code
        input_uom = rm_uom

        for op_idx, fg_row in enumerate(fg_slice):
            fg_item = fg_row.item
            routing_op = routing_ops[op_idx]
            operation = routing_op.operation
            yield_pct = flt(fg_row.expected_yield_)

            if not yield_pct:
                frappe.throw(
                    _("Finished Goods row {0}: Expected Yield cannot be zero for {1}").format(
                        fg_row.idx, fg_item
                    )
                )

            fg_uom = frappe.db.get_value("Item", fg_item, "stock_uom") or "Gram"
            yield_fraction = yield_pct / 100.0

            # RM qty needed to produce 1 unit of FG
            if input_uom == "LBS":
                bom_rm_qty = (1.0 / yield_fraction) / LBS_TO_GRAM
            else:
                bom_rm_qty = 1.0 / yield_fraction

            # Workstation from Routing row
            workstation_type = routing_op.workstation_type or ""
            workstation = getattr(routing_op, "workstation", "") or ""

            # Reuse any existing active BOM for this FG + RM combination
            existing_bom = _find_existing_bom(fg_item, input_item)
            if existing_bom:
                frappe.msgprint(
                    _("BOM <b>{0}</b> already exists for {1} ← {2} — reusing.").format(
                        existing_bom, fg_item, input_item
                    ),
                    alert=True,
                )
                input_item = fg_item
                input_uom = fg_uom
                continue

            # ── Create BOM ──
            bom = frappe.new_doc("BOM")
            bom.item = fg_item
            bom.quantity = 1
            bom.uom = fg_uom
            bom.company = doc.company
            bom.with_operations = 1
            bom.custom_material_request = doc.name
            bom.project = ""   # prevent ERPNext from auto-fetching project from linked docs

            bom.append("items", {
                "item_code": input_item,
                "qty": bom_rm_qty,
                "uom": input_uom,
                "stock_uom": input_uom,
                "include_item_in_manufacturing": 1,
            })

            bom.append("operations", {
                "operation": operation,
                "workstation_type": workstation_type,
                "workstation": workstation,
                "time_in_mins": routing_op.time_in_mins or 60,
            })

            bom.flags.ignore_permissions = True
            bom.insert()
            bom.submit()

            frappe.msgprint(
                _("BOM <b>{0}</b>: {1} → {2} ({3})").format(
                    bom.name, input_item, fg_item, operation
                ),
                alert=True,
            )

            input_item = fg_item
            input_uom = fg_uom


def _find_existing_bom(fg_item, rm_item):
    """Return the name of an existing active BOM for fg_item that uses rm_item
    as its sole raw material input, or None if no such BOM exists."""
    result = frappe.db.sql("""
        SELECT b.name
        FROM `tabBOM` b
        INNER JOIN `tabBOM Item` bi ON bi.parent = b.name
        WHERE b.item       = %s
          AND bi.item_code = %s
          AND b.docstatus  = 1
          AND b.is_active  = 1
        ORDER BY b.modified DESC
        LIMIT 1
    """, (fg_item, rm_item))
    return result[0][0] if result else None