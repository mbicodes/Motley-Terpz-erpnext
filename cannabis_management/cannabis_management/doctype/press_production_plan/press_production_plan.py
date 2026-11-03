"""Press Production Plan: which washed Bubble Hash goes on the rosin press on which day.

One row = one wash = one existing Rosin Pressing Work Order. Scheduling never creates a Material Request or a
Work Order: it dates the existing Work Order and its job card and sets the Bubble Hash the Work Order consumes.
Rosin actuals per micron come back from the press job card (doc_hooks/press_plan_sync.py).
"""
import datetime
import json
import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, date_diff, flt, get_datetime, getdate, nowdate

SLOTS = ("150", "120_73", "45")  # row columns g_150 / g_120_73 / g_45 = micron groups 1-3 of Press Plan Settings
OPEN = ("Draft", "In Progress")
CLOSED_WO = ("Completed", "Stopped", "Closed", "Cancelled")
YIELD_FIELDS = tuple("exp_yield_" + s for s in SLOTS)
LOCKED_FIELDS = ("planned_date", "bh_planned_g") + YIELD_FIELDS


def get_settings():
    return frappe.get_cached_doc("Press Plan Settings")


def norm(label):
    """'120u - 73u', '120u – 73u' and '120U-73U' are the same micron group."""
    s = re.sub(r"\s+", "", (label or "").lower().replace("µ", "u").replace("μ", "u"))
    return re.sub(r"[–—]", "-", s)


def groups(s=None):
    """Micron groups of Press Plan Settings in order, each tied to one row column slot."""
    s = s or get_settings()
    return [frappe._dict(slot=slot, label=g.micron_label, yield_pct=flt(g.expected_yield))
            for slot, g in zip(SLOTS, s.micron_groups or [])]


def strain_of(item_name):
    return re.sub(r"\s*-\s*(Bubble Hash|BH)\s*$", "", (item_name or "").strip(), flags=re.I).strip()


# ---------- micron split and yields (plain functions; rows may be documents or dicts) ----------

def split_microns(rows, grps):
    """Grams per slot from Micron Collection Detail rows, plus {micron size: grams} for sizes that are not a
    configured group. Those are reported, never guessed into a group."""
    slot_of = {norm(g.label): g.slot for g in grps}
    grams, unknown = {s: 0.0 for s in SLOTS}, {}
    for r in rows or []:
        slot = slot_of.get(norm(r.get("micron_size")))
        if slot:
            grams[slot] += flt(r.get("grams_collected"))
        else:
            k = r.get("micron_size") or _("(blank)")
            unknown[k] = unknown.get(k, 0) + flt(r.get("grams_collected"))
    return grams, unknown


def micron_note(job_card, grams, unknown, bh_actual, grps):
    """Plain-English warning for a wash micron split that cannot be used as is ('' when it is fine)."""
    if not grps:
        return _("No micron groups are set up in Press Plan Settings.")
    if not job_card:
        return _("The wash job card has no micron split.")
    notes = []
    if unknown:
        notes.append(_("Job card {0} has micron size(s) {1} that are not set up in Press Plan Settings ({2}); those grams are left out.").format(
            job_card, ", ".join("{0} ({1} g)".format(k, round(v, 1)) for k, v in unknown.items()), ", ".join(g.label for g in grps)))
    total = sum(grams.values()) + sum(unknown.values())
    if bh_actual and abs(total - flt(bh_actual)) > 0.5:
        notes.append(_("The micron split on {0} adds up to {1} g; the wash produced {2} g.").format(
            job_card, round(total, 1), round(flt(bh_actual), 1)))
    return " ".join(notes)


def row_math(row):
    """Expected rosin per micron = BH grams of that micron (scaled to the BH being pressed) x its expected yield.
    Actual yield per micron = rosin recorded for that micron on the press job card / its BH grams."""
    split = sum(flt(row.get("g_" + s)) for s in SLOTS)
    scale = flt(row.get("bh_planned_g")) / split if split else 0
    total = 0.0
    for s in SLOTS:
        base = flt(row.get("g_" + s)) * scale
        exp = base * flt(row.get("exp_yield_" + s)) / 100
        act = flt(row.get("act_rosin_" + s))
        setattr(row, "exp_rosin_" + s, exp)
        setattr(row, "act_yield_" + s, act / base * 100 if base and act else 0)
        total += exp
    row.expected_rosin_g = total
    bh, act = flt(row.get("bh_planned_g")), flt(row.get("actual_rosin_g"))
    row.actual_yield = act / bh * 100 if bh and act else 0
    return row


def metrc_tag(notes, s=None):
    """METRC tag typed in the job card sub-operation notes ({"Press Run": "TAG: 2620"}): the press note first,
    then the whipping note, then any note. A leading 'TAG:' is dropped."""
    s = s or get_settings()
    if isinstance(notes, str):
        try:
            notes = json.loads(notes)
        except ValueError:
            return ""
    if not isinstance(notes, dict):
        return ""
    for k in (s.press_sub_operation, s.whipping_sub_operation, *notes):
        v = str(notes.get(k) or "").strip()
        if v:
            return re.sub(r"^tag\s*[:#]?\s*", "", v, flags=re.I).strip()
    return ""


def press_state(wo, jc, sub_ops, s=None):
    """Row status from the source documents. Cancelled: the Work Order is cancelled. Pressed: the press
    sub-operation is complete on the job card (or the card is submitted). Whipped: the whipping sub-operation is
    complete as well. Otherwise Scheduled."""
    s = s or get_settings()
    if not wo or wo.docstatus == 2:
        return "Cancelled"
    done = {so.sub_operation for so in sub_ops or [] if so.status == "Complete"}
    pressed = bool(jc) and (s.press_sub_operation in done or jc.docstatus == 1)
    if pressed and s.whipping_sub_operation in done:
        return "Whipped"
    if pressed or wo.status == "Completed":
        return "Pressed"
    return "Scheduled"


# ---------- source documents ----------

def rosin_work_orders(names=None, s=None):
    """Open Rosin Pressing Work Orders (an operation on the press workstation; not completed, stopped or
    closed) with their Bubble Hash line and the hash Work Order of the same Material Request that makes it."""
    s = s or get_settings()
    cond, args = "", {"ws": s.press_workstation, "closed": CLOSED_WO}
    if names is not None:
        if not names:
            return []
        cond, args["names"] = " and r.name in %(names)s", list(names)
    return frappe.db.sql(f"""
        select r.name, r.production_item rosin_item, r.status, r.material_request, r.project, r.company,
            r.planned_start_date, r.wip_warehouse,
            wi.item_code bubble_hash_item, coalesce(nullif(wi.source_warehouse, ''), r.source_warehouse) source_warehouse,
            wi.required_qty, wi.transferred_qty, wi.consumed_qty,
            h.name hash_work_order, h.produced_qty, h.status hash_status, h.actual_end_date,
            mr.custom_wash_production_plan wash_plan, mr.custom_wash_plan_row wash_plan_row
        from `tabWork Order` r
        join `tabWork Order Item` wi on wi.parent = r.name and wi.parenttype = 'Work Order'
        join `tabWork Order` h on h.material_request = r.material_request and h.name != r.name
            and h.production_item = wi.item_code and h.docstatus = 1
        left join `tabMaterial Request` mr on mr.name = r.material_request
        where r.docstatus = 1 and r.status not in %(closed)s{cond}
          and exists (select 1 from `tabWork Order Operation` o where o.parent = r.name and o.workstation = %(ws)s)
        order by h.actual_end_date, r.name""", args, as_dict=True)


def micron_rows(job_cards):
    out = {}
    job_cards = [j for j in job_cards or [] if j]
    if job_cards:
        for r in frappe.db.sql(
            """select parent, micron_size, grams_collected from `tabMicron Collection Detail`
            where parenttype = 'Job Card' and parent in %(j)s order by parent, idx""", {"j": job_cards}, as_dict=True):
            out.setdefault(r.parent, []).append(r)
    return out


def wash_job_cards(hash_wos):
    """{hash Work Order: its submitted job card that carries the micron split (the latest one)}."""
    out = {}
    hash_wos = [w for w in hash_wos or [] if w]
    if hash_wos:
        for r in frappe.db.sql(
            """select jc.work_order, jc.name from `tabJob Card` jc where jc.work_order in %(w)s and jc.docstatus = 1
            and exists (select 1 from `tabMicron Collection Detail` m where m.parent = jc.name and m.parenttype = 'Job Card')
            order by jc.creation""", {"w": hash_wos}, as_dict=True):
            out[r.work_order] = r.name
    return out


def item_names(codes):
    codes = [c for c in set(codes) if c]
    return dict(frappe.db.sql("select name, item_name from tabItem where name in %(c)s", {"c": codes})) if codes else {}


def stock_need(info, planned_g):
    """Where the Work Order's Bubble Hash is and how much it still needs: in WIP once it has been transferred,
    otherwise the grams to press from the source warehouse."""
    if flt(info.transferred_qty) > 0:
        return info.wip_warehouse, max(flt(info.transferred_qty) - flt(info.consumed_qty), 0)
    return info.source_warehouse, flt(planned_g)


def build_rows(infos, s=None):
    """Plan-row values for Rosin Work Orders (rosin_work_orders() results), from the hash Work Order and the
    micron split on its job card. Also carries the stock need used by the stock check."""
    s = s or get_settings()
    grps = groups(s)
    jcs = wash_job_cards([i.hash_work_order for i in infos])
    mrows = micron_rows(jcs.values())
    names = item_names([i.bubble_hash_item for i in infos])
    out = []
    for i in infos:
        jc = jcs.get(i.hash_work_order)
        grams, unknown = split_microns(mrows.get(jc), grps)
        bh = flt(i.produced_qty)
        moved = flt(i.transferred_qty) > 0
        wash_plan = i.wash_plan if i.wash_plan and frappe.db.exists("Wash Production Plan", i.wash_plan) else None
        row = frappe._dict(
            rosin_work_order=i.name, hash_work_order=i.hash_work_order, material_request=i.material_request,
            wash_plan=wash_plan, wash_plan_row=i.wash_plan_row if wash_plan else None,
            bubble_hash_item=i.bubble_hash_item, rosin_item=i.rosin_item, project=i.project,
            hash_finished_on=i.actual_end_date, wash_job_card=jc, strain=strain_of(names.get(i.bubble_hash_item)),
            bh_actual_g=bh, bh_planned_g=flt(i.transferred_qty) if moved else bh,
            micron_note=micron_note(jc, grams, unknown, bh, grps),
            # not stored on the row
            bh_name=names.get(i.bubble_hash_item) or i.bubble_hash_item, hash_status=i.hash_status,
            wo_status=i.status, transferred=moved, planned_start_date=i.planned_start_date,
            days=date_diff(nowdate(), i.actual_end_date) if i.actual_end_date else None,
        )
        row.warehouse, row.need = stock_need(i, row.bh_planned_g)
        for g in grps:
            row["exp_yield_" + g.slot] = g.yield_pct
        for slot in SLOTS:
            row["g_" + slot] = grams[slot]
        out.append(row_math(row))
    return out


def open_plan_rows():
    """Rows of open plans that are not cancelled, in planned order (they draw on the stock before the queue)."""
    return frappe.db.sql(
        """select i.name, i.parent, i.rosin_work_order, i.bh_planned_g from `tabPress Plan Item` i
        join `tabPress Production Plan` p on p.name = i.parent
        where p.status in %(o)s and i.row_status != 'Cancelled' order by i.planned_date, i.sequence, i.idx""",
        {"o": OPEN}, as_dict=True)


def planned_work_orders(exclude_plan=None):
    """{Rosin Work Order: plan} for rows of open plans that are not cancelled."""
    return {r.rosin_work_order: r.parent for r in open_plan_rows() if r.parent != exclude_plan}


def ready_queue(s=None):
    """Ready to Press: open Rosin Pressing Work Orders whose wash (hash Work Order) is Completed, whose Bubble
    Hash comes from the configured source warehouse and that are not in an open plan. Oldest wash first."""
    s = s or get_settings()
    taken = planned_work_orders()
    infos = [i for i in rosin_work_orders(s=s) if i.hash_status == "Completed" and i.name not in taken
             and (not s.source_warehouse or i.source_warehouse == s.source_warehouse)]
    return build_rows(infos, s)


def allocate(entries):
    """Give each entry, in order, the Bubble Hash it can really get: the lower of what is left of the item in its
    warehouse (Bin.actual_qty) and of its project's balance there (Stock Ledger, project dimension). Several
    washes can draw on one BH item. Sets covered, stock and sharing on each entry."""
    keys = {(e.bubble_hash_item, e.warehouse) for e in entries if e.bubble_hash_item and e.warehouse}
    bins, proj = {}, {}
    if keys:
        args = {"i": list({k[0] for k in keys}), "w": list({k[1] for k in keys})}
        for item, wh, qty in frappe.db.sql(
                "select item_code, warehouse, actual_qty from tabBin where item_code in %(i)s and warehouse in %(w)s", args):
            bins[(item, wh)] = flt(qty)
        for item, wh, project, qty in frappe.db.sql(
                """select item_code, warehouse, ifnull(project, ''), sum(actual_qty) from `tabStock Ledger Entry`
                where is_cancelled = 0 and item_code in %(i)s and warehouse in %(w)s
                group by item_code, warehouse, ifnull(project, '')""", args):
            proj[(item, wh, project)] = flt(qty)
    left_i, left_p, users = dict(bins), dict(proj), {}
    for e in entries:
        users[(e.bubble_hash_item, e.warehouse)] = users.get((e.bubble_hash_item, e.warehouse), 0) + 1
    for e in entries:
        ki, kp = (e.bubble_hash_item, e.warehouse), (e.bubble_hash_item, e.warehouse, e.project or "")
        e.stock = flt(bins.get(ki))
        e.covered = max(min(flt(e.need), left_i.get(ki, 0), left_p.get(kp, 0)), 0)
        e.sharing = users.get(ki, 0)
        left_i[ki] = left_i.get(ki, 0) - e.covered
        left_p[kp] = left_p.get(kp, 0) - e.covered
    return entries


def live_job_card(work_order):
    jc = frappe.get_all("Job Card", filters={"work_order": work_order, "docstatus": ["<", 2]},
        fields=["name", "docstatus", "total_completed_qty", "custom_sub_op_notes", "expected_start_date"],
        order_by="creation desc", limit=1)
    return jc[0] if jc else None


def started(work_orders):
    """({Work Order: its stock entry}, {Work Order: its job card with time logs}) for the given Work Orders;
    drafts count, cancelled documents do not."""
    if not work_orders:
        return {}, {}
    a = {"w": list(work_orders)}
    return (dict(frappe.db.sql("select work_order, name from `tabStock Entry` where work_order in %(w)s and docstatus < 2", a)),
            dict(frappe.db.sql("""select jc.work_order, jc.name from `tabJob Card` jc where jc.work_order in %(w)s and jc.docstatus < 2
                and exists (select 1 from `tabJob Card Time Log` t where t.parent = jc.name)""", a)))


def unschedule_reason(row_status, work_order, stock_entry=None, logged_job_card=None):
    """Why a row cannot be unscheduled (None when it can): pressing has started once the Work Order has a stock
    entry or its job card has a time log."""
    if row_status == "Cancelled":
        return None
    if row_status != "Scheduled":
        return _("it is already {0}").format(_(row_status))
    if stock_entry:
        return _("Stock Entry {0} exists for Work Order {1}").format(stock_entry, work_order)
    if logged_job_card:
        return _("job card {0} already has time logs").format(logged_job_card)
    return None


def unschedule_block(r):
    se, logs = started([r.rosin_work_order]) if r.row_status == "Scheduled" else ({}, {})
    return unschedule_reason(r.row_status, r.rosin_work_order, se.get(r.rosin_work_order), logs.get(r.rosin_work_order))


# ---------- effects on the Work Order and its job card ----------

def at_date(day, like):
    """The given day at the time of day of `like`, so a Work Order keeps its usual start time."""
    like = get_datetime(like) if like else None
    return datetime.datetime.combine(getdate(day), like.time() if like else datetime.time())


def _note(work_order, text):
    frappe.get_doc({"doctype": "Comment", "comment_type": "Info", "reference_doctype": "Work Order",
                    "reference_name": work_order, "content": text}).insert(ignore_permissions=True)


def set_dates(work_order, start, jc_start=None):
    """Move the Work Order start (its planned end moves by the same amount) and the open job card start."""
    wo = frappe.db.get_value("Work Order", work_order, ["planned_start_date", "planned_end_date"], as_dict=True)
    upd = {"planned_start_date": start}
    if wo.planned_start_date and wo.planned_end_date:
        upd["planned_end_date"] = get_datetime(wo.planned_end_date) + (get_datetime(start) - get_datetime(wo.planned_start_date))
    frappe.db.set_value("Work Order", work_order, upd)
    for jc in frappe.get_all("Job Card", filters={"work_order": work_order, "docstatus": 0}, pluck="name"):
        frappe.db.set_value("Job Card", jc, "expected_start_date", jc_start or start)


def apply_dates(r):
    start = at_date(r.planned_date, r.orig_wo_start)
    set_dates(r.rosin_work_order, start, at_date(r.planned_date, r.orig_jc_start) if r.orig_jc_start else start)


def restore_dates(r, plan_name):
    if r.orig_wo_start:
        set_dates(r.rosin_work_order, r.orig_wo_start, r.orig_jc_start)
    _note(r.rosin_work_order, _("Removed from Press Production Plan {0}; the planned start date is back to {1}.").format(
        plan_name, frappe.utils.format_datetime(r.orig_wo_start) if r.orig_wo_start else _("what it was")))


def apply_consumption(r):
    """Point the Rosin Work Order at the Bubble Hash being pressed: its BH line's required qty = bh_planned_g
    (what the hash-to-rosin hook already does with the hash output), then refresh the reserved qty in the Bin.
    Only before any material has been transferred. No Work Order is cancelled or amended."""
    lines = frappe.get_all("Work Order Item", filters={"parent": r.rosin_work_order, "parenttype": "Work Order",
        "item_code": r.bubble_hash_item}, fields=["name", "required_qty", "transferred_qty", "consumed_qty"])
    if not lines or any(flt(x.transferred_qty) or flt(x.consumed_qty) for x in lines):
        return False
    if abs(flt(lines[0].required_qty) - flt(r.bh_planned_g)) > 0.0005:
        frappe.db.set_value("Work Order Item", lines[0].name, "required_qty", flt(r.bh_planned_g))
    frappe.get_doc("Work Order", r.rosin_work_order).update_reserved_qty_for_production()
    return True


class PressProductionPlan(Document):
    def before_validate(self):
        s = get_settings()
        self.company = self.company or frappe.db.get_value("Warehouse", s.source_warehouse, "company")
        self.planned_by = self.planned_by or frappe.session.user
        if self.plan_type == "Daily":
            self.to_date = self.from_date
        elif self.plan_type == "Weekly" and self.from_date:
            self.to_date = add_days(self.from_date, 6)

    def validate(self):
        if self.flags.from_sync:
            return
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw(_("To Date cannot be before From Date."))
        before = self.get_doc_before_save()
        old = {r.name: r for r in (before.items if before else [])}
        fresh = [r for r in self.items if r.name not in old]
        built = {b.rosin_work_order: b for b in build_rows(rosin_work_orders([r.rosin_work_order for r in fresh]))} if fresh else {}
        taken = planned_work_orders(exclude_plan=self.name)
        changes = frappe._dict(added=[], dated=[], consume=[], removed=[])
        seen = set()
        for r in self.items:
            if not r.rosin_work_order:
                frappe.throw(_("Row {0}: Rosin Work Order is required.").format(r.idx))
            if r.rosin_work_order in seen:
                frappe.throw(_("Row {0}: Work Order {1} is in this plan twice.").format(r.idx, r.rosin_work_order))
            seen.add(r.rosin_work_order)
            if not (getdate(self.from_date) <= getdate(r.planned_date) <= getdate(self.to_date)):
                frappe.throw(_("Row {0}: Planned Date {1} is outside the plan period {2} to {3}.").format(
                    r.idx, r.planned_date, self.from_date, self.to_date))
            o = old.get(r.name)
            if not o:
                if r.rosin_work_order in taken:
                    frappe.throw(_("Row {0}: Work Order {1} is already planned in {2}.").format(
                        r.idx, r.rosin_work_order, taken[r.rosin_work_order]))
                self.fill_new_row(r, built.get(r.rosin_work_order))
                changes.added.append(r)
            else:
                if o.row_status != "Scheduled" and any(str(o.get(f) or "") != str(r.get(f) or "") for f in LOCKED_FIELDS):
                    frappe.throw(_("Row {0}: {1} is {2}; only Scheduled washes can be changed.").format(
                        r.idx, r.strain, _(o.row_status)))
                if str(o.planned_date) != str(r.planned_date):
                    changes.dated.append(r)
                if abs(flt(o.bh_planned_g) - flt(r.bh_planned_g)) > 0.0005:
                    if frappe.db.exists("Stock Entry", {"work_order": r.rosin_work_order, "docstatus": ["<", 2]}):
                        frappe.throw(_("Row {0}: Work Order {1} already has a stock entry; its Bubble Hash can no longer be changed.").format(
                            r.idx, r.rosin_work_order))
                    changes.consume.append(r)
            if flt(r.bh_planned_g) <= 0:
                frappe.throw(_("Row {0}: Bubble Hash to press must be greater than 0 g.").format(r.idx))
            for f in YIELD_FIELDS:
                if not 0 <= flt(r.get(f)) <= 100:
                    frappe.throw(_("Row {0}: an expected yield must be between 0% and 100%.").format(r.idx))
            row_math(r)
        current = {r.name for r in self.items}
        for name, o in old.items():
            if name not in current:
                why = unschedule_block(o)
                if why:
                    frappe.throw(_("{0} cannot be unscheduled: {1}.").format(o.strain or o.rosin_work_order, why))
                changes.removed.append(o)
        self.flags.press_changes = changes
        self.set_totals_and_status()

    def fill_new_row(self, r, b):
        if not b:
            frappe.throw(_("Row {0}: {1} is not an open Rosin Pressing Work Order on {2}.").format(
                r.idx, r.rosin_work_order, get_settings().press_workstation))
        if b.hash_status != "Completed":
            frappe.throw(_("Row {0}: the wash for {1} is not finished yet (hash Work Order {2} is {3}).").format(
                r.idx, r.rosin_work_order, b.hash_work_order, _(b.hash_status)))
        keep = flt(r.bh_planned_g) if flt(r.bh_planned_g) > 0 and not b.transferred else None
        for f in frappe.get_meta("Press Plan Item").get_valid_columns():
            if f in b and f not in ("planned_date", "sequence", "name", "idx"):
                r.set(f, b[f])
        if keep:
            r.bh_planned_g = keep
        r.row_status = "Scheduled"
        r.orig_wo_start = b.planned_start_date
        jc = live_job_card(r.rosin_work_order)
        r.orig_jc_start = jc.expected_start_date if jc and jc.docstatus == 0 else None

    def on_update(self):
        ch = self.flags.pop("press_changes", None)
        if not ch:
            return
        for o in ch.removed:
            restore_dates(o, self.name)
        for r in ch.added:
            apply_dates(r)
            consumed = apply_consumption(r)
            _note(r.rosin_work_order, _("Scheduled for pressing on {0} in Press Production Plan {1}. {2}").format(
                frappe.utils.formatdate(r.planned_date), self.name,
                _("Bubble Hash to consume: {0} g.").format(round(flt(r.bh_planned_g), 3)) if consumed
                else _("Its Bubble Hash was already transferred, so the quantity is unchanged.")))
        for r in ch.dated:
            if r not in ch.added:
                apply_dates(r)
                _note(r.rosin_work_order, _("Press date moved to {0} in Press Production Plan {1}.").format(
                    frappe.utils.formatdate(r.planned_date), self.name))
        for r in ch.consume:
            if r not in ch.added and apply_consumption(r):
                _note(r.rosin_work_order, _("Bubble Hash to consume set to {0} g in Press Production Plan {1}.").format(
                    round(flt(r.bh_planned_g), 3), self.name))

    def set_totals_and_status(self):
        live = [r for r in self.items if r.row_status != "Cancelled"]
        self.washes = len(live)
        self.bh_planned_g = sum(flt(r.bh_planned_g) for r in live)
        self.expected_rosin_g = sum(flt(r.expected_rosin_g) for r in live)
        self.actual_rosin_g = sum(flt(r.actual_rosin_g) for r in live)
        if live and all(r.row_status == "Whipped" for r in live):
            self.status = "Completed"
        elif any(r.row_status in ("Pressed", "Whipped") for r in live):
            self.status = "In Progress"
        else:
            self.status = "Draft"

    def on_trash(self):
        for r in self.items:
            why = unschedule_block(r)
            if why:
                frappe.throw(_("Plan {0} cannot be deleted: {1} {2}.").format(self.name, r.strain or r.rosin_work_order, why))
        for r in self.items:
            if r.row_status == "Scheduled":
                restore_dates(r, self.name)


def recompute(plan_name):
    plan = frappe.get_doc("Press Production Plan", plan_name)
    plan.set_totals_and_status()
    plan.db_set({"washes": plan.washes, "bh_planned_g": plan.bh_planned_g, "expected_rosin_g": plan.expected_rosin_g,
                 "actual_rosin_g": plan.actual_rosin_g, "status": plan.status})
    plan.notify_update()
