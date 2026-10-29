from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


def _get_item_group(item_code: str, cache: dict) -> str:
    if item_code not in cache:
        cache[item_code] = frappe.db.get_value("Item", item_code, "item_group") or ""
    return cache[item_code]


def _get_warehouse_mapping(warehouse: str, cache: dict) -> dict:
    if warehouse not in cache:
        rows = frappe.db.get_all(
            "Warehouse Item Group Account Mapping",
            filters={"parent": warehouse, "parenttype": "Warehouse"},
            fields=["item_group", "account"],
        )
        cache[warehouse] = {r.item_group: r.account for r in rows if r.item_group and r.account}
    return cache[warehouse]


def resolve_account(
    warehouse: str,
    item_code: str,
    fallback_account: str,
    ig_cache: dict,
    wh_map_cache: dict,
) -> str:
    item_group = _get_item_group(item_code, ig_cache)
    if not item_group:
        return fallback_account
    mapping = _get_warehouse_mapping(warehouse, wh_map_cache)
    return mapping.get(item_group, fallback_account)


def apply_item_group_mapping(doc, gl_entries: list, warehouse_account: dict) -> list:
    if not warehouse_account:
        return gl_entries

    item_rows = {
        item.name: item for item in (doc.get("items") or []) if item.get("item_code")
    }
    fallback_cost_center = doc.get("cost_center") or frappe.get_cached_value(
        "Company", doc.company, "cost_center"
    )

    ig_cache = {}
    wh_map_cache = {}

    sles = frappe.db.get_all(
        "Stock Ledger Entry",
        filters={
            "voucher_no": doc.name,
            "voucher_type": doc.doctype,
            "is_cancelled": 0,
        },
        fields=["voucher_detail_no", "warehouse", "stock_value_difference"],
    )

    agg = defaultdict(float)
    representative = {}

    for sle in sles:
        wh = sle.warehouse
        wh_acct_info = warehouse_account.get(wh)
        if not wh_acct_info:
            continue
        original_account = wh_acct_info.get("account")
        if not original_account:
            continue

        item_row = item_rows.get(sle.voucher_detail_no)
        resolved = (
            resolve_account(wh, item_row.get("item_code"), original_account, ig_cache, wh_map_cache)
            if item_row
            else original_account
        )

        cost_center = (item_row.get("cost_center") if item_row else None) or fallback_cost_center
        key = (resolved, cost_center)
        agg[key] += flt(sle.stock_value_difference)
        representative.setdefault(key, item_row)

    precision = frappe.get_precision("GL Entry", "debit_in_account_currency")
    warehouse_accounts = {
        info.get("account") for info in warehouse_account.values() if info.get("account")
    }

    rounding_remark = _("Rounding gain/loss Entry for Stock Transfer")
    kept_entries = [
        gle
        for gle in gl_entries
        if gle.get("account") not in warehouse_accounts or gle.get("remarks") == rounding_remark
    ]

    new_entries = []
    for (account, cost_center), amount in agg.items():
        amount = flt(amount, precision)
        if abs(amount) < (1.0 / (10**precision)):
            continue

        item_row = representative.get((account, cost_center))
        args = {
            "account": account,
            "against": (item_row.get("expense_account") if item_row else None),
            "cost_center": cost_center,
            "project": (item_row.get("project") if item_row else None) or doc.get("project"),
            "remarks": doc.get("remarks") or _("Accounting Entry for Stock"),
            "is_opening": (item_row.get("is_opening") if item_row else None)
            or doc.get("is_opening")
            or "No",
        }
        if amount >= 0:
            args["debit"] = amount
            args["debit_in_account_currency"] = amount
        else:
            args["credit"] = -amount
            args["credit_in_account_currency"] = -amount

        new_entries.append(doc.get_gl_dict(args, item=item_row))

    return kept_entries + new_entries

_ROW_WAREHOUSE_FIELDS = ("s_warehouse", "t_warehouse", "warehouse", "target_warehouse", "from_warehouse")


def validate_item_group_mapping(doc, method=None):
    moves = []
    for d in doc.get("items") or []:
        if not d.get("item_code"):
            continue
        for field in _ROW_WAREHOUSE_FIELDS:
            if d.get(field):
                moves.append((f"#{d.idx}", d.item_code, d.get(field)))
        if d.get("rejected_warehouse") and flt(d.get("rejected_qty")):
            moves.append((f"#{d.idx}", d.item_code, d.rejected_warehouse))
    for d in doc.get("packed_items") or []:
        if d.get("item_code") and d.get("warehouse"):
            moves.append((_("Packed #{0}").format(d.idx), d.item_code, d.warehouse))

    tables = {}
    items = {}
    missing = {}
    for row, item_code, warehouse in moves:
        if warehouse not in tables:
            rows = frappe.get_all(
                "Warehouse Item Group Account Mapping",
                filters={"parent": warehouse, "parenttype": "Warehouse"},
                fields=["item_group", "account"],
            )
            tables[warehouse] = {r.item_group: r.account for r in rows if r.item_group} if rows else None
        table = tables[warehouse]
        if table is None:
            continue
        if item_code not in items:
            items[item_code] = frappe.db.get_value("Item", item_code, ["item_group", "is_stock_item"]) or ("", 0)
        item_group, is_stock_item = items[item_code]
        if not is_stock_item or table.get(item_group):
            continue
        entry = missing.setdefault((warehouse, item_group), {
            "rows": [], "items": [],
            "reason": _("no Account set") if item_group in table else _("not in the table"),
        })
        if row not in entry["rows"]:
            entry["rows"].append(row)
        if item_code not in entry["items"]:
            entry["items"].append(item_code)

    if not missing:
        return

    lines = "".join(
        "<tr><td>{rows}</td><td>{items}</td><td><b>{group}</b></td><td>{wh}</td><td>{reason}</td></tr>".format(
            rows=", ".join(e["rows"]),
            items=", ".join(frappe.bold(i) for i in e["items"]),
            group=frappe.utils.escape_html(item_group or _("(no Item Group)")),
            wh=frappe.utils.get_link_to_form("Warehouse", warehouse),
            reason=e["reason"],
        )
        for (warehouse, item_group), e in missing.items()
    )
    frappe.throw(
        _("These Item Groups are missing from the Warehouse's Item Group Account Mapping table:")
        + "<table class='table table-bordered' style='margin-top:8px'>"
        + "<tr><th>{0}</th><th>{1}</th><th>{2}</th><th>{3}</th><th></th></tr>".format(
            _("Row"), _("Item"), _("Item Group"), _("Warehouse"))
        + lines + "</table>"
        + _("Add each Item Group with its Account to the Warehouse's Item Group Account Mapping, then submit again."),
        title=_("Item Group Account Mapping Missing"),
    )
