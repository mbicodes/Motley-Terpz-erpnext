"""One-time backfill: classify every existing Fresh Frozen item from its past wash history.

Preview (read-only, writes a CSV next to the site's private files):
    bench --site <site> execute cannabis_management.ff_wash_backfill.preview
Apply (only after the preview is approved):
    bench --site <site> execute cannabis_management.ff_wash_backfill.apply --kwargs "{'confirm': 'YES'}"

Also: setup() creates the three read-only Item fields, rebuild_tree() repairs the Item Group nested set.
"""
import csv
import os

import frappe
from frappe.utils import now_datetime

from cannabis_management.doc_hooks import ff_wash_classify as fwc

CSV_COLUMNS = ["item", "item_name", "disabled", "stock_lbs", "wash_runs", "best_yield", "yields",
               "last_wash_date", "wash_entries", "old_group", "new_group", "group_changes",
               "mtm_row", "mtm_accounts_change", "rule"]

CUSTOM_FIELDS = {
    "Item": [
        {"fieldname": "custom_wash_runs", "label": "Wash Runs", "fieldtype": "Int", "read_only": 1,
         "insert_after": "item_group", "no_copy": 1, "default": "0",
         "depends_on": "eval:(doc.item_group||'').indexOf('Fresh Frozen')===0",
         "description": "Submitted wash Stock Entries that consumed this item (set automatically)"},
        {"fieldname": "custom_best_wash_yield", "label": "Best Yield %", "fieldtype": "Percent",
         "read_only": 1, "insert_after": "custom_wash_runs", "no_copy": 1, "precision": "2",
         "depends_on": "eval:(doc.item_group||'').indexOf('Fresh Frozen')===0",
         "description": "Highest hash yield of any wash run; 2.5% or above = SHO"},
        {"fieldname": "custom_last_wash_date", "label": "Last Wash Date", "fieldtype": "Date",
         "read_only": 1, "insert_after": "custom_best_wash_yield", "no_copy": 1,
         "depends_on": "eval:(doc.item_group||'').indexOf('Fresh Frozen')===0"},
    ]
}


def setup():
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    create_custom_fields(CUSTOM_FIELDS, update=True)
    frappe.db.commit()


def rebuild_tree():
    from frappe.utils.nestedset import rebuild_tree as _rebuild
    _rebuild("Item Group")
    frappe.db.commit()


def build_plans():
    ff = fwc.ff_groups()
    items = frappe.get_all("Item", filters={"item_group": ["in", ff], "disabled": 0},
                           fields=["name", "item_name", "disabled"], order_by="name")
    history = fwc.wash_runs(None, ff=ff)
    stock = dict(frappe.db.sql(
        """select item_code, sum(actual_qty) from tabBin where item_code in %s group by item_code""",
        (tuple(i.name for i in items) or ("",),)))
    out = []
    for it in items:
        runs = history.get(it.name) or []
        p = fwc.plan_item(it.name, fwc.summarize(runs), ff=ff)
        if not p:
            continue
        p.update(item_name=it.item_name, disabled=it.disabled, stock_lbs=round(stock.get(it.name) or 0, 3),
                 runs=runs)
        out.append(p)
    return out


def _row(p):
    return {
        "item": p.item, "item_name": p.item_name, "disabled": p.disabled, "stock_lbs": p.stock_lbs,
        "wash_runs": p.stats["custom_wash_runs"], "best_yield": p.stats["custom_best_wash_yield"],
        "yields": " / ".join(f"{r['yield']:.2f}" for r in p.runs),
        "last_wash_date": p.stats["custom_last_wash_date"] or "",
        "wash_entries": " ".join(r.stock_entry for r in p.runs),
        "old_group": p.old_group, "new_group": p.new_group,
        "group_changes": "YES" if p.group_changed else "",
        "mtm_row": "yes" if p.default_row else "no (group defaults apply)",
        "mtm_accounts_change": "; ".join(f"{f}: {p.old_accounts.get(f) or '-'} -> {v or '-'}"
                                         for f, v in p.accounts.items()),
        "rule": "0 runs: Untested" if not p.stats["custom_wash_runs"] else "wash yield rules",
    }


def preview(path=None):
    plans = build_plans()
    path = path or frappe.get_site_path("private", "files", "ff_wash_backfill_preview.csv")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=CSV_COLUMNS)
        w.writeheader()
        for p in plans:
            w.writerow(_row(p))
    moves = {}
    for p in plans:
        if p.group_changed:
            moves[(p.old_group, p.new_group)] = moves.get((p.old_group, p.new_group), 0) + 1
    print(f"{len(plans)} FF items, {sum(moves.values())} change group, "
          f"{sum(1 for p in plans if p.accounts)} MTM default rows change. CSV: {path}")
    for (a, b), n in sorted(moves.items()):
        print(f"  {a} -> {b}: {n}")
    return path


def apply(confirm=None, commit=True):
    """Backfill in one transaction (single commit at the end). Returns the counts."""
    if confirm != "YES":
        print("Dry run only. Pass confirm='YES' to write.")
        return preview()
    if not all(frappe.db.has_column("Item", c) for c in fwc.STAT_FIELDS):
        setup()
    stamp = now_datetime().strftime("%Y-%m-%d %H:%M")
    plans = build_plans()
    out = frappe._dict(in_scope=len(plans), moved=0, mtm_rows=0, wash_fields=0, comments=0, touched=[])
    for p in plans:
        if p.group_changed or p.stats_changed or p.accounts:
            fwc.apply_plan(p, source=f"Backfill ({stamp})")
            out.touched.append(p.item)
            out.moved += p.group_changed
            out.mtm_rows += bool(p.accounts and p.default_row)
            out.wash_fields += p.stats_changed or p.group_changed
            out.comments += p.group_changed
    if commit:
        frappe.db.commit()
    print(f"Backfill: {out.in_scope} in scope, {out.moved} moved, {out.mtm_rows} MTM rows, "
          f"{out.wash_fields} wash fields, {out.comments} comments")
    return out


# ---------------------------------------------------------------- dependency patch (DB-only pages)
# Pages built as Web Page / Custom HTML Block / Server Script records hard-code the old three FF
# groups. These rules add Untested + To Be Determined so FF items don't vanish when they move.
import re  # noqa: E402

NEW2_JS = "'Fresh Frozen Untested', 'Fresh Frozen - To Be Determined'"
NEW2_PY = '"Fresh Frozen Untested", "Fresh Frozen - To Be Determined"'
RULES = [
    # const FRESH_FROZEN_SUBGROUPS = ['Fresh Frozen', 'Fresh Frozen - BHO', 'Fresh Frozen - SHO']
    (r"(FRESH_FROZEN_SUBGROUPS\s*=\s*\[[^\]]*'Fresh Frozen - SHO')(\s*\])", r"\1, " + NEW2_JS + r"\2"),
    (r"(WO_FRESH_FROZEN_SUBS\s*=\s*\[[^\]]*'Fresh Frozen - SHO')(\s*\])", r"\1, " + NEW2_JS + r"\2"),
    # sidebar filters that hide only BHO / SHO -> hide every Fresh Frozen sub group
    (r"(\w+) !== 'Fresh Frozen - BHO' && \1 !== 'Fresh Frozen - SHO'",
     r"!(String(\1).indexOf('Fresh Frozen') === 0 && String(\1) !== 'Fresh Frozen')"),
    # type badges
    (r"(\n([ \t]*)if \((\w+) === 'Fresh Frozen - SHO'\) return 'SHO';)",
     r"\1\n\2if (\3 === 'Fresh Frozen Untested') return 'Untested';\n\2if (\3 === 'Fresh Frozen - To Be Determined') return 'TBD';"),
    # extracts menus: hide every Fresh Frozen group, not only the one named exactly "fresh frozen"
    (r"return g\.name\.toLowerCase\(\) !== 'fresh frozen';", "return g.name.toLowerCase().indexOf('fresh frozen') !== 0;"),
    # Frozen Planner (HTML block JS + server script)
    (r'(GROUPS = \["Fresh Frozen", "Fresh Frozen - SHO", "Fresh Frozen - BHO")(, "Frozen"\])', r"\1, " + NEW2_PY + r"\2"),
    # sales target m-lists that roll FF groups up into Fresh Frozen Main
    (r"('Fresh Frozen','Fresh Frozen - SHO','Fresh Frozen - BHO',)",
     r"\1'Fresh Frozen Untested','Fresh Frozen - To Be Determined',"),
    (r"(\n([ \t]*)<option>Fresh Frozen - BHO</option>)",
     r"\1\n\2<option>Fresh Frozen Untested</option>\n\2<option>Fresh Frozen - To Be Determined</option>"),
]
TARGETS = [
    ("Web Page", "mtm-inventory-dashboard"), ("Web Page", "fresh-frozen-live"), ("Web Page", "live-menu-2"),
    ("Web Page", "mtm-live-menu"), ("Web Page", "consignment"), ("Web Page", "inventory-dashboard"),
    ("Custom HTML Block", "Frozen Planner"), ("Server Script", "Frozen Planner - Data"),
    ("Custom HTML Block", "Sales Target and Inventory Dashboard"),
]
TEXT_FIELDS = {"Web Page": ["javascript", "main_section", "main_section_html", "main_section_md", "css"],
               "Custom HTML Block": ["html", "script", "style"], "Server Script": ["script"]}


def patch_text(text):
    if not text or "Untested" in text and "To Be Determined" in text:
        return text, 0  # already patched
    n = 0
    for pat, rep in RULES:
        text, k = re.subn(pat, rep, text)
        n += k
    return text, n


def patch_dependencies(apply=False):
    """Dry run by default: prints what would change. apply=True writes the DB records (no doc hooks)."""
    for dt, name in TARGETS:
        if not frappe.db.exists(dt, name):
            print(f"skip {dt} {name}: not found")
            continue
        for f in TEXT_FIELDS[dt]:
            if not frappe.db.has_column(dt, f):
                continue
            old = frappe.db.get_value(dt, name, f)
            new, n = patch_text(old)
            if n:
                print(f"{dt} {name}.{f}: {n} change(s)")
                if apply:
                    frappe.db.set_value(dt, name, f, new, update_modified=True)
    for g in ("Fresh Frozen - To Be Determined",):  # same visibility as the other sub groups (all rolled into 'Fresh Frozen')
        vals = {"custom_show_in_dashboard": 0, "custom_show_in_extracts_live": 0, "custom_show_in_inventory_dashboard": 0}
        print(f"Item Group {g}: show flags -> 0")
        if apply:
            frappe.db.set_value("Item Group", g, vals)
    if apply:
        frappe.db.commit()
        frappe.clear_cache()


# ---------------------------------------------------------------- accounts (open questions 3 + 4, TBD mapping)
MTM = "Master Touch Manufacturing"
RENAMES = {  # duplicated "- MTM - MTM" suffix on the Untested accounts (0 GL entries on 2026-11-04)
    "Fresh Frozen - UNTESTED - Expense - MTM - MTM": "Fresh Frozen - UNTESTED - Expense",
    "Fresh Frozen - UNTESTED - Income - MTM - MTM": "Fresh Frozen - UNTESTED - Income",
}
GROUP_INV = {
    "Fresh Frozen Untested": "Fresh Frozen - UNTESTED - INV - MTM",
    "Fresh Frozen - SHO": "Fresh Frozen - SHO - INV - MTM",
    "Fresh Frozen - BHO": "Fresh Frozen - BHO - INV - MTM",
}
TBD_WIP = ("Fresh Frozen - To Be Determined - WIP", "Work In Progress - MTM")


def setup_accounts(apply=False):
    """Dry run by default. 1) rename the two Untested accounts, 2) create the TBD WIP account,
    3) map the INV accounts on the Untested / SHO / BHO groups (MTM row, custom_asset_account),
    4) add a 'Fresh Frozen - To Be Determined' row to every warehouse mapping that has an Untested row,
       so the Item Group submit guard does not block items that move to TBD."""
    from erpnext.accounts.doctype.account.account import update_account_number
    for old, new_name in RENAMES.items():
        if frappe.db.exists("Account", old):
            print(f"rename account {old} -> {new_name} - MTM")
            if apply:
                update_account_number(old, new_name)
    wip_name = f"{TBD_WIP[0]} - MTM"
    if not frappe.db.exists("Account", wip_name):
        print(f"create account {wip_name} under {TBD_WIP[1]}")
        if apply:
            frappe.get_doc({"doctype": "Account", "account_name": TBD_WIP[0], "parent_account": TBD_WIP[1],
                            "company": MTM, "root_type": "Asset", "is_group": 0}).insert(ignore_permissions=True)
    for grp, inv in GROUP_INV.items():
        row = frappe.db.get_value("Item Default", {"parenttype": "Item Group", "parent": grp, "company": MTM},
                                  ["name", "custom_asset_account"], as_dict=True)
        if row and not row.custom_asset_account and frappe.db.exists("Account", inv):
            print(f"map {inv} on Item Group {grp}")
            if apply:
                frappe.db.set_value("Item Default", row.name, "custom_asset_account", inv)
    rows = frappe.db.sql("""select parent, account from `tabWarehouse Item Group Account Mapping`
        where parenttype = 'Warehouse' and item_group = 'Fresh Frozen Untested'""", as_dict=True)
    for r in rows:
        if frappe.db.exists("Warehouse Item Group Account Mapping",
                            {"parent": r.parent, "item_group": fwc.TBD}):
            continue
        acct = (r.account or "").replace("UNTESTED", "To Be Determined")
        if not frappe.db.exists("Account", acct) and acct != wip_name:
            print(f"!! {r.parent}: no account {acct}, skipped")
            continue
        print(f"warehouse {r.parent}: add {fwc.TBD} -> {acct}")
        if apply:
            wh = frappe.get_doc("Warehouse", r.parent)
            wh.append("custom_item_group_account_mapping", {"item_group": fwc.TBD, "account": acct})
            wh.save(ignore_permissions=True)
    if apply:
        frappe.db.commit()
