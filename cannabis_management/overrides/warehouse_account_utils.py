"""
Item Group → Account resolution for warehouse GL entries.

Logic (exactly as specified):
  1. Look in the warehouse's custom_item_group_account_mapping child table.
  2. If the item's group has a row there → use that account.
  3. If not → fall back to the warehouse's own `account` field (system default).

Why we rebuild the warehouse leg from SLEs instead of patching gl_entries
──────────────────────────────────────────────────────────────────────────
ERPNext's StockController.get_gl_entries() merges all SLEs that share the same
account (via process_gl_map -> merge_similar_entries) before this runs. When a
Repack's source and target warehouse fall back to the same account (e.g. both
have no explicit `account` set and use the company default), their amounts net
against each other. If the net happens to be zero, core drops the row entirely
-- so there's nothing left in gl_entries to split by item group, and the whole
warehouse-side entry silently disappears. Rebuilding directly from the Stock
Ledger Entries avoids depending on what survived that merge.

Why we avoid a reverse account→warehouse map
─────────────────────────────────────────────
Multiple warehouses in a company can share the same GL account (when the
warehouse has no explicit account set and all fall back to the company default,
e.g. "Stock In Hand - MTM"). Building account_to_wh = {account: warehouse}
would lose all but one warehouse per account, causing the wrong warehouse's
mappings to be looked up. Instead we read the warehouse directly from each SLE,
which is always unambiguous.
"""

from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import flt


# ── Per-call helpers ──────────────────────────────────────────────────────────

def _get_item_group(item_code: str, cache: dict) -> str:
    if item_code not in cache:
        cache[item_code] = frappe.db.get_value("Item", item_code, "item_group") or ""
    return cache[item_code]


def _get_warehouse_mapping(warehouse: str, cache: dict) -> dict:
    """Return {item_group: account} for the warehouse child table. Cached."""
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


# ── GL entry post-processing ──────────────────────────────────────────────────

def apply_item_group_mapping(doc, gl_entries: list, warehouse_account: dict) -> list:
    """
    Rebuild the warehouse-account leg of the Stock GL entries so each item's
    stock movement posts to its item-group-mapped account (falling back to the
    warehouse's default account), instead of trying to split whatever core's
    already-merged GL list happens to still contain.

    Returns a new list; originals are not mutated.
    """
    if not warehouse_account:
        return gl_entries

    item_rows = {
        item.name: item for item in (doc.get("items") or []) if item.get("item_code")
    }
    fallback_cost_center = doc.get("cost_center") or frappe.get_cached_value(
        "Company", doc.company, "cost_center"
    )

    ig_cache = {}      # item_code → item_group
    wh_map_cache = {}  # warehouse → {item_group: account}

    sles = frappe.db.get_all(
        "Stock Ledger Entry",
        filters={
            "voucher_no": doc.name,
            "voucher_type": doc.doctype,
            "is_cancelled": 0,
        },
        fields=["voucher_detail_no", "warehouse", "stock_value_difference"],
    )

    # (resolved_account, cost_center) → net amount, plus one representative
    # item row per bucket (used for against/project/is_opening/dimensions)
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

    # Drop core's warehouse-leg entries entirely -- regenerated below from SLEs.
    # Rounding-gain/loss entries (internal stock transfer) are kept as-is.
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
