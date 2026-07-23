import frappe
from frappe import _
from frappe.utils import flt


def before_validate(doc, method=None):
    """
    Keep a manually-rated Repack finished-good row internally consistent
    BEFORE core's set_basic_rate()/distribute_additional_costs() run.

    When set_basic_rate_manually is checked, core skips recalculating that
    row's basic_rate *and* basic_amount (same skipped code block) -- but it
    still later recomputes amount = basic_amount + additional_cost using
    whatever basic_amount happens to already be stored. If the user just
    edited Amount (or Rate) and basic_amount wasn't refreshed to match, that
    stale basic_amount silently overwrites their edit back to the old value.
    Sync basic_amount here so core's recompute lands on the value the user
    actually intended, however they edited the row.
    """
    if doc.stock_entry_type != "Repack":
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
            # Amount was hand-edited this save -- treat it as the source of
            # truth and derive rate/basic_amount from it.
            if flt(item.qty):
                item.basic_rate = flt(item.amount) / flt(item.qty)
            item.basic_amount = flt(item.amount)
        else:
            # Nothing changed, or the user edited Rate instead -- keep
            # basic_amount in step with basic_rate.
            item.basic_amount = flt(item.qty) * flt(item.basic_rate)


def validate(doc, method):
    """
    For any stock entry where material is going out (s_warehouse is set),
    if an item row has custom_project_mandatory checked:
    1. Ensure the project field is filled
    2. Fetch the available project qty from Stock Ledger Entry
    3. Block submission if qty exceeds available project qty
    """
    _pin_rm_qty_to_work_order(doc)

    for item in doc.items:
        if not item.custom_project_mandatory:
            continue

        # Only validate items where material is going out (source warehouse is set)
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

    # Calculate Total Quantity for finished goods only
    doc.total_quantity = sum(item.qty for item in doc.items if item.get("is_finished_item"))

    # ── For Repack: Match Valuation and Allow Zero Rates ──
    if doc.stock_entry_type == "Repack":
        # Items across different item groups get different Difference Accounts
        # (expense_account) from their Item Defaults. That mismatch alone posts
        # a GL entry for the account difference, on top of the real item-group
        # inventory-account movement. Force one shared Difference Account per
        # Repack so that leg only ever reflects a genuine RM/FG valuation gap.
        unify_repack_difference_account(doc)

        # ERPNext's set_basic_rate() (core, runs before this hook) recomputes an
        # incoming row's rate/amount from the outgoing cost every single save,
        # unless set_basic_rate_manually is checked on that row -- overwriting
        # any amount the user just typed. Flip it on automatically so a manual
        # edit sticks from the next save onward, without the user having to
        # find and check that box themselves.
        for item in doc.items:
            if item.t_warehouse and not item.s_warehouse:
                item.set_basic_rate_manually = 1

        if doc.get("custom_rosin_recording_reference"):
            # First: allow zero rate for outgoing items
            for item in doc.items:
                if item.s_warehouse and not item.t_warehouse:
                    item.allow_zero_valuation_rate = 1

            # Second: distribute the input value (even if 0) across outputs,
            # skipping any finished-good row the user has manually rated.
            set_repack_valuation(doc)


def _pin_rm_qty_to_work_order(doc):
    """
    For Manufacture SEs linked to a Work Order: keep every raw-material row's
    qty at the WO's planned required_qty instead of ERPNext's proportionally
    scaled value (which grows when actual FG > expected FG).
    """
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
            continue  # already correct, skip recalc
        item.qty = pinned_qty
        item.transfer_qty = flt(pinned_qty) * flt(item.conversion_factor or 1)
        item.basic_amount = flt(pinned_qty) * flt(item.basic_rate)
        item.amount = flt(pinned_qty) * flt(item.valuation_rate or item.basic_rate)


def unify_repack_difference_account(doc):
    """
    Force every item row in a Repack entry onto one shared Difference Account
    (expense_account), instead of each item's own Item Default (which varies
    by item group). With a shared account, the Difference Account GL leg nets
    to zero when RM value == FG value, and only shows a real amount when
    there's a genuine valuation gap -- matching what "Difference Account" is
    meant to represent, rather than an artifact of different item defaults.
    """
    shared_account = frappe.get_cached_value(
        "Company", doc.company, "stock_adjustment_account"
    ) or next((item.expense_account for item in doc.items if item.expense_account), None)

    if not shared_account:
        return

    for item in doc.items:
        item.expense_account = shared_account


def set_repack_valuation(doc):
    """
    Custom valuation for Rosin Repack entries.
    Formula applied per 'block' (1 Raw Material followed by N Finished Goods).
    Example block: $1,808.50 RM / 563 total FG qty = $3.21 basic rate assigned to those specific FG rows.
    """
    from frappe.utils import flt
    
    blocks = []
    current_block = None
    
    # 1. Group items into clusters (1 Raw Material -> Many Finished Goods)
    for item in doc.items:
        if item.s_warehouse and not item.t_warehouse:
            # Start of a new yield operation
            current_block = {
                "rm_item": item,
                "fg_items": []
            }
            blocks.append(current_block)
        elif item.t_warehouse and not item.s_warehouse:
            if current_block is not None:
                current_block["fg_items"].append(item)
                
    # 2. Calculate and assign valuation rate per cluster independently
    for block in blocks:
        rm_item = block["rm_item"]
        fg_items = block["fg_items"]
        
        # Calculate Raw Material Amount
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

        # Rows the user has manually rated keep their own amount; only the
        # remaining pool (RM value minus what's manually assigned) gets
        # divided across the still-automatic finished goods.
        manual_fg = [fg for fg in fg_items if fg.get("set_basic_rate_manually")]
        auto_fg = [fg for fg in fg_items if not fg.get("set_basic_rate_manually")]
        remaining_amount = rm_amount - sum(flt(fg.amount) for fg in manual_fg)

        # Divide amount among this block's specific finished goods
        sum_fg_qty = sum(flt(fg.qty) for fg in auto_fg)
        if sum_fg_qty > 0:
            new_rate = remaining_amount / sum_fg_qty
            for fg in auto_fg:
                fg.basic_rate = flt(new_rate, 4)
                fg.amount = flt(fg.qty) * fg.basic_rate



@frappe.whitelist()
def get_project_qty(item_code, warehouse, project):
    """
    Get the available qty for an Item in a specific Warehouse and Project
    by summing actual_qty from Stock Ledger Entry.
    """
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
    """Return {item_code: required_qty} for a Work Order's raw material rows."""
    rows = frappe.get_all(
        "Work Order Item",
        filters={"parent": work_order},
        fields=["item_code", "required_qty"],
    )
    return {r.item_code: flt(r.required_qty) for r in rows if flt(r.required_qty) > 0}