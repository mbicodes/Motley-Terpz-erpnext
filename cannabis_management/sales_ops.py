# Sales Operation Board (/app/sales-operation-board): shared rules for Sales Pipeline Deal.
# Settings come from the single DocType "Sales Pipeline Settings"; nothing about stages, owners,
# product lines or alert switches is hard-coded here. Used by the deal controller, the page API,
# the permission hooks and the daily digest.

from datetime import timedelta

import frappe
from frappe import _
from frappe.utils import add_days, cint, date_diff, flt, formatdate, get_datetime, get_url, getdate, nowdate

DEAL = "Sales Pipeline Deal"
SETTINGS = "Sales Pipeline Settings"
BOARD_ROUTE = "sales-operation-board"

# Deal fields whose Select options are driven by Settings: fieldname -> settings list key.
SELECT_SOURCES = {
	"priority": "priority",
	"tier": "tier",
	"samples": "samples",
	"hardware": "hardware",
	"payment_terms": "payment_terms",
	"lead_source": "lead_source",
}


def _lines(text):
	out = []
	for line in (text or "").replace(",", "\n").splitlines():
		line = line.strip()
		if line and line not in out:
			out.append(line)
	return out


def _plain_lines(text):
	"""Like _lines but keeps commas (list options such as 'Net 7')."""
	out = []
	for line in (text or "").splitlines():
		line = line.strip()
		if line and line not in out:
			out.append(line)
	return out


def get_settings():
	"""Settings as a plain dict, memoised for the request."""
	if getattr(frappe.local, "sales_ops_settings", None) is not None:
		return frappe.local.sales_ops_settings
	doc = frappe.get_cached_doc(SETTINGS)
	stages = sorted(doc.get("stages") or [], key=lambda r: (cint(r.sort_order), r.idx))
	stage_list = [
		frappe._dict(
			name=(r.stage or "").strip(),
			sort_order=cint(r.sort_order),
			probability=flt(r.probability),
			max_days=cint(r.max_days),
			colour=r.colour or "",
			is_closed=cint(r.is_closed),
			is_won=cint(r.is_won),
			notify_managers=cint(r.notify_managers),
		)
		for r in stages
		if (r.stage or "").strip()
	]
	open_stages = [x for x in stage_list if not x.is_closed]
	product_lines = []
	for r in doc.get("product_lines") or []:
		if not (r.product_line or "").strip():
			continue
		product_lines.append(
			frappe._dict(
				product_line=r.product_line.strip(),
				tier=(r.tier or "").strip(),
				item_groups=_lines(r.item_groups),
				warehouses=_lines(r.warehouses),
				default_price=flt(r.default_price),
				quotation_item=r.quotation_item or "",
			)
		)
	line_names = []
	for r in product_lines:
		if r.product_line not in line_names:
			line_names.append(r.product_line)
	s = frappe._dict(
		stages=stage_list,
		first_stage=open_stages[0].name if open_stages else (stage_list[0].name if stage_list else None),
		owners=[
			frappe._dict(
				user=r.user,
				name=(r.display_name or "").strip() or r.user,
				colour=r.colour or "",
				active=cint(r.active),
				is_manager=cint(r.is_manager),
			)
			for r in (doc.get("owners") or [])
			if r.user
		],
		product_lines=product_lines,
		product_line_names=line_names,
		stock_company=doc.stock_company,
		lists=frappe._dict(
			priority=_plain_lines(doc.priority_options) or ["High", "Medium", "Low"],
			tier=_plain_lines(doc.tier_options),
			samples=_plain_lines(doc.samples_options),
			samples_done=_plain_lines(doc.samples_done_options),
			hardware=_plain_lines(doc.hardware_options),
			payment_terms=_plain_lines(doc.payment_terms_options),
			lead_source=_plain_lines(doc.lead_source_options),
		),
		alerts=frappe._dict(
			followup_overdue=cint(doc.alert_followup_overdue),
			followup_today=cint(doc.alert_followup_today),
			stalled=cint(doc.alert_stalled),
			missing_owner=cint(doc.alert_missing_owner),
			missing_value=cint(doc.alert_missing_value),
			short_stock=cint(doc.alert_short_stock),
			sample_due=cint(doc.alert_sample_due),
		),
		sample_due_days=cint(doc.sample_due_days),
		hide_closed_after_days=cint(doc.hide_closed_after_days),
		send_daily_digest=cint(doc.send_daily_digest),
		notify_on_reassign=cint(doc.notify_on_reassign),
		notify_managers_on_stage=cint(doc.notify_managers_on_stage),
		unassigned_alert_days=cint(doc.unassigned_alert_days),
	)
	frappe.local.sales_ops_settings = s
	return s


def clear_settings_memo():
	frappe.local.sales_ops_settings = None


def stage_info(s, stage):
	return next((x for x in s.stages if x.name == stage), None)


def won_stage(s):
	return next((x for x in s.stages if x.is_closed and x.is_won), None)


def lost_stage(s):
	return next((x for x in s.stages if x.is_closed and not x.is_won), None)


def needs_followup(s, st):
	return bool(st) and not st.is_closed and st.name != s.first_stage


def default_priority(s):
	p = s.lists.priority
	return p[len(p) // 2] if p else None


def owner_label(s, user):
	o = next((x for x in s.owners if x.user == user), None)
	if o:
		return o.name
	return frappe.db.get_value("User", user, "full_name") or user if user else _("Unassigned")


def manager_users(s=None):
	s = s or get_settings()
	return [o.user for o in s.owners if o.active and o.is_manager]


# ---------- permissions ----------


def is_manager(user=None):
	user = user or frappe.session.user
	if user == "Administrator" or "System Manager" in frappe.get_roles(user):
		return True
	try:
		s = get_settings()
	except Exception:
		return False
	return any(o.user == user and o.is_manager for o in s.owners)


def deal_query_conditions(user=None):
	user = user or frappe.session.user
	if is_manager(user):
		return ""
	return "ifnull(`tab{dt}`.`deal_owner`, '') in ('', {u})".format(dt=DEAL, u=frappe.db.escape(user))


def deal_has_permission(doc, ptype=None, user=None, debug=False):
	user = user or frappe.session.user
	if is_manager(user):
		return None
	owner = doc.get("deal_owner") or ""
	saved_owner = owner
	if doc.get("name") and not doc.get("__islocal"):
		saved_owner = frappe.db.get_value(DEAL, doc.get("name"), "deal_owner") or ""
	if ptype == "create":
		return None
	if ptype == "delete":
		return None if saved_owner == user else False
	if ptype in ("write", "submit", "cancel", "amend"):
		# own deals, or an unassigned deal (taking it is checked in validate)
		return None if saved_owner in ("", user) else False
	return None if saved_owner in ("", user) or owner == user else False


def settings_has_permission(doc, ptype=None, user=None, debug=False):
	if ptype in ("read", "print", "email", "report", "export"):
		return None
	return None if is_manager(user) else False


@frappe.whitelist()
@frappe.validate_and_sanitize_search_inputs
def active_owner_query(doctype, txt, searchfield, start, page_len, filters):
	s = get_settings()
	txt = (txt or "").lower()
	rows = [
		(o.user, o.name)
		for o in s.owners
		if o.active and (not txt or txt in o.user.lower() or txt in o.name.lower())
	]
	start, page_len = cint(start), cint(page_len) or 20
	return rows[start : start + page_len]


# ---------- stock and attention flags ----------


def stock_map(s):
	"""{"Cold Cure|T1": {"grams": ..., "label": ...}} — one query for every product line row."""
	groups = sorted({g for r in s.product_lines for g in r.item_groups})
	if not groups:
		return {}
	rows = frappe.db.sql(
		"""
		SELECT i.item_group, b.warehouse, w.company,
			SUM(b.actual_qty) AS actual, SUM(b.reserved_qty) AS on_orders
		FROM `tabBin` b
		JOIN `tabItem` i ON i.name = b.item_code
		JOIN `tabWarehouse` w ON w.name = b.warehouse
		WHERE i.item_group IN %(groups)s AND i.stock_uom = 'Gram'
		  AND IFNULL(w.is_rejected_warehouse, 0) = 0
		GROUP BY i.item_group, b.warehouse, w.company
		""",
		{"groups": tuple(groups)},
		as_dict=True,
	)
	out = {}
	for r in s.product_lines:
		if not r.item_groups:
			continue
		actual = on_orders = 0.0
		for x in rows:
			if x.item_group not in r.item_groups:
				continue
			if r.warehouses:
				if x.warehouse not in r.warehouses:
					continue
			elif s.stock_company and x.company != s.stock_company:
				continue
			actual += flt(x.actual)
			on_orders += flt(x.on_orders)
		out[r.product_line + "|" + r.tier] = frappe._dict(
			grams=max(0.0, actual - on_orders),
			on_hand=actual,
			on_orders=on_orders,
			groups=r.item_groups,
			warehouses=r.warehouses or ([s.stock_company] if s.stock_company else []),
		)
	return out


def product_row(s, product_line, tier):
	if not product_line:
		return None
	exact = next((r for r in s.product_lines if r.product_line == product_line and r.tier == (tier or "")), None)
	return exact or next((r for r in s.product_lines if r.product_line == product_line and not r.tier), None)


def stock_for(stock, product_line, tier):
	if not product_line:
		return None
	return stock.get(product_line + "|" + (tier or "")) or stock.get(product_line + "|")


def enrich(d, s, today, stock):
	"""Adds probability, weighted value, stage age, stock and attention flags to a deal row (in place)."""
	st = stage_info(s, d.stage) or frappe._dict(probability=0, max_days=0, is_closed=0, is_won=0)
	d.probability = st.probability
	d.deal_value = flt(d.deal_value)
	d.weighted_value = d.deal_value * flt(st.probability) / 100.0
	d.is_closed = st.is_closed
	d.is_won = st.is_closed and st.is_won
	since = getdate(d.stage_changed_on or d.creation)
	d.days_in_stage = max(0, date_diff(today, since))
	d.hidden_closed = bool(st.is_closed and s.hide_closed_after_days and d.days_in_stage > s.hide_closed_after_days)
	d.won_this_month = bool(d.is_won and since.year == today.year and since.month == today.month)
	stk = stock_for(stock, d.product_line, d.tier)
	d.stock = stk
	d.short = max(0.0, flt(d.total_grams) - stk.grams) if (stk and flt(d.total_grams)) else 0.0
	for f in ("next_step_due", "sample_date", "expected_close", "delivery_pickup"):
		d[f] = str(d[f]) if d.get(f) else None
	d.flags = deal_flags(d, s, st, today)
	d.attention = any(f["kind"] == "action" for f in d.flags)
	return d


def deal_flags(d, s, st, today):
	flags = []
	if st.is_closed:
		return flags
	a = s.alerts

	def add(key, label, kind):
		flags.append({"key": key, "label": label, "kind": kind})

	follow = getdate(d.next_step_due) if d.get("next_step_due") else None
	if follow and follow < today and a.followup_overdue:
		add("overdue", _("Overdue follow-up · {0}").format(formatdate(follow)), "action")
	elif follow and follow == today and a.followup_today:
		add("followup_today", _("Follow-up today"), "info")
	if a.stalled and st.max_days and cint(d.get("days_in_stage")) > st.max_days:
		add("stalled", _("Stalled · {0} days").format(cint(d.days_in_stage)), "action")
	if a.missing_owner and not d.get("deal_owner"):
		add("no_owner", _("No owner"), "action")
	if a.missing_value and not flt(d.get("deal_value")) and d.stage != s.first_stage:
		add("no_value", _("No value"), "action")
	if a.short_stock and flt(d.get("short")) > 0:
		add("short", _("Short {0} g").format(frappe.utils.fmt_money(d.short, precision=0)), "action")
	sample = getdate(d.sample_date) if d.get("sample_date") else None
	if (
		a.sample_due
		and sample
		and date_diff(sample, today) <= cint(s.sample_due_days)
		and (d.get("samples") or "") not in s.lists.samples_done
	):
		add("sample_due", _("Sample due · {0}").format(formatdate(sample)), "action")
	return flags


# ---------- notifications ----------


def deal_link(name):
	return get_url("/app/{0}?deal={1}".format(BOARD_ROUTE, name))


def notify(users, subject, deal=None, html=None):
	"""In-app alert (bell). Sent after commit, never to the person who made the change."""
	from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

	users = [u for u in dict.fromkeys(users or []) if u and u != frappe.session.user]
	if not users:
		return
	enqueue_create_notification(
		users,
		{
			"type": "Alert",
			"subject": subject,
			"document_type": DEAL if deal else None,
			"document_name": deal,
			"from_user": frappe.session.user,
			"email_content": html or subject,
		},
	)


def send_daily_digest():
	"""Scheduler, daily 8:00 AM site time: each owner gets their follow-ups, stalled deals and samples due;
	pipeline managers also get deals that have been unassigned too long."""
	if not frappe.db.exists("DocType", SETTINGS):
		return
	clear_settings_memo()
	s = get_settings()
	if not s.stages:
		return
	today = getdate(nowdate())
	rows = frappe.get_all(
		DEAL,
		fields=[
			"name", "account", "stage", "deal_owner", "next_step_due", "sample_date", "samples",
			"stage_changed_on", "creation", "deal_value", "product_line", "tier", "total_grams",
			"expected_close", "delivery_pickup",
		],
	)
	by_owner = {}
	for d in rows:
		enrich(d, s, today, {})
		if d.is_closed or not d.deal_owner:
			continue
		keys = {f["key"] for f in d.flags}
		bucket = by_owner.setdefault(d.deal_owner, {"overdue": [], "followup_today": [], "stalled": [], "sample_due": []})
		for k in bucket:
			if k in keys:
				bucket[k].append(d)

	sections = [
		("overdue", _("Overdue follow-ups"), "next_step_due"),
		("followup_today", _("Follow-ups today"), "next_step_due"),
		("stalled", _("Stalled deals"), None),
		("sample_due", _("Samples due"), "sample_date"),
	]
	if s.send_daily_digest:
		for user, bucket in by_owner.items():
			total = sum(len(v) for v in bucket.values())
			if not total:
				continue
			html = [
				"<p>{0}</p>".format(_("Your Sales Operation Board for {0}:").format(formatdate(today))),
			]
			for key, title, date_field in sections:
				if not bucket[key]:
					continue
				html.append("<h4 style='margin:14px 0 6px'>{0} ({1})</h4><ul>".format(title, len(bucket[key])))
				for d in bucket[key]:
					extra = formatdate(d[date_field]) if date_field and d.get(date_field) else _("{0} days in {1}").format(d.days_in_stage, d.stage)
					html.append(
						"<li><a href='{0}'>{1}</a> · {2} · {3}</li>".format(
							deal_link(d.name), frappe.utils.escape_html(d.account), frappe.utils.escape_html(d.stage), extra
						)
					)
				html.append("</ul>")
			html.append("<p><a href='{0}'>{1}</a></p>".format(get_url("/app/" + BOARD_ROUTE), _("Open the Sales Operation Board")))
			subject = _("Sales pipeline: {0} item(s) need your attention today").format(total)
			body = "".join(html)
			notify([user], subject, html=body)
			try:
				frappe.sendmail(recipients=[user], subject=subject, message=body, delayed=True)
			except Exception:
				frappe.log_error(title="Sales Operation Board digest email failed")

	days = cint(s.unassigned_alert_days)
	if days > 0:
		cutoff = get_datetime(add_days(today, -days))
		stale = [d for d in rows if not d.deal_owner and not d.is_closed and get_datetime(d.creation) < cutoff]
		if stale:
			items = "".join(
				"<li><a href='{0}'>{1}</a> · {2}</li>".format(deal_link(d.name), frappe.utils.escape_html(d.account), frappe.utils.escape_html(d.stage))
				for d in stale
			)
			notify(
				manager_users(s),
				_("{0} deal(s) have been unassigned for more than {1} days").format(len(stale), days),
				html="<ul>{0}</ul>".format(items),
			)
	frappe.db.commit()


# ---------- settings side effects ----------


def sync_deal_options(s):
	"""Push Settings lists into the deal's Select options (stage, product line and the fixed lists)."""
	meta = frappe.get_meta(DEAL)
	wanted = {
		"stage": "\n".join(x.name for x in s.stages),
		"product_line": "\n" + "\n".join(s.product_line_names),
	}
	for field, key in SELECT_SOURCES.items():
		values = s.lists.get(key) or []
		wanted[field] = ("" if field == "priority" else "\n") + "\n".join(values)
	changed = False
	for field, options in wanted.items():
		df = meta.get_field(field)
		if not df or df.fieldtype != "Select" or (df.options or "") == options:
			continue
		frappe.make_property_setter(
			{"doctype": DEAL, "fieldname": field, "property": "options", "value": options, "property_type": "Text"},
			validate_fields_for_doctype=False,
		)
		changed = True
	defaults = {"stage": s.first_stage, "priority": default_priority(s)}
	for field, value in defaults.items():
		df = meta.get_field(field)
		if df and value and df.default != value:
			frappe.make_property_setter(
				{"doctype": DEAL, "fieldname": field, "property": "default", "value": value, "property_type": "Text"},
				validate_fields_for_doctype=False,
			)
			changed = True
	if changed:
		frappe.clear_cache(doctype=DEAL)


def recompute_probabilities(s):
	"""Stage probability lives in Settings; keep stored probability / weighted value in step on every deal."""
	for st in s.stages:
		frappe.db.sql(
			"""UPDATE `tab{dt}` SET probability = %(p)s, weighted_value = deal_value * %(p)s / 100
			WHERE stage = %(stage)s AND (probability != %(p)s OR weighted_value != deal_value * %(p)s / 100)""".format(dt=DEAL),
			{"p": st.probability, "stage": st.name},
		)


def publish_board_update(name=None):
	frappe.publish_realtime("sales_pipeline_update", {"name": name}, after_commit=True)
