import re

import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import add_days, flt, getdate

LBS_TO_GRAM = 453.592
LOCKED_FIELDS = (
    "planned_date", "fresh_frozen_item", "source_freezer", "planned_qty_lbs",
    "project", "bubble_hash_item", "rosin_item", "expected_hash_yield", "expected_rosin_yield",
)


def get_settings():
    return frappe.get_cached_doc("Wash Plan Settings")


def row_math(row, settings=None):
    """grams / expected hash / expected rosin for one row."""
    s = settings or get_settings()
    if row.get("expected_hash_yield") in (None, ""):
        row.expected_hash_yield = flt(s.default_hash_yield)
    if row.get("expected_rosin_yield") in (None, ""):
        row.expected_rosin_yield = flt(s.default_rosin_yield)
    row.planned_qty_grams = flt(row.planned_qty_lbs) * LBS_TO_GRAM
    row.expected_hash_g = row.planned_qty_grams * flt(row.expected_hash_yield) / 100
    row.expected_rosin_g = row.expected_hash_g * flt(row.expected_rosin_yield) / 100


def base_name(item_name):
    """Strain name: text before the first underscore; without one, strip a trailing FF suffix."""
    n = (item_name or "").strip()
    if "_" in n:
        return n.split("_", 1)[0].strip()
    return re.sub(r"\s*-\s*(FF|Fresh Frozen)\s*$", "", n, flags=re.I).strip()


def _transferred(wo_name):
    if not wo_name:
        return False
    v = frappe.db.get_value("Work Order", wo_name, ["material_transferred_for_manufacturing", "docstatus"], as_dict=1)
    return bool(v and (flt(v.material_transferred_for_manufacturing) > 0 or v.docstatus == 2))


def _blank(project):
    return project or ""


def stock_balance(item, freezer, project=None):
    """Stock Ledger balance of item in freezer for one value of the project inventory dimension
    (blank project = stock that carries no project). Never Bin.projected_qty."""
    return flt(frappe.db.sql(
        """select sum(actual_qty) from `tabStock Ledger Entry`
        where item_code = %s and warehouse = %s and ifnull(project, '') = %s and is_cancelled = 0""",
        (item, freezer, _blank(project)))[0][0])


@frappe.whitelist()
def get_stock_projects(item, freezer):
    """Projects (blank = no project) that hold stock of the item in the freezer, with qty."""
    return frappe.db.sql(
        """select ifnull(project, '') as project, sum(actual_qty) as qty from `tabStock Ledger Entry`
        where item_code = %s and warehouse = %s and is_cancelled = 0
        group by ifnull(project, '') having sum(actual_qty) > 0.0001 order by project""",
        (item, freezer), as_dict=True)


def external_holds(item, freezer, project=None, exclude_plan=None, exclude_row=None):
    """Stock held by other Wash Production Plans and by open Manufacture MRs not linked to a plan.
    Returns (qty, [description, ...])."""
    qty, holders = 0.0, []
    rows = frappe.db.sql(
        """select i.name, i.parent, i.idx, i.planned_qty_lbs, i.hash_work_order, i.planned_date
        from `tabWash Production Plan Item` i join `tabWash Production Plan` p on p.name = i.parent
        where i.fresh_frozen_item = %s and i.source_freezer = %s and ifnull(i.project, '') = %s
          and i.row_status in ('Planned', 'MR Created') and p.status != 'Cancelled'""",
        (item, freezer, _blank(project)), as_dict=True)
    for r in rows:
        if r.name == exclude_row or r.parent == exclude_plan or _transferred(r.hash_work_order):
            continue
        qty += flt(r.planned_qty_lbs)
        holders.append(_("{0} row {1}: {2} lbs ({3})").format(r.parent, r.idx, flt(r.planned_qty_lbs), r.planned_date))
    for mr, q, dt in frappe.db.sql(
        """select mr.name, sum(mri.stock_qty), mr.transaction_date from `tabMaterial Request` mr
        join `tabMaterial Request Item` mri on mri.parent = mr.name
        where mr.material_request_type = 'Manufacture' and mr.docstatus = 1
          and mr.status not in ('Stopped', 'Cancelled', 'Completed')
          and ifnull(mr.custom_wash_production_plan, '') = ''
          and ifnull(mr.custom_project, '') = %s and mri.item_code = %s and mri.warehouse = %s
        group by mr.name""", (_blank(project), item, freezer)):
        if frappe.db.exists("Work Order", {"material_request": mr, "docstatus": 1, "material_transferred_for_manufacturing": [">", 0]}):
            continue
        qty += flt(q)
        holders.append(_("{0}: {1} lbs ({2})").format(mr, flt(q), dt))
    return qty, holders


def get_available_qty(item, freezer, exclude_row=None, exclude_plan=None, project=None):
    """Balance of the chosen project's stock minus everything booked against it elsewhere."""
    return stock_balance(item, freezer, project) - external_holds(item, freezer, project, exclude_plan, exclude_row)[0]


@frappe.whitelist()
def get_row_availability(item, freezer, project=None, plan=None, row=None):
    ext, holders = external_holds(item, freezer, project, exclude_plan=plan, exclude_row=row)
    bal = stock_balance(item, freezer, project)
    return {"balance": bal, "available": bal - ext, "holders": holders}


@frappe.whitelist()
def get_item_freezers(item):
    s = get_settings()
    out = []
    for f in s.freezers:
        q = flt(frappe.db.get_value("Bin", {"item_code": item, "warehouse": f.warehouse}, "actual_qty"))
        if q > 0:
            out.append({"warehouse": f.warehouse, "qty": q})
    return out


@frappe.whitelist()
def suggest_finished_items(item):
    """History first (latest submitted Manufacture MR of the same strain), name match only as fallback.
    Anything not confidently matched stays None; never guess."""
    s = get_settings()
    base = base_name(frappe.db.get_value("Item", item, "item_name") or "")
    out = {"bubble_hash_item": None, "rosin_item": None, "base": base}
    if not base:
        return out
    ff_groups = frappe.db.get_descendants("Item Group", s.fresh_frozen_item_group) + [s.fresh_frozen_item_group]
    cands = [i.name for i in frappe.get_all(
        "Item", filters={"item_group": ["in", ff_groups], "item_name": ["like", base.replace("%", "") + "%"]},
        fields=["name", "item_name"], limit=500) if base_name(i.item_name).lower() == base.lower()]
    if cands:
        hist = frappe.db.sql(
            """select fg.item from `tabMaterial Request` mr
            join `tabFinished Goods Detail` fg on fg.parent = mr.name and fg.parenttype = 'Material Request'
            where mr.docstatus = 1 and mr.material_request_type = 'Manufacture'
              and exists (select 1 from `tabMaterial Request Item` mri where mri.parent = mr.name and mri.item_code in %(c)s)
            order by mr.creation desc, fg.idx""", {"c": cands}, pluck=True)
        for it in hist:
            grp = frappe.db.get_value("Item", it, "item_group")
            if grp == s.bubble_hash_item_group and not out["bubble_hash_item"]:
                out["bubble_hash_item"] = it
            elif grp == s.rosin_item_group and not out["rosin_item"]:
                out["rosin_item"] = it
    for key, grp, suffix in (("bubble_hash_item", s.bubble_hash_item_group, "Bubble Hash"), ("rosin_item", s.rosin_item_group, "Rosin")):
        if not out[key]:
            hits = frappe.get_all("Item", filters={"item_group": grp}, fields=["name", "item_name"], limit=2000)
            m = [h.name for h in hits if (h.item_name or "").strip().lower() == f"{base} - {suffix}".lower()]
            out[key] = m[0] if len(m) == 1 else None
    return out


def _next_code(group, prefix):
    """Next item code from a real naming series ("BH-.#####" / "RS.#####"), first catching the
    series up with the codes that already exist so numbering continues, never restarts."""
    from frappe.model.naming import make_autoname

    top = frappe.db.sql(
        "select max(cast(substr(name, %s) as unsigned)) from tabItem where item_group = %s and name like %s",
        (len(prefix) + 1, group, prefix + "%"))[0][0] or 0
    cur = frappe.db.sql("select `current` from `tabSeries` where name = %s", prefix)
    if not cur:
        frappe.db.sql("insert into `tabSeries` (name, `current`) values (%s, %s)", (prefix, int(top)))
    elif cur[0][0] < top:
        frappe.db.sql("update `tabSeries` set `current` = %s where name = %s", (int(top), prefix))
    return make_autoname(f"{prefix}.#####")


@frappe.whitelist()
def create_finished_item(base, kind):
    """Create '<base> - Bubble Hash' / '<base> - Rosin' following the existing code pattern."""
    s = get_settings()
    group, suffix, prefix = (
        (s.bubble_hash_item_group, "Bubble Hash", "BH-") if kind == "bubble_hash"
        else (s.rosin_item_group, "Rosin", "RS")
    )
    existing = frappe.db.get_value("Item", {"item_group": group, "item_name": f"{base} - {suffix}"}, "name")
    if existing:
        return existing
    ref = frappe.db.get_value("Item", {"item_group": group, "name": ["like", prefix + "%"]}, ["stock_uom"], as_dict=1) or {}
    item = frappe.new_doc("Item")
    item.item_code = _next_code(group, prefix)
    item.item_name = f"{base} - {suffix}"
    item.item_group = group
    item.stock_uom = ref.get("stock_uom") or "Gram"
    item.is_stock_item = 1
    item.insert()
    return item.name


def block_reason(r, remaining):
    """Why this row cannot get a Material Request yet (None when it can). One rule set for the
    form, the Board and the bulk action."""
    if r.row_status != "Planned":
        return _("not in Planned status")
    if flt(r.planned_qty_lbs) <= 0:
        return _("Planned Qty must be greater than 0 lbs")
    if not (r.bubble_hash_item and r.rosin_item):
        return _("Bubble Hash / Rosin item is missing")
    if remaining.get(r.name, 0) < flt(r.planned_qty_lbs):
        held = [x.project for x in get_stock_projects(r.fresh_frozen_item, r.source_freezer) if x.project]
        if not r.project and held:
            return _("choose the project that holds this stock ({0})").format(", ".join(held))
        return _("planned qty exceeds the stock available for project {0}").format(r.project or _("(none)"))
    return None


@frappe.whitelist()
def create_material_requests(plan, rows=None):
    doc = frappe.get_doc("Wash Production Plan", plan)
    doc.check_permission("write")
    wanted = frappe.parse_json(rows) if rows else None
    made, skipped = [], []
    remaining = doc.allocate()[0]
    for r in doc.items:
        if wanted and r.name not in wanted:
            continue
        why = block_reason(r, remaining)
        if why:
            skipped.append(f"{r.idx} {r.item_name}: {why}")
            continue
        made.append((r, build_mr(doc, r)))
    for r, mr in made:
        r.db_set({"material_request": mr.name, "row_status": "MR Created"})
    recompute(doc.name)
    return {
        "made": [{"mr": m.name, "project": r.project or "", "row": r.idx} for r, m in made],
        "skipped": skipped,
    }


def build_mr(plan, r):
    mfg = frappe.get_cached_doc("Manufacturing Settings")
    mr = frappe.new_doc("Material Request")
    mr.material_request_type = "Manufacture"
    mr.company = plan.company
    mr.transaction_date = mr.schedule_date = r.planned_date
    mr.set_warehouse = r.source_freezer
    mr.custom_routing = plan.routing
    if r.project:  # must be the project the stock sits under; empty only for project-less stock
        mr.custom_project = r.project
    mr.custom_wash_production_plan = plan.name
    mr.custom_wash_plan_row = r.name
    mr.append("items", {
        "item_code": r.fresh_frozen_item, "qty": r.planned_qty_lbs, "uom": "LBS", "stock_uom": "LBS",
        "conversion_factor": 1, "warehouse": r.source_freezer, "schedule_date": r.planned_date,
    })
    for item, op, y, g in (
        (r.bubble_hash_item, "Hash Processing", r.expected_hash_yield, r.expected_hash_g),
        (r.rosin_item, "Rosin Pressing", r.expected_rosin_yield, r.expected_rosin_g),
    ):
        mr.append("custom_finished_goods", {
            "item": item, "operation": op, "expected_yield_": y,
            "finished_qty_grams": g, "finished_qty_pounds": g / LBS_TO_GRAM,
            "source_warehouse": r.source_freezer if op == "Hash Processing" else mfg.default_fg_warehouse,
            "wip_warehouse": mfg.default_wip_warehouse, "target_warehouse": mfg.default_fg_warehouse,
        })
    mr.insert()  # first workflow state; the workflow is not bypassed
    return mr


def recompute(plan_name):
    plan = frappe.get_doc("Wash Production Plan", plan_name)
    plan.flags.from_sync = True
    plan.set_totals_and_status()
    plan.db_set({
        "total_washes": plan.total_washes, "total_planned_lbs": plan.total_planned_lbs,
        "total_expected_hash_g": plan.total_expected_hash_g, "total_expected_rosin_g": plan.total_expected_rosin_g,
        "total_actual_hash_g": plan.total_actual_hash_g, "total_actual_rosin_g": plan.total_actual_rosin_g,
        "status": plan.status,
    })
    plan.notify_update()


class WashProductionPlan(Document):
    def onload(self):
        # HTML fields have no column; the summary is rendered on load and refreshed by the form.
        self.set_onload("project_summary", self.render_summary())

    def before_validate(self):
        s = get_settings()
        self.company = self.company or s.default_company
        self.routing = s.routing
        self.planned_by = self.planned_by or frappe.session.user
        if self.plan_type == "Daily":
            self.to_date = self.from_date
        elif self.plan_type == "Weekly" and self.from_date:
            self.to_date = add_days(self.from_date, 6)

    def validate(self):
        if self.flags.from_sync:
            return
        s = get_settings()
        if getdate(self.to_date) < getdate(self.from_date):
            frappe.throw(_("To Date cannot be before From Date."))
        freezers = {f.warehouse for f in s.freezers}
        old = {r.name: r for r in (self.get_doc_before_save().items if self.get_doc_before_save() else [])}
        for r in self.items:
            if not (getdate(self.from_date) <= getdate(r.planned_date) <= getdate(self.to_date)):
                frappe.throw(_("Row {0}: Planned Date {1} is outside the plan period {2} to {3}.").format(
                    r.idx, r.planned_date, self.from_date, self.to_date))
            if flt(r.planned_qty_lbs) <= 0:
                frappe.throw(_("Row {0}: Planned Qty must be greater than 0 lbs.").format(r.idx))
            if r.source_freezer not in freezers:
                frappe.throw(_("Row {0}: {1} is not a configured freezer in Wash Plan Settings.").format(r.idx, r.source_freezer))
            o = old.get(r.name)
            if o and o.row_status != "Planned":
                for f in LOCKED_FIELDS:
                    if (o.get(f) or "") != (r.get(f) or ""):
                        frappe.throw(_("Row {0}: only rows in Planned status can be edited.").format(r.idx))
            if not r.is_new() and not o:
                pass
            row_math(r, s)
        gone = [o for n, o in old.items() if n not in {r.name for r in self.items} and o.row_status != "Planned"]
        if gone:
            frappe.throw(_("Row {0}: only rows in Planned status can be deleted.").format(gone[0].idx))
        remaining, holders = self.allocate()
        over = []
        for r in self.items:
            if r.row_status != "Planned":
                continue
            r.available_qty_lbs = remaining[r.name]
            r.stock_held_by = "\n".join(holders[r.name])
            gap = flt(r.planned_qty_lbs) - remaining[r.name]
            if gap > 0:
                name = r.item_name or r.fresh_frozen_item
                held = [x["project"] for x in get_stock_projects(r.fresh_frozen_item, r.source_freezer) if x["project"]]
                if not r.project and held and stock_balance(r.fresh_frozen_item, r.source_freezer) <= 0:
                    over.append(_("Row {0}: {1} in {2} is held under project(s) {3}. Choose a project.").format(
                        r.idx, name, r.source_freezer, ", ".join(held)))
                else:
                    msg = _("Row {0}: {1} in {2} exceeds available stock by {3} lbs.").format(r.idx, name, r.source_freezer, round(gap, 2))
                    if holders[r.name]:
                        msg += " " + _("Held by: {0}").format("; ".join(holders[r.name]))
                    over.append(msg)
        self.set_totals_and_status()
        if over:
            frappe.msgprint("<br>".join(over), title=_("Over-booked"), indicator="orange")

    def allocate(self):
        """Allocate stock row by row in (planned_date, idx) order, after other plans and open MRs.
        Returns ({row name: qty left for that row}, {row name: [holders]})."""
        used, remaining, holders = {}, {}, {}
        for r in sorted(self.items, key=lambda x: (str(x.planned_date or ""), x.idx)):
            key = (r.fresh_frozen_item, r.source_freezer, _blank(r.project))
            if key not in used:
                ext, hold = external_holds(*key[:2], key[2], exclude_plan=self.name)
                used[key] = [stock_balance(*key[:2], key[2]) - ext, hold]
            remaining[r.name] = used[key][0]
            holders[r.name] = used[key][1]
            if r.row_status in ("Planned", "MR Created") and not _transferred(r.hash_work_order):
                used[key][0] -= flt(r.planned_qty_lbs)
        return remaining, holders

    def set_totals_and_status(self):
        rows = self.items
        self.total_washes = len(rows)
        self.total_planned_lbs = sum(flt(r.planned_qty_lbs) for r in rows)
        self.total_expected_hash_g = sum(flt(r.expected_hash_g) for r in rows)
        self.total_expected_rosin_g = sum(flt(r.expected_rosin_g) for r in rows)
        self.total_actual_hash_g = sum(flt(r.actual_hash_g) for r in rows)
        self.total_actual_rosin_g = sum(flt(r.actual_rosin_g) for r in rows)
        if self.status != "Cancelled":
            if rows and all(r.row_status in ("Completed", "Skipped") for r in rows):
                self.status = "Completed"
            elif any(r.material_request for r in rows):
                self.status = "In Progress"
            else:
                self.status = "Draft"

    def render_summary(self):
        g = {}
        for r in self.items:
            k = r.project or ""
            d = g.setdefault(k, {"w": 0, "l": 0, "h": 0, "r": 0})
            d["w"] += 1; d["l"] += flt(r.planned_qty_lbs); d["h"] += flt(r.expected_hash_g); d["r"] += flt(r.expected_rosin_g)
        html = ""
        for k, d in sorted(g.items(), key=lambda x: (x[0] == "", x[0])):
            title = frappe.db.get_value("Project", k, "project_name") if k else "No Project"
            html += (
                '<div style="display:inline-block;border:1px solid var(--border-color);border-radius:8px;padding:8px 12px;margin:0 8px 8px 0;min-width:170px">'
                f"<b>{frappe.utils.escape_html(title or k)}</b><br><span class='text-muted'>{frappe.utils.escape_html(k or 'MR project left empty')}</span><br>"
                f"{d['w']} wash(es) · {d['l']:,.0f} lbs<br><span class='text-muted'>Exp. hash {d['h']:,.0f} g · rosin {d['r']:,.0f} g</span></div>"
            )
        return html or ""

    def on_trash(self):
        if any(r.row_status != "Planned" for r in self.items):
            frappe.throw(_("A plan with rows that have a Material Request cannot be deleted."))
