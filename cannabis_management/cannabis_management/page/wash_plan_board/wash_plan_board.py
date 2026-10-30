import frappe
from frappe import _
from frappe.utils import add_days, flt, getdate, nowdate, strip_html

from cannabis_management.cannabis_management.doctype.wash_production_plan import wash_production_plan as wpp

PLAN = "Wash Production Plan"
ROW = "Wash Production Plan Item"
OPEN = ("Draft", "In Progress")
EDITABLE_FIELDS = (
	"planned_date", "source_freezer", "project", "planned_qty_lbs",
	"expected_hash_yield", "expected_rosin_yield", "bubble_hash_item", "rosin_item", "notes",
)


def is_admin():
	return "System Manager" in frappe.get_roles()


def week_of(d):
	d = getdate(d or nowdate())
	start = getdate(add_days(d, -d.weekday()))
	return start, getdate(add_days(start, 6))


def fmt_date(d):
	return getdate(d).strftime("%a, %b %-d") if d else ""


@frappe.whitelist()
def get_context():
	s = wpp.get_settings()
	start, end = week_of(nowdate())
	return {
		"company": s.default_company,
		"routing": s.routing,
		"hash_yield": flt(s.default_hash_yield),
		"rosin_yield": flt(s.default_rosin_yield),
		"bubble_hash_group": s.bubble_hash_item_group,
		"rosin_group": s.rosin_item_group,
		"freezers": [f.warehouse for f in s.freezers],
		"is_admin": is_admin(),
		"user": {"name": frappe.session.user, "full_name": frappe.utils.get_fullname(frappe.session.user)},
		"week": {"from": str(start), "to": str(end)},
		"strains": strains(s),
		"plans": open_plans(),
	}


def strains(s=None):
	"""Fresh Frozen items with stock in a configured freezer, with qty per freezer (all projects)."""
	s = s or wpp.get_settings()
	freezers = [f.warehouse for f in s.freezers]
	if not freezers:
		return []
	groups = frappe.db.get_descendants("Item Group", s.fresh_frozen_item_group) + [s.fresh_frozen_item_group]
	out = {}
	for r in frappe.db.sql(
		"""select sle.item_code, i.item_name, sle.warehouse, sum(sle.actual_qty) qty
		from `tabStock Ledger Entry` sle join `tabItem` i on i.name = sle.item_code
		where sle.warehouse in %(w)s and sle.is_cancelled = 0 and i.item_group in %(g)s and i.disabled = 0
		group by sle.item_code, sle.warehouse having sum(sle.actual_qty) > 0.0001""",
		{"w": freezers, "g": groups}, as_dict=True):
		e = out.setdefault(r.item_code, {"item": r.item_code, "item_name": r.item_name or r.item_code, "stock": {}})
		e["stock"][r.warehouse] = flt(r.qty, 3)
	return sorted(out.values(), key=lambda x: x["item_name"].lower())


def open_plans():
	return frappe.get_all(
		PLAN, filters={"status": ["in", OPEN]},
		fields=["name", "plan_type", "from_date", "to_date", "status", "total_washes", "total_planned_lbs"],
		order_by="from_date desc, creation desc", limit=100,
	)


@frappe.whitelist()
def get_board(scope):
	return board(frappe.parse_json(scope) or {})


def board(scope):
	if scope.get("mode") == "plan" and scope.get("plan"):
		plan = frappe.get_doc(PLAN, scope["plan"])
		plan.check_permission("read")
		plans, start, end = [plan], getdate(plan.from_date), getdate(plan.to_date)
	else:
		week = week_of(nowdate())
		start, end = getdate(scope.get("from") or week[0]), getdate(scope.get("to") or week[1])
		if end < start:
			frappe.throw(_("To Date cannot be before From Date."))
		names = frappe.db.sql_list(
			"""select distinct p.name from `tabWash Production Plan` p
			join `tabWash Production Plan Item` i on i.parent = p.name
			where p.status != 'Cancelled' and i.planned_date between %s and %s
			order by p.from_date, p.name""", (start, end))
		plans = [frappe.get_doc(PLAN, n) for n in names]
		plan = None

	cache = {"projects": {}, "freezers": {}, "names": {}, "project_names": {}}
	rows, booked = [], {}
	for p in plans:
		can_write = p.has_permission("write")
		remaining = p.allocate()[0] if p.status != "Cancelled" else {}
		for r in p.items:
			if not plan and not (start <= getdate(r.planned_date) <= end):
				continue
			rows.append(row_view(p, r, remaining, can_write, cache))
			if r.row_status in ("Planned", "MR Created") and not wpp._transferred(r.hash_work_order):
				k = (r.fresh_frozen_item, r.source_freezer)
				booked[k] = booked.get(k, 0) + flt(r.planned_qty_lbs)
	rows.sort(key=lambda x: (x["planned_date"], x["plan"], x["idx"]))

	return {
		"mode": "plan" if plan else "view",
		"from": str(start), "to": str(end),
		"plan": plan_view(plan) if plan else None,
		"plans_in_view": [] if plan else [
			{"name": p.name, "status": p.status, "from_date": str(p.from_date), "to_date": str(p.to_date)} for p in plans],
		"rows": rows,
		"freezers": freezer_stock(booked),
	}


def plan_view(p):
	return {
		"name": p.name, "plan_type": p.plan_type, "from_date": str(p.from_date), "to_date": str(p.to_date),
		"status": p.status, "company": p.company, "routing": p.routing,
		"planned_by": frappe.utils.get_fullname(p.planned_by) if p.planned_by else "",
		"can_write": bool(p.has_permission("write")) and p.status != "Cancelled",
	}


def _item_name(code, cache):
	if not code:
		return ""
	if code not in cache["names"]:
		cache["names"][code] = frappe.db.get_value("Item", code, "item_name") or code
	return cache["names"][code]


def _project_name(project, cache):
	if not project:
		return ""
	if project not in cache["project_names"]:
		cache["project_names"][project] = frappe.db.get_value("Project", project, "project_name") or ""
	return cache["project_names"][project]


def _stock_projects(item, freezer, cache):
	k = (item, freezer)
	if k not in cache["projects"]:
		cache["projects"][k] = [
			{"project": x.project, "qty": flt(x.qty, 3), "project_name": _project_name(x.project, cache)}
			for x in wpp.get_stock_projects(item, freezer)]
	return cache["projects"][k]


def row_view(p, r, remaining, can_write, cache):
	editable = bool(can_write) and p.status != "Cancelled" and r.row_status == "Planned"
	left = remaining.get(r.name) if r.row_status == "Planned" else None
	name = r.item_name or _item_name(r.fresh_frozen_item, cache)
	out = {
		"name": r.name, "plan": p.name, "plan_status": p.status, "idx": r.idx,
		"planned_date": str(r.planned_date), "item": r.fresh_frozen_item, "item_name": name,
		"base": wpp.base_name(name),
		"freezer": r.source_freezer, "project": r.project or "", "project_name": _project_name(r.project, cache),
		"planned_lbs": flt(r.planned_qty_lbs),
		"available_lbs": flt(left, 3) if left is not None else None,
		"over_by": max(flt(r.planned_qty_lbs) - flt(left), 0) if left is not None else 0,
		"expected_hash_yield": flt(r.expected_hash_yield), "expected_rosin_yield": flt(r.expected_rosin_yield),
		"expected_hash_g": flt(r.expected_hash_g), "expected_rosin_g": flt(r.expected_rosin_g),
		"actual_hash_g": flt(r.actual_hash_g), "actual_rosin_g": flt(r.actual_rosin_g),
		"actual_hash_yield": flt(r.actual_hash_yield), "actual_rosin_yield": flt(r.actual_rosin_yield),
		"status": r.row_status or "Planned",
		"material_request": r.material_request or "",
		"mr_state": frappe.db.get_value("Material Request", r.material_request, "status") if r.material_request else "",
		"hash_work_order": r.hash_work_order or "", "rosin_work_order": r.rosin_work_order or "",
		"bubble_hash_item": r.bubble_hash_item or "", "bubble_hash_name": _item_name(r.bubble_hash_item, cache),
		"rosin_item": r.rosin_item or "", "rosin_name": _item_name(r.rosin_item, cache),
		"notes": r.notes or "",
		"editable": editable,
		"blocked": wpp.block_reason(r, remaining) if editable else None,
	}
	if editable:
		if r.fresh_frozen_item not in cache["freezers"]:
			cache["freezers"][r.fresh_frozen_item] = wpp.get_item_freezers(r.fresh_frozen_item)
		out["freezer_options"] = cache["freezers"][r.fresh_frozen_item]
		out["project_options"] = _stock_projects(r.fresh_frozen_item, r.source_freezer, cache)
	return out


def freezer_stock(booked):
	"""Per configured freezer: Fresh Frozen items that have stock or washes booked in this view."""
	s = wpp.get_settings()
	stock = {}
	for st in strains(s):
		for w, q in st["stock"].items():
			stock[(st["item"], w)] = (st["item_name"], q)
	out = []
	for f in (x.warehouse for x in s.freezers):
		items = []
		for k in {k for k in stock if k[1] == f} | {k for k in booked if k[1] == f}:
			name = stock[k][0] if k in stock else (frappe.db.get_value("Item", k[0], "item_name") or k[0])
			items.append({"item": k[0], "item_name": name,
				"stock": flt(stock[k][1], 3) if k in stock else 0, "booked": flt(booked.get(k), 3)})
		items.sort(key=lambda x: (-x["booked"], x["item_name"].lower()))
		out.append({"name": f, "stock": sum(i["stock"] for i in items),
			"booked": sum(i["booked"] for i in items), "items": items})
	return out


# ---------- writes: every change goes through the plan document and its validations ----------

def _mutate(scope, fn):
	scope = frappe.parse_json(scope) or {}
	frappe.db.savepoint("wash_plan_board")
	try:
		result = fn(scope) or {}
	except (frappe.ValidationError, frappe.PermissionError) as e:
		frappe.db.rollback(save_point="wash_plan_board")
		msg = strip_html(str(e) or "").strip()
		if not msg and frappe.local.message_log:
			last = frappe.local.message_log[-1]
			msg = strip_html((frappe.parse_json(last) if isinstance(last, str) else last).get("message", ""))
		frappe.local.message_log = []
		return {"ok": False, "error": msg or _("The change could not be saved."), "board": board(scope)}
	# warnings such as "Over-booked" are shown on the rows themselves, not as pop-ups
	frappe.local.message_log = []
	return {"ok": True, **result, "board": board(result.get("scope") or scope), "plans": open_plans()}


def _get_row(row):
	parent = frappe.db.get_value(ROW, row, "parent")
	if not parent:
		frappe.throw(_("This wash no longer exists. Refresh the board."))
	doc = frappe.get_doc(PLAN, parent)
	doc.check_permission("write")
	return doc, next(r for r in doc.items if r.name == row)


def _new_plan(plan_type, from_date, to_date=None):
	doc = frappe.new_doc(PLAN)
	doc.plan_type = plan_type or "Weekly"
	doc.from_date = from_date
	doc.to_date = to_date or from_date
	return doc


def _target(planned_date, plan=None, new_plan=None):
	"""Where a new wash goes: the given plan, the unsaved new plan, the open plan that covers the date,
	or else a new Weekly plan for that week."""
	if plan:
		return plan, None
	if new_plan:
		return None, new_plan
	hit = frappe.get_all(
		PLAN, filters={"status": ["in", OPEN], "from_date": ["<=", planned_date], "to_date": [">=", planned_date]},
		pluck="name", order_by="creation desc", limit=1)
	if hit:
		return hit[0], None
	return None, {"plan_type": "Weekly", "from_date": str(week_of(planned_date)[0])}


@frappe.whitelist()
def create_plan(plan_type, from_date, to_date=None, scope=None):
	def run(sc):
		doc = _new_plan(plan_type, from_date, to_date)
		doc.insert()
		return {"message": _("Plan {0} created.").format(doc.name), "plan": doc.name,
			"scope": {"mode": "plan", "plan": doc.name}}
	return _mutate(scope, run)


@frappe.whitelist()
def update_plan(plan, plan_type, from_date, to_date=None, scope=None):
	def run(sc):
		doc = frappe.get_doc(PLAN, plan)
		doc.check_permission("write")
		doc.plan_type, doc.from_date = plan_type, from_date
		if plan_type == "Custom":
			doc.to_date = to_date
		doc.save()
		return {"message": _("Plan period updated.")}
	return _mutate(scope, run)


@frappe.whitelist()
def preview_wash(item, freezer=None, project=None, qty=0, planned_date=None, plan=None, new_plan=None):
	"""What adding this wash would give: expected output, free stock, finished items and target plan."""
	s = wpp.get_settings()
	row = frappe._dict(planned_qty_lbs=flt(qty), expected_hash_yield=None, expected_rosin_yield=None)
	wpp.row_math(row, s)
	fin = wpp.suggest_finished_items(item)
	cache = {"project_names": {}, "projects": {}}
	out = {
		"expected_hash_g": row.expected_hash_g, "expected_rosin_g": row.expected_rosin_g,
		"bubble_hash_item": fin.get("bubble_hash_item"), "rosin_item": fin.get("rosin_item"),
		"projects": _stock_projects(item, freezer, cache) if freezer else [],
		"available": wpp.get_available_qty(item, freezer, project=project or "") if freezer else None,
		"target": None,
	}
	if planned_date:
		name, new = _target(planned_date, plan, frappe.parse_json(new_plan) if new_plan else None)
		if name:
			out["target"] = {"plan": name}
		else:
			t = _new_plan(new.get("plan_type"), new.get("from_date"), new.get("to_date"))
			t.run_method("before_validate")
			out["target"] = {"new": True, "plan_type": t.plan_type, "from_date": str(t.from_date), "to_date": str(t.to_date)}
	return out


@frappe.whitelist()
def add_wash(planned_date, item, freezer, qty, project=None, plan=None, new_plan=None, scope=None):
	def run(sc):
		name, new = _target(planned_date, plan, frappe.parse_json(new_plan) if new_plan else None)
		if name:
			doc = frappe.get_doc(PLAN, name)
			doc.check_permission("write")
		else:
			doc = _new_plan(new.get("plan_type"), new.get("from_date"), new.get("to_date"))
		fin = wpp.suggest_finished_items(item)
		doc.append("items", {
			"planned_date": planned_date, "fresh_frozen_item": item,
			"item_name": frappe.db.get_value("Item", item, "item_name"),
			"source_freezer": freezer, "project": project or None, "planned_qty_lbs": flt(qty),
			"bubble_hash_item": fin.get("bubble_hash_item"), "rosin_item": fin.get("rosin_item"),
		})
		if doc.is_new():
			doc.insert()
		else:
			doc.save()
		r = doc.items[-1]
		msg = _("{0} ({1}) added to {2} for {3}").format(r.item_name, freezer, doc.name, fmt_date(r.planned_date))
		msg += " " + (_("under {0}.").format(project) if project else _("with no project."))
		out = {"message": msg, "row": r.name, "plan": doc.name}
		if sc.get("mode") != "view" or new_plan:
			out["scope"] = {"mode": "plan", "plan": doc.name}
		return out
	return _mutate(scope, run)


@frappe.whitelist()
def update_wash(row, field, value=None, scope=None):
	if field not in EDITABLE_FIELDS:
		frappe.throw(_("{0} cannot be changed here.").format(field))

	def run(sc):
		doc, r = _get_row(row)
		if field in ("expected_hash_yield", "expected_rosin_yield", "planned_qty_lbs"):
			r.set(field, flt(value))
		else:
			r.set(field, value or None)
		if field == "source_freezer":
			# same rule as the form: one project holds the stock -> use it; a project without stock there is cleared
			held = [x.project for x in wpp.get_stock_projects(r.fresh_frozen_item, r.source_freezer)]
			if len(held) == 1:
				r.project = held[0] or None
			elif (r.project or "") not in held:
				r.project = None
		doc.save()
		return {"row": row}
	return _mutate(scope, run)


@frappe.whitelist()
def remove_wash(row, scope=None):
	def run(sc):
		doc, r = _get_row(row)
		name = r.item_name
		doc.remove(r)
		doc.save()
		return {"message": _("{0} removed from {1}.").format(name, doc.name)}
	return _mutate(scope, run)


@frappe.whitelist()
def create_item(row, kind, scope=None):
	if kind not in ("bubble_hash", "rosin"):
		frappe.throw(_("Unknown item type."))

	def run(sc):
		doc, r = _get_row(row)
		code = wpp.create_finished_item(wpp.base_name(r.item_name), kind)
		field = "bubble_hash_item" if kind == "bubble_hash" else "rosin_item"
		for x in doc.items:
			if x.row_status == "Planned" and x.fresh_frozen_item == r.fresh_frozen_item and not x.get(field):
				x.set(field, code)
		doc.save()
		s = wpp.get_settings()
		group = s.bubble_hash_item_group if kind == "bubble_hash" else s.rosin_item_group
		return {"message": _("Item {0} ({1}) is set on the wash, in the {2} item group.").format(
			code, frappe.db.get_value("Item", code, "item_name"), group)}
	return _mutate(scope, run)


@frappe.whitelist()
def create_mrs(rows, scope=None):
	rows = frappe.parse_json(rows) or []

	def run(sc):
		by_plan = {}
		for name in rows:
			parent = frappe.db.get_value(ROW, name, "parent")
			if parent:
				by_plan.setdefault(parent, []).append(name)
		made, skipped = [], []
		for plan, names in by_plan.items():
			res = wpp.create_material_requests(plan, frappe.as_json(names))
			made += res["made"]
			skipped += res["skipped"]
		if not made:
			frappe.throw("; ".join(skipped) or _("No wash is ready for a Material Request."))
		if len(made) == 1:
			m = made[0]
			msg = _("Material Request {0} created {1}.").format(
				m["mr"], _("with project {0}").format(m["project"]) if m["project"] else _("with no project"))
		else:
			with_p = len([m for m in made if m["project"]])
			msg = _("{0} Material Requests created ({1} to {2}). {3} with a project, {4} without.").format(
				len(made), made[0]["mr"], made[-1]["mr"], with_p, len(made) - with_p)
		if skipped:
			msg += " " + _("Skipped: {0}").format("; ".join(skipped))
		return {"message": msg, "made": made, "skipped": skipped}
	return _mutate(scope, run)
