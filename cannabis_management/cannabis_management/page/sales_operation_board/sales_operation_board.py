# Sales Operation Board (/app/sales-operation-board): API for the page (Board, By Owner, Calendar, List).
# All rules (probability, weighted value, stage log, attention flags, stock) live in Python; the page only renders.

import json

import frappe
from frappe import _
from frappe.utils import cint, flt, getdate, nowdate

from cannabis_management import sales_ops

DT = sales_ops.DEAL
ACC = sales_ops.ACCOUNT

FIELDS = [
	"name", "account", "pipeline_account", "stage", "deal_owner", "priority", "contact_name", "phone", "email",
	"location_address", "license_number", "customer", "lead", "next_step_due", "sample_date",
	"expected_close", "delivery_pickup", "stage_changed_on", "product_line", "tier", "form",
	"total_grams", "price_per_gram", "value_override", "deal_value", "probability", "weighted_value",
	"timeline", "status_detail", "samples", "copack", "hardware", "size_per_strain", "strain_profiles",
	"buyer_notes", "deal_notes", "next_steps", "fulfillment_notes", "ops_notes", "payment_terms",
	"lead_source", "lost_reason", "creation", "modified", "modified_by",
]

# Fields the page may change directly (drag and drop, inline edit, panel selectors, requirement prompts).
BUYER_FIELDS = {"contact_name", "phone", "email", "location_address", "license_number", "customer", "lead", "pipeline_account"}
PRODUCT_FIELDS = {"product_line", "tier", "total_grams", "price_per_gram", "requirements", "value_override"}
NOTE_FIELDS = {"buyer_notes", "deal_notes", "next_steps", "fulfillment_notes", "ops_notes"}
# Owners may change these only on their own deals (pipeline managers on any deal).
OWN_ONLY = BUYER_FIELDS | PRODUCT_FIELDS | NOTE_FIELDS
EDITABLE = {
	"stage", "deal_owner", "co_owners", "priority", "next_step_due", "sample_date", "expected_close",
	"delivery_pickup", "lost_reason", "samples",
} | OWN_ONLY
# New Deal dialog
CREATE_FIELDS = {
	"account", "pipeline_account", "customer", "stage", "deal_owner", "co_owners", "priority", "next_step_due",
	"product_line", "tier", "total_grams", "price_per_gram", "value_override", "requirements",
}
REQ_FIELDS = ("product_line", "tier", "total_grams", "price_per_gram", "details")

# Accounts (Leads board)
ACC_FIELDS = [
	"name", "account_name", "lead_status", "account_owner", "next_step_due", "lead_source", "status_changed_on",
	"customer", "lead", "contact_name", "phone", "email", "location_address", "license_number",
	"weekly_volume", "monthly_demand", "monthly_potential", "relationship_notes", "creation", "modified", "modified_by",
]
ACC_EDITABLE = {
	"account_name", "lead_status", "account_owner", "next_step_due", "lead_source", "customer", "lead", "contact_name",
	"phone", "email", "location_address", "license_number", "relationship_notes", "volume",
}
ACC_CREATE = ACC_EDITABLE - {"lead"}
VOL_FIELDS = ("product_line", "tier", "activity", "weekly_volume", "wants_qty", "wants_per", "uom", "price", "notes")
VOL_NUM = ("weekly_volume", "wants_qty", "price")
VOL_LABELS = {
	"product_line": "Product line", "tier": "Tier", "activity": "They", "weekly_volume": "Volume / week", "wants_qty": "Wants",
	"wants_per": "Per", "uom": "Unit", "price": "Price", "notes": "Notes",
}
DATE_FIELDS = {"next_step_due", "sample_date", "expected_close", "delivery_pickup"}
FLOAT_FIELDS = {"total_grams", "price_per_gram", "value_override"}

# Activity tab: which Version changes become a line, and their labels.
DATE_LABELS = {
	"next_step_due": "Next follow-up", "sample_date": "Sample date",
	"expected_close": "Expected close", "delivery_pickup": "Delivery / pickup",
}
VALUE_LABELS = {"total_grams": "Total grams", "price_per_gram": "Price per gram", "value_override": "Manual deal value"}
REQ_LABELS = {"product_line": "Product line", "tier": "Tier", "total_grams": "Grams", "price_per_gram": "Price per gram", "details": "Details"}

# Export column order = Pipeline sheet of Matt's workbook.
EXPORT_COLUMNS = [
	("Account", "account"), ("Stage", "stage"), ("Owner", "owner_name"), ("Product Line", "product_line"),
	("Tier", "tier"), ("Form", "form"), ("Total Grams", "total_grams"), ("Price per Gram", "price_per_gram"),
	("Value Override", "value_override"), ("Deal Value", "deal_value"), ("Timeline", "timeline"),
	("Status Detail", "status_detail"), ("Samples", "samples"), ("Copack", "copack"), ("Hardware", "hardware"),
	("Size per Strain", "size_per_strain"), ("Strain Profiles", "strain_profiles"),
	("Buyer Notes / Requests", "buyer_notes"), ("Deal Notes", "deal_notes"), ("Next Steps to Close", "next_steps"),
	("Last Updated", "modified"), ("Lost Reason", "lost_reason"), ("Priority", "priority"),
	("Contact Name", "contact_name"), ("Phone", "phone"), ("Email", "email"),
	("Location / Address", "location_address"), ("License #", "license_number"), ("Customer", "customer"),
	("Win Probability %", "probability"), ("Weighted Value", "weighted_value"), ("Next Follow-up", "next_step_due"),
	("Sample Date", "sample_date"), ("Expected Close", "expected_close"), ("Delivery / Pickup", "delivery_pickup"),
	("Fulfillment Notes", "fulfillment_notes"), ("Ops Notes", "ops_notes"), ("Payment Terms", "payment_terms"),
	("Lead Source", "lead_source"), ("ID", "name"),
]


def _line_tiers(s):
	"""{"VRR": ["T1", "T2", ...]} — the tiers mapped to each product line in Settings."""
	out = {name: [] for name in s.product_line_names}
	for r in s.product_lines:
		if r.tier and r.tier not in out[r.product_line]:
			out[r.product_line].append(r.tier)
	return out


def _settings_payload(s):
	return {
		"stages": s.stages,
		"first_stage": s.first_stage,
		"lead_statuses": s.lead_statuses,
		"first_status": s.first_status,
		"owners": [o for o in s.owners if o.active],
		"all_owners": s.owners,
		"product_lines": s.product_line_names,
		"line_tiers": _line_tiers(s),
		"line_units": s.line_units,
		"line_groups": s.line_groups,
		"lists": s.lists,
		"hide_closed_after_days": s.hide_closed_after_days,
	}


def _buyer_titles(deals):
	"""Readable names for linked Customers and Leads (the Lead ID alone means nothing to the team)."""
	leads = list({d.lead for d in deals if d.get("lead")})
	customers = list({d.customer for d in deals if d.get("customer")})
	lead_t = {}
	if leads:
		for r in frappe.get_all("Lead", filters={"name": ("in", leads)}, fields=["name", "company_name", "lead_name"]):
			lead_t[r.name] = r.company_name or r.lead_name or r.name
	cust_t = {}
	if customers:
		for r in frappe.get_all("Customer", filters={"name": ("in", customers)}, fields=["name", "customer_name"]):
			cust_t[r.name] = r.customer_name or r.name
	emails = {}
	for c in customers:
		emails[c] = sales_ops.customer_email(c)
	for d in deals:
		d.lead_title = lead_t.get(d.get("lead"), d.get("lead")) if d.get("lead") else None
		d.customer_title = cust_t.get(d.get("customer"), d.get("customer")) if d.get("customer") else None
		# the Email button writes to the deal's email, else the Customer's
		d.customer_email = emails.get(d.get("customer")) if d.get("customer") else None


def _requirements(deals):
	names = [d.name for d in deals]
	by = {}
	if names:
		for r in frappe.get_all(
			sales_ops.REQUIREMENT, filters={"parenttype": DT, "parent": ("in", names)},
			fields=["name", "parent", "product_line", "tier", "total_grams", "price_per_gram", "amount", "details"],
			order_by="idx asc",
		):
			by.setdefault(r.parent, []).append(r)
	for d in deals:
		d.requirements = by.get(d.name, [])


def _set_requirements(doc, rows):
	"""Requirement lines from the page. Rows keep their name so Activity shows what really changed."""
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	existing = {r.name: r for r in doc.get("requirements") or []}
	keep = []
	for i, row in enumerate(rows or [], start=1):
		row = row or {}
		vals = {}
		for f in REQ_FIELDS:
			v = row.get(f)
			if f in ("total_grams", "price_per_gram"):
				v = flt(v)
				if v < 0:
					frappe.throw(_("Requirement {0}: grams and price cannot be negative.").format(i))
			else:
				v = (v or "").strip() if isinstance(v, str) else (v or "")
			vals[f] = v
		if not (vals["product_line"] or vals["total_grams"] or vals["price_per_gram"]):
			continue
		r = existing.get(row.get("name")) if row.get("name") else None
		if r:
			r.update(vals)
		else:
			r = doc.append("requirements", vals)
		keep.append(r)
	doc.set("requirements", keep)
	for i, r in enumerate(keep, start=1):
		r.idx = i
	if not keep:
		# every line removed: the deal has no product
		doc.product_line = doc.tier = None
		doc.total_grams = doc.price_per_gram = 0


def _co_owners(deals):
	names = [d.name for d in deals]
	by = {}
	if names:
		for r in frappe.get_all(
			sales_ops.CO_OWNER, filters={"parenttype": DT, "parent": ("in", names)},
			fields=["parent", "user"], order_by="idx asc",
		):
			by.setdefault(r.parent, []).append(r.user)
	for d in deals:
		d.co_owners = by.get(d.name, [])


def _check_own(doc, values):
	"""Buyer, product and note fields: owners edit only their own deals; pipeline managers edit any deal."""
	if not (set(values) & OWN_ONLY):
		return
	user = frappe.session.user
	if sales_ops.is_manager(user):
		return
	saved_owner = frappe.db.get_value(DT, doc.name, "deal_owner") or ""
	if saved_owner == user or values.get("deal_owner") == user or sales_ops.is_co_owner(doc.name, user):
		return
	frappe.throw(_("You can edit the buyer, product and notes only on deals you own or co-own."), frappe.PermissionError)


def _set_co_owners(doc, users):
	"""Keep existing rows (so Activity shows only real additions and removals), add the new people."""
	if isinstance(users, str):
		users = json.loads(users) if users.strip().startswith("[") else [u.strip() for u in users.split(",")]
	wanted = []
	for u in users or []:
		u = (u.get("user") if isinstance(u, dict) else u) or ""
		u = u.strip()
		if u and u not in wanted:
			wanted.append(u)
	doc.set("co_owners", [r for r in (doc.get("co_owners") or []) if r.user in wanted])
	have = {r.user for r in doc.co_owners}
	for u in wanted:
		if u not in have:
			doc.append("co_owners", {"user": u})


def _check_product(values, doc):
	if not ({"product_line", "tier"} & set(values)):
		return
	s = sales_ops.get_settings()
	line = values.get("product_line", doc.product_line) or None
	tier = values.get("tier", doc.tier) or None
	if "product_line" in values and line and line not in s.product_line_names:
		frappe.throw(_("{0} is not a Product Line in Sales Pipeline Settings.").format(line))
	if tier and (not line or tier not in _line_tiers(s).get(line, [])):
		frappe.throw(_("Tier {0} is not mapped to {1} in Sales Pipeline Settings.").format(tier, line or _("an empty Product Line")))


@frappe.whitelist()
def get_form_settings():
	frappe.has_permission(DT, "read", throw=True)
	s = sales_ops.get_settings()
	return {"stages": s.stages, "first_stage": s.first_stage}


@frappe.whitelist()
def get_board():
	frappe.has_permission(DT, "read", throw=True)
	s = sales_ops.get_settings()
	if not s.stages:
		frappe.throw(_("Set up stages in Sales Pipeline Settings first."))
	today = getdate(nowdate())
	stock = sales_ops.stock_map(s)
	deals = frappe.get_list(DT, fields=FIELDS, order_by="creation asc", limit_page_length=0)
	_requirements(deals)
	for d in deals:
		sales_ops.enrich(d, s, today, stock)
	_buyer_titles(deals)
	_co_owners(deals)
	accounts = _accounts(s, today, deals)
	user = frappe.session.user
	return {
		"today": str(today),
		"user": user,
		"is_manager": sales_ops.is_manager(user),
		"is_owner": any(o.user == user and o.active for o in s.owners),
		"settings": _settings_payload(s),
		"deals": deals,
		"accounts": accounts,
		"can_write": bool(frappe.has_permission(DT, "write")),
		"can_write_account": bool(frappe.has_permission(ACC, "write")),
		"can_create_account": bool(frappe.has_permission(ACC, "create")),
		"can_create": bool(frappe.has_permission(DT, "create")),
		"can_quote": bool(frappe.has_permission("Quotation", "create")),
		"can_create_customer": bool(frappe.has_permission("Customer", "create")),
		"can_create_lead": bool(frappe.has_permission("Lead", "create")),
		"can_settings": sales_ops.is_manager(user) and bool(frappe.has_permission(sales_ops.SETTINGS, "write")),
	}


def _clean(values):
	out = {}
	for key, value in values.items():
		if isinstance(value, str):
			value = value.strip()
		if value in ("", None):
			value = None
		elif key in DATE_FIELDS:
			value = str(getdate(value))
		elif key in FLOAT_FIELDS:
			value = flt(value)
			if value < 0:
				frappe.throw(_("{0} cannot be negative.").format(VALUE_LABELS.get(key, key)))
		out[key] = value
	return out


@frappe.whitelist()
def update_deal(name, values):
	"""Apply a small change from the page; the deal's validate() enforces every rule."""
	if isinstance(values, str):
		values = json.loads(values)
	bad = set(values) - EDITABLE
	if bad:
		frappe.throw(_("These fields cannot be changed from the board: {0}").format(", ".join(sorted(bad))))
	doc = frappe.get_doc(DT, name)
	doc.check_permission("write")
	co = values.pop("co_owners", None) if "co_owners" in values else False
	reqs = values.pop("requirements", None) if "requirements" in values else False
	values = _clean(values)
	_check_own(doc, dict(values, **({"requirements": 1} if reqs is not False else {})))
	_check_product(values, doc)
	if values.get("pipeline_account"):
		frappe.has_permission(ACC, "read", doc=values["pipeline_account"], throw=True)
	for key, value in values.items():
		doc.set(key, value)
	if co is not False:
		_set_co_owners(doc, co)
	if reqs is not False:
		_set_requirements(doc, reqs)
	doc.save()
	# names of the saved requirement lines, in order, so the page can keep editing them
	return {"name": doc.name, "requirements": [r.name for r in doc.get("requirements") or []]}


@frappe.whitelist()
def create_deal(values):
	"""New Deal dialog. A Buyer (Customer) is optional; the deal fills Account and contact details from it."""
	if isinstance(values, str):
		values = json.loads(values)
	frappe.has_permission(DT, "create", throw=True)
	bad = set(values) - CREATE_FIELDS
	if bad:
		frappe.throw(_("These fields cannot be set from the New Deal dialog: {0}").format(", ".join(sorted(bad))))
	co = values.pop("co_owners", None)
	reqs = values.pop("requirements", None)
	values = _clean(values)
	if not values.get("account") and not values.get("customer") and not values.get("pipeline_account"):
		frappe.throw(_("Please choose the account, or enter a new account name."))
	if values.get("pipeline_account"):
		frappe.has_permission(ACC, "read", doc=values["pipeline_account"], throw=True)
	if values.get("customer"):
		frappe.has_permission("Customer", "read", doc=values["customer"], throw=True)
	doc = frappe.new_doc(DT)
	_check_product(values, doc)
	if reqs is None and values.get("product_line"):
		# the dialog's product fields become the first requirement line
		reqs = [{f: values.get(f) for f in REQ_FIELDS}]
	for key, value in values.items():
		if value is not None and key not in ("product_line", "tier", "total_grams", "price_per_gram"):
			doc.set(key, value)
	if not reqs:
		for key in ("product_line", "tier", "total_grams", "price_per_gram"):
			if values.get(key) is not None:
				doc.set(key, values[key])
	if co:
		_set_co_owners(doc, co)
	if reqs:
		_set_requirements(doc, reqs)
	doc.insert()
	return doc.name

# ---------- buyer ----------


@frappe.whitelist()
def search_buyers(txt=None):
	"""Customers and Leads for the Buyer tab search, with the user's own permissions applied."""
	frappe.has_permission(DT, "read", throw=True)
	txt = (txt or "").strip()
	like = "%{0}%".format(txt)
	out = []
	if frappe.has_permission("Customer", "read"):
		rows = frappe.get_list(
			"Customer",
			filters={"disabled": 0},
			or_filters={"name": ("like", like), "customer_name": ("like", like)} if txt else None,
			fields=["name", "customer_name"],
			order_by="modified desc",
			limit_page_length=8,
		)
		out += [{"type": "Customer", "name": r.name, "title": r.customer_name or r.name} for r in rows]
	if frappe.has_permission("Lead", "read"):
		rows = frappe.get_list(
			"Lead",
			or_filters={"name": ("like", like), "company_name": ("like", like), "lead_name": ("like", like)} if txt else None,
			fields=["name", "company_name", "lead_name", "status"],
			order_by="modified desc",
			limit_page_length=8,
		)
		out += [
			{"type": "Lead", "name": r.name, "title": r.company_name or r.lead_name or r.name, "status": r.status}
			for r in rows
		]
	return out


def _dt(doctype):
	"""The page works on deals and on accounts; nothing else."""
	if doctype in (None, "", DT):
		return DT
	if doctype == ACC:
		return ACC
	frappe.throw(_("The Sales Operation Board only works on deals and accounts."))


@frappe.whitelist()
def create_buyer(name, buyer_type, buyer_name, contact_name=None, phone=None, email=None, extra=None, doctype=None):
	"""Create a Customer or Lead from the deal (or account) drawer and link it in one transaction."""
	dt = _dt(doctype)
	if isinstance(extra, str):
		extra = json.loads(extra or "{}")
	extra = {k: v for k, v in (extra or {}).items() if k in {"deal_owner", "next_step_due", "lost_reason"}} if dt == DT else {}
	doc = frappe.get_doc(dt, name)
	doc.check_permission("write")
	extra = _clean(extra)
	if dt == DT:
		_check_own(doc, dict(extra, customer=1))
	buyer_name = (buyer_name or "").strip()
	contact_name, phone, email = ((x or "").strip() for x in (contact_name, phone, email))
	if not buyer_name:
		frappe.throw(_("Please enter the Buyer Name."))
	if email:
		frappe.utils.validate_email_address(email, throw=True)
	if buyer_type == "Customer":
		frappe.has_permission("Customer", "create", throw=True)
		party = frappe.new_doc("Customer")
		party.customer_name = buyer_name
		party.customer_type = "Company"
		party.email_id = email or None
		party.mobile_no = phone or None
		if contact_name:
			first, _sep, last = contact_name.partition(" ")
			party.first_name, party.last_name = first, last or None
		# create permission checked above; this also lets ERPNext add the primary Contact for the user
		party.flags.ignore_permissions = True
		party.insert()
		doc.customer = party.name
		title = party.customer_name
	elif buyer_type == "Lead":
		frappe.has_permission("Lead", "create", throw=True)
		party = frappe.new_doc("Lead")
		party.company_name = buyer_name
		if contact_name:
			party.first_name = contact_name
		party.email_id = email or None
		party.mobile_no = phone or None
		party.lead_owner = extra.get("deal_owner") or doc.get("deal_owner") or doc.get("account_owner") or frappe.session.user
		party.insert()
		doc.lead = party.name
		doc.customer = None
		title = party.company_name
	else:
		frappe.throw(_("Choose Customer or Lead as the buyer type."))
	for key, value in (("contact_name", contact_name), ("phone", phone), ("email", email)):
		if value:
			doc.set(key, value)
	for key, value in extra.items():
		doc.set(key, value)
	doc.save()
	return {"name": doc.name, "type": buyer_type, "buyer": party.name, "title": title}


# ---------- notes (Comments on the deal) ----------


def _note_text(html):
	"""Comment HTML -> plain text for the edit box."""
	import html as html_lib
	import re

	text = re.sub(r"(?i)<br\s*/?>", "\n", html or "")
	text = re.sub(r"(?i)</(p|div|li)>", "\n", text)
	text = frappe.utils.strip_html_tags(text)
	return re.sub(r"\n{3,}", "\n\n", html_lib.unescape(text)).strip()


def _note_html(text):
	return frappe.utils.escape_html(text).replace("\n", "<br>")


def _notes(name, dt=DT):
	user = frappe.session.user
	manager = sales_ops.is_manager(user)
	rows = frappe.get_all(
		"Comment",
		filters={"reference_doctype": dt, "reference_name": name, "comment_type": "Comment"},
		fields=["name", "content", "owner", "creation", "modified"],
		order_by="creation desc",
		limit_page_length=500,
	)
	return [
		{
			"name": c.name,
			"content": c.content,
			"text": _note_text(c.content),
			"by": frappe.utils.get_fullname(c.owner),
			"on": str(c.creation),
			"edited": str(c.modified) if (c.modified and c.creation and (c.modified - c.creation).total_seconds() > 2) else None,
			"can_edit": c.owner == user,
			"can_delete": c.owner == user or manager,
		}
		for c in rows
	]


def _own_comment(comment, action):
	c = frappe.get_doc("Comment", comment)
	if c.reference_doctype not in (DT, ACC) or c.comment_type != "Comment":
		frappe.throw(_("This is not a note on a Sales Pipeline deal or account."))
	frappe.get_doc(c.reference_doctype, c.reference_name).check_permission("read")
	user = frappe.session.user
	allowed = c.owner == user or (action == "delete" and sales_ops.is_manager(user))
	if not allowed:
		frappe.throw(
			_("Only the author can edit this note.") if action == "edit"
			else _("Only the author or a pipeline manager can delete this note."),
			frappe.PermissionError,
		)
	return c


@frappe.whitelist()
def add_note(name, note, doctype=None):
	dt = _dt(doctype)
	doc = frappe.get_doc(dt, name)
	doc.check_permission("read")
	note = (note or "").strip()
	if not note:
		frappe.throw(_("Please type a note first."))
	doc.add_comment("Comment", _note_html(note))
	return _notes(name, dt)


@frappe.whitelist()
def edit_note(comment, note):
	note = (note or "").strip()
	if not note:
		frappe.throw(_("A note cannot be empty. Use Delete to remove it."))
	c = _own_comment(comment, "edit")
	c.content = _note_html(note)
	c.save(ignore_permissions=True)
	return _notes(c.reference_name, c.reference_doctype)


@frappe.whitelist()
def delete_note(comment):
	c = _own_comment(comment, "delete")
	name, dt = c.reference_name, c.reference_doctype
	c.delete(ignore_permissions=True)
	return _notes(name, dt)


# ---------- activity (system events: Version + stage log, never Comments) ----------


def _who(user):
	return frappe.utils.get_fullname(user) if user else _("System")


def _party_title(doctype, name):
	if not name:
		return None
	if doctype == "Lead":
		r = frappe.db.get_value("Lead", name, ["company_name", "lead_name"], as_dict=True)
		return (r and (r.company_name or r.lead_name)) or name
	return frappe.db.get_value("Customer", name, "customer_name") or name


def _req_label(r):
	"""Requirement in the unit the team uses for its line: lb for fresh frozen, g for extracts."""
	r = frappe._dict(r or {})
	lb = sales_ops.line_unit(sales_ops.get_settings(), r.product_line) == "lb"
	per = sales_ops.UNIT_GRAMS["lb"] if lb else 1.0
	parts = [" · ".join(x for x in (r.product_line, r.tier) if x) or _("No product line")]
	if flt(r.total_grams):
		parts.append("{0} {1}".format(frappe.utils.fmt_money(flt(r.total_grams) / per, precision=1 if lb else 0), "lb" if lb else "g"))
	if flt(r.price_per_gram):
		parts.append("@ {0}/{1}".format(frappe.utils.fmt_money(flt(r.price_per_gram) * per, precision=2, currency="USD"), "lb" if lb else "g"))
	return " ".join(parts)


def _req_lines(data):
	"""Requirement rows added / removed / changed in one Version."""
	out = []
	for row in data.get("added") or []:
		if isinstance(row, (list, tuple)) and len(row) == 2 and row[0] == "requirements" and isinstance(row[1], dict):
			out.append(("product", _("Requirement added: {0}").format(_req_label(row[1]))))
	for row in data.get("removed") or []:
		if isinstance(row, (list, tuple)) and len(row) == 2 and row[0] == "requirements" and isinstance(row[1], dict):
			out.append(("product", _("Requirement removed: {0}").format(_req_label(row[1]))))
	for row in data.get("row_changed") or []:
		if isinstance(row, (list, tuple)) and len(row) == 4 and row[0] == "requirements":
			diffs = [
				"{0} {1} → {2}".format(_(REQ_LABELS[c[0]]), c[1] or "—", c[2] or "—")
				for c in row[3] or []
				if isinstance(c, (list, tuple)) and len(c) == 3 and c[0] in REQ_LABELS
			]
			if diffs:
				out.append(("product", _("Requirement {0} changed: {1}").format(cint(row[1]) + 1, "; ".join(diffs))))
	return out


def _version_lines(changed, s, lead_now=None, has_req=False):
	"""One Version's field changes -> Activity lines (kind, text without the 'by').
	lead_now = the Lead linked right after this change (used when only the Customer is cleared).
	has_req = this version changed requirement lines (they get their own lines; skip the summary fields)."""
	ch = {row[0]: (row[1], row[2]) for row in changed if isinstance(row, (list, tuple)) and len(row) == 3}
	if has_req:
		for f in ("product_line", "tier", "total_grams", "price_per_gram"):
			ch.pop(f, None)
	out = []
	blank = lambda v: v in (None, "", 0, "0", "0.0")  # noqa: E731
	if "deal_owner" in ch:
		old, new = ch["deal_owner"]
		out.append(("owner", _("Owner changed from {0} to {1}").format(
			sales_ops.owner_label(s, old) if old else _("Unassigned"),
			sales_ops.owner_label(s, new) if new else _("Unassigned"))))
	if "customer" in ch or "lead" in ch:
		cust = ch.get("customer", (None, None))[1]
		lead = ch.get("lead", (None, None))[1]
		if cust:
			out.append(("buyer", _("Buyer set to {0} (Customer)").format(_party_title("Customer", cust))))
		elif lead:
			out.append(("buyer", _("Buyer set to {0} (Lead)").format(_party_title("Lead", lead))))
		elif "customer" in ch and "lead" not in ch and lead_now:
			out.append(("buyer", _("Buyer set to {0} (Lead)").format(_party_title("Lead", lead_now))))
		else:
			out.append(("buyer", _("Buyer removed")))
	if "product_line" in ch:
		old, new = ch["product_line"]
		if "tier" in ch:
			old = " · ".join(x for x in (old, ch["tier"][0]) if x)
			new = " · ".join(x for x in (new, ch["tier"][1]) if x)
		out.append(("product", _("Product line changed from {0} to {1}").format(old or _("not set"), new or _("not set"))))
	elif "tier" in ch:
		old, new = ch["tier"]
		out.append(("product", _("Tier changed from {0} to {1}").format(old or _("not set"), new or _("not set"))))
	details = [
		"{0}: {1} → {2}".format(_(label), "—" if blank(ch[f][0]) else ch[f][0], "—" if blank(ch[f][1]) else ch[f][1])
		for f, label in VALUE_LABELS.items()
		if f in ch
	]
	if "deal_value" in ch:
		old, new = ch["deal_value"]
		line = _("Deal value changed from {0} to {1}").format("—" if blank(old) else old, "—" if blank(new) else new)
		out.append(("value", line + (" ({0})".format("; ".join(details)) if details else "")))
	elif details:
		out.append(("value", "; ".join(details)))
	if "pipeline_account" in ch and ch["pipeline_account"][0] and ch["pipeline_account"][1]:
		new = ch["pipeline_account"][1]
		out.append(("buyer", _("Moved to the account {0}").format(frappe.db.get_value(ACC, new, "account_name") or new)))
	if "lost_reason" in ch and (ch["lost_reason"][1] or "").strip():
		out.append(("lost", _("Lost reason: {0}").format(ch["lost_reason"][1].strip())))
	for f, label in DATE_LABELS.items():
		if f not in ch:
			continue
		old, new = ch[f]
		if not old:
			text = _("{0} set to {1}").format(_(label), new)
		elif not new:
			text = _("{0} cleared (was {1})").format(_(label), old)
		else:
			text = _("{0} moved from {1} to {2}").format(_(label), old, new)
		out.append(("date", text))
	return out


def _short_recipients(recipients):
	addrs = [x.strip() for x in (recipients or "").replace(";", ",").split(",") if x.strip()]
	if not addrs:
		return _("no recipient")
	return ", ".join(addrs[:3]) + (_(" and {0} more").format(len(addrs) - 3) if len(addrs) > 3 else "")


def _activity(doc):
	s = sales_ops.get_settings()
	won, lost = sales_ops.won_stage(s), sales_ops.lost_stage(s)
	items = []
	for r in doc.get("stage_log") or []:
		by = _who(r.changed_by)
		if not r.from_stage:
			kind, text = "created", _("Deal created in {0} by {1}").format(r.to_stage, by)
		elif won and r.to_stage == won.name:
			kind, text = "won", _("Marked won (moved from {0}) by {1}").format(r.from_stage, by)
		elif lost and r.to_stage == lost.name:
			kind, text = "lost", _("Marked lost (moved from {0}) by {1}").format(r.from_stage, by)
		else:
			kind, text = "stage", _("Stage changed from {0} to {1} by {2}").format(r.from_stage, r.to_stage, by)
		days = flt(r.days_in_previous, 1)
		detail = (_("{0} days in the previous stage").format("{0:g}".format(days)) if days >= 1 else _("less than a day in the previous stage")) if r.from_stage else ""
		items.append({"kind": kind, "text": text, "detail": detail, "on": str(r.changed_on)})
	if not any(i["kind"] == "created" for i in items):
		items.append({"kind": "created", "text": _("Deal created by {0}").format(_who(doc.owner)), "detail": "", "on": str(doc.creation)})
	versions = frappe.get_all(
		"Version",
		filters={"ref_doctype": DT, "docname": doc.name},
		fields=["data", "owner", "creation"],
		order_by="creation desc",
		limit_page_length=500,
	)
	parsed = []
	co_now = {r.user for r in doc.get("co_owners") or []}
	for v in versions:  # newest first
		try:
			data = json.loads(v.data or "{}")
			v.req_lines = _req_lines(data)
			parsed.append((v, data.get("changed") or []))
		except (ValueError, AttributeError):
			continue
		by = _who(v.owner)
		for key, verb in (("added", _("{0} added as a co-owner by {1}")), ("removed", _("{0} removed as a co-owner by {1}"))):
			for row in data.get(key) or []:
				if isinstance(row, (list, tuple)) and len(row) == 2 and row[0] == "co_owners" and isinstance(row[1], dict):
					who = row[1].get("user")
					items.append({"kind": "owner", "text": verb.format(sales_ops.owner_label(s, who), by), "detail": "", "on": str(v.creation)})
					# walk back to the co-owners the deal was created with
					if key == "added":
						co_now.discard(who)
					else:
						co_now.add(who)
	# co-owners set when the deal was created (no Version is written on insert)
	for who in sorted(co_now):
		items.insert(0, {"kind": "owner", "text": _("{0} added as a co-owner by {1}").format(sales_ops.owner_label(s, who), _who(doc.owner)),
			"detail": "", "on": str(doc.creation)})
	for c in frappe.get_all(
		"Communication",
		filters={"reference_doctype": DT, "reference_name": doc.name, "communication_type": "Communication",
			"communication_medium": "Email"},
		fields=["sent_or_received", "recipients", "sender", "sender_full_name", "owner", "subject", "communication_date", "creation"],
		order_by="creation desc", limit_page_length=200,
	):
		if c.sent_or_received == "Sent":
			text = _("Email sent to {0} by {1}").format(_short_recipients(c.recipients), _who(c.owner))
			kind = "email"
		else:
			text = _("Email received from {0}").format(c.sender_full_name or c.sender or _("unknown sender"))
			kind = "email_in"
		items.append({"kind": kind, "text": text, "detail": c.subject or "", "on": str(c.communication_date or c.creation)})
	# which Lead was linked after each version: walk back from the current value
	lead_now = doc.lead
	for v, changed in parsed:  # newest first
		v.lead_after = lead_now
		for row in changed:
			if isinstance(row, (list, tuple)) and len(row) == 3 and row[0] == "lead":
				lead_now = row[1]
	for v, changed in parsed:
		by = _who(v.owner)
		for kind, text in v.req_lines + _version_lines(changed, s, v.lead_after, bool(v.req_lines)):
			items.append({"kind": kind, "text": _("{0} by {1}").format(text, by), "detail": "", "on": str(v.creation)})
	items.sort(key=lambda x: x["on"], reverse=True)
	return items


@frappe.whitelist()
def get_activity(name):
	doc = frappe.get_doc(DT, name)
	doc.check_permission("read")
	return _activity(doc)


@frappe.whitelist()
def get_feed(name, doctype=None):
	"""Drawer Notes + Activity in one call (a deal or an account)."""
	dt = _dt(doctype)
	doc = frappe.get_doc(dt, name)
	doc.check_permission("read")
	return {"notes": _notes(name, dt), "activity": _activity(doc) if dt == DT else _account_activity(doc)}


GRAMS_PER = {"Gram": 1.0, "LBS": 453.59237}


def _history_customer(doc):
	"""The deal's Customer, or the Customer that was created from its Lead."""
	if doc.customer:
		return doc.customer
	if doc.lead:
		return frappe.db.get_value("Customer", {"lead_name": doc.lead}, "name")
	return None


@frappe.whitelist()
def get_buyer_history(name, doctype=None):
	"""Drawer Purchases tab: every submitted Sales Invoice of the deal's (or account's) buyer, newest first, with its items.
	Anyone who can open the record sees its buyer's history; invoice links show only to users who can read invoices."""
	doc = frappe.get_doc(_dt(doctype), name)
	doc.check_permission("read")
	customer = _history_customer(doc)
	out = {
		"name": name, "customer": customer, "customer_title": None, "via_lead": bool(customer and not doc.customer),
		"can_open": bool(frappe.has_permission("Sales Invoice", "read")), "invoices": [], "by_line": [], "totals": {},
	}
	if not customer:
		return out
	out["customer_title"] = frappe.db.get_value("Customer", customer, "customer_name") or customer
	invoices = frappe.get_all(
		"Sales Invoice",
		filters={"customer": customer, "docstatus": 1},
		fields=["name", "posting_date", "due_date", "company", "base_grand_total", "outstanding_amount", "status", "is_return"],
		order_by="posting_date desc, creation desc",
		limit_page_length=0,
	)
	if not invoices:
		return out
	items = frappe.get_all(
		"Sales Invoice Item",
		filters={"parenttype": "Sales Invoice", "parent": ("in", [i.name for i in invoices])},
		fields=["parent", "item_code", "item_name", "item_group", "qty", "uom", "stock_qty", "stock_uom", "rate", "base_net_amount"],
		order_by="idx asc",
		limit_page_length=0,
	)
	s = sales_ops.get_settings()
	line_of = {}
	for r in s.product_lines:
		for g in r.item_groups:
			line_of.setdefault(g, r.product_line)
	by_inv, by_line = {}, {}
	for it in items:
		by_inv.setdefault(it.parent, []).append({
			"item_name": it.item_name or it.item_code, "qty": flt(it.qty), "uom": it.uom,
			"rate": flt(it.rate), "amount": flt(it.base_net_amount),
		})
		label = line_of.get(it.item_group) or it.item_group or _("Other")
		row = by_line.setdefault(label, {"label": label, "grams": 0.0, "units": 0.0, "amount": 0.0})
		per = GRAMS_PER.get(it.stock_uom)
		if per:
			row["grams"] += flt(it.stock_qty) * per
		else:
			row["units"] += flt(it.stock_qty)
		row["amount"] += flt(it.base_net_amount)
	sales = [i for i in invoices if not i.is_return]
	out["invoices"] = [{
		"name": i.name, "date": str(i.posting_date), "due": str(i.due_date) if i.due_date else None, "company": i.company,
		"amount": flt(i.base_grand_total), "outstanding": flt(i.outstanding_amount), "status": i.status,
		"is_return": cint(i.is_return), "items": by_inv.get(i.name, []),
	} for i in invoices]
	out["by_line"] = sorted(by_line.values(), key=lambda r: -r["amount"])
	out["totals"] = {
		"billed": sum(flt(i.base_grand_total) for i in invoices),
		"outstanding": sum(flt(i.outstanding_amount) for i in invoices),
		"count": len(sales),
		"returns": len(invoices) - len(sales),
		"first": str(sales[-1].posting_date) if sales else None,
		"last": str(sales[0].posting_date) if sales else None,
		"companies": len({i.company for i in invoices}),
	}
	return out


@frappe.whitelist()
def make_quotation(name):
	"""Unsaved Quotation for the deal's Customer: item from Product Line + Tier, qty = grams, rate = price per gram."""
	doc = frappe.get_doc(DT, name)
	doc.check_permission("read")
	frappe.has_permission("Quotation", "create", throw=True)
	if not doc.customer:
		frappe.throw(_("Link a Customer to this deal before creating a Quotation."))
	s = sales_ops.get_settings()
	q = frappe.new_doc("Quotation")
	q.quotation_to = "Customer"
	q.party_name = doc.customer
	missing = []
	rates = []
	lines = sales_ops.deal_lines(frappe._dict(doc.as_dict()))
	for line in lines:
		row = sales_ops.product_row(s, line.product_line, line.tier)
		if row and row.quotation_item:
			if flt(line.total_grams):
				# lb lines (fresh frozen) are quoted in lb, the rest in grams
				per = sales_ops.UNIT_GRAMS["lb"] if sales_ops.line_unit(s, line.product_line) == "lb" else 1.0
				q.append("items", {"item_code": row.quotation_item, "qty": flt(line.total_grams) / per, "rate": flt(line.price_per_gram) * per})
				rates.append(flt(line.price_per_gram) * per)
		else:
			missing.append(" ".join(x for x in (line.product_line, line.tier) if x))
	message = None
	if missing or not lines:
		message = _("No Quotation Item is set for {0} in Sales Pipeline Settings. Add the item on the Quotation.").format(
			", ".join(missing) or _("this deal"))
	q.run_method("set_missing_values")
	for it, rate in zip(q.get("items") or [], rates):
		it.rate = rate
	q.run_method("calculate_taxes_and_totals")
	out = q.as_dict(convert_dates_to_str=True)
	out["__islocal"] = 1
	for it in out.get("items") or []:
		it["__islocal"] = 1
		it["parent"] = None
		it["name"] = None
	return {"doc": out, "message": message}


@frappe.whitelist()
def export_xlsx(names):
	from frappe.utils.xlsxutils import make_xlsx

	if isinstance(names, str):
		names = json.loads(names)
	frappe.has_permission(DT, "read", throw=True)
	s = sales_ops.get_settings()
	rows = frappe.get_list(DT, fields=FIELDS, filters={"name": ("in", names or [""])}, limit_page_length=0)
	order = {n: i for i, n in enumerate(names or [])}
	rows.sort(key=lambda r: order.get(r.name, 0))
	data = [[c[0] for c in EXPORT_COLUMNS]]
	for r in rows:
		st = sales_ops.stage_info(s, r.stage)
		r.probability = st.probability if st else 0
		r.weighted_value = flt(r.deal_value) * flt(r.probability) / 100.0
		r.owner_name = sales_ops.owner_label(s, r.deal_owner) if r.deal_owner else ""
		line = []
		for _label, key in EXPORT_COLUMNS:
			v = r.get(key)
			if key == "modified" and v:
				v = frappe.utils.format_datetime(v)
			elif key in DATE_FIELDS and v:
				v = getdate(v)
			line.append("" if v is None else v)
		data.append(line)
	xlsx = make_xlsx(data, "Pipeline")
	frappe.response["filename"] = "Sales_Pipeline_{0}.xlsx".format(nowdate())
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"


# ---------- accounts (Leads board) ----------


def _volumes(accounts):
	names = [a.name for a in accounts]
	by = {}
	if names:
		for r in frappe.get_all(
			sales_ops.VOLUME, filters={"parenttype": ACC, "parent": ("in", names)},
			fields=["name", "parent"] + list(VOL_FIELDS) + ["price_unit", "price_per_gram", "weekly_grams", "monthly_grams", "monthly_value"],
			order_by="idx asc",
		):
			by.setdefault(r.parent, []).append(r)
	for a in accounts:
		a.volume = by.get(a.name, [])


def _accounts(s, today, deals):
	"""Accounts the user may see, with lead status, volume rows, totals of their deals and attention flags."""
	if not frappe.has_permission(ACC, "read"):
		return []
	rows = frappe.get_list(ACC, fields=ACC_FIELDS, order_by="creation asc", limit_page_length=0)
	_volumes(rows)
	stats = sales_ops.deal_stats(deals)
	for a in rows:
		sales_ops.enrich_account(a, s, today, stats)
	_buyer_titles(rows)
	return rows


def _set_volume(doc, rows):
	"""Volume rows from the page. Rows keep their name so Activity shows what really changed."""
	if isinstance(rows, str):
		rows = json.loads(rows or "[]")
	existing = {r.name: r for r in doc.get("volume") or []}
	keep = []
	for i, row in enumerate(rows or [], start=1):
		row = row or {}
		vals = {}
		for f in VOL_FIELDS:
			v = row.get(f)
			if f in VOL_NUM:
				v = flt(v)
				if v < 0:
					frappe.throw(_("Volume row {0}: amounts cannot be negative.").format(i))
			else:
				v = (v or "").strip() if isinstance(v, str) else (v or "")
			vals[f] = v
		if not (vals["product_line"] or vals["weekly_volume"] or vals["wants_qty"]):
			continue
		r = existing.get(row.get("name")) if row.get("name") else None
		if r:
			r.update(vals)
		else:
			r = doc.append("volume", vals)
		keep.append(r)
	doc.set("volume", keep)
	for i, r in enumerate(keep, start=1):
		r.idx = i


@frappe.whitelist()
def update_account(name, values):
	"""Apply a change from the Leads board; the account's validate() enforces every rule."""
	if isinstance(values, str):
		values = json.loads(values)
	bad = set(values) - ACC_EDITABLE
	if bad:
		frappe.throw(_("These fields cannot be changed from the board: {0}").format(", ".join(sorted(bad))))
	doc = frappe.get_doc(ACC, name)
	doc.check_permission("write")
	vol = values.pop("volume", None) if "volume" in values else False
	for key, value in values.items():
		if isinstance(value, str):
			value = value.strip()
		if value in ("", None):
			value = None
		elif key == "next_step_due":
			value = str(getdate(value))
		if key in ("account_name", "lead_status", "account_owner") and not value:
			frappe.throw(_("{0} cannot be empty.").format(_(frappe.get_meta(ACC).get_label(key))))
		doc.set(key, value)
	if vol is not False:
		_set_volume(doc, vol)
	doc.save()
	return {"name": doc.name, "volume": [r.name for r in doc.get("volume") or []]}


@frappe.whitelist()
def create_account(values):
	"""New Lead dialog on the Leads board."""
	if isinstance(values, str):
		values = json.loads(values)
	frappe.has_permission(ACC, "create", throw=True)
	bad = set(values) - ACC_CREATE
	if bad:
		frappe.throw(_("These fields cannot be set from the New Lead dialog: {0}").format(", ".join(sorted(bad))))
	vol = values.pop("volume", None)
	values = {k: (v.strip() if isinstance(v, str) else v) for k, v in values.items()}
	values = {k: v for k, v in values.items() if v not in ("", None)}
	if not values.get("account_name") and not values.get("customer"):
		frappe.throw(_("Please enter the account name or choose a Customer."))
	if values.get("customer"):
		frappe.has_permission("Customer", "read", doc=values["customer"], throw=True)
		hit = sales_ops.find_account(values["customer"])
		if hit:
			frappe.throw(_("{0} already has an account on the Leads board: {1}").format(
				values["customer"], frappe.db.get_value(ACC, hit, "account_name")))
	doc = frappe.new_doc(ACC)
	for key, value in values.items():
		doc.set(key, str(getdate(value)) if key == "next_step_due" else value)
	if vol:
		_set_volume(doc, vol)
	doc.insert()
	return doc.name


def _vol_label(r):
	r = frappe._dict(r or {})
	head = " · ".join(x for x in (r.product_line, r.tier) if x) or _("No product line")
	unit = r.uom or "g"
	parts = []
	if flt(r.weekly_volume):
		parts.append(_("{0} {1} {2}/week").format(
			_("produces") if r.activity == "Produce" else _("procures"), "{0:g}".format(flt(r.weekly_volume)), unit))
	if flt(r.wants_qty):
		parts.append(_("wants {0} {1}/{2}").format("{0:g}".format(flt(r.wants_qty)), unit, _("week") if r.wants_per == "Week" else _("month")))
	return head + (": " + ", ".join(parts) if parts else "")


def _vol_lines(data):
	out = []
	for key, verb in (("added", _("Volume added: {0}")), ("removed", _("Volume removed: {0}"))):
		for row in data.get(key) or []:
			if isinstance(row, (list, tuple)) and len(row) == 2 and row[0] == "volume" and isinstance(row[1], dict):
				out.append(("product", verb.format(_vol_label(row[1]))))
	for row in data.get("row_changed") or []:
		if isinstance(row, (list, tuple)) and len(row) == 4 and row[0] == "volume":
			diffs = [
				"{0} {1} → {2}".format(_(VOL_LABELS[c[0]]), c[1] if c[1] not in (None, "") else "—", c[2] if c[2] not in (None, "") else "—")
				for c in row[3] or []
				if isinstance(c, (list, tuple)) and len(c) == 3 and c[0] in VOL_LABELS
			]
			if diffs:
				out.append(("product", _("Volume row {0} changed: {1}").format(cint(row[1]) + 1, "; ".join(diffs))))
	return out


def _account_activity(doc):
	"""Lead status, owner, follow-up, buyer and volume changes, emails, and the account's deals opening and closing."""
	s = sales_ops.get_settings()
	items = [{"kind": "created", "text": _("Account created by {0}").format(_who(doc.owner)), "detail": "", "on": str(doc.creation)}]
	for v in frappe.get_all("Version", filters={"ref_doctype": ACC, "docname": doc.name}, fields=["data", "owner", "creation"],
			order_by="creation desc", limit_page_length=500):
		try:
			data = json.loads(v.data or "{}")
		except ValueError:
			continue
		by = _who(v.owner)
		ch = {row[0]: (row[1], row[2]) for row in data.get("changed") or [] if isinstance(row, (list, tuple)) and len(row) == 3}
		lines = []
		if "lead_status" in ch:
			lines.append(("stage", _("Lead status changed from {0} to {1}").format(ch["lead_status"][0] or _("not set"), ch["lead_status"][1])))
		if "account_owner" in ch:
			old, new = ch["account_owner"]
			lines.append(("owner", _("Relationship manager changed from {0} to {1}").format(
				sales_ops.owner_label(s, old) if old else _("Unassigned"), sales_ops.owner_label(s, new) if new else _("Unassigned"))))
		if "account_name" in ch:
			lines.append(("buyer", _("Renamed from {0} to {1}").format(ch["account_name"][0], ch["account_name"][1])))
		if "customer" in ch and ch["customer"][1]:
			lines.append(("buyer", _("Customer set to {0}").format(_party_title("Customer", ch["customer"][1]))))
		elif "lead" in ch and ch["lead"][1]:
			lines.append(("buyer", _("Lead set to {0}").format(_party_title("Lead", ch["lead"][1]))))
		if "next_step_due" in ch:
			old, new = ch["next_step_due"]
			lines.append(("date", _("Next follow-up set to {0}").format(new) if new else _("Next follow-up cleared (was {0})").format(old)))
		lines += _vol_lines(data)
		for kind, text in lines:
			items.append({"kind": kind, "text": _("{0} by {1}").format(text, by), "detail": "", "on": str(v.creation)})
	for c in frappe.get_all(
		"Communication",
		filters={"reference_doctype": ACC, "reference_name": doc.name, "communication_type": "Communication", "communication_medium": "Email"},
		fields=["sent_or_received", "recipients", "sender", "sender_full_name", "owner", "subject", "communication_date", "creation"],
		order_by="creation desc", limit_page_length=200,
	):
		sent = c.sent_or_received == "Sent"
		items.append({
			"kind": "email" if sent else "email_in",
			"text": _("Email sent to {0} by {1}").format(_short_recipients(c.recipients), _who(c.owner)) if sent
			else _("Email received from {0}").format(c.sender_full_name or c.sender or _("unknown sender")),
			"detail": c.subject or "", "on": str(c.communication_date or c.creation),
		})
	# the deals on this account the user can see: opened, won, lost
	deals = frappe.get_list(DT, filters={"pipeline_account": doc.name}, fields=["name", "product_line", "tier", "lost_reason"], limit_page_length=0)
	if deals:
		won, lost = sales_ops.won_stage(s), sales_ops.lost_stage(s)
		label = {d.name: (" · ".join(x for x in (d.product_line, d.tier) if x) + " ") if d.product_line else "" for d in deals}
		reason = {d.name: d.lost_reason for d in deals}
		for r in frappe.get_all("Sales Pipeline Stage Log", filters={"parenttype": DT, "parent": ("in", list(label))},
				fields=["parent", "from_stage", "to_stage", "changed_by", "changed_on"], limit_page_length=0):
			if not r.from_stage:
				kind, text = "created", _("New deal: {0}{1} by {2}").format(label[r.parent], r.parent, _who(r.changed_by))
			elif won and r.to_stage == won.name:
				kind, text = "won", _("Deal won: {0}{1}").format(label[r.parent], r.parent)
			elif lost and r.to_stage == lost.name:
				kind, text = "lost", _("Deal lost: {0}{1}").format(label[r.parent], r.parent)
			else:
				continue
			items.append({"kind": kind, "text": text, "detail": (reason.get(r.parent) or "") if kind == "lost" else "", "on": str(r.changed_on)})
	items.sort(key=lambda x: x["on"], reverse=True)
	return items


ACC_EXPORT = [
	("Account", "account_name"), ("Lead Status", "lead_status"), ("Relationship Manager", "owner_name"),
	("Volume / Week (g)", "weekly_volume"), ("Wants / Month (g)", "monthly_demand"), ("Potential / Month", "monthly_potential"),
	("Weighted / Month", "weighted_potential"), ("Open Deals", "open_deals"), ("Open Deal Value", "open_value"),
	("Next Follow-up", "next_step_due"), ("Customer", "customer"), ("Lead", "lead"), ("Contact Name", "contact_name"),
	("Phone", "phone"), ("Email", "email"), ("Location / Address", "location_address"), ("License #", "license_number"),
	("Lead Source", "lead_source"), ("Relationship Notes", "relationship_notes"), ("Last Updated", "modified"), ("ID", "name"),
]
VOL_EXPORT = [
	("Account", "account_name"), ("Lead Status", "lead_status"), ("Product Line", "product_line"), ("Tier", "tier"),
	("They", "activity"), ("Volume / Week", "weekly_volume"), ("Wants From Us", "wants_qty"), ("Per", "wants_per"), ("Unit", "uom"),
	("Price", "price"), ("Price per", "price_unit"), ("Volume / Week (g)", "weekly_grams"), ("Wants / Month (g)", "monthly_grams"),
	("Potential / Month", "monthly_value"), ("Notes", "notes"),
]


@frappe.whitelist()
def export_accounts_xlsx(names):
	"""Leads board export: one sheet of accounts and one of their volume rows."""
	from openpyxl import Workbook
	from io import BytesIO

	if isinstance(names, str):
		names = json.loads(names)
	frappe.has_permission(ACC, "read", throw=True)
	s = sales_ops.get_settings()
	today = getdate(nowdate())
	rows = frappe.get_list(ACC, fields=ACC_FIELDS, filters={"name": ("in", names or [""])}, limit_page_length=0)
	_volumes(rows)
	deals = frappe.get_list(DT, fields=["name", "pipeline_account", "stage", "deal_value"], filters={"pipeline_account": ("in", names or [""])},
		limit_page_length=0)
	for d in deals:
		st = sales_ops.stage_info(s, d.stage) or frappe._dict(is_closed=0, is_won=0, probability=0)
		d.is_closed, d.is_won = st.is_closed, st.is_closed and st.is_won
		d.weighted_value = flt(d.deal_value) * flt(st.probability) / 100.0
	stats = sales_ops.deal_stats(deals)
	order = {n: i for i, n in enumerate(names or [])}
	rows.sort(key=lambda r: order.get(r.name, 0))
	wb = Workbook()
	ws = wb.active
	ws.title = "Accounts"
	ws.append([c[0] for c in ACC_EXPORT])
	vs = wb.create_sheet("Volume")
	vs.append([c[0] for c in VOL_EXPORT])
	for r in rows:
		sales_ops.enrich_account(r, s, today, stats)
		r.owner_name = sales_ops.owner_label(s, r.account_owner) if r.account_owner else ""
		ws.append(["" if r.get(k) is None else (getdate(r[k]) if k == "next_step_due" and r[k] else
			(frappe.utils.format_datetime(r[k]) if k == "modified" else r[k])) for _l, k in ACC_EXPORT])
		for v in r.volume:
			v.account_name, v.lead_status = r.account_name, r.lead_status
			vs.append(["" if v.get(k) is None else v[k] for _l, k in VOL_EXPORT])
	out = BytesIO()
	wb.save(out)
	frappe.response["filename"] = "Sales_Accounts_{0}.xlsx".format(nowdate())
	frappe.response["filecontent"] = out.getvalue()
	frappe.response["type"] = "binary"
