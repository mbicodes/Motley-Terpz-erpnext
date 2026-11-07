"""AR Collections: shared logic for the AR Collection DocType, the ar-collections board, the
Payment Entry / Communication hooks and the daily job.

Outstanding, aging and tier always come from the AR Accountability calculation
(ar_weekly_review._build_rows); payments are counted per ledger with the same rule
(the ledger of the invoice a payment is allocated against)."""

import frappe
from frappe import _
from frappe.utils import add_days, add_months, cint, flt, get_first_day, getdate, nowdate

DOCTYPE = "AR Collection"
SETTINGS = "AR Collections Settings"
REALTIME_EVENT = "ar_collections_refresh"

TO_COLLECT = "To Collect"
REACHED_OUT = "Reached Out"
PROMISE = "Promise to Pay"
PLAN = "Payment Plan"
DISPUTED = "Disputed"
ESCALATED = "Escalated"
COLLECTED = "Collected"
STAGES = (TO_COLLECT, REACHED_OUT, PROMISE, PLAN, DISPUTED, ESCALATED, COLLECTED)

LEDGERS = ("New AR", "Legacy AR")
FREQUENCIES = ("Weekly", "Bi-weekly", "Monthly")

INST_PENDING = "Pending"
INST_PARTIAL = "Partially Paid"
INST_PAID = "Paid"
INST_MISSED = "Missed"

EPS = 0.005


# ---------------------------------------------------------------- settings


def settings():
	return frappe.get_cached_doc(SETTINGS)


def thresholds():
	s = settings()
	return cint(s.escalation_hint_after_broken_promises), cint(s.escalation_hint_after_missed_installments)


# ---------------------------------------------------------------- AR snapshot (shared calculation)


def _ar():
	from cannabis_management.credit_and_ar.page.ar_weekly_review import ar_weekly_review

	return ar_weekly_review


def ledger_of(posting_date):
	return _ar()._ledger_for(posting_date)


def aging_index(due_date, today=None):
	days = (getdate(today or nowdate()) - getdate(due_date)).days if due_date else 0
	if days <= 30:
		return 0
	if days <= 60:
		return 1
	if days <= 90:
		return 2
	return 3


def live_snapshot(ledger=None):
	"""{(customer, ledger): {outstanding, overdue, tier, aging[4], invoices[]}} from the
	AR Accountability rows (same function the AR Accountability page uses)."""
	ar = _ar()
	today = getdate(nowdate())
	out = {}
	for r in ar._build_rows(ledger or "all"):
		key = (r["customer"], r["ledger"])
		s = out.setdefault(
			key,
			{"outstanding": 0.0, "overdue": 0.0, "tier": "upcoming", "aging": [0.0, 0.0, 0.0, 0.0], "invoices": []},
		)
		s["outstanding"] += flt(r["amount"])
		if r["portion"] == "overdue":
			s["overdue"] += flt(r["amount"])
		if ar.TIER_RANK[r["tier"]] > ar.TIER_RANK[s["tier"]]:
			s["tier"] = r["tier"]
		for inv in r["invoices"]:
			s["aging"][aging_index(inv["due_date"], today)] += flt(inv["outstanding"])
			s["invoices"].append(inv)
	for s in out.values():
		s["outstanding"] = flt(s["outstanding"], 2)
		s["overdue"] = flt(s["overdue"], 2)
		s["aging"] = [flt(a, 2) for a in s["aging"]]
		s["invoices"].sort(key=lambda i: (i["due_date"] or "9999-12-31", i["name"]))
	return out


def empty_snapshot():
	return {"outstanding": 0.0, "overdue": 0.0, "tier": "", "aging": [0.0, 0.0, 0.0, 0.0], "invoices": []}


def snapshot_for(customer, ledger, snap=None):
	snap = snap if snap is not None else live_snapshot(ledger)
	return snap.get((customer, ledger)) or empty_snapshot()


# ---------------------------------------------------------------- payments


def pe_payments(customer=None, from_date=None):
	"""Submitted Payment Entries applied to Sales Invoices, one row per entry per customer per
	ledger: {payment_entry, posting_date, customer, ledger, amount}. Read from the Payment Ledger,
	so cancelled entries and later reconciliations are counted correctly."""
	cond = [
		"ple.delinked = 0",
		"ple.against_voucher_type = 'Sales Invoice'",
		"ple.voucher_type = 'Payment Entry'",
		"si.docstatus = 1",
	]
	params = {}
	if customer:
		cond.append("si.customer = %(customer)s")
		params["customer"] = customer
	if from_date:
		cond.append("ple.posting_date >= %(from_date)s")
		params["from_date"] = getdate(from_date)
	rows = frappe.db.sql(
		f"""
		select ple.voucher_no as payment_entry, ple.posting_date, si.customer,
		       si.posting_date as invoice_date, -sum(ple.amount) as amount
		from `tabPayment Ledger Entry` ple
		join `tabSales Invoice` si on si.name = ple.against_voucher_no
		where {" and ".join(cond)}
		group by ple.voucher_no, ple.posting_date, si.name
		""",
		params,
		as_dict=True,
	)
	grouped = {}
	for r in rows:
		key = (r.payment_entry, r.customer, ledger_of(r.invoice_date))
		g = grouped.setdefault(
			key,
			{
				"payment_entry": r.payment_entry,
				"posting_date": getdate(r.posting_date),
				"customer": r.customer,
				"ledger": key[2],
				"amount": 0.0,
			},
		)
		g["amount"] += flt(r.amount)
	out = [g for g in grouped.values() if flt(g["amount"], 2) > EPS]
	for g in out:
		g["amount"] = flt(g["amount"], 2)
	out.sort(key=lambda g: (g["posting_date"], g["payment_entry"]))
	return out


def payments_for(customer, ledger, from_date=None, to_date=None, payments=None):
	payments = payments if payments is not None else pe_payments(customer, from_date)
	f = getdate(from_date) if from_date else None
	t = getdate(to_date) if to_date else None
	return [
		p
		for p in payments
		if p["customer"] == customer
		and p["ledger"] == ledger
		and (not f or p["posting_date"] >= f)
		and (not t or p["posting_date"] <= t)
	]


# ---------------------------------------------------------------- payment plan


def split_schedule(amount, count, first_due, frequency):
	"""Equal installments rounded to cents; the remainder goes on the last one."""
	count = cint(count)
	cents = int(round(flt(amount) * 100))
	if count < 1 or cents <= 0:
		return []
	base = cents // count
	rows = []
	for i in range(count):
		c = cents - base * (count - 1) if i == count - 1 else base
		rows.append({"due_date": due_date_for(first_due, frequency, i), "amount": c / 100.0})
	return rows


def due_date_for(first_due, frequency, i):
	first_due = getdate(first_due)
	if frequency == "Weekly":
		return add_days(first_due, 7 * i)
	if frequency == "Bi-weekly":
		return add_days(first_due, 14 * i)
	return add_months(first_due, i)


def installment_status(amount, paid, due_date, today=None):
	amount, paid = flt(amount, 2), flt(paid, 2)
	if amount <= EPS or paid >= amount - EPS:
		return INST_PAID
	if due_date and getdate(due_date) < getdate(today or nowdate()):
		return INST_MISSED
	if paid > EPS:
		return INST_PARTIAL
	return INST_PENDING


def has_plan(doc):
	return bool(doc.get("installments"))


def recalculate_plan(collection, snap=None, payments=None, save=True):
	"""Apply the customer's Payment Entries (same ledger, on/after plan_created_on) to the
	installments oldest due date first, trim the plan if the outstanding fell below the unpaid
	plan balance, and close the collection when nothing is owed."""
	doc = frappe.get_doc(DOCTYPE, collection) if isinstance(collection, str) else collection
	before = _plan_state(doc)
	live = snapshot_for(doc.customer, doc.ledger, snap)["outstanding"]
	today = getdate(nowdate())

	if has_plan(doc):
		start = doc.plan_created_on or getdate(doc.creation)
		pays = payments_for(doc.customer, doc.ledger, from_date=start, payments=payments)
		doc.set(
			"payments",
			[{"payment_entry": p["payment_entry"], "posting_date": p["posting_date"], "amount": p["amount"]} for p in pays],
		)

		rows = sorted(doc.installments, key=lambda r: (getdate(r.due_date), r.idx))
		for r in rows:
			r.paid_amount = 0
			r.paid_on = None
		for p in pays:
			left = flt(p["amount"], 2)
			for r in rows:
				if left <= EPS:
					break
				room = flt(flt(r.amount, 2) - flt(r.paid_amount, 2), 2)
				if room <= EPS:
					continue
				take = min(room, left)
				r.paid_amount = flt(flt(r.paid_amount) + take, 2)
				r.paid_on = p["posting_date"]
				left = flt(left - take, 2)

		unpaid = flt(sum(flt(r.amount) - flt(r.paid_amount) for r in rows), 2)
		if live < unpaid - EPS:
			diff = flt(unpaid - live, 2)
			for r in reversed(rows):
				if diff <= EPS:
					break
				room = flt(flt(r.amount) - flt(r.paid_amount), 2)
				take = min(room, diff)
				if take > EPS:
					r.amount = flt(flt(r.amount) - take, 2)
					diff = flt(diff - take, 2)
			rows = [r for r in rows if flt(r.amount, 2) > EPS]
			doc.plan_amount = flt(sum(flt(r.amount) for r in rows), 2)
			doc.flags.plan_trim_note = _(
				"Payment plan reduced by {0}: the outstanding balance of {1} is below the unpaid plan balance of {2}."
			).format(fmt_money(unpaid - live), fmt_money(live), fmt_money(unpaid))

		for i, r in enumerate(rows, 1):
			r.idx = i
			r.status = installment_status(r.amount, r.paid_amount, r.due_date, today)
		doc.set("installments", rows)

	doc.outstanding_cached = live
	_auto_collect(doc, live)
	_set_escalation_hint(doc)

	changed = _plan_state(doc) != before
	if save and changed:
		doc.flags.ignore_permissions = True
		doc.save()
	return changed


def _plan_state(doc):
	return frappe.as_json(
		{
			"i": [(str(r.due_date), flt(r.amount, 2), flt(r.paid_amount, 2), str(r.paid_on or ""), r.status) for r in doc.get("installments") or []],
			"p": [(r.payment_entry, str(r.posting_date), flt(r.amount, 2)) for r in doc.get("payments") or []],
			"o": flt(doc.outstanding_cached, 2),
			"s": doc.stage,
			"pa": flt(doc.plan_amount, 2),
			"ce": cint(doc.consider_escalation),
		}
	)


def _auto_collect(doc, live):
	if live <= EPS and doc.stage != COLLECTED:
		doc.flags.from_stage = doc.stage
		doc.flags.move_note = _("balance written off") if doc.write_off_journal_entry else _("paid in full")
		doc.flags.live_outstanding = live
		doc.stage = COLLECTED


def missed_count(doc, today=None):
	return sum(
		1
		for r in doc.get("installments") or []
		if installment_status(r.amount, r.paid_amount, r.due_date, today) == INST_MISSED
	)


def _set_escalation_hint(doc):
	b, m = thresholds()
	doc.consider_escalation = 1 if (
		doc.stage != COLLECTED
		and ((b and cint(doc.promises_broken) >= b) or (m and missed_count(doc) >= m))
	) else 0


def refresh_collection(collection, snap=None, payments=None):
	"""Recalculate one open collection: plan (if any), cached outstanding, escalation hint,
	auto-close at zero."""
	doc = frappe.get_doc(DOCTYPE, collection) if isinstance(collection, str) else collection
	if doc.stage == COLLECTED:
		return False
	return recalculate_plan(doc, snap=snap, payments=payments)


def refresh_customer_collections(customer):
	"""Background job after a Payment Entry is submitted or cancelled."""
	names = frappe.get_all(DOCTYPE, filters={"customer": customer, "stage": ["!=", COLLECTED]}, pluck="name")
	if not names:
		return
	snap = live_snapshot()
	payments = pe_payments(customer)
	for name in names:
		try:
			refresh_collection(name, snap=snap, payments=payments)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("AR Collections: payment recalculation failed for {0}").format(name))
	publish_refresh(customer)


# ---------------------------------------------------------------- creation / assignment / contact


def open_collection(customer, ledger, exclude=None):
	filters = {"customer": customer, "ledger": ledger, "stage": ["!=", COLLECTED]}
	if exclude:
		filters["name"] = ["!=", exclude]
	return frappe.db.get_value(DOCTYPE, filters, "name")


def default_contact(customer):
	"""{contact, contact_email, contact_phone} from the customer's primary contact, else the
	first linked contact, else the customer's own email / phone."""
	out = {"contact": None, "contact_email": None, "contact_phone": None}
	contact = frappe.db.get_value("Customer", customer, "customer_primary_contact")
	if not contact:
		rows = frappe.db.sql(
			"""select c.name from `tabContact` c
			   join `tabDynamic Link` dl on dl.parent = c.name and dl.parenttype = 'Contact'
			   where dl.link_doctype = 'Customer' and dl.link_name = %s
			   order by c.is_primary_contact desc, c.modified desc limit 1""",
			customer,
		)
		contact = rows[0][0] if rows else None
	if contact:
		c = frappe.db.get_value("Contact", contact, ["email_id", "mobile_no", "phone"], as_dict=True) or {}
		out.update(contact=contact, contact_email=c.get("email_id"), contact_phone=c.get("mobile_no") or c.get("phone"))
	if not out["contact_email"] or not out["contact_phone"]:
		cust = frappe.db.get_value("Customer", customer, ["email_id", "mobile_no"], as_dict=True) or {}
		out["contact_email"] = out["contact_email"] or cust.get("email_id")
		out["contact_phone"] = out["contact_phone"] or cust.get("mobile_no")
	return out


def contact_details(contact):
	if not contact:
		return {}
	c = frappe.db.get_value("Contact", contact, ["email_id", "mobile_no", "phone", "full_name"], as_dict=True) or {}
	return {"contact_email": c.get("email_id"), "contact_phone": c.get("mobile_no") or c.get("phone"), "contact_name": c.get("full_name")}


def sync_assignment(doc, notify=True):
	"""One open ToDo per collection, for assigned_to. notify=False creates it silently (daily job)."""
	user = doc.assigned_to
	open_todos = frappe.get_all(
		"ToDo",
		filters={"reference_type": DOCTYPE, "reference_name": doc.name, "status": "Open"},
		fields=["name", "allocated_to"],
	)
	for t in open_todos:
		if t.allocated_to != user:
			todo = frappe.get_doc("ToDo", t.name)
			todo.status = "Cancelled"
			todo.flags.ignore_permissions = True
			todo.save()
	if not user or any(t.allocated_to == user for t in open_todos):
		return
	description = _("Collect the outstanding balance from {0} ({1}).").format(doc.customer_name or doc.customer, doc.ledger)
	if notify:
		from frappe.desk.form.assign_to import add

		add(
			{"assign_to": [user], "doctype": DOCTYPE, "name": doc.name, "description": description},
			ignore_permissions=True,
		)
	else:
		frappe.get_doc(
			{
				"doctype": "ToDo",
				"allocated_to": user,
				"reference_type": DOCTYPE,
				"reference_name": doc.name,
				"description": description,
				"assigned_by": "Administrator",
			}
		).insert(ignore_permissions=True)


def close_assignments(doc):
	for name in frappe.get_all(
		"ToDo", filters={"reference_type": DOCTYPE, "reference_name": doc.name, "status": "Open"}, pluck="name"
	):
		todo = frappe.get_doc("ToDo", name)
		todo.status = "Closed"
		todo.flags.ignore_permissions = True
		todo.save()


# ---------------------------------------------------------------- daily job


def ar_collections_daily():
	"""06:00: create missing collections, recalculate plans, check promises, escalation hints,
	close zero balances, refresh cached outstanding."""
	snap = live_snapshot()
	today = getdate(nowdate())
	s = settings()

	# 1. one open collection per customer + ledger with overdue outstanding
	open_keys = {
		(r.customer, r.ledger)
		for r in frappe.get_all(DOCTYPE, filters={"stage": ["!=", COLLECTED]}, fields=["customer", "ledger"])
	}
	for (customer, ledger), info in sorted(snap.items()):
		if info["overdue"] <= EPS or (customer, ledger) in open_keys:
			continue
		try:
			doc = frappe.get_doc(
				{
					"doctype": DOCTYPE,
					"customer": customer,
					"ledger": ledger,
					"stage": TO_COLLECT,
					"assigned_to": s.default_assignee,
					"outstanding_cached": info["outstanding"],
				}
			)
			doc.flags.silent_assignment = True
			doc.flags.no_realtime = True
			doc.insert(ignore_permissions=True)
			open_keys.add((customer, ledger))
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("AR Collections: could not create a collection for {0}").format(customer))

	# 2-6. every open collection
	opens = frappe.get_all(DOCTYPE, filters={"stage": ["!=", COLLECTED]}, fields=["name", "creation"])
	since = min((getdate(o.creation) for o in opens), default=today)
	plan_since = frappe.db.sql(
		f"select min(plan_created_on) from `tab{DOCTYPE}` where stage != %s", COLLECTED
	)[0][0]
	if plan_since:
		since = min(since, getdate(plan_since))
	payments = pe_payments(from_date=since)
	for o in opens:
		try:
			doc = frappe.get_doc(DOCTYPE, o.name)
			_check_promise(doc, payments, today)
			doc.flags.no_realtime = True
			if not recalculate_plan(doc, snap=snap, payments=payments, save=False) and not doc.flags.promise_changed:
				continue
			doc.flags.ignore_permissions = True
			doc.save()
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(title=_("AR Collections: daily update failed for {0}").format(o.name))


def _check_promise(doc, payments, today):
	if doc.stage != PROMISE or doc.promise_status != "Open" or not doc.promise_date:
		return
	since = doc.promise_made_on or getdate(doc.creation)
	paid = flt(sum(p["amount"] for p in payments_for(doc.customer, doc.ledger, from_date=since, payments=payments)), 2)
	if paid >= flt(doc.promise_amount, 2) - EPS:
		doc.promise_status = "Kept"
		doc.flags.promise_changed = True
		doc.flags.extra_note = _("Promise kept: {0} received against the promised {1}.").format(
			fmt_money(paid), fmt_money(doc.promise_amount)
		)
	elif getdate(doc.promise_date) < today:
		doc.promise_status = "Broken"
		doc.promises_broken = cint(doc.promises_broken) + 1
		doc.flags.promise_changed = True
		doc.flags.from_stage = doc.stage
		doc.flags.move_note = _("promise of {0} due {1} was not kept ({2} received)").format(
			fmt_money(doc.promise_amount), frappe.format(doc.promise_date, {"fieldtype": "Date"}), fmt_money(paid)
		)
		doc.stage = REACHED_OUT


# ---------------------------------------------------------------- realtime + hooks


def publish_refresh(customer):
	if not customer:
		return
	from frappe.realtime import get_doctype_room

	frappe.publish_realtime(
		REALTIME_EVENT, {"customer": customer}, room=get_doctype_room(DOCTYPE), after_commit=True
	)


def _customers_of(doc):
	if doc.doctype == "Sales Invoice":
		return {doc.customer} if doc.customer else set()
	if doc.doctype == "Payment Entry":
		return {doc.party} if doc.party_type == "Customer" and doc.party else set()
	if doc.doctype == "Journal Entry":
		return {a.party for a in doc.get("accounts") or [] if a.party_type == "Customer" and a.party}
	return set()


def realtime_on_change(doc, method=None):
	"""Sales Invoice / Journal Entry submit and cancel: tell open boards to reload the card.
	Message only, never blocks the document."""
	try:
		for customer in _customers_of(doc):
			publish_refresh(customer)
	except Exception:
		frappe.log_error(title=_("AR Collections: realtime refresh failed for {0}").format(doc.name))


def payment_entry_on_change(doc, method=None):
	"""Payment Entry submit and cancel: recalculate the customer's open collections after commit.
	Errors go to the Error Log and never block the Payment Entry."""
	try:
		if doc.party_type != "Customer" or not doc.party:
			return
		publish_refresh(doc.party)
		if frappe.db.exists(DOCTYPE, {"customer": doc.party, "stage": ["!=", COLLECTED]}):
			frappe.enqueue(
				"cannabis_management.credit_and_ar.collections_engine.refresh_customer_collections",
				queue="short",
				customer=doc.party,
				enqueue_after_commit=True,
			)
	except Exception:
		frappe.log_error(title=_("AR Collections: Payment Entry hook failed for {0}").format(doc.name))


def _emails(*values):
	from frappe.utils import parse_addr, split_emails

	out = set()
	for v in values:
		for e in split_emails(v or ""):
			e = (parse_addr(e)[1] or e).strip().lower()
			if e:
				out.add(e)
	return out


def _is_collection_email(doc, direction):
	return (
		doc.reference_doctype == DOCTYPE
		and (doc.communication_type or "Communication") == "Communication"
		and doc.sent_or_received == direction
	)


def communication_before_insert(doc, method=None):
	"""Copy the collections person on every email sent from an AR Collection, and only those."""
	if not _is_collection_email(doc, "Sent"):
		return
	cc_email = (settings().cc_email or "").strip()
	if not cc_email or cc_email.lower() in _emails(doc.recipients, doc.cc):
		return
	doc.cc = f"{doc.cc}, {cc_email}" if doc.cc else cc_email


def communication_after_insert(doc, method=None):
	"""A customer reply threaded to an AR Collection: Call Log row + notify the collections person."""
	if not _is_collection_email(doc, "Received") or not doc.reference_name:
		return
	try:
		coll = frappe.get_doc(DOCTYPE, doc.reference_name)
		coll.append(
			"call_log",
			{
				"call_date": getdate(doc.communication_date or nowdate()),
				"call_type": "Email",
				"contact_person": doc.sender_full_name or doc.sender,
				"outcome": "Reply received",
				"notes": doc.subject,
				"logged_by": "Administrator",
			},
		)
		coll.flags.ignore_permissions = True
		coll.save()

		cc_email = (settings().cc_email or "").strip()
		if cc_email and cc_email.lower() not in _emails(doc.recipients, doc.cc, doc.bcc):
			subject = _("Customer reply on collection {0}: {1}").format(coll.customer_name or coll.customer, doc.subject or "")
			user = frappe.db.get_value("User", {"email": cc_email, "enabled": 1}, "name")
			if user:
				from frappe.desk.doctype.notification_log.notification_log import enqueue_create_notification

				enqueue_create_notification(
					user,
					{
						"type": "Alert",
						"document_type": DOCTYPE,
						"document_name": coll.name,
						"subject": subject,
						"from_user": "Administrator",
						"email_content": doc.content,
					},
				)
			else:
				frappe.sendmail(
					recipients=[cc_email],
					subject=subject,
					message=doc.content,
					reference_doctype=DOCTYPE,
					reference_name=coll.name,
				)
	except Exception:
		frappe.log_error(title=_("AR Collections: could not record the reply {0}").format(doc.name))


# ---------------------------------------------------------------- misc


def fmt_money(v):
	return frappe.utils.fmt_money(flt(v, 2), currency="USD")


def month_start(today=None):
	return get_first_day(getdate(today or nowdate()))
