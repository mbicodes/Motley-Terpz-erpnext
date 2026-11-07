"""AR Collections board (page ar-collections). Every method checks AR Collection permission
first; balances come from the shared AR Accountability calculation in collections_engine."""

import json

import frappe
from frappe import _
from frappe.utils import add_days, cint, cstr, escape_html, flt, getdate, nowdate

from cannabis_management.credit_and_ar import collections_engine as engine

DOCTYPE = engine.DOCTYPE
COLLECTED_DAYS = 30
CARD_FIELDS = [
	"name",
	"customer",
	"customer_name",
	"ledger",
	"stage",
	"assigned_to",
	"creation",
	"next_action",
	"next_action_date",
	"google_sheet_link",
	"promise_date",
	"promise_amount",
	"promise_status",
	"promises_broken",
	"written_off",
	"collected_on",
	"plan_frequency",
	"payment_method",
	"plan_created_on",
	"consider_escalation",
]
MOVE_FIELDS = (
	"next_action",
	"next_action_date",
	"promise_date",
	"promise_amount",
	"dispute_reason",
	"dispute_details",
	"escalation_reason",
	"escalated_to",
)
UPDATE_FIELDS = (
	"assigned_to",
	"next_action",
	"next_action_date",
	"google_sheet_link",
	"contact",
	"contact_email",
	"contact_phone",
	"dispute_reason",
	"dispute_details",
	"escalation_reason",
	"escalated_to",
	"write_off_journal_entry",
)


def _require(ptype="read", doc=None):
	if not frappe.has_permission(DOCTYPE, ptype, doc):
		frappe.throw(_("You do not have permission to use AR Collections."), frappe.PermissionError)


def _get(name, ptype="write"):
	doc = frappe.get_doc(DOCTYPE, name)
	_require(ptype, doc)
	return doc


def _parse(values):
	if isinstance(values, str):
		values = json.loads(values or "{}")
	return frappe._dict(values or {})


# ---------------------------------------------------------------- cards


def _cards(filters=None, or_filters=None, snap=None):
	rows = frappe.get_all(DOCTYPE, filters=filters, or_filters=or_filters, fields=CARD_FIELDS, limit_page_length=0)
	if not rows:
		return []
	names = [r.name for r in rows]
	snap = snap if snap is not None else engine.live_snapshot()
	today = getdate(nowdate())
	b_thr, m_thr = engine.thresholds()

	insts = {}
	for i in frappe.get_all(
		"AR Collection Installment",
		filters={"parent": ["in", names], "parenttype": DOCTYPE},
		fields=["parent", "due_date", "amount", "paid_amount", "idx"],
		order_by="due_date asc, idx asc",
		limit_page_length=0,
	):
		insts.setdefault(i.parent, []).append(i)
	last_contact = {
		r.parent: r.d
		for r in frappe.db.sql(
			"""select parent, max(call_date) as d from `tabAR Collection Call`
			   where parenttype = %s and parent in %s group by parent""",
			(DOCTYPE, tuple(names)),
			as_dict=True,
		)
	}
	since = min(getdate(r.creation) for r in rows)
	customers = {r.customer for r in rows}
	payments = [p for p in engine.pe_payments(from_date=since) if p["customer"] in customers]
	m_start = engine.month_start(today)

	users = {r.assigned_to for r in rows if r.assigned_to}
	names_of = (
		{u.name: u.full_name for u in frappe.get_all("User", filters={"name": ["in", list(users)]}, fields=["name", "full_name"])}
		if users
		else {}
	)

	out = []
	for r in rows:
		s = engine.snapshot_for(r.customer, r.ledger, snap)
		created = getdate(r.creation)
		end = getdate(r.collected_on) if r.stage == engine.COLLECTED and r.collected_on else None
		pays = engine.payments_for(r.customer, r.ledger, from_date=created, to_date=end, payments=payments)
		plan_rows = []
		for i in insts.get(r.name, []):
			plan_rows.append(
				{
					"due": str(i.due_date),
					"amount": flt(i.amount, 2),
					"paid": flt(i.paid_amount, 2),
					"status": engine.installment_status(i.amount, i.paid_amount, i.due_date, today),
				}
			)
		missed = sum(1 for p in plan_rows if p["status"] == engine.INST_MISSED)
		open_card = r.stage != engine.COLLECTED
		out.append(
			{
				"name": r.name,
				"customer": r.customer,
				"customer_name": r.customer_name or r.customer,
				"ledger": r.ledger,
				"stage": r.stage,
				"assigned_to": r.assigned_to or "",
				"assigned_name": names_of.get(r.assigned_to) or r.assigned_to or "",
				"outstanding": s["outstanding"],
				"aging": s["aging"],
				"next_action": r.next_action or "",
				"next_action_date": cstr(r.next_action_date or ""),
				"last_contact": cstr(last_contact.get(r.name) or ""),
				"google_sheet_link": r.google_sheet_link or "",
				"promise_date": cstr(r.promise_date or ""),
				"promise_amount": flt(r.promise_amount, 2),
				"promise_status": r.promise_status or "",
				"promises_broken": cint(r.promises_broken),
				"written_off": cint(r.written_off),
				"collected_on": cstr(r.collected_on or ""),
				"collected_amount": flt(sum(p["amount"] for p in pays), 2),
				"month_collected": flt(sum(p["amount"] for p in pays if p["posting_date"] >= m_start), 2),
				"plan": (
					{"frequency": r.plan_frequency or "", "method": r.payment_method or "", "rows": plan_rows}
					if plan_rows
					else None
				),
				"missed": missed,
				"consider_escalation": 1
				if open_card
				and ((b_thr and cint(r.promises_broken) >= b_thr) or (m_thr and missed >= m_thr))
				else 0,
			}
		)
	return out


@frappe.whitelist()
def get_board(collected_all=0):
	_require("read")
	today = getdate(nowdate())
	cutoff = min(add_days(today, -COLLECTED_DAYS), engine.month_start(today))
	or_filters = [["stage", "!=", engine.COLLECTED]]
	if cint(collected_all):
		or_filters = None
	else:
		or_filters.append(["collected_on", ">=", cutoff])
	cards = _cards(or_filters=or_filters)
	s = engine.settings()
	return {
		"cards": cards,
		"stages": list(engine.STAGES),
		"today": str(today),
		"collected_days": COLLECTED_DAYS,
		"collected_all": cint(collected_all),
		"cc_email": s.cc_email or "",
		"default_assignee": s.default_assignee or "",
		"statement_print_format": s.statement_print_format or "",
		"can_write": frappe.has_permission(DOCTYPE, "write"),
		"can_create": frappe.has_permission(DOCTYPE, "create"),
		"can_payment": frappe.has_permission("Payment Entry", "create"),
		"users": _assignable_users(),
	}


@frappe.whitelist()
def get_cards(customer):
	_require("read")
	today = getdate(nowdate())
	cutoff = min(add_days(today, -COLLECTED_DAYS), engine.month_start(today))
	cards = _cards(filters={"customer": customer})
	return [c for c in cards if c["stage"] != engine.COLLECTED or (c["collected_on"] and getdate(c["collected_on"]) >= cutoff)]


def _card(name):
	cards = _cards(filters={"name": name})
	return cards[0] if cards else None


def _assignable_users():
	roles = ("System Manager", "Accounts Manager")
	users = frappe.db.sql(
		"""select distinct u.name, u.full_name from `tabUser` u
		   join `tabHas Role` hr on hr.parent = u.name and hr.parenttype = 'User'
		   where u.enabled = 1 and u.user_type = 'System User' and hr.role in %s
		     and u.name not in ('Administrator', 'Guest')
		   order by u.full_name""",
		(roles,),
		as_dict=True,
	)
	known = {u.name for u in users}
	extra = set(frappe.get_all(DOCTYPE, filters={"assigned_to": ["is", "set"]}, pluck="assigned_to", distinct=True))
	default = engine.settings().default_assignee
	if default:
		extra.add(default)
	for name in sorted(extra - known):
		full = frappe.db.get_value("User", name, "full_name")
		if full is not None:
			users.append(frappe._dict(name=name, full_name=full))
	return [{"value": u.name, "label": u.full_name or u.name} for u in users]


# ---------------------------------------------------------------- panel


@frappe.whitelist()
def get_collection(name):
	doc = _get(name, "read")
	today = getdate(nowdate())
	s = engine.snapshot_for(doc.customer, doc.ledger)
	comments = frappe.get_all(
		"Comment",
		filters={
			"reference_doctype": DOCTYPE,
			"reference_name": name,
			"comment_type": ["in", ["Comment", "Info"]],
		},
		fields=["name", "comment_type", "content", "owner", "creation"],
		order_by="creation desc",
		limit_page_length=200,
	)
	owners = {c.owner for c in comments} | {r.logged_by for r in doc.call_log if r.logged_by}
	full = (
		{u.name: u.full_name for u in frappe.get_all("User", filters={"name": ["in", list(owners)]}, fields=["name", "full_name"])}
		if owners
		else {}
	)
	files = frappe.get_all(
		"File",
		filters={"attached_to_doctype": DOCTYPE, "attached_to_name": name},
		fields=["name", "file_name", "file_url", "is_private"],
		order_by="creation desc",
	)
	contact_name = frappe.db.get_value("Contact", doc.contact, "full_name") if doc.contact else ""
	return {
		"name": doc.name,
		"customer": doc.customer,
		"customer_name": doc.customer_name or doc.customer,
		"ledger": doc.ledger,
		"stage": doc.stage,
		"assigned_to": doc.assigned_to or "",
		"outstanding": s["outstanding"],
		"aging": s["aging"],
		"invoices": s["invoices"],
		"next_action": doc.next_action or "",
		"next_action_date": cstr(doc.next_action_date or ""),
		"google_sheet_link": doc.google_sheet_link or "",
		"contact": doc.contact or "",
		"contact_name": contact_name or "",
		"contact_email": doc.contact_email or "",
		"contact_phone": doc.contact_phone or "",
		"promise_date": cstr(doc.promise_date or ""),
		"promise_amount": flt(doc.promise_amount, 2),
		"promise_status": doc.promise_status or "",
		"promises_broken": cint(doc.promises_broken),
		"dispute_reason": doc.dispute_reason or "",
		"dispute_details": doc.dispute_details or "",
		"escalation_reason": doc.escalation_reason or "",
		"escalated_to": doc.escalated_to or "",
		"written_off": cint(doc.written_off),
		"write_off_journal_entry": doc.write_off_journal_entry or "",
		"collected_on": cstr(doc.collected_on or ""),
		"plan": {
			"amount": flt(doc.plan_amount, 2),
			"frequency": doc.plan_frequency or "",
			"installments": cint(doc.plan_installments),
			"first_due_date": cstr(doc.plan_first_due_date or ""),
			"method": doc.payment_method or "",
			"instructions": doc.payment_instructions or "",
			"signed_document": doc.plan_signed_document or "",
			"created_on": cstr(doc.plan_created_on or ""),
			"rows": [
				{
					"due": cstr(r.due_date),
					"amount": flt(r.amount, 2),
					"paid": flt(r.paid_amount, 2),
					"paid_on": cstr(r.paid_on or ""),
					"status": engine.installment_status(r.amount, r.paid_amount, r.due_date, today),
					"notes": r.notes or "",
				}
				for r in sorted(doc.installments, key=lambda r: (getdate(r.due_date), r.idx))
			],
			"payments": [
				{"payment_entry": p.payment_entry, "posting_date": cstr(p.posting_date), "amount": flt(p.amount, 2)}
				for p in doc.payments
			],
		}
		if doc.installments
		else None,
		"calls": [
			{
				"date": cstr(r.call_date),
				"type": r.call_type or "",
				"contact_person": r.contact_person or "",
				"outcome": r.outcome or "",
				"notes": r.notes or "",
				"follow_up_date": cstr(r.follow_up_date or ""),
				"logged_by": full.get(r.logged_by) or r.logged_by or "",
			}
			for r in sorted(doc.call_log, key=lambda r: (cstr(r.call_date), r.idx), reverse=True)
		],
		"notes": [
			{
				"type": c.comment_type,
				"content": c.content,
				"by": full.get(c.owner) or c.owner,
				"at": cstr(c.creation),
			}
			for c in comments
		],
		"files": files,
		"can_write": frappe.has_permission(DOCTYPE, "write", doc),
	}


# ---------------------------------------------------------------- actions


@frappe.whitelist(methods=["POST"])
def move_stage(name, stage, values=None):
	doc = _get(name)
	v = _parse(values)
	if stage not in engine.STAGES:
		frappe.throw(_("{0} is not a valid stage.").format(stage))
	if stage == doc.stage:
		return _card(name)
	for f in MOVE_FIELDS:
		if f in v:
			doc.set(f, v.get(f) or None)
	if stage == engine.PROMISE and not v.get("next_action"):
		doc.next_action = doc.next_action or _("Confirm payment")
		doc.next_action_date = doc.promise_date
	doc.stage = stage
	note = cstr(v.get("note")).strip()
	if stage == engine.PROMISE and doc.promise_date and flt(doc.promise_amount) > 0:
		promise = _("{0} by {1}").format(
			engine.fmt_money(doc.promise_amount), frappe.format(doc.promise_date, {"fieldtype": "Date"})
		)
		note = f"{promise}. {note}" if note else promise
	elif stage == engine.DISPUTED and doc.dispute_reason:
		note = f"{_(doc.dispute_reason)}. {note}" if note else _(doc.dispute_reason)
	elif stage == engine.ESCALATED and doc.escalation_reason:
		note = f"{_(doc.escalation_reason)}. {note}" if note else _(doc.escalation_reason)
	doc.flags.move_note = note
	doc.save()
	return _card(name)


@frappe.whitelist(methods=["POST"])
def create_plan(name, values=None):
	doc = _get(name)
	v = _parse(values)
	amount = flt(v.get("plan_amount"), 2)
	count = cint(v.get("plan_installments"))
	frequency = v.get("plan_frequency") or "Monthly"
	first_due = v.get("plan_first_due_date")
	if amount <= 0 or count < 1 or not first_due:
		frappe.throw(_("Enter a plan amount, the number of installments and the first due date."))
	if frequency not in engine.FREQUENCIES:
		frappe.throw(_("{0} is not a valid frequency.").format(frequency))
	live = engine.snapshot_for(doc.customer, doc.ledger)["outstanding"]
	if amount > live + engine.EPS:
		frappe.throw(
			_("The plan amount cannot be more than the outstanding balance of {0}.").format(engine.fmt_money(live))
		)
	if doc.installments and any(flt(r.paid_amount) > 0 for r in doc.installments):
		frappe.throw(_("This collection already has a payment plan with payments applied. Edit the installments on the form instead."))

	from_stage = doc.stage
	doc.plan_amount = amount
	doc.plan_frequency = frequency
	doc.plan_installments = count
	doc.plan_first_due_date = getdate(first_due)
	doc.payment_method = v.get("payment_method") or None
	doc.payment_instructions = v.get("payment_instructions") or None
	doc.plan_signed_document = v.get("plan_signed_document") or None
	doc.plan_created_on = getdate(nowdate())
	doc.set("installments", [])
	doc.set("payments", [])
	for r in engine.split_schedule(amount, count, first_due, frequency):
		doc.append("installments", {"due_date": r["due_date"], "amount": r["amount"], "status": engine.INST_PENDING})
	doc.next_action = _("Collect first installment")
	doc.next_action_date = getdate(first_due)
	summary = _("{0} {1} installments totalling {2}, first due {3}{4}").format(
		count,
		_(frequency).lower(),
		engine.fmt_money(amount),
		frappe.format(getdate(first_due), {"fieldtype": "Date"}),
		(", " + _("by {0}").format(_(doc.payment_method))) if doc.payment_method else "",
	)
	note = cstr(v.get("note")).strip()
	if note:
		summary += ". " + note
	if doc.stage != engine.PLAN:
		doc.stage = engine.PLAN
		doc.flags.move_note = summary
	else:
		doc.flags.extra_note = _("Payment plan set up: {0}").format(summary)
	doc.save()
	if doc.plan_signed_document:
		_attach_file(doc.plan_signed_document, doc.name)
	engine.recalculate_plan(doc.name)
	return _card(name)


def _attach_file(file_url, name):
	f = frappe.db.get_value(
		"File", {"file_url": file_url, "attached_to_name": ["is", "not set"]}, "name", order_by="creation desc"
	)
	if f:
		frappe.db.set_value("File", f, {"attached_to_doctype": DOCTYPE, "attached_to_name": name})


@frappe.whitelist(methods=["POST"])
def log_call(name, values=None):
	doc = _get(name)
	v = _parse(values)
	if not v.get("outcome"):
		frappe.throw(_("Select the outcome of the call."))
	doc.append(
		"call_log",
		{
			"call_date": getdate(v.get("call_date") or nowdate()),
			"call_type": v.get("call_type") or "Call",
			"contact_person": v.get("contact_person"),
			"outcome": v.get("outcome"),
			"notes": v.get("notes"),
			"follow_up_date": v.get("follow_up_date") or None,
			"logged_by": frappe.session.user,
		},
	)
	if v.get("follow_up_date"):
		doc.next_action_date = getdate(v.get("follow_up_date"))
		doc.next_action = doc.next_action or _("Follow up")
	doc.save()
	return _card(name)


@frappe.whitelist(methods=["POST"])
def add_note(name, note):
	doc = _get(name)
	note = cstr(note).strip()
	if not note:
		frappe.throw(_("Enter a note."))
	doc.add_comment("Comment", escape_html(note).replace("\n", "<br>"))
	engine.publish_refresh(doc.customer)
	return get_collection(name)


@frappe.whitelist(methods=["POST"])
def new_collection(customer, ledger, assigned_to=None):
	_require("create")
	if ledger not in engine.LEDGERS:
		frappe.throw(_("Select New AR or Legacy AR."))
	if not frappe.db.exists("Customer", customer):
		frappe.throw(_("Customer {0} does not exist.").format(customer))
	if engine.open_collection(customer, ledger):
		frappe.throw(_("This customer already has an open collection."), title=_("Open collection exists"))
	live = engine.snapshot_for(customer, ledger)["outstanding"]
	doc = frappe.get_doc(
		{
			"doctype": DOCTYPE,
			"customer": customer,
			"ledger": ledger,
			"stage": engine.TO_COLLECT,
			"assigned_to": assigned_to or engine.settings().default_assignee,
			"outstanding_cached": live,
		}
	)
	doc.insert()
	return _card(doc.name)


@frappe.whitelist(methods=["POST"])
def update_collection(name, values=None):
	doc = _get(name)
	v = _parse(values)
	for f in UPDATE_FIELDS:
		if f in v:
			doc.set(f, v.get(f) or None)
	doc.save()
	return _card(name)


@frappe.whitelist(methods=["POST"])
def send_email(name, recipients, subject, message, attach_statement=0):
	doc = _get(name)
	_require("email", doc)
	from frappe.utils import split_emails, validate_email_address

	to = [e for e in split_emails(recipients or "") if validate_email_address(e)]
	if not to:
		frappe.throw(_("Enter a valid email address for the customer."), title=_("Email address"))
	subject = cstr(subject).strip()
	if not subject:
		frappe.throw(_("Enter a subject."))
	content = escape_html(cstr(message)).replace("\n", "<br>")
	print_format = engine.settings().statement_print_format if cint(attach_statement) else None

	from frappe.core.doctype.communication.email import make

	make(
		doctype=DOCTYPE,
		name=name,
		content=content,
		subject=subject,
		sent_or_received="Sent",
		recipients=", ".join(to),
		communication_medium="Email",
		send_email=True,
		print_format=print_format,
		print_letterhead=True,
	)

	doc.reload()
	doc.append(
		"call_log",
		{
			"call_date": getdate(nowdate()),
			"call_type": "Email",
			"contact_person": ", ".join(to),
			"outcome": "Email sent",
			"notes": subject + (" " + _("(statement attached)") if print_format else ""),
			"logged_by": frappe.session.user,
		},
	)
	if doc.stage == engine.TO_COLLECT:
		doc.stage = engine.REACHED_OUT
		doc.flags.move_note = _("email sent")
	doc.save()
	return _card(name)


@frappe.whitelist()
def make_payment_entry(name):
	"""A new, unsaved Payment Entry (Receive) for the customer, against the ledger's open invoices,
	prefilled with the next installment (or the outstanding). The accountant completes and submits it."""
	doc = _get(name, "read")
	if not frappe.has_permission("Payment Entry", "create"):
		frappe.throw(_("You do not have permission to create a Payment Entry."), frappe.PermissionError)
	s = engine.snapshot_for(doc.customer, doc.ledger)
	invoices = s["invoices"]
	if not invoices:
		frappe.throw(_("{0} has no open invoices in {1}.").format(doc.customer_name or doc.customer, doc.ledger))

	amount = s["outstanding"]
	today = getdate(nowdate())
	for r in sorted(doc.installments, key=lambda r: (getdate(r.due_date), r.idx)):
		if engine.installment_status(r.amount, r.paid_amount, r.due_date, today) != engine.INST_PAID:
			amount = flt(flt(r.amount) - flt(r.paid_amount), 2)
			break

	from erpnext.accounts.doctype.payment_entry.payment_entry import get_payment_entry

	first = invoices[0]
	company, account = frappe.db.get_value("Sales Invoice", first["name"], ["company", "debit_to"])
	try:
		pe = get_payment_entry("Sales Invoice", first["name"])
	except frappe.PermissionError:
		frappe.local.message_log = []
		frappe.throw(
			_("You do not have access to the {0} accounts, so the payment cannot be recorded from your account. "
			  "Ask a user with access to {0} to record it.").format(company),
			title=_("No access to {0}").format(company),
		)
	same = [
		i
		for i in invoices
		if i.get("company") == company and frappe.db.get_value("Sales Invoice", i["name"], "debit_to") == account
	]
	pe.set("references", [])
	left = amount
	for inv in same:
		if left <= engine.EPS:
			break
		alloc = min(flt(inv["outstanding"], 2), left)
		pe.append(
			"references",
			{
				"reference_doctype": "Sales Invoice",
				"reference_name": inv["name"],
				"due_date": inv.get("due_date") or None,
				"total_amount": flt(inv.get("invoiced"), 2),
				"outstanding_amount": flt(inv["outstanding"], 2),
				"allocated_amount": alloc,
				"exchange_rate": 1,
			},
		)
		left = flt(left - alloc, 2)
	paid = flt(amount - max(left, 0), 2)
	pe.paid_amount = paid
	pe.received_amount = paid
	pe.base_paid_amount = paid
	pe.base_received_amount = paid
	pe.total_allocated_amount = paid
	pe.base_total_allocated_amount = paid
	pe.unallocated_amount = 0
	pe.difference_amount = 0
	pe.remarks = _("Payment from {0} recorded from AR Collection {1}.").format(doc.customer_name or doc.customer, doc.name)
	return pe
