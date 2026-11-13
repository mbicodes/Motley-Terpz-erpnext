"""Project Tracker: every Fresh Frozen toll / in-house project end to end (sent, hash, rosin, yields, cost).

Read-only page. Every figure comes from submitted documents tagged with the project:

- Fresh Frozen sent
  Toll:     FF received into the project's Partner Warehouse (Purchase Receipt or Stock Entry transfer),
            read from the Stock Ledger (project inventory dimension). FF leaving that warehouse other than
            through production counts as returned unprocessed.
  In-house: FF moved into production (Material Transfer for Manufacture into WIP), or consumed straight
            from stock by a Manufacture / Repack entry.
- Production: Repack / Manufacture Stock Entries of the project, including the Repack entries a Conversion
  Entry creates (those carry no project, only custom_conversion_entry_reference). Repack rows are read in row
  blocks (inputs, then their outputs), the same way the lab enters them, so each output is tied to the Fresh
  Frozen it came from even when the names differ ("London Poundcake" FF -> "Crumpets - T1").
- Hash: hash-group outputs of a wash. Toll partners return rosin straight from FF (no hash row), so for those
  strains the hash comes from the lab's Rosin Recording (Lab Tolling Data). A recording that repeats an
  earlier one line for line is skipped and raised as a Check alert.
- Rosin: rosin-group outputs of production. Tier = item group (Tier 1 / Tier 2 / Tier 3); raw rosin that is
  later graded by a Conversion Entry moves into its tier.
- Cost: FF valuation + non-stock Purchase Invoice lines + Journal Entry lines tagged with the project.
  Stock-item invoice lines (the Fresh Frozen bill itself) are left out, the stock valuation already has them.
"""

import hashlib
import json
import re
from collections import defaultdict

import frappe
from frappe import _
from frappe.utils import cint, date_diff, flt, get_quarter_start, getdate, nowdate

LB = 453.592
IN_HOUSE = "In-house"
PRODUCTION = ("Repack", "Manufacture")
PAGE_ROLES = {"Manufacturing Manager", "Stock Manager", "Accounts Manager", "System Manager"}
COST_ROLES = {"Accounts Manager", "System Manager"}
CACHE_TTL = 300
CACHE_VER_KEY = "project_tracker:ver"

COST_ORDER = ["material", "toll", "freight", "testing", "labor", "consumables", "other"]
COST_LABELS = {
	"material": "Fresh Frozen material (stock valuation)",
	"toll": "Toll fee",
	"freight": "Freight / transport",
	"testing": "Lab testing",
	"labor": "Labor",
	"consumables": "Consumables",
	"other": "Other costs",
}
TIERS = ("Tier 1", "Tier 2", "Tier 3", "Untiered")


# ---------------------------------------------------------------- access, settings, helpers


def _check_access():
	if frappe.session.user == "Administrator":
		return
	if not PAGE_ROLES & set(frappe.get_roles()):
		frappe.throw(_("You do not have access to the Project Tracker."), frappe.PermissionError)


def can_see_cost():
	return frappe.session.user == "Administrator" or bool(COST_ROLES & set(frappe.get_roles()))


def get_settings():
	st = frappe._dict(
		hash_target=2.5,
		rosin_target=75.0,
		rosin_warn=72.0,
		pending_days=30,
		ff_root="Fresh Frozen Main",
		hash_groups=["Bubble Hash"],
		rosin_groups=["Rosins", "Rosin"],
		labor_accounts=set(),
		consumable_accounts=set(),
	)
	if not frappe.db.exists("DocType", "Project Tracker Settings"):
		return st
	d = frappe.get_cached_doc("Project Tracker Settings")
	st.hash_target = flt(d.default_hash_target) or st.hash_target
	st.rosin_target = flt(d.default_rosin_target) or st.rosin_target
	st.rosin_warn = flt(d.rosin_warning_threshold) or st.rosin_warn
	st.pending_days = cint(d.pending_alert_days) or st.pending_days
	st.ff_root = d.ff_item_group or st.ff_root
	if d.get("hash_item_groups"):
		st.hash_groups = [r.item_group for r in d.hash_item_groups if r.item_group]
	if d.get("rosin_item_groups"):
		st.rosin_groups = [r.item_group for r in d.rosin_item_groups if r.item_group]
	st.labor_accounts = {r.account for r in (d.get("labor_accounts") or []) if r.account}
	st.consumable_accounts = {r.account for r in (d.get("consumable_accounts") or []) if r.account}
	return st


def to_lbs(qty, uom):
	u = (uom or "").strip().lower()
	qty = flt(qty)
	if u in ("gram", "grams", "g", "gm", "gms"):
		return qty / LB
	if u in ("kg", "kgs", "kilogram", "kilograms"):
		return qty * 1000 / LB
	if u in ("oz", "ounce", "ounces"):
		return qty / 16
	return qty


def to_g(qty, uom):
	u = (uom or "").strip().lower()
	qty = flt(qty)
	if u in ("lbs", "lb", "pound", "pounds"):
		return qty * LB
	if u in ("kg", "kgs", "kilogram", "kilograms"):
		return qty * 1000
	if u in ("oz", "ounce", "ounces"):
		return qty * 28.3495
	return qty


def tier_of(group):
	g = (group or "").lower()
	if "tier 1" in g or g in ("primes", "prime"):
		return "Tier 1"
	if "tier 2" in g or g in ("subprimes", "subprime"):
		return "Tier 2"
	if "tier 3" in g:
		return "Tier 3"
	return "Untiered"


def strain_label(name):
	n = name or ""
	n = re.sub(r"\s*[-–]\s*(fresh frozen|ff|bubble hash|hash|rosin)\s*$", "", n, flags=re.I)
	n = re.sub(r"_(l|\d+)\s*$", "", n, flags=re.I)
	return n.strip() or name


def _pct(num, den):
	return (num / den * 100) if den and num else None


class Items:
	"""Item master facts + which tracker category (FF / HASH / ROSIN) an item group falls under."""

	def __init__(self, st):
		self.groups = {r.name: (r.lft, r.rgt) for r in frappe.db.sql("select name, lft, rgt from `tabItem Group`", as_dict=1)}
		self.roots = [("FF", [st.ff_root]), ("HASH", st.hash_groups), ("ROSIN", st.rosin_groups)]
		self.info = {}
		self._cat = {}

	def load(self, codes):
		codes = [c for c in set(codes) if c and c not in self.info]
		for i in range(0, len(codes), 500):
			for r in frappe.get_all(
				"Item", filters={"name": ["in", codes[i : i + 500]]}, fields=["name", "item_name", "item_group", "stock_uom"]
			):
				self.info[r.name] = r

	def group_cat(self, group):
		if group not in self._cat:
			cat, lr = None, self.groups.get(group)
			if lr:
				for c, roots in self.roots:
					if any(r in self.groups and self.groups[r][0] <= lr[0] and lr[1] <= self.groups[r][1] for r in roots):
						cat = c
						break
			self._cat[group] = cat
		return self._cat[group]

	def cat(self, code):
		i = self.info.get(code)
		return self.group_cat(i.item_group) if i else None

	def group(self, code):
		i = self.info.get(code)
		return i.item_group if i else None

	def uom(self, code):
		i = self.info.get(code)
		return i.stock_uom if i else None

	def name(self, code):
		i = self.info.get(code)
		return (i.item_name if i else None) or code


# ---------------------------------------------------------------- projects


def _user_restrictions():
	"""(companies, projects) the user is limited to by User Permissions; None = no limit."""
	user = frappe.session.user
	if user == "Administrator":
		return None, None
	up = frappe.permissions.get_user_permissions(user) or {}

	def allowed(doctype):
		docs = [d.get("doc") for d in up.get(doctype, []) if not d.get("applicable_for") or d.get("applicable_for") == "Project"]
		return set(docs) if docs else None

	return allowed("Company"), allowed("Project")


PROJECT_FIELDS = [
	"name",
	"project_name",
	"status",
	"company",
	"custom_processing_type as ptype",
	"custom_toll_partner as partner",
	"custom_partner_warehouse as partner_wh",
	"custom_dispatch_date as dispatch_date",
	"custom_return_completed_on as returned_on",
	"custom_expected_hash_pct as exp_hash",
	"custom_expected_rosin_pct as exp_rosin",
	"custom_metrc_tag as metrc_tag",
	"creation",
]


def load_projects(names=None, apply_user_permissions=True):
	filters = {"custom_processing_type": ["in", ["Toll", IN_HOUSE]], "status": ["!=", "Cancelled"]}
	if names:
		filters["name"] = ["in", list(names)]
	if apply_user_permissions:
		companies, projects = _user_restrictions()
		if companies is not None:
			filters["company"] = ["in", list(companies)]
		if projects is not None:
			allowed = projects & set(names) if names else projects
			if not allowed:
				return []
			filters["name"] = ["in", list(allowed)]
	return frappe.get_all("Project", filters=filters, fields=PROJECT_FIELDS, order_by="creation desc")


# ---------------------------------------------------------------- engine


def _new_acc(p, st):
	return frappe._dict(
		p=p,
		toll=p.ptype == "Toll",
		hash_t=flt(p.exp_hash) or st.hash_target,
		rosin_t=flt(p.exp_rosin) or st.rosin_target,
		strains={},
		ff_sent=0.0,
		ff_sent_value=0.0,
		ff_returned=0.0,
		ff_returned_value=0.0,
		sent_dates=[],
		output_dates=[],
		tiers=defaultdict(float),
		hash_origin={},
		wip=set(),
		docs={},
		events=defaultdict(float),
		event_text={},
		lab_dups=[],
		repack_dups=[],
		wrong_wh=[],
		costs={k: {"amount": 0.0, "docs": {}} for k in COST_ORDER},
		has_toll_invoice=False,
	)


def _strain(acc, key, items):
	s = acc.strains.get(key)
	if s is None:
		s = acc.strains[key] = frappe._dict(
			key=key,
			name=strain_label(items.name(key)),
			sent=0.0,
			returned=0.0,
			proc=0.0,
			hash=0.0,
			hash_base=0.0,
			hash_pressed=0.0,
			rosin=0.0,
			rosin_direct=0.0,
			lab_hash=0.0,
			lab_lbs=0.0,
			orphan=False,
		)
	return s


def _doc(acc, doctype, name, date, label, status="Submitted"):
	k = (doctype, name)
	if k not in acc.docs:
		acc.docs[k] = {"doctype": doctype, "name": name, "date": str(date or ""), "type": label, "status": status}
	return acc.docs[k]


def _event(acc, date, kind, qty, text):
	"""Timeline: one line per (date, kind), quantities summed. text has a {q} placeholder."""
	k = (str(date), kind)
	acc.events[k] += flt(qty)
	acc.event_text[k] = text


def _blocks(rows, single):
	"""Repack rows are entered as blocks: the inputs, then the outputs made from them."""
	if single:
		return [
			{
				"in": [r for r in rows if r.s_warehouse and not r.t_warehouse],
				"out": [r for r in rows if r.t_warehouse and not r.s_warehouse],
			}
		]
	blocks, cur = [], None
	for r in rows:
		is_in = bool(r.s_warehouse) and not r.t_warehouse
		is_out = bool(r.t_warehouse) and not r.s_warehouse
		if not (is_in or is_out):
			continue
		if cur is None or (is_in and cur["out"]):
			cur = {"in": [], "out": []}
			blocks.append(cur)
		cur["in" if is_in else "out"].append(r)
	return blocks


def _is_wip(acc, wh):
	return bool(wh) and (wh in acc.wip or "work in progress" in wh.lower())


def compute(projects, st, with_docs=False):
	"""{project name: accumulator with strains, totals, costs (and documents when with_docs)}."""
	P = {p.name: p for p in projects}
	if not P:
		return {}
	names = list(P)
	accs = {n: _new_acc(p, st) for n, p in P.items()}
	items = Items(st)

	# -- Conversion Entries of the projects (their Repack entries carry no project)
	ce_rows = frappe.db.sql(
		"select name, project, posting_date from `tabConversion Entry` where docstatus = 1 and project in %(p)s",
		{"p": names},
		as_dict=1,
	)
	ce_proj = {r.name: r.project for r in ce_rows}

	# -- Stock Entries of the projects: header project, row project, or made by one of their Conversion Entries
	se_names = set(
		frappe.db.sql_list("select name from `tabStock Entry` where docstatus = 1 and project in %(p)s", {"p": names})
	)
	se_names |= set(
		frappe.db.sql_list(
			"select distinct parent from `tabStock Entry Detail` where docstatus = 1 and project in %(p)s", {"p": names}
		)
	)
	if ce_proj:
		se_names |= set(
			frappe.db.sql_list(
				"select name from `tabStock Entry` where docstatus = 1 and custom_conversion_entry_reference in %(c)s",
				{"c": list(ce_proj)},
			)
		)
	se_rows = []
	if se_names:
		se_rows = frappe.db.sql(
			"""select se.name as se, se.purpose, se.posting_date, se.project as se_project,
				se.custom_conversion_entry_reference as ce, sed.idx, sed.item_code, sed.s_warehouse, sed.t_warehouse,
				sed.transfer_qty as qty, sed.stock_uom, sed.amount, sed.project as row_project
			from `tabStock Entry` se join `tabStock Entry Detail` sed on sed.parent = se.name
			where se.name in %(s)s
			order by se.posting_date, se.posting_time, se.name, sed.idx""",
			{"s": list(se_names)},
			as_dict=1,
		)

	# -- Stock Ledger of toll projects (FF in / out of the partner warehouse)
	toll = [n for n in names if accs[n].toll]
	sle = []
	if toll:
		sle = frappe.db.sql(
			"""select project, voucher_type, voucher_no, posting_date, warehouse, item_code, actual_qty, stock_value_difference
			from `tabStock Ledger Entry` where is_cancelled = 0 and project in %(p)s
			order by posting_date, posting_time, creation""",
			{"p": toll},
			as_dict=1,
		)
	se_purpose = {r.se: r.purpose for r in se_rows}
	missing = {e.voucher_no for e in sle if e.voucher_type == "Stock Entry" and e.voucher_no not in se_purpose}
	if missing:
		for r in frappe.get_all("Stock Entry", filters={"name": ["in", list(missing)]}, fields=["name", "purpose"]):
			se_purpose[r.name] = r.purpose

	# -- Lab data (hash for partners that return rosin straight from FF)
	lab = frappe.db.sql(
		"""select rr.name, rr.batch as project, rr.creation, ltd.idx, ltd.strain_name, ltd.pounds_sent, ltd.pounds_ran,
			ltd.total_hash, ltd.total_rosin
		from `tabRosin Recording` rr
		join `tabLab Tolling Data` ltd on ltd.parent = rr.name and ltd.parenttype = 'Rosin Recording'
		where rr.docstatus = 1 and rr.batch in %(p)s
		order by rr.creation, ltd.idx""",
		{"p": names},
		as_dict=1,
	)

	items.load([r.item_code for r in se_rows] + [e.item_code for e in sle] + [l.strain_name for l in lab])

	# ---- toll: Fresh Frozen in / out of the partner warehouse
	off_wh = defaultdict(float)
	for e in sle:
		acc = accs.get(e.project)
		if not acc or items.cat(e.item_code) != "FF":
			continue
		if e.voucher_type == "Stock Entry" and se_purpose.get(e.voucher_no) in PRODUCTION:
			continue
		lbs = to_lbs(e.actual_qty, items.uom(e.item_code))
		if e.warehouse != acc.p.partner_wh:
			off_wh[(e.project, e.item_code, e.warehouse)] += lbs
			continue
		s = _strain(acc, e.item_code, items)
		label = e.voucher_type + ("" if e.voucher_type != "Stock Entry" else " · " + (se_purpose.get(e.voucher_no) or ""))
		if lbs > 0:
			s.sent += lbs
			acc.ff_sent += lbs
			acc.ff_sent_value += flt(e.stock_value_difference)
			acc.sent_dates.append(getdate(e.posting_date))
			acc.costs["material"]["docs"][e.voucher_no] = e.voucher_type
			_event(acc, e.posting_date, "sent", lbs, "{q} lbs Fresh Frozen sent to " + (acc.p.partner_wh or ""))
		elif lbs < 0:
			s.returned += -lbs
			acc.ff_returned += -lbs
			acc.ff_returned_value += -flt(e.stock_value_difference)
			_event(acc, e.posting_date, "returned", -lbs, "{q} lbs Fresh Frozen returned unprocessed")
		_doc(acc, e.voucher_type, e.voucher_no, e.posting_date, label)
	for (proj, code, wh), lbs in off_wh.items():
		if lbs > 0.01:
			accs[proj].wrong_wh.append((code, wh, lbs))

	# ---- Stock Entries, grouped per entry
	by_se = defaultdict(list)
	for r in se_rows:
		proj = (
			r.row_project
			if r.row_project in accs
			else (r.se_project if r.se_project in accs else ce_proj.get(r.ce))
		)
		if proj in accs:
			by_se[(proj, r.se)].append(r)

	# WIP warehouses first (in-house FF moved into production)
	for (proj, se), rows in by_se.items():
		if rows[0].purpose == "Material Transfer for Manufacture":
			for r in rows:
				if r.t_warehouse:
					accs[proj].wip.add(r.t_warehouse)

	wash, press, regrade = [], [], []
	repack_sigs = defaultdict(dict)
	for (proj, se), rows in by_se.items():
		acc = accs[proj]
		purpose, date = rows[0].purpose, rows[0].posting_date
		_doc(acc, "Stock Entry", se, date, "Stock Entry · " + (purpose or ""))
		if rows[0].ce:
			ce_date = next((c.posting_date for c in ce_rows if c.name == rows[0].ce), date)
			_doc(acc, "Conversion Entry", rows[0].ce, ce_date, "Conversion Entry")

		if not acc.toll and purpose in ("Material Transfer for Manufacture", "Material Transfer"):
			for r in rows:
				if items.cat(r.item_code) != "FF":
					continue
				lbs = to_lbs(r.qty, r.stock_uom)
				s = _strain(acc, r.item_code, items)
				if purpose == "Material Transfer for Manufacture":
					s.sent += lbs
					acc.ff_sent += lbs
					acc.ff_sent_value += flt(r.amount)
					acc.sent_dates.append(getdate(date))
					acc.costs["material"]["docs"][se] = "Stock Entry"
					_event(acc, date, "sent", lbs, "{q} lbs Fresh Frozen moved into production")
				elif _is_wip(acc, r.s_warehouse) and not _is_wip(acc, r.t_warehouse):
					s.returned += lbs
					acc.ff_returned += lbs
					acc.ff_returned_value += flt(r.amount)
					_event(acc, date, "returned", lbs, "{q} lbs Fresh Frozen returned from production")
			continue

		if purpose not in PRODUCTION:
			continue
		if purpose == "Repack":
			sig = tuple(sorted((r.item_code, round(flt(r.qty), 3), bool(r.t_warehouse)) for r in rows))
			if sig in repack_sigs[proj]:
				acc.repack_dups.append((se, repack_sigs[proj][sig]))
			else:
				repack_sigs[proj][sig] = se
		for b in _blocks(rows, single=purpose == "Manufacture"):
			cats_in = {items.cat(r.item_code) for r in b["in"]}
			cats_out = {items.cat(r.item_code) for r in b["out"]}
			if "FF" in cats_in and cats_out & {"HASH", "ROSIN"}:
				wash.append((acc, se, date, b))
			elif "HASH" in cats_in and "ROSIN" in cats_out:
				press.append((acc, se, date, b))
			elif "ROSIN" in cats_in and "ROSIN" in cats_out:
				regrade.append((acc, se, date, b))

	# washes (FF -> hash and/or rosin)
	for acc, se, date, b in wash:
		ff = [(r, to_lbs(r.qty, r.stock_uom)) for r in b["in"] if items.cat(r.item_code) == "FF"]
		ff_total = sum(l for _r, l in ff) or 1
		hash_out = [(r, to_g(r.qty, r.stock_uom)) for r in b["out"] if items.cat(r.item_code) == "HASH"]
		rosin_out = [(r, to_g(r.qty, r.stock_uom)) for r in b["out"] if items.cat(r.item_code) == "ROSIN"]
		h_total, r_total = sum(g for _r, g in hash_out), sum(g for _r, g in rosin_out)
		main_ff = max(ff, key=lambda x: x[1])[0].item_code
		for r, lbs in ff:
			share = lbs / ff_total
			s = _strain(acc, r.item_code, items)
			s.proc += lbs
			if not acc.toll and not _is_wip(acc, r.s_warehouse):
				# in-house FF consumed straight from stock, no transfer into WIP first
				s.sent += lbs
				acc.ff_sent += lbs
				acc.ff_sent_value += flt(r.amount)
				acc.sent_dates.append(getdate(date))
				acc.costs["material"]["docs"][se] = "Stock Entry"
			if h_total:
				s.hash += h_total * share
				s.hash_base += lbs
			if r_total:
				s.rosin += r_total * share
				s.rosin_direct += r_total * share
		for r, g in hash_out:
			acc.hash_origin.setdefault(r.item_code, main_ff)
		for r, g in rosin_out:
			acc.tiers[tier_of(items.group(r.item_code))] += g
		if h_total:
			_event(acc, date, "hash", h_total, "{q} g hash recorded")
		if r_total:
			_event(acc, date, "rosin", r_total, "{q} g rosin received")
		acc.output_dates.append(getdate(date))

	# presses (hash -> rosin), tied back to the FF the hash was washed from
	for acc, se, date, b in press:
		hin = [(r, to_g(r.qty, r.stock_uom)) for r in b["in"] if items.cat(r.item_code) == "HASH"]
		h_total = sum(g for _r, g in hin) or 1
		rosin_out = [(r, to_g(r.qty, r.stock_uom)) for r in b["out"] if items.cat(r.item_code) == "ROSIN"]
		r_total = sum(g for _r, g in rosin_out)
		for r, g in hin:
			key = acc.hash_origin.get(r.item_code) or r.item_code
			s = _strain(acc, key, items)
			if key == r.item_code:
				s.orphan = True
			s.hash_pressed += g
			s.rosin += r_total * g / h_total
		for r, g in rosin_out:
			acc.tiers[tier_of(items.group(r.item_code))] += g
		if r_total:
			_event(acc, date, "rosin", r_total, "{q} g rosin pressed from hash")
		acc.output_dates.append(getdate(date))

	# grading (raw rosin -> Tier 1 / 2 / 3): only moves grams between tiers
	for acc, se, date, b in regrade:
		for r in b["out"]:
			if items.cat(r.item_code) == "ROSIN":
				acc.tiers[tier_of(items.group(r.item_code))] += to_g(r.qty, r.stock_uom)
		for r in b["in"]:
			if items.cat(r.item_code) == "ROSIN":
				acc.tiers[tier_of(items.group(r.item_code))] -= to_g(r.qty, r.stock_uom)
		_event(acc, date, "graded", 0, "Rosin graded into tiers")

	# ---- lab recordings: hash per strain; a recording repeating an earlier one is skipped
	recs = defaultdict(lambda: defaultdict(list))
	rec_date = {}
	for l in lab:
		recs[l.project][l.name].append(l)
		rec_date[l.name] = getdate(l.creation)
	for proj, by_rec in recs.items():
		acc = accs[proj]
		seen = {}
		for name, lines in by_rec.items():
			sig = tuple(
				sorted((l.strain_name or "", flt(l.pounds_sent), flt(l.total_hash), flt(l.total_rosin)) for l in lines)
			)
			if sig in seen:
				acc.lab_dups.append((name, seen[sig]))
				_doc(acc, "Rosin Recording", name, rec_date[name], "Lab recording", "Duplicate")
				continue
			seen[sig] = name
			_doc(acc, "Rosin Recording", name, rec_date[name], "Lab recording")
			total_hash = 0.0
			for l in lines:
				s = _strain(acc, l.strain_name or _("Unspecified strain"), items)
				sent, ran = flt(l.pounds_sent), flt(l.pounds_ran)
				s.lab_lbs += min(sent, ran) if sent > 0 and ran > 0 else (sent or ran)
				s.lab_hash += flt(l.total_hash)
				total_hash += flt(l.total_hash)
			if total_hash:
				_event(acc, rec_date[name], "lab", total_hash, "Lab recorded {q} g hash (" + name + ")")

	_costs(accs, st, items)
	if with_docs:
		_attachments(accs)
	for acc in accs.values():
		_finish(acc, st)
	return accs


def _costs(accs, st, items):
	names = list(accs)
	pi = frappe.db.sql(
		"""select if(ifnull(pii.project, '') = '', pi.project, pii.project) as project, pi.name, pi.posting_date,
			pi.supplier, pi.status, pii.item_code, pii.item_name, pii.item_group, pii.expense_account,
			pii.base_net_amount as amount, ifnull(i.is_stock_item, 0) as is_stock_item
		from `tabPurchase Invoice Item` pii
		join `tabPurchase Invoice` pi on pi.name = pii.parent
		left join `tabItem` i on i.name = pii.item_code
		where pi.docstatus = 1
			and (pii.project in %(p)s or (ifnull(pii.project, '') = '' and pi.project in %(p)s))""",
		{"p": names},
		as_dict=1,
	)
	je = frappe.db.sql(
		"""select jea.project, je.name, je.posting_date, jea.account, a.root_type, a.account_type,
			jea.debit - jea.credit as amount
		from `tabJournal Entry Account` jea
		join `tabJournal Entry` je on je.name = jea.parent
		left join `tabAccount` a on a.name = jea.account
		where je.docstatus = 1 and jea.project in %(p)s""",
		{"p": names},
		as_dict=1,
	)
	for r in pi:
		acc = accs.get(r.project)
		if not acc:
			continue
		if r.is_stock_item or (r.expense_account or "").lower().startswith("stock received but not billed"):
			# the Fresh Frozen bill itself: already in the stock valuation
			_doc(acc, "Purchase Invoice", r.name, r.posting_date, "Purchase Invoice · Fresh Frozen", r.status)
			continue
		bucket = _bucket(r.expense_account, " ".join(filter(None, [r.item_name, r.item_group, r.expense_account])), st)
		acc.costs[bucket]["amount"] += flt(r.amount)
		acc.costs[bucket]["docs"][r.name] = "Purchase Invoice"
		if bucket == "toll":
			acc.has_toll_invoice = True
		_doc(acc, "Purchase Invoice", r.name, r.posting_date, "Purchase Invoice · " + COST_LABELS[bucket], r.status)
		_event(acc, r.posting_date, "inv:" + r.name, 0, "Invoice " + r.name + " posted (" + COST_LABELS[bucket].lower() + ")")
	for r in je:
		acc = accs.get(r.project)
		if not acc or not flt(r.amount):
			continue
		configured = r.account in st.labor_accounts or r.account in st.consumable_accounts
		if not configured and (
			r.root_type != "Expense"
			or r.account_type in ("Cost of Goods Sold", "Stock Adjustment")
			or "cost of goods sold" in (r.account or "").lower()
		):
			continue
		bucket = _bucket(r.account, r.account, st)
		acc.costs[bucket]["amount"] += flt(r.amount)
		acc.costs[bucket]["docs"][r.name] = "Journal Entry"
		if bucket == "toll":
			acc.has_toll_invoice = True
		_doc(acc, "Journal Entry", r.name, r.posting_date, "Journal Entry · " + COST_LABELS[bucket])


def _bucket(account, text, st):
	if account in st.labor_accounts:
		return "labor"
	if account in st.consumable_accounts:
		return "consumables"
	t = (text or "").lower()
	if re.search(r"\btest|coa\b|potency", t):
		return "testing"
	if re.search(r"freight|transport|shipping|courier|delivery", t):
		return "freight"
	if re.search(r"labou?r|wage|salar|payroll", t):
		return "labor"
	if re.search(r"consumable|supplies", t):
		return "consumables"
	if re.search(r"toll|processing|lab expense", t):
		return "toll"
	return "other"


def _attachments(accs):
	for f in frappe.get_all(
		"File",
		filters={"attached_to_doctype": "Project", "attached_to_name": ["in", list(accs)]},
		fields=["name", "file_name", "file_url", "attached_to_name", "creation"],
	):
		d = _doc(accs[f.attached_to_name], "File", f.name, getdate(f.creation), "Attachment", "Attached")
		d["label"] = f.file_name
		d["url"] = f.file_url


def _finish(acc, st):
	"""Totals, yields, status, dates and cost lines from the accumulated rows."""
	p = acc.p
	acc.costs["material"]["amount"] = acc.ff_sent_value - acc.ff_returned_value
	T = frappe._dict(ff_sent=acc.ff_sent, ff_returned=acc.ff_returned)
	for k in ("processed", "hash", "hash_base", "rosin", "rosin_h", "H", "ff_rosin", "hash_waiting"):
		T[k] = 0.0
	for s in acc.strains.values():
		use_lab = s.hash <= 0 and s.lab_hash > 0
		s.hash_g = s.hash if s.hash > 0 else s.lab_hash
		s.hash_base_lbs = s.hash_base if s.hash > 0 else (s.lab_lbs or s.proc)
		s.processed = max(s.proc, s.lab_lbs if use_lab else 0)
		# hash that has become rosin: pressed in our stock, or (partner) washed and pressed in one go
		s.H = s.hash_pressed + (s.hash_g if use_lab and s.rosin_direct > 0 else 0)
		s.hash_waiting = max(0.0, s.hash_g - s.H) if (s.hash_g and not (s.rosin_direct > 0 and use_lab)) else 0.0
		s.hash_pct = _pct(s.hash_g, s.hash_base_lbs * LB) if s.hash_base_lbs else None
		s.rosin_pct = _pct(s.rosin, s.H)
		s.overall_pct = _pct(s.rosin, s.processed * LB)
		if s.rosin > 0:
			s.status = "Received"
		elif s.hash_g > 0:
			s.status = "Hash only"
		else:
			s.status = "At partner" if acc.toll else "In production"
		T.processed += s.processed
		T.hash += s.hash_g
		if s.hash_g:
			T.hash_base += s.hash_base_lbs
		T.rosin += s.rosin
		if s.H > 0:
			# rosin % of hash only over strains whose hash is known; rosin with no hash record would inflate it
			T.rosin_h += s.rosin
		T.H += s.H
		if s.rosin:
			T.ff_rosin += s.processed
		T.hash_waiting += s.hash_waiting
	T.pending = max(0.0, T.ff_sent - T.ff_returned - T.processed)
	T.hash_pct = _pct(T.hash, T.hash_base * LB)
	T.rosin_pct = _pct(T.rosin_h, T.H)
	T.overall_pct = _pct(T.rosin, T.ff_rosin * LB)
	T.expected_rosin = T.pending * LB * acc.hash_t / 100 * acc.rosin_t / 100 + T.hash_waiting * acc.rosin_t / 100
	acc.T = T

	tiers = {t: max(0.0, acc.tiers.get(t, 0.0)) for t in TIERS}
	tier_total = sum(tiers.values())
	acc.tier_list = [{"label": t, "g": g, "pct": _pct(g, tier_total)} for t, g in tiers.items() if g > 0.0001]

	acc.dispatch = min(acc.sent_dates) if acc.sent_dates else (getdate(p.dispatch_date) if p.dispatch_date else None)
	if p.status == "Completed":
		acc.returned_on = getdate(p.returned_on) if p.returned_on else (max(acc.output_dates) if acc.output_dates else None)
		acc.page_status = "Completed"
	else:
		acc.returned_on = None
		if T.ff_sent <= 0 and T.hash <= 0 and T.rosin <= 0:
			acc.page_status = "Planned"
		elif T.hash <= 0 and T.rosin <= 0:
			acc.page_status = "At Partner" if acc.toll else "In Progress"
		else:
			acc.page_status = "In Progress"
	end = acc.returned_on or getdate(nowdate())
	acc.days = date_diff(end, acc.dispatch) if acc.dispatch else None

	total = sum(acc.costs[k]["amount"] for k in COST_ORDER)
	acc.cost_total = total
	acc.cost_material = acc.costs["material"]["amount"]


# ---------------------------------------------------------------- payloads


def _partner_key(p):
	return IN_HOUSE if p.ptype == IN_HOUSE else (p.partner or _("No partner set"))


def _row(acc, show_cost):
	p, T = acc.p, acc.T
	row = {
		"id": p.name,
		"name": p.project_name or p.name,
		"status": acc.page_status,
		"erp_status": p.status,
		"ptype": p.ptype,
		"partner": _partner_key(p),
		"company": p.company,
		"dispatch": str(acc.dispatch) if acc.dispatch else None,
		"returned": str(acc.returned_on) if acc.returned_on else None,
		"days": acc.days,
		"ff_sent": T.ff_sent,
		"ff_returned": T.ff_returned,
		"processed": T.processed,
		"pending": T.pending,
		"hash": T.hash,
		"hash_base": T.hash_base,
		"hash_pct": T.hash_pct,
		"rosin": T.rosin,
		"rosin_h": T.rosin_h,
		"hash_pressed": T.H,
		"rosin_pct": T.rosin_pct,
		"ff_rosin": T.ff_rosin,
		"overall_pct": T.overall_pct,
		"hash_waiting": T.hash_waiting,
		"expected_rosin": T.expected_rosin,
		"hash_target": acc.hash_t,
		"rosin_target": acc.rosin_t,
		"tiers": {t["label"]: t["g"] for t in acc.tier_list},
	}
	if show_cost:
		row.update(
			{
				"cost": acc.cost_total,
				"cost_material": acc.cost_material,
				"cost_lines": {k: acc.costs[k]["amount"] for k in COST_ORDER},
				"cpg": (acc.cost_total / T.rosin) if T.rosin else None,
			}
		)
	return row


def _search_blob(acc):
	p = acc.p
	parts = [p.name, p.project_name, p.metrc_tag, p.partner, p.partner_wh]
	for s in acc.strains.values():
		parts += [s.key, s.name]
	return " ".join(str(x) for x in parts if x).lower()


def _summary(partner=None, status=None, from_date=None, to_date=None, search=None):
	st = get_settings()
	show_cost = can_see_cost()
	projects = load_projects()
	accs = compute(projects, st)
	from_d = getdate(from_date) if from_date else get_quarter_start(nowdate())
	to_d = getdate(to_date) if to_date else getdate(nowdate())

	def in_period(acc):
		d = acc.dispatch or getdate(acc.p.creation)
		return from_d <= d <= to_d

	period = [a for a in accs.values() if in_period(a)]
	q = (search or "").strip().lower()
	partner = partner or "All"
	status = status or "All"

	def keep(a):
		if partner != "All" and _partner_key(a.p) != partner:
			return False
		if status == "Active" and a.page_status not in ("At Partner", "In Progress"):
			return False
		if status == "Completed" and a.page_status != "Completed":
			return False
		return not q or q in _search_blob(a)

	shown = sorted(
		[a for a in period if keep(a)],
		key=lambda a: (a.dispatch or getdate(a.p.creation), a.p.name),
		reverse=True,
	)
	rows = [_row(a, show_cost) for a in shown]

	K = defaultdict(float)
	for r in rows:
		for k in ("ff_sent", "pending", "hash", "hash_base", "rosin", "rosin_h", "hash_pressed", "ff_rosin"):
			K[k] += flt(r[k])
		if show_cost:
			K["cost"] += flt(r["cost"])
			if r["rosin"]:
				K["cost_out"] += flt(r["cost"])
				K["rosin_out"] += flt(r["rosin"])
	kpis = {
		"projects": len(rows),
		"ff_sent": K["ff_sent"],
		"pending": K["pending"],
		"hash": K["hash"],
		"hash_pct": _pct(K["hash"], K["hash_base"] * LB),
		"rosin": K["rosin"],
		"rosin_pct": _pct(K["rosin_h"], K["hash_pressed"]),
		"overall_pct": _pct(K["rosin"], K["ff_rosin"] * LB),
		"hash_target": st.hash_target,
		"rosin_target": st.rosin_target,
	}
	if show_cost:
		kpis["cost"] = K["cost"]
		kpis["cpg"] = (K["cost_out"] / K["rosin_out"]) if K["rosin_out"] else None

	# partner scorecard: every project in the period, whatever the partner / status / search filter
	sc = defaultdict(lambda: defaultdict(float))
	tat = defaultdict(list)
	for a in period:
		k = _partner_key(a.p)
		T = a.T
		g = sc[k]
		g["ff"] += T.ff_sent
		g["projects"] += 1
		g["hash"] += T.hash
		g["hash_base"] += T.hash_base
		g["rosin"] += T.rosin
		g["rosin_h"] += T.rosin_h
		g["H"] += T.H
		if a.page_status == "Completed":
			g["c_cost"] += a.cost_total
			g["c_rosin"] += T.rosin
			if a.days is not None and a.dispatch:
				tat[k].append(a.days)
	scorecard = []
	for k, g in sorted(sc.items(), key=lambda x: (x[0] == IN_HOUSE, x[0])):
		row = {
			"partner": k,
			"projects": int(g["projects"]),
			"ff": g["ff"],
			"hash_pct": _pct(g["hash"], g["hash_base"] * LB),
			"rosin_pct": _pct(g["rosin_h"], g["H"]),
			"tat": (sum(tat[k]) / len(tat[k])) if tat[k] else None,
		}
		if show_cost:
			row["cpg"] = (g["c_cost"] / g["c_rosin"]) if g["c_rosin"] else None
		scorecard.append(row)

	aging = [
		{"id": a.p.name, "name": a.p.project_name, "partner": _partner_key(a.p), "pending": a.T.pending, "days": a.days}
		for a in sorted(period, key=lambda a: -(a.days or 0))
		if a.page_status != "Completed" and a.T.pending > 0.01
	]

	return {
		"kpis": kpis,
		"projects": rows,
		"scorecard": scorecard,
		"aging": aging,
		"show_cost": show_cost,
		"from_date": str(from_d),
		"to_date": str(to_d),
		"pending_days": st.pending_days,
		"rosin_warn": st.rosin_warn,
		"generated": frappe.utils.now(),
	}


def _alerts(acc, st):
	p, T = acc.p, acc.T
	out = []

	def add(tag, sev, text):
		out.append({"tag": tag, "severity": sev, "text": text})

	if acc.toll and not p.partner_wh:
		add("Check", "warning", _("No Partner Warehouse is set on this project, so Fresh Frozen sent cannot be counted."))
	for s in sorted(acc.strains.values(), key=lambda s: s.name):
		if s.hash_pct is not None and s.hash_pct < acc.hash_t:
			add(
				"Yield",
				"warning",
				_("{0} washed at {1}% hash, below the {2}% target. Review its Fresh Frozen classification (SHO / BHO).").format(
					s.name, f"{s.hash_pct:.2f}", f"{acc.hash_t:g}"
				),
			)
		if s.rosin_pct is not None and s.rosin_pct < st.rosin_warn:
			add("Yield", "warning", _("{0} pressed at {1}% rosin, below the {2}% target.").format(s.name, f"{s.rosin_pct:.1f}", f"{acc.rosin_t:g}"))
	if T.pending > 0.01 and p.status != "Completed":
		days = acc.days or 0
		if acc.toll:
			text = _("{0} lbs of Fresh Frozen still at {1} — {2} days since dispatch.").format(f"{T.pending:,.0f}", p.partner, days)
		else:
			text = _("{0} lbs of Fresh Frozen moved into production but not yet washed — {1} days since dispatch.").format(
				f"{T.pending:,.0f}", days
			)
		add("Pending", "warning" if days > st.pending_days else "info", text)
	if T.hash_waiting > 0.5:
		add("Pending", "info", _("{0} g hash returned but not yet pressed or converted to rosin.").format(f"{T.hash_waiting:,.0f}"))
	for dup, orig in acc.lab_dups:
		add("Check", "warning", _("Batch {0} repeats the line items of {1}. Confirm with the lab before closing totals.").format(dup, orig))
	for dup, orig in acc.repack_dups:
		add("Check", "warning", _("Batch {0} repeats the line items of {1}. Confirm with the lab before closing totals.").format(dup, orig))
	if acc.toll and T.rosin > 0 and not acc.has_toll_invoice:
		add("Check", "warning", _("Rosin received but no toll fee invoice is linked to this project."))
	for code, wh, lbs in acc.wrong_wh:
		add("Check", "warning", _("{0} ({1} lbs) was sent to {2}, not to the partner warehouse.").format(code, f"{lbs:,.0f}", wh))
	for s in acc.strains.values():
		has_output = s.hash_g > 0 or s.rosin > 0
		if has_output and s.sent <= 0 and (s.orphan or s.proc > 0 or s.lab_hash > 0):
			add("Check", "warning", _("{0} has output but no matching Fresh Frozen sent.").format(s.name))
		elif s.sent > 0 and not has_output and p.status == "Completed":
			add("Check", "warning", _("{0} was sent but has no output recorded.").format(s.name))
	if p.status == "Completed" and T.pending > 0.01:
		add("Check", "info", _("Project is Completed but {0} lbs are not accounted for.").format(f"{T.pending:,.0f}"))
	out.sort(key=lambda a: a["severity"] != "warning")
	return out


def _detail(project):
	st = get_settings()
	show_cost = can_see_cost()
	projects = load_projects([project])
	if not projects:
		frappe.throw(_("Project {0} is not on the Project Tracker or you do not have access to it.").format(project))
	acc = compute(projects, st, with_docs=True)[project]
	p, T = acc.p, acc.T
	row = _row(acc, show_cost)

	strains = []
	for s in sorted(acc.strains.values(), key=lambda s: (-(s.sent or s.processed), s.name)):
		strains.append(
			{
				"key": s.key,
				"name": s.name,
				"lbs": s.sent or s.processed,
				"hash": s.hash_g,
				"hash_pct": s.hash_pct,
				"rosin": s.rosin,
				"rosin_pct": s.rosin_pct,
				"overall_pct": s.overall_pct,
				"status": s.status,
				"hash_from_lab": s.hash <= 0 < s.lab_hash,
			}
		)

	docs = sorted(acc.docs.values(), key=lambda d: (d["date"], d["doctype"], d["name"]))
	if not show_cost:
		docs = [d for d in docs if d["doctype"] not in ("Journal Entry",)]
	timeline = []
	for (date, kind), qty in sorted(acc.events.items()):
		if kind.startswith("inv:") and not show_cost:
			continue
		text = acc.event_text[(date, kind)]
		timeline.append({"date": date, "text": text.replace("{q}", f"{qty:,.0f}")})
	if acc.returned_on:
		timeline.append({"date": str(acc.returned_on), "text": _("Project marked Completed")})
	timeline.sort(key=lambda e: e["date"])

	out = {
		"row": row,
		"partner_warehouse": p.partner_wh,
		"supplier": p.partner if acc.toll else None,
		"company": p.company,
		"tiers": acc.tier_list,
		"strains": strains,
		"alerts": _alerts(acc, st),
		"docs": docs,
		"timeline": timeline,
		"show_cost": show_cost,
		"rosin_warn": st.rosin_warn,
	}
	if show_cost:
		lines = []
		for k in COST_ORDER:
			c = acc.costs[k]
			if abs(c["amount"]) < 0.005:
				continue
			label = COST_LABELS[k]
			if k == "toll" and acc.toll and p.partner:
				label = f"{label} — {p.partner}"
			lines.append(
				{
					"key": k,
					"label": label,
					"amount": c["amount"],
					"pct": _pct(c["amount"], acc.cost_total),
					"docs": [{"doctype": dt, "name": n} for n, dt in c["docs"].items()],
				}
			)
		out["costs"] = lines
		out["cost_total"] = acc.cost_total
		out["unit_costs"] = {
			"per_g_rosin": (acc.cost_total / T.rosin) if T.rosin else None,
			"per_g_hash": (acc.cost_total / T.hash) if T.hash else None,
			"per_lb_ff": (acc.cost_total / T.ff_sent) if T.ff_sent else None,
			"toll_per_g": ((acc.cost_total - acc.cost_material) / T.rosin) if T.rosin else None,
		}
	return out


# ---------------------------------------------------------------- cache + whitelisted API


def _cached(kind, args, fn, refresh=False):
	ver = frappe.cache().get_value(CACHE_VER_KEY) or "0"
	raw = json.dumps([kind, frappe.session.user, args], sort_keys=True, default=str)
	key = "project_tracker:" + str(ver) + ":" + hashlib.md5(raw.encode()).hexdigest()
	if not cint(refresh):
		hit = frappe.cache().get_value(key)
		if hit is not None:
			return hit
	val = fn()
	frappe.cache().set_value(key, val, expires_in_sec=CACHE_TTL)
	return val


@frappe.whitelist()
def get_tracker_summary(partner=None, status=None, from_date=None, to_date=None, search=None, refresh=0):
	_check_access()
	args = {"partner": partner, "status": status, "from_date": from_date, "to_date": to_date, "search": search}
	return _cached("summary", args, lambda: _summary(**args), refresh)


@frappe.whitelist()
def get_project_detail(project, refresh=0):
	_check_access()
	return _cached("detail", {"project": project}, lambda: _detail(project), refresh)


@frappe.whitelist()
def get_partners():
	_check_access()
	partners = frappe.get_all(
		"Supplier", filters={"custom_is_toll_partner": 1, "disabled": 0}, fields=["name", "supplier_name"], order_by="supplier_name"
	)
	return [{"value": p.name, "label": p.supplier_name or p.name} for p in partners] + [{"value": IN_HOUSE, "label": IN_HOUSE}]


@frappe.whitelist()
def export_tracker(partner=None, status=None, from_date=None, to_date=None, search=None):
	_check_access()
	from frappe.utils.xlsxutils import make_xlsx

	data = _summary(partner, status, from_date, to_date, search)
	show_cost = data["show_cost"]

	def r2(v):
		return None if v is None else round(flt(v), 2)

	header = [
		"Project", "Project Name", "Partner", "Processing Type", "Status", "Company", "Dispatch Date", "Return Completed On",
		"Days", "FF Sent (lbs)", "FF Returned Unprocessed (lbs)", "FF Processed (lbs)", "Still at Partner (lbs)",
		"Hash Received (g)", "Hash Yield %", "Hash Target %", "Rosin Received (g)", "Rosin Yield %", "Rosin Target %",
		"Overall FF to Rosin %", "Hash Waiting (g)", "Expected Rosin Still to Come (g)", "Tier 1 (g)", "Tier 2 (g)",
		"Tier 3 (g)", "Untiered (g)",
	]
	if show_cost:
		header += [COST_LABELS[k] for k in COST_ORDER] + ["Total Cost", "Cost per g Rosin", "Cost per g Hash", "Cost per lb FF"]
	rows = [header]
	for r in data["projects"]:
		line = [
			r["id"], r["name"], r["partner"], r["ptype"], r["status"], r["company"], r["dispatch"], r["returned"], r["days"],
			r2(r["ff_sent"]), r2(r["ff_returned"]), r2(r["processed"]), r2(r["pending"]), r2(r["hash"]), r2(r["hash_pct"]),
			r2(r["hash_target"]), r2(r["rosin"]), r2(r["rosin_pct"]), r2(r["rosin_target"]), r2(r["overall_pct"]),
			r2(r["hash_waiting"]), r2(r["expected_rosin"]),
		] + [r2(r["tiers"].get(t, 0)) for t in TIERS]
		if show_cost:
			line += [r2(r["cost_lines"][k]) for k in COST_ORDER]
			line += [
				r2(r["cost"]),
				r2(r["cpg"]),
				r2(r["cost"] / r["hash"]) if r["hash"] else None,
				r2(r["cost"] / r["ff_sent"]) if r["ff_sent"] else None,
			]
		rows.append(line)
	xlsx = make_xlsx(rows, "Project Tracker")
	frappe.response["filename"] = f"Project Tracker {data['from_date']} to {data['to_date']}.xlsx"
	frappe.response["filecontent"] = xlsx.getvalue()
	frappe.response["type"] = "binary"


def refresh_project_dates(project):
	"""Keep Project.custom_dispatch_date equal to the first Fresh Frozen sent for the project (hooks)."""
	projects = load_projects([project], apply_user_permissions=False)
	if not projects:
		return
	acc = compute(projects, get_settings())[project]
	first = min(acc.sent_dates) if acc.sent_dates else None
	if str(first or "") != str(projects[0].dispatch_date or ""):
		frappe.db.set_value("Project", project, "custom_dispatch_date", first, update_modified=False)
