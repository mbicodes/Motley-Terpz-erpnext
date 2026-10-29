import frappe
from frappe import _
from frappe.utils import flt


def is_conversion_repack(doc) -> bool:
    return doc.stock_entry_type == "Repack" and bool(
        doc.get("custom_conversion_entry_reference")
    )


def before_validate(doc, method=None):
    if doc.stock_entry_type != "Repack":
        return

    if is_conversion_repack(doc):
        _pin_conversion_fg_rows(doc)
        return

    before = doc.get_doc_before_save()
    before_items = {i.name: i for i in (before.items if before else [])}

    for item in doc.items:
        if not (item.t_warehouse and not item.s_warehouse):
            continue
        if not item.get("set_basic_rate_manually"):
            continue

        prev = before_items.get(item.name)
        if prev and flt(item.amount) != flt(prev.amount):
            if flt(item.qty):
                item.basic_rate = flt(item.amount) / flt(item.qty)
            item.basic_amount = flt(item.amount)
        else:
            item.basic_amount = flt(item.qty) * flt(item.basic_rate)


def validate(doc, method):
    _pin_rm_qty_to_work_order(doc)

    for item in doc.items:
        if not item.custom_project_mandatory:
            continue

        if not item.s_warehouse:
            continue

        if not item.project:
            frappe.throw(
                _("Row {0}: Project is mandatory for Item {1} as 'Project Mandatory' is checked").format(
                    item.idx, frappe.bold(item.item_code)
                )
            )

        available_qty = get_project_qty(item.item_code, item.s_warehouse, item.project)
        item.custom_project_back_qty = available_qty

        if item.qty > available_qty:
            frappe.throw(
                _("Row {0}: Qty ({1}) exceeds available Project Qty ({2}) for Item {3}, "
                  "Project {4}, Warehouse {5}").format(
                    item.idx,
                    frappe.bold(item.qty),
                    frappe.bold(available_qty),
                    frappe.bold(item.item_code),
                    frappe.bold(item.project),
                    frappe.bold(item.s_warehouse),
                )
            )

    doc.total_quantity = sum(item.qty for item in doc.items if item.get("is_finished_item"))

    if doc.stock_entry_type == "Repack":
        unify_repack_difference_account(doc)

        if is_conversion_repack(doc):
            rebalance_conversion_repack(doc)
            return

        for item in doc.items:
            if item.t_warehouse and not item.s_warehouse:
                item.set_basic_rate_manually = 1

        if doc.get("custom_rosin_recording_reference"):
            for item in doc.items:
                if item.s_warehouse and not item.t_warehouse:
                    item.allow_zero_valuation_rate = 1

            set_repack_valuation(doc)


def _pin_conversion_fg_rows(doc):
    for item in doc.items:
        if item.t_warehouse and not item.s_warehouse:
            item.set_basic_rate_manually = 1


def rebalance_conversion_repack(doc):
    _pin_conversion_fg_rows(doc)

    outgoing = [d for d in doc.items if d.s_warehouse and not d.t_warehouse]
    finished = [d for d in doc.items if d.t_warehouse and not d.s_warehouse]
    if not finished:
        return

    total_outgoing = sum(flt(d.basic_amount) for d in outgoing)
    total_fg_qty = sum(flt(d.transfer_qty) for d in finished)
    if total_fg_qty <= 0:
        return

    precision = finished[0].precision("basic_amount")
    assigned = 0.0

    for index, item in enumerate(finished):
        if index == len(finished) - 1:
            amount = flt(total_outgoing - assigned, precision)
        else:
            amount = flt(total_outgoing * flt(item.transfer_qty) / total_fg_qty, precision)
        assigned += amount

        item.basic_amount = amount
        item.basic_rate = amount / flt(item.transfer_qty) if flt(item.transfer_qty) else 0.0

    doc.distribute_additional_costs()
    doc.update_valuation_rate()
    doc.set_total_incoming_outgoing_value()
    doc.set_total_amount()


def _pin_rm_qty_to_work_order(doc):
    if doc.stock_entry_type != "Manufacture":
        return
    wo_name = doc.get("work_order")
    if not wo_name:
        return

    planned = {
        row.item_code: flt(row.required_qty)
        for row in frappe.get_all(
            "Work Order Item",
            filters={"parent": wo_name},
            fields=["item_code", "required_qty"],
        )
        if flt(row.required_qty) > 0
    }
    if not planned:
        return

    for item in doc.items:
        if item.is_finished_item or item.is_scrap_item:
            continue
        if not item.s_warehouse:
            continue
        pinned_qty = planned.get(item.item_code)
        if pinned_qty is None:
            continue
        if flt(item.qty) == pinned_qty:
            continue
        item.qty = pinned_qty
        item.transfer_qty = flt(pinned_qty) * flt(item.conversion_factor or 1)
        item.basic_amount = flt(pinned_qty) * flt(item.basic_rate)
        item.amount = flt(pinned_qty) * flt(item.valuation_rate or item.basic_rate)


def unify_repack_difference_account(doc):
    shared_account = frappe.get_cached_value(
        "Company", doc.company, "stock_adjustment_account"
    ) or next((item.expense_account for item in doc.items if item.expense_account), None)

    if not shared_account:
        return

    for item in doc.items:
        item.expense_account = shared_account


def set_repack_valuation(doc):
    from frappe.utils import flt

    blocks = []
    current_block = None

    for item in doc.items:
        if item.s_warehouse and not item.t_warehouse:
            current_block = {
                "rm_item": item,
                "fg_items": []
            }
            blocks.append(current_block)
        elif item.t_warehouse and not item.s_warehouse:
            if current_block is not None:
                current_block["fg_items"].append(item)

    for block in blocks:
        rm_item = block["rm_item"]
        fg_items = block["fg_items"]

        rate = flt(rm_item.valuation_rate)
        if rate <= 0:
            rate = flt(frappe.db.get_value("Stock Ledger Entry", {
                "item_code": rm_item.item_code,
                "warehouse": rm_item.s_warehouse,
                "is_cancelled": 0
            }, "valuation_rate", order_by="posting_date desc, creation desc"))

        rm_item.basic_rate = rate
        rm_amount = flt(rm_item.qty) * rate
        rm_item.amount = rm_amount

        manual_fg = [fg for fg in fg_items if fg.get("set_basic_rate_manually")]
        auto_fg = [fg for fg in fg_items if not fg.get("set_basic_rate_manually")]
        remaining_amount = rm_amount - sum(flt(fg.amount) for fg in manual_fg)

        sum_fg_qty = sum(flt(fg.qty) for fg in auto_fg)
        if sum_fg_qty > 0:
            new_rate = remaining_amount / sum_fg_qty
            for fg in auto_fg:
                fg.basic_rate = flt(new_rate, 4)
                fg.amount = flt(fg.qty) * fg.basic_rate


@frappe.whitelist()
def get_project_qty(item_code, warehouse, project):
    result = frappe.db.sql(
        """
        SELECT IFNULL(SUM(actual_qty), 0) as qty
        FROM `tabStock Ledger Entry`
        WHERE item_code = %s
          AND warehouse = %s
          AND project = %s
          AND is_cancelled = 0
        """,
        (item_code, warehouse, project),
        as_dict=True,
    )

    return result[0].qty if result else 0


@frappe.whitelist()
def get_wo_rm_planned_qty(work_order):
    rows = frappe.get_all(
        "Work Order Item",
        filters={"parent": work_order},
        fields=["item_code", "required_qty"],
    )
    return {r.item_code: flt(r.required_qty) for r in rows if flt(r.required_qty) > 0}
