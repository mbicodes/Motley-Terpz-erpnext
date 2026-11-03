"""Press Plan Board: the single screen for planning rosin pressing. Layout follows
motley-press-production-plan-demo.html. Every rule runs on the Press Production Plan document; this module only
reads and calls it."""
import frappe
from frappe import _
from frappe.utils import add_days, cint, flt, getdate, nowdate, strip_html

from cannabis_management.cannabis_management.doctype.press_production_plan import press_production_plan as ppp
from cannabis_management.doc_hooks import press_plan_sync

PLAN = "Press Production Plan"
ROW = "Press Plan Item"
EDITABLE_FIELDS = ("planned_date", "bh_planned_g") + ppp.YIELD_FIELDS


def is_admin():
	return "System Manager" in frappe.get_roles()


def week_of(d):
	d = getdate(d or nowdate())
	start = getdate(add_days(d, -d.weekday()))
	return start, getdate(add_days(start, 6))


def fmt_date(d):
	return getdate(d).strftime("%a, %b %-d") if d else ""


def fmt_g(n):
	return "{:,.0f}".format(flt(n))


@frappe.whitelist()
def get_context():
	s = ppp.get_settings()
	start, end = week_of(nowdate())
	return {
		"app_name": frappe.db.get_single_value("Website Settings", "app_name") or frappe.db.get_single_value("System Settings", "app_name") or "ERPNext",
		"company": frappe.db.get_value("Warehouse", s.source_warehouse, "company") if s.source_warehouse else "",
		"press_workstation": s.press_workstation,
		"source_warehouse": s.source_warehouse,
		"aging_days": cint(s.aging_warning_days),
		"press_step": s.press_sub_operation,
		"whip_step": s.whipping_sub_operation,
		"microns": [{"slot": g.slot, "label": g.label, "yield": g.yield_pct} for g in ppp.groups(s)],
		"is_admin": is_admin(),
		"user": {"name": frappe.session.user, "full_name": frappe.utils.get_fullname(frappe.session.user)},
		"today": nowdate(),
		"week": {"from": str(start), "to": str(end)},
		"plans": open_plans(),
	}


def open_plans():
	return frappe.get_all(
		PLAN, filters={"status": ["in", ppp.OPEN]},
		fields=["name", "plan_type", "from_date", "to_date", "status", "washes", "bh_planned_g"],
		order_by="from_date desc, creation desc", limit=100,
	)


@frappe.whitelist()
def ready_to_press():
	"""Ready to Press queue with the stock check (open plans draw on the stock first)."""
	s = ppp.get_settings()
	queue = ppp.ready_queue(s)
	stock_check(s, queue)
	c = lookups(s, [], queue)
	return [queue_view(q, ppp.groups(s), cint(s.aging_warning_days), c) for q in queue]


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
			"""select distinct p.name from `tabPress Production Plan` p join `tabPress Plan Item` i on i.parent = p.name
			where i.planned_date between %s and %s order by p.from_date, p.name""", (start, end))
		plans = [frappe.get_doc(PLAN, n) for n in names]
		plan = None

	s = ppp.get_settings()
	grps = ppp.groups(s)
	pairs = [(p, r) for p in plans for r in p.items if plan or start <= getdate(r.planned_date) <= end]
	queue = ppp.ready_queue(s)
	stock = stock_check(s, queue)
	cache = lookups(s, [r for _p, r in pairs], queue)
	rows = [row_view(p, r, grps, stock.get(r.name), cache) for p, r in pairs]
	rows.sort(key=lambda x: (x["planned_date"], x["sequence"] or 0, x["plan"], x["idx"]))
	return {
		"mode": "plan" if plan else "view",
		"from": str(start), "to": str(end),
		"plan": plan_view(plan) if plan else None,
		"plans_in_view": [] if plan else [
			{"name": p.name, "status": p.status, "from_date": str(p.from_date), "to_date": str(p.to_date)} for p in plans],
		"rows": rows,
		"queue": [queue_view(q, grps, cint(s.aging_warning_days), cache) for q in queue],
	}


def stock_check(s, queue):
	"""One allocation over everything that still needs Bubble Hash: rows of open plans (by planned date) first,
	then the Ready to Press queue (oldest wash first). Returns {plan row name: allocation}; queue entries get
	their allocation set in place."""
	open_rows = ppp.open_plan_rows()
	infos = {i.name: i for i in ppp.rosin_work_orders([r.rosin_work_order for r in open_rows], s)}
	entries = []
	for r in open_rows:
		i = infos.get(r.rosin_work_order)
		if i:
			wh, need = ppp.stock_need(i, r.bh_planned_g)
			entries.append(frappe._dict(key=r.name, bubble_hash_item=i.bubble_hash_item, warehouse=wh, project=i.project, need=need))
	ppp.allocate(entries + list(queue))
	return {e.key: e for e in entries}


def lookups(s, rows, queue):
	"""Names, Work Order / job card states and 'pressing started' facts for everything shown, in bulk."""
	wos = [r.rosin_work_order for r in rows]
	jcs = [r.job_card for r in rows if r.job_card]
	c = frappe._dict(
		names=ppp.item_names([r.bubble_hash_item for r in rows] + [q.bubble_hash_item for q in queue]),
		projects=dict(frappe.db.sql("select name, project_name from tabProject where name in %(p)s",
			{"p": list({x.project for x in list(rows) + list(queue) if x.project}) or [""]})),
		wo={w.name: w for w in frappe.get_all("Work Order", filters={"name": ["in", wos or [""]]}, fields=["name", "status", "docstatus"])},
		moved={x.parent: flt(x.transferred_qty) for x in frappe.get_all("Work Order Item",
			filters={"parent": ["in", wos or [""]], "parenttype": "Work Order"}, fields=["parent", "transferred_qty"])},
		jc={j.name: j for j in frappe.get_all("Job Card", filters={"name": ["in", jcs or [""]]}, fields=["name", "docstatus", "status"])},
		steps={},
		press_step=s.press_sub_operation, whip_step=s.whipping_sub_operation,
	)
	for parent, op, status in frappe.db.sql(
			"select parent, sub_operation, status from `tabJob Card Operation` where parenttype = 'Job Card' and parent in %(j)s",
			{"j": jcs or [""]}):
		c.steps.setdefault(parent, {})[op] = status
	c.se, c.logs = ppp.started([r.rosin_work_order for r in rows if r.row_status == "Scheduled"])
	c.can_write = {}
	return c


def plan_view(p):
	return {
		"name": p.name, "plan_type": p.plan_type, "from_date": str(p.from_date), "to_date": str(p.to_date),
		"status": p.status, "company": p.company,
		"planned_by": frappe.utils.get_fullname(p.planned_by) if p.planned_by else "",
		"can_write": bool(p.has_permission("write")),
	}


def _stock_view(e):
	if not e:
		return None
	return {"need": flt(e.need, 3), "covered": flt(e.covered, 3), "stock": flt(e.stock, 3),
		"warehouse": e.warehouse or "", "sharing": e.sharing or 0}


def _microns(x, grps, actual=True):
	out = []
	split = sum(flt(x.get("g_" + g.slot)) for g in grps)
	scale = flt(x.get("bh_planned_g")) / split if split else 0
	for g in grps:
		m = {"slot": g.slot, "label": g.label, "g": flt(x.get("g_" + g.slot)), "bh": flt(x.get("g_" + g.slot)) * scale,
			"exp_yield": flt(x.get("exp_yield_" + g.slot)), "exp_rosin": flt(x.get("exp_rosin_" + g.slot))}
		if actual:
			m.update({"act": flt(x.get("act_rosin_" + g.slot)), "act_yield": flt(x.get("act_yield_" + g.slot))})
		out.append(m)
	return out


def _day(d):
	return str(getdate(d)) if d else ""


def row_view(p, r, grps, alloc, c):
	if p.name not in c.can_write:
		c.can_write[p.name] = bool(p.has_permission("write"))
	can_write = c.can_write[p.name]
	status = r.row_status or "Scheduled"
	wo = c.wo.get(r.rosin_work_order) or {}
	jc = c.jc.get(r.job_card) or {}
	steps = c.steps.get(r.job_card, {})
	pressed = status in ("Pressed", "Whipped")
	block = ppp.unschedule_reason(status, r.rosin_work_order, c.se.get(r.rosin_work_order), c.logs.get(r.rosin_work_order))
	return {
		"name": r.name, "plan": p.name, "plan_status": p.status, "idx": r.idx,
		"planned_date": str(r.planned_date), "sequence": cint(r.sequence),
		"strain": r.strain or r.bubble_hash_item, "bubble_hash_item": r.bubble_hash_item or "",
		"bh_name": c.names.get(r.bubble_hash_item) or r.bubble_hash_item or "", "rosin_item": r.rosin_item or "",
		"project": r.project or "", "project_name": c.projects.get(r.project) or "",
		"rosin_work_order": r.rosin_work_order, "hash_work_order": r.hash_work_order or "",
		"material_request": r.material_request or "", "wash_plan": r.wash_plan or "",
		"wash_job_card": r.wash_job_card or "", "job_card": r.job_card or "", "metrc_tag": r.metrc_tag or "",
		"bh_actual_g": flt(r.bh_actual_g), "bh_planned_g": flt(r.bh_planned_g),
		"expected_rosin_g": flt(r.expected_rosin_g), "actual_rosin_g": flt(r.actual_rosin_g), "actual_yield": flt(r.actual_yield),
		"status": status, "micron_note": r.micron_note or "",
		"microns": _microns(r, grps),
		"washed_on": _day(r.hash_finished_on),
		"steps": {
			"press": "Complete" if pressed else steps.get(c.press_step) or "Pending",
			"whip": steps.get(c.whip_step) or ("Complete" if status == "Whipped" else "Pending"),
		},
		"jc_docstatus": jc.get("docstatus"), "wo_status": wo.get("status") or "",
		"transferred": c.moved.get(r.rosin_work_order, 0) > 0,
		"stock": _stock_view(alloc) if status == "Scheduled" else None,
		"editable": can_write and status == "Scheduled",
		"can_change_bh": can_write and status == "Scheduled" and not c.se.get(r.rosin_work_order),
		"unschedule_block": block,
		"can_whip": can_write and status == "Pressed" and jc.get("docstatus") == 1,
	}


def queue_view(q, grps, aging, c):
	return {
		"rosin_work_order": q.rosin_work_order, "strain": q.strain or q.bubble_hash_item,
		"bubble_hash_item": q.bubble_hash_item, "bh_name": q.bh_name,
		"project": q.project or "", "project_name": c.projects.get(q.project) or "",
		"bh_actual_g": flt(q.bh_actual_g), "bh_planned_g": flt(q.bh_planned_g),
		"microns": _microns(q, grps, actual=False), "expected_rosin_g": flt(q.expected_rosin_g),
		"days": q.days, "aging": bool(aging and q.days is not None and q.days >= aging),
		"washed_on": _day(q.hash_finished_on),
		"hash_work_order": q.hash_work_order, "material_request": q.material_request or "",
		"wash_job_card": q.wash_job_card or "", "micron_note": q.micron_note or "",
		"transferred": bool(q.transferred), "wo_status": q.wo_status,
		"stock": _stock_view(q),
	}


# ---------- writes: every change goes through the plan document and its validations ----------

def _mutate(scope, fn):
	scope = frappe.parse_json(scope) or {}
	frappe.db.savepoint("press_plan_board")
	try:
		result = fn(scope) or {}
	except (frappe.ValidationError, frappe.PermissionError) as e:
		frappe.db.rollback(save_point="press_plan_board")
		msg = strip_html(str(e) or "").strip()
		if not msg and frappe.local.message_log:
			last = frappe.local.message_log[-1]
			msg = strip_html((frappe.parse_json(last) if isinstance(last, str) else last).get("message", ""))
		frappe.local.message_log = []
		return {"ok": False, "error": msg or _("The change could not be saved."), "board": board(scope)}
	frappe.local.message_log = []
	return {"ok": True, **result, "board": board(result.get("scope") or scope), "plans": open_plans()}


def _get_row(row):
	parent = frappe.db.get_value(ROW, row, "parent")
	if not parent:
		frappe.throw(_("This wash is no longer in a plan. Refresh the board."))
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
	"""Where a scheduled wash goes: the given plan, the unsaved new plan, the open plan that covers the date, or
	else a new Weekly plan for that week."""
	if plan:
		return plan, None
	if new_plan:
		return None, new_plan
	hit = frappe.get_all(
		PLAN, filters={"status": ["in", ppp.OPEN], "from_date": ["<=", planned_date], "to_date": [">=", planned_date]},
		pluck="name", order_by="creation desc", limit=1)
	if hit:
		return hit[0], None
	return None, {"plan_type": "Weekly", "from_date": str(week_of(planned_date)[0])}


@frappe.whitelist()
def create_plan(plan_type, from_date, to_date=None, scope=None):
	def run(sc):
		doc = _new_plan(plan_type, from_date, to_date)
		doc.insert()
		return {"message": _("Plan {0} created.").format(doc.name), "plan": doc.name, "scope": {"mode": "plan", "plan": doc.name}}
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
def schedule(rosin_work_order, planned_date, plan=None, new_plan=None, scope=None):
	def run(sc):
		name, new = _target(planned_date, plan, frappe.parse_json(new_plan) if new_plan else None)
		if name:
			doc = frappe.get_doc(PLAN, name)
			doc.check_permission("write")
		else:
			doc = _new_plan(new.get("plan_type"), new.get("from_date"), new.get("to_date"))
		seq = max([cint(r.sequence) for r in doc.items if str(r.planned_date) == str(planned_date)] or [0]) + 1
		doc.append("items", {"planned_date": planned_date, "rosin_work_order": rosin_work_order, "sequence": seq})
		if doc.is_new():
			doc.insert()
		else:
			doc.save()
		r = next(x for x in doc.items if x.rosin_work_order == rosin_work_order)
		msg = _("{0} scheduled for {1} in {2}.").format(r.strain, fmt_date(r.planned_date), doc.name) + " "
		if frappe.db.get_value("Work Order Item", {"parent": rosin_work_order, "item_code": r.bubble_hash_item}, "transferred_qty"):
			msg += _("Its Bubble Hash ({0} g) is already transferred to Work Order {1}.").format(fmt_g(r.bh_planned_g), rosin_work_order)
		else:
			msg += _("Rosin Work Order {0} updated to {1} g Bubble Hash.").format(rosin_work_order, fmt_g(r.bh_planned_g))
		out = {"message": msg, "row": r.name, "plan": doc.name}
		if sc.get("mode") != "view" or new_plan:
			out["scope"] = {"mode": "plan", "plan": doc.name}
		return out
	return _mutate(scope, run)


@frappe.whitelist()
def unschedule(row, scope=None):
	def run(sc):
		doc, r = _get_row(row)
		name, wo = r.strain, r.rosin_work_order
		doc.remove(r)
		doc.save()
		return {"message": _("{0} moved back to Ready to Press. Work Order {1} has its original start date again.").format(name, wo)}
	return _mutate(scope, run)


@frappe.whitelist()
def update_row(row, field, value=None, scope=None):
	if field not in EDITABLE_FIELDS:
		frappe.throw(_("{0} cannot be changed here.").format(field))

	def run(sc):
		doc, r = _get_row(row)
		r.set(field, value if field == "planned_date" else flt(value))
		doc.save()
		return {"row": row}
	return _mutate(scope, run)


@frappe.whitelist()
def complete_whipping(row, scope=None):
	"""Mark the whipping sub-operation complete on the submitted press job card. A submitted card takes no new
	time logs, so this is the only place Whipping can be closed after Press Run; the card records it."""

	def run(sc):
		doc, r = _get_row(row)
		s = ppp.get_settings()
		if r.row_status != "Pressed":
			frappe.throw(_("Only a Pressed wash can be marked as whipped."))
		if not r.job_card or frappe.db.get_value("Job Card", r.job_card, "docstatus") != 1:
			frappe.throw(_("Record {0} on job card {1}; the card is not submitted yet.").format(s.whipping_sub_operation, r.job_card or ""))
		if not frappe.has_permission("Job Card", "write"):
			frappe.throw(_("You are not allowed to change job cards."), frappe.PermissionError)
		jc = frappe.get_doc("Job Card", r.job_card)
		sub = next((x for x in jc.sub_operations if x.sub_operation == s.whipping_sub_operation), None)
		if not sub:
			frappe.throw(_("Job card {0} has no {1} sub-operation.").format(jc.name, s.whipping_sub_operation))
		frappe.db.set_value("Job Card Operation", sub.name, "status", "Complete")
		jc.add_comment("Info", _("{0} marked complete from the Press Plan Board.").format(s.whipping_sub_operation))
		press_plan_sync.sync_work_order(r.rosin_work_order)
		return {"message": _("{0}: {1} complete on job card {2}.").format(r.strain, s.whipping_sub_operation, jc.name)}
	return _mutate(scope, run)
