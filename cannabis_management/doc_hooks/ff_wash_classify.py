"""Auto-classify Fresh Frozen (FF) items into Item Groups by wash yield.

Every time a wash Stock Entry is submitted or cancelled, each FF item it consumed is re-classified
from its FULL submitted wash history (never incremented), so cancellations undo themselves:

    never washed (0 submitted runs)            -> Fresh Frozen Untested, whatever the current group
    washed once, yield below 2.5%              -> Fresh Frozen - To Be Determined
    any run ever at 2.5% or above              -> Fresh Frozen - SHO   (later low runs keep it there)
    washed 2+ times, every run below 2.5%      -> Fresh Frozen - BHO

A wash run is one submitted Stock Entry that consumes FF and produces Bubble Hash:
  * Manufacture: at least one FF input row and at least one Bubble Hash output row
    (all micron grades are Bubble Hash items and are added together);
  * Repack (the pre-Work Order washes of Sept 2026): every input row is FF and every output row is
    Bubble Hash, so FF -> Primes / FF -> FF / FF -> Tier repacks are not counted.
Yield = hash grams / FF grams consumed x 100, rounded to 2 decimals (exactly 2.50% is SHO). When one
entry washes several FF items together, the combined yield of the entry counts for each of them.
"""
import frappe
from frappe import _
from frappe.utils import cint, flt, getdate

FF_ROOT = "Fresh Frozen Main"
UNTESTED = "Fresh Frozen Untested"
TBD = "Fresh Frozen - To Be Determined"
SHO = "Fresh Frozen - SHO"
BHO = "Fresh Frozen - BHO"
SHO_THRESHOLD = 2.5
CLASSIFY_COMPANY = "Master Touch Manufacturing"
DEFAULT_FIELDS = ("expense_account", "income_account", "custom_asset_account")
STAT_FIELDS = ("custom_wash_runs", "custom_best_wash_yield", "custom_last_wash_date")

# grams per 1 unit of stock UOM; same LBS factor as Wash Production Plan
GRAMS_PER_UOM = {"lbs": 453.592, "lb": 453.592, "pound": 453.592, "gram": 1.0, "grams": 1.0, "g": 1.0,
                 "kg": 1000.0, "kilogram": 1000.0}


# ---------------------------------------------------------------- groups

def _children_map():
    out = {}
    for g in frappe.get_all("Item Group", fields=["name", "parent_item_group"]):
        out.setdefault(g.parent_item_group, []).append(g.name)
    return out


def subtree(root):
    """root + all descendants, walked by parent_item_group (works even when lft/rgt is broken)."""
    kids, out, stack = _children_map(), [], [root]
    while stack:
        g = stack.pop()
        if g in out:
            continue
        out.append(g)
        stack.extend(kids.get(g, []))
    return out


def ff_groups():
    return subtree(FF_ROOT)


def hash_groups():
    grp = frappe.db.get_single_value("Wash Plan Settings", "bubble_hash_item_group") or "Bubble Hash"
    return subtree(grp)


def classify(yields):
    """yields: list of per-run yield % (already rounded). Returns the Item Group name."""
    if not yields:
        return UNTESTED
    if any(flt(y) >= SHO_THRESHOLD for y in yields):
        return SHO
    return TBD if len(yields) == 1 else BHO


# ---------------------------------------------------------------- wash history

def _grams(qty, uom):
    f = GRAMS_PER_UOM.get((uom or "").strip().lower())
    return None if f is None else flt(qty) * f


def wash_runs(items=None, ff=None, hashg=None):
    """{ff item: [run dicts]} built from submitted Stock Entries. items=None -> every FF item.
    Run dict: stock_entry, posting_date, purpose, ff_g, hash_g, yield."""
    ff = set(ff or ff_groups())
    hashg = set(hashg or hash_groups())
    cond, params = "", {}
    if items is not None:
        if not items:
            return {}
        cond = """and se.name in (select d2.parent from `tabStock Entry Detail` d2
            where d2.item_code in %(items)s and ifnull(d2.s_warehouse, '') != '')"""
        params["items"] = tuple(items)
    rows = frappe.db.sql(f"""
        select se.name, se.purpose, se.posting_date, d.item_code, i.item_group, d.transfer_qty,
            d.stock_uom, ifnull(d.s_warehouse, '') s_wh, ifnull(d.t_warehouse, '') t_wh
        from `tabStock Entry` se
        join `tabStock Entry Detail` d on d.parent = se.name and d.parenttype = 'Stock Entry'
        join `tabItem` i on i.name = d.item_code
        where se.docstatus = 1 and se.purpose in ('Manufacture', 'Repack') {cond}
        order by se.posting_date, se.name, d.idx""", params, as_dict=True)

    entries = {}
    for r in rows:
        entries.setdefault(r.name, []).append(r)

    out = {}
    for name, lines in entries.items():
        ins = [r for r in lines if r.s_wh and not r.t_wh]
        outs = [r for r in lines if r.t_wh and not r.s_wh]
        ff_in = [r for r in ins if r.item_group in ff]
        hash_out = [r for r in outs if r.item_group in hashg]
        if not ff_in or not hash_out:
            continue
        purpose = lines[0].purpose
        if purpose == "Repack" and (len(ff_in) != len(ins) or len(hash_out) != len(outs)):
            continue
        ff_g = [_grams(r.transfer_qty, r.stock_uom) for r in ff_in]
        hash_g = [_grams(r.transfer_qty, r.stock_uom) for r in hash_out]
        if None in ff_g or None in hash_g or not sum(ff_g):
            continue  # unknown UOM (e.g. Nos) -> cannot compute a yield
        run = frappe._dict(
            stock_entry=name, posting_date=lines[0].posting_date, purpose=purpose,
            ff_g=sum(ff_g), hash_g=sum(hash_g),
            ff_items=sorted({r.item_code for r in ff_in}),
        )
        run["yield"] = round(run.hash_g / run.ff_g * 100, 2)
        for it in run.ff_items:
            out.setdefault(it, []).append(run)
    return out


def summarize(runs):
    runs = runs or []
    yields = [r["yield"] for r in runs]
    return frappe._dict(
        group=classify(yields),
        wash_runs=len(runs),
        best_yield=max(yields) if yields else 0,
        last_wash_date=max(getdate(r.posting_date) for r in runs) if runs else None,
    )


# ---------------------------------------------------------------- apply

def _group_defaults(group, company=CLASSIFY_COMPANY):
    return frappe.db.get_value(
        "Item Default", {"parenttype": "Item Group", "parent": group, "company": company},
        list(DEFAULT_FIELDS), as_dict=True) or frappe._dict()


def plan_item(item, summary, ff=None):
    """What would change on one item. None when the item is out of scope: disabled, or not in
    Fresh Frozen Main / its child groups."""
    stat_cols = [c for c in STAT_FIELDS if frappe.db.has_column("Item", c)]
    cur = frappe.db.get_value("Item", item, ["item_group", "disabled"] + stat_cols, as_dict=True)
    if not cur or cint(cur.disabled) or cur.item_group not in (ff or ff_groups()):
        return None
    new_group = summary.group
    group_changed = cur.item_group != new_group
    row = frappe.db.get_value(
        "Item Default", {"parenttype": "Item", "parent": item, "company": CLASSIFY_COMPANY},
        ["name"] + list(DEFAULT_FIELDS), as_dict=True)
    acct = {}
    if row and group_changed:  # MTM row follows the group on every group change; other companies untouched
        gdef = _group_defaults(new_group)
        acct = {f: gdef.get(f) for f in DEFAULT_FIELDS if (row.get(f) or None) != (gdef.get(f) or None)}
    stats = {
        "custom_wash_runs": summary.wash_runs,
        "custom_best_wash_yield": summary.best_yield,
        "custom_last_wash_date": summary.last_wash_date,
    }
    stats_changed = (cint(cur.custom_wash_runs) != stats["custom_wash_runs"]
                     or flt(cur.custom_best_wash_yield, 2) != flt(stats["custom_best_wash_yield"], 2)
                     or (getdate(cur.custom_last_wash_date) if cur.custom_last_wash_date else None)
                     != stats["custom_last_wash_date"])
    return frappe._dict(
        item=item, old_group=cur.item_group, new_group=new_group,
        group_changed=group_changed,
        default_row=row.name if row else None, old_accounts={f: row.get(f) for f in acct} if row else {},
        accounts=acct, stats=stats, stats_changed=stats_changed,
    )


def apply_plan(p, trigger=None, source=None):
    """Write one plan_item() result. trigger = Stock Entry name; source = text for backfill comments."""
    if p.stats_changed or p.group_changed:
        vals = {k: v for k, v in p.stats.items() if frappe.db.has_column("Item", k)}
        if p.group_changed:
            vals["item_group"] = p.new_group
        if vals:
            frappe.db.set_value("Item", p.item, vals, update_modified=p.group_changed)
    if p.accounts and p.default_row:
        frappe.db.set_value("Item Default", p.default_row, p.accounts, update_modified=False)
    if p.group_changed:
        why = (_("Stock Entry {0} ({1})").format(frappe.utils.get_link_to_form("Stock Entry", trigger), source)
               if trigger and source else
               _("Stock Entry {0}").format(frappe.utils.get_link_to_form("Stock Entry", trigger)) if trigger
               else source or _("Backfill"))
        msg = _("Item Group changed automatically from {0} to {1} by {2}. Wash runs: {3}, best yield: {4}%.").format(
            frappe.bold(p.old_group), frappe.bold(p.new_group), why, p.stats["custom_wash_runs"],
            p.stats["custom_best_wash_yield"])
        if p.accounts:
            msg += " " + _("MTM item defaults updated: {0}.").format(
                ", ".join(f"{f}: {p.old_accounts.get(f) or '-'} &rarr; {v or '-'}" for f, v in p.accounts.items()))
        frappe.get_doc({
            "doctype": "Comment", "comment_type": "Info", "reference_doctype": "Item",
            "reference_name": p.item, "content": msg,
        }).insert(ignore_permissions=True)
    if p.group_changed or p.stats_changed or p.accounts:
        frappe.clear_document_cache("Item", p.item)


def reclassify_items(items, trigger=None, source=None):
    ff = ff_groups()
    history = wash_runs(items, ff=ff)
    changed = []
    for it in items:
        p = plan_item(it, summarize(history.get(it)), ff=ff)
        if p:
            apply_plan(p, trigger=trigger, source=source)
            if p.group_changed:
                changed.append(p)
    return changed


# ---------------------------------------------------------------- hooks

def _ff_input_items(doc, ff):
    return sorted({d.item_code for d in doc.get("items") or []
                   if d.get("s_warehouse") and not d.get("t_warehouse")
                   and frappe.db.get_value("Item", d.item_code, "item_group") in ff})


def stock_entry_on_change(doc, method=None):
    """Stock Entry on_submit / on_cancel. Cheap exit for anything that is not a wash."""
    if doc.purpose not in ("Manufacture", "Repack"):
        return
    hashg = set(hash_groups())
    if not any(d.get("t_warehouse") and frappe.db.get_value("Item", d.item_code, "item_group") in hashg
               for d in doc.get("items") or []):
        return
    ff = set(ff_groups())
    items = _ff_input_items(doc, ff)
    if not items:
        return
    source = _("cancelled") if method == "on_cancel" else _("submitted")
    # never block the wash itself: on error roll back only this step and log it
    frappe.db.savepoint("ff_wash_classify")
    try:
        changed = reclassify_items(items, trigger=doc.name, source=source)
    except Exception:
        frappe.db.rollback(save_point="ff_wash_classify")
        frappe.log_error(title=f"FF wash classify failed for {doc.name}")
        frappe.msgprint(_("Fresh Frozen item group could not be updated automatically. See Error Log."),
                        indicator="orange", alert=True)
        return
    for p in changed:
        frappe.msgprint(_("{0}: Item Group {1} &rarr; {2}").format(p.item, p.old_group, p.new_group),
                        indicator="blue", alert=True)


def item_before_insert(doc, method=None):
    """New Fresh Frozen items start in Fresh Frozen Untested (they have no wash history yet)."""
    if not doc.item_group or doc.item_group not in ff_groups():
        return
    doc.item_group = UNTESTED
    gdef = _group_defaults(UNTESTED)
    for d in doc.get("item_defaults") or []:  # e.g. copied from a duplicated SHO item
        if d.company == CLASSIFY_COMPANY:
            for f in DEFAULT_FIELDS:
                d.set(f, gdef.get(f))
