"""
Item Group → Account resolution for warehouse GL entries.

Logic (exactly as specified):
  1. Look in the warehouse's custom_item_group_account_mapping child table.
  2. If the item's group has a row there → use that account.
  3. If not → fall back to the warehouse's own `account` field (system default).

Why we query SLEs instead of using voucher_detail_no on GL entries
──────────────────────────────────────────────────────────────────
ERPNext's StockController.get_gl_entries() calls process_gl_map() internally,
which runs merge_similar_entries(). That collapses entries sharing the same
account + cost_center into one row and nulls voucher_detail_no. By the time
apply_item_group_mapping() sees the list, every warehouse entry is already a
single merged row with voucher_detail_no=NULL. We work around this by querying
the Stock Ledger Entries from the DB — they carry correct voucher_detail_no
values and are available because make_gl_entries() is called after SLE creation.

Why we avoid a reverse account→warehouse map
─────────────────────────────────────────────
Multiple warehouses in a company can share the same GL account (when the
warehouse has no explicit account set and all fall back to the company default,
e.g. "Stock In Hand - MTM"). Building account_to_wh = {account: warehouse}
would lose all but one warehouse per account, causing the wrong warehouse's
mappings to be looked up. Instead we read the warehouse directly from each SLE,
which is always unambiguous.
"""

import copy
from collections import defaultdict

import frappe
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
    Split any merged warehouse GL entry that spans multiple item groups with
    different mapped accounts.

    Returns a new list; originals are not mutated.
    """
    if not warehouse_account:
        return gl_entries

    # Build item_code lookup: child row name → item_code
    item_code_map = {
        item.name: item.item_code
        for item in (doc.get("items") or [])
        if item.item_code
    }

    ig_cache    = {}  # item_code → item_group
    wh_map_cache = {}  # warehouse → {item_group: account}

    # Query SLEs — they retain per-item voucher_detail_no after submission
    sles = frappe.db.get_all(
        "Stock Ledger Entry",
        filters={
            "voucher_no":   doc.name,
            "voucher_type": doc.doctype,
            "is_cancelled": 0,
        },
        fields=["voucher_detail_no", "warehouse", "stock_value_difference"],
    )

    # Build: original_account → {resolved_account → total_amount}
    # Drive entirely from SLE.warehouse — never reverse-map from account→warehouse,
    # because multiple warehouses may share the same company-default GL account.
    splits_by_account   = {}           # str → defaultdict(float)
    sle_total_by_account = defaultdict(float)

    for sle in sles:
        wh = sle.warehouse
        wh_acct_info = warehouse_account.get(wh)
        if not wh_acct_info:
            continue
        original_account = wh_acct_info.get("account")
        if not original_account:
            continue

        # Skip warehouses with no custom mapping rows at all
        if not _get_warehouse_mapping(wh, wh_map_cache):
            continue

        amount = flt(sle.stock_value_difference)
        sle_total_by_account[original_account] += amount

        item_code = item_code_map.get(sle.voucher_detail_no)
        if not item_code:
            # No item match → tracked as remainder, stays in original account
            continue

        resolved = resolve_account(wh, item_code, original_account, ig_cache, wh_map_cache)

        if original_account not in splits_by_account:
            splits_by_account[original_account] = defaultdict(float)
        splits_by_account[original_account][resolved] += amount

    # Only process accounts where at least one item maps to a *different* account
    accounts_to_split = {
        acc: d
        for acc, d in splits_by_account.items()
        if any(resolved != acc for resolved in d)
    }

    if not accounts_to_split:
        return gl_entries

    # Rebuild the GL entry list
    new_entries = []
    for gle in gl_entries:
        account = gle.get("account")
        splits  = accounts_to_split.get(account)

        if not splits:
            new_entries.append(gle)
            continue

        # Absorb SLEs with no item match into the original account bucket
        mapped_total = sum(splits.values())
        sle_total    = sle_total_by_account.get(account, 0.0)
        remainder    = sle_total - mapped_total
        if abs(remainder) > 0.0001:
            splits[account] += remainder

        # Absorb any valuation-rate rounding difference between GL and SLEs
        gle_net      = flt(gle.get("debit", 0)) - flt(gle.get("credit", 0))
        gl_sle_diff  = gle_net - sle_total
        if abs(gl_sle_diff) > 0.0001:
            splits[account] += gl_sle_diff

        # Emit one GL entry per resolved account
        for resolved_acc, amount in splits.items():
            if abs(amount) < 0.0001:
                continue
            new_gle = copy.copy(gle)
            new_gle["account"] = resolved_acc
            if resolved_acc != account:
                new_gle["account_currency"] = (
                    frappe.db.get_value("Account", resolved_acc, "account_currency")
                    or gle.get("account_currency")
                )
            if amount >= 0:
                new_gle["debit"]                     = amount
                new_gle["debit_in_account_currency"]  = amount
                new_gle["credit"]                    = 0.0
                new_gle["credit_in_account_currency"] = 0.0
            else:
                new_gle["debit"]                     = 0.0
                new_gle["debit_in_account_currency"]  = 0.0
                new_gle["credit"]                    = -amount
                new_gle["credit_in_account_currency"] = -amount
            new_entries.append(new_gle)

    return new_entries
