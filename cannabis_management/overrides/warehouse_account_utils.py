"""
Item Group → Account resolution for warehouse GL entries.

Logic (exactly as specified):
  1. Look in the warehouse's custom_item_group_account_mapping child table.
  2. If the item's group has a row there → use that account.
  3. If not → fall back to the warehouse's own `account` field (system default).

All lookups are cached per-call via plain dicts passed by the caller,
preventing N+1 queries on multi-line transactions.
"""

import copy
import frappe
from frappe.utils import flt


# ── Per-call helpers ──────────────────────────────────────────────────────────

def _get_item_group(item_code: str, cache: dict) -> str:
    """item_code → item_group, cached in caller-supplied dict."""
    if item_code not in cache:
        cache[item_code] = (
            frappe.db.get_value("Item", item_code, "item_group") or ""
        )
    return cache[item_code]


def _get_warehouse_mapping(warehouse: str, cache: dict) -> dict:
    """
    Return {item_group: account} for the warehouse's child table.
    Empty dict when the table has no rows.
    Cached in caller-supplied dict.
    """
    if warehouse not in cache:
        rows = frappe.db.get_all(
            "Warehouse Item Group Account Mapping",
            filters={"parent": warehouse, "parenttype": "Warehouse"},
            fields=["item_group", "account"],
        )
        cache[warehouse] = {r.item_group: r.account for r in rows if r.item_group and r.account}
    return cache[warehouse]


def _get_warehouse_default_account(warehouse: str, cache: dict) -> str:
    """
    Return the warehouse's own `account` field (ERPNext default behaviour).
    Cached in caller-supplied dict.
    """
    key = f"__default__{warehouse}"
    if key not in cache:
        cache[key] = frappe.db.get_value("Warehouse", warehouse, "account") or ""
    return cache[key]


def resolve_account(
    warehouse: str,
    item_code: str,
    fallback_account: str,
    ig_cache: dict,
    wh_map_cache: dict,
) -> str:
    """
    Main resolution function.

    Priority:
      1. Warehouse child table has a row for this item's group → return that account.
      2. No mapping row exists → return fallback_account
         (the standard ERPNext warehouse_account[wh]["account"]).

    fallback_account already IS the warehouse's account from ERPNext's
    warehouse_account dict, so step 2 preserves system-default behaviour exactly.
    """
    item_group = _get_item_group(item_code, ig_cache)
    if not item_group:
        return fallback_account

    mapping = _get_warehouse_mapping(warehouse, wh_map_cache)
    return mapping.get(item_group, fallback_account)


# ── GL entry post-processing ──────────────────────────────────────────────────

def apply_item_group_mapping(doc, gl_entries: list, warehouse_account: dict) -> list:
    """
    Walk the GL entry list produced by super().get_gl_entries() and substitute
    any warehouse inventory account with the item-group-specific account where
    a mapping exists on the Warehouse record.

    Returns a new list (original entries are not mutated).

    How it works
    ────────────
    ERPNext's process_gl_map → merge_similar_entries collapses entries with the
    same (account, voucher_detail_no, cost_center, ...) into one row.
    Each voucher_detail_no uniquely identifies one item row, so we can
    correlate back from GL entry → item row → item_code → item_group → mapped account.

    If the resolved account differs from the original, we copy the GL entry dict
    and swap the account.  Entries for different item groups now carry different
    accounts and will NOT be re-merged by make_gl_entries, producing the
    per-item-group split lines the business requires.

    The credit side (expense / RBNB / stock adjustment accounts) is NEVER touched,
    so debit == credit balance is always maintained.
    """
    if not warehouse_account:
        return gl_entries

    # Reverse map: account value → warehouse name (for fast lookup)
    account_to_wh = {
        v.get("account"): k
        for k, v in warehouse_account.items()
        if v.get("account")
    }

    # Build item_code lookup from the doc's item rows keyed by child row name
    # (voucher_detail_no on a GL entry = child row name of the item table)
    item_code_map = {}
    for item in doc.get("items") or []:
        if item.item_code:
            item_code_map[item.name] = item.item_code

    ig_cache  = {}   # item_code → item_group
    wh_map    = {}   # warehouse  → {item_group: account}
    new_entries = []

    for gle in gl_entries:
        original_account = gle.get("account")

        # Is this a warehouse inventory account?
        wh_name = account_to_wh.get(original_account)
        if not wh_name:
            new_entries.append(gle)
            continue

        # Can we identify the item from voucher_detail_no?
        vdn      = gle.get("voucher_detail_no")
        item_code = item_code_map.get(vdn)
        if not item_code:
            new_entries.append(gle)
            continue

        resolved = resolve_account(
            wh_name, item_code, original_account, ig_cache, wh_map
        )

        if resolved == original_account:
            new_entries.append(gle)
        else:
            new_gle = copy.copy(gle)
            new_gle["account"] = resolved
            # Sync account_currency in case the mapped account uses a different currency
            new_gle["account_currency"] = (
                frappe.db.get_value("Account", resolved, "account_currency")
                or gle.get("account_currency")
            )
            new_entries.append(new_gle)

    return new_entries
