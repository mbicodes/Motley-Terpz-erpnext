# Sales Operation Board -> calendars.
#
# Every deal date (Next Follow-up, Sample Date, Expected Close, Delivery / Pickup) becomes an all-day
# Frappe Event for the deal owner, each co-owner and every user in Settings "Also Show Every Deal Date
# To" (Muhammad sees the whole team's dates). Each Event belongs to its user (private, owner = user).
# When that user has connected Google (a Google Calendar doc with Push on and a refresh token) the
# event is put in their Google calendar too, and moved / removed when the deal changes.
#
# Google is called here, not through Frappe's Event hooks: those send a one-day all-day event with an
# empty date range, and they fire for any Event with a `google_calendar` link. Our Events never set
# that link; they keep the Google ids in google_calendar_id / google_calendar_event_id instead.
#
# Events carry sales_pipeline_key = "<deal>|<kind>|<user>" (custom field on Event).
# Triggers: deal save / delete and Settings save queue a sync; a cron every 10 minutes reconciles
# everything (picks up users who just connected Google, retries failures).

import frappe
from frappe import _
from frappe.utils import add_days, cint, escape_html, fmt_money, formatdate, getdate

from cannabis_management import sales_ops

EVENT = "Event"
KEY_FIELD = "sales_pipeline_key"
CALENDAR_NAME = "Motley Sales Pipeline"
SKIP_USERS = {"Administrator", "Guest", None, ""}

# key, deal field, label, Settings switch, ERP colour, Google colorId
KINDS = (
	("followup", "next_step_due", "Follow-up", "cal_followup", "#7c3aed", "3"),
	("sample", "sample_date", "Sample", "cal_sample", "#0891b2", "7"),
	("close", "expected_close", "Expected close", "cal_expected_close", "#16a34a", "10"),
	("delivery", "delivery_pickup", "Delivery / Pickup", "cal_delivery", "#ea580c", "6"),
)


# ---------- settings ----------


def config():
	doc = frappe.get_cached_doc(sales_ops.SETTINGS)
	return frappe._dict(
		enabled=cint(doc.get("calendar_sync")),
		kinds={k[0] for k in KINDS if cint(doc.get(k[3]))},
		watchers=[r.user for r in doc.get("calendar_watchers") or [] if r.user],
	)


# ---------- triggers ----------


def queue_deal(name):
	"""Called from the deal's on_update / on_trash: sync its events after the commit.
	No dedupe: a job that is already running may have read the deal before this change."""
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_test:
		return
	frappe.enqueue(
		"cannabis_management.sales_ops_calendar.sync_deals",
		queue="short",
		deals=[name],
		enqueue_after_commit=True,
	)


def queue_all():
	if frappe.flags.in_install or frappe.flags.in_migrate or frappe.flags.in_test:
		return
	frappe.enqueue(
		"cannabis_management.sales_ops_calendar.sync_all",
		queue="long",
		enqueue_after_commit=True,
		job_id="sales_pipeline_calendar::all",
		deduplicate=True,
	)


def sync_all():
	"""Cron: reconcile every deal's events (and remove events of deleted deals)."""
	sync_deals(None)


# ---------- what should exist ----------


def _deal_rows(deals=None):
	filters = {"name": ("in", deals)} if deals else {}
	fields = ["name", "account", "stage", "deal_owner", "deal_value", "product_line", "tier", "total_grams",
		"contact_name", "phone", "email", "next_steps", "status_detail"] + [k[1] for k in KINDS]
	rows = frappe.get_all(sales_ops.DEAL, filters=filters, fields=fields)
	co = {}
	if rows:
		for r in frappe.get_all(sales_ops.CO_OWNER, filters={"parenttype": sales_ops.DEAL, "parent": ("in", [x.name for x in rows])},
			fields=["parent", "user"], order_by="idx asc"):
			co.setdefault(r.parent, []).append(r.user)
	for r in rows:
		r.co_owners = co.get(r.name, [])
	return rows


def _stage(s, stage):
	return sales_ops.stage_info(s, stage) or sales_ops.status_info(s, stage) or frappe._dict(is_closed=0, is_won=0)


def _desired(d, s, cfg, enabled_users):
	"""{key: payload} of the events this deal should have."""
	if not cfg.enabled:
		return {}
	st = _stage(s, d.stage)
	if st.is_closed and not st.is_won:
		return {}  # lost: nothing more to do
	users = [d.deal_owner] + list(d.co_owners) + list(cfg.watchers)
	users = [u for u in dict.fromkeys(users) if u not in SKIP_USERS and u in enabled_users]
	if not users:
		return {}
	owner_name = sales_ops.owner_label(s, d.deal_owner) if d.deal_owner else _("Unassigned")
	out = {}
	for kind, field, label, _switch, colour, gcolour in KINDS:
		if kind not in cfg.kinds or not d.get(field):
			continue
		if st.is_won and kind != "delivery":
			continue  # won: only the delivery / pickup date still matters
		date = getdate(d.get(field))
		for user in users:
			subject = f"{_(label)}: {d.account}"
			if user != d.deal_owner:
				subject += f" · {owner_name}"
			text, html = _describe(d, s, label, date, owner_name)
			out[f"{d.name}|{kind}|{user}"] = frappe._dict(
				user=user, deal=d.name, kind=kind, date=date, subject=subject, text=text, html=html,
				colour=colour, gcolour=gcolour,
			)
	return out


def _describe(d, s, label, date, owner_name):
	lines = [
		(_("Deal"), f"{d.account} ({d.name})"),
		(_("Date"), f"{_(label)} · {formatdate(date)}"),
		(_("Stage"), d.stage),
		(_("Owner"), owner_name),
	]
	if d.co_owners:
		lines.append((_("Co-owners"), ", ".join(sales_ops.owner_label(s, u) for u in d.co_owners)))
	if d.deal_value:
		lines.append((_("Value"), fmt_money(d.deal_value, currency="USD")))
	product = " ".join(x for x in [d.product_line, d.tier] if x)
	if product:
		grams = f" · {frappe.utils.fmt_money(d.total_grams, precision=0)} g" if d.total_grams else ""
		lines.append((_("Product"), product + grams))
	contact = " · ".join(x for x in [d.contact_name, d.phone, d.email] if x)
	if contact:
		lines.append((_("Contact"), contact))
	if d.next_steps:
		lines.append((_("Next steps"), d.next_steps.strip()))
	if d.status_detail:
		lines.append((_("Status"), d.status_detail))
	link = sales_ops.deal_link(d.name)
	lines = [(k, v) for k, v in lines if v]
	text = "\n".join(f"{k}: {v}" for k, v in lines) + f"\n\n{_('Open on the Sales Operation Board')}: {link}"
	html = "".join(f"<p><b>{escape_html(k)}:</b> {escape_html(str(v))}</p>" for k, v in lines if v)
	html += f"<p><a href='{link}'>{escape_html(_('Open on the Sales Operation Board'))}</a></p>"
	return text, html


# ---------- sync ----------


def sync_deals(deals=None):
	"""Make the Events (and Google entries) of these deals match their dates. deals=None: all deals.
	Runs one at a time (file lock), so a deal job and the cron never both insert the same event."""
	if not frappe.db.exists("DocType", sales_ops.SETTINGS) or not frappe.db.has_column(EVENT, KEY_FIELD):
		return
	from frappe.utils.synchronization import filelock

	with filelock("sales_pipeline_calendar", timeout=300):
		# start a fresh transaction: a snapshot taken before the lock would not see the events the
		# previous run just committed, and we would insert them again (REPEATABLE READ)
		frappe.db.rollback()
		_sync(deals)


def _sync(deals):
	sales_ops.clear_settings_memo()
	s = sales_ops.get_settings()
	cfg = config()
	enabled_users = set(frappe.get_all("User", filters={"enabled": 1}, pluck="name"))

	rows = _deal_rows(deals)
	want = {}
	for d in rows:
		want.update(_desired(d, s, cfg, enabled_users))

	ev_filters = {KEY_FIELD: ("is", "set")}
	if deals:
		ev_filters["reference_docname"] = ("in", deals)
	have, extra = {}, []
	for e in frappe.get_all(EVENT, filters=ev_filters, order_by="creation asc",
		fields=["name", KEY_FIELD, "owner", "subject", "starts_on", "description", "color",
			"google_calendar_id", "google_calendar_event_id"]):
		if e[KEY_FIELD] in have:
			extra.append(e)  # duplicate of a key: keep the oldest
		else:
			have[e[KEY_FIELD]] = e

	google = _GoogleAccounts()
	stale = extra + [ev for key, ev in have.items() if key not in want]
	for ev in stale:
		google.delete(ev)
		frappe.delete_doc(EVENT, ev.name, ignore_permissions=True, force=True, delete_permanently=True)

	for key, p in want.items():
		ev = have.get(key)
		if not ev:
			ev = _insert_event(key, p)
		elif _differs(ev, p):
			_update_event(ev, p)
		google.push(ev, p)
	frappe.db.commit()


def _differs(ev, p):
	return (
		ev.owner != p.user
		or (ev.subject or "") != p.subject
		or getdate(ev.starts_on) != p.date
		or (ev.description or "") != p.html
		or (ev.color or "") != p.colour
	)


def _event_values(p):
	day = str(p.date)
	return {
		"subject": p.subject,
		"starts_on": f"{day} 00:00:00",
		"ends_on": f"{day} 23:59:59",
		"all_day": 1,
		"event_type": "Private",
		"event_category": "Event",
		"send_reminder": 0,  # Frappe's own daily event email would reach No Email owners
		"color": p.colour,
		"description": p.html,
		"reference_doctype": sales_ops.DEAL,
		"reference_docname": p.deal,
		"status": "Open",
	}


def _insert_event(key, p):
	doc = frappe.get_doc({"doctype": EVENT, KEY_FIELD: key, **_event_values(p)})
	doc.flags.ignore_permissions = True
	doc.insert()
	# insert always stamps the session user as owner; the event belongs to the person it is for
	frappe.db.set_value(EVENT, doc.name, "owner", p.user, update_modified=False)
	return frappe._dict(name=doc.name, owner=p.user, google_calendar_id=None, google_calendar_event_id=None, changed=True)


def _update_event(ev, p):
	doc = frappe.get_doc(EVENT, ev.name)
	doc.update(_event_values(p))
	doc.flags.ignore_permissions = True
	doc.save()
	if doc.owner != p.user:
		frappe.db.set_value(EVENT, doc.name, "owner", p.user, update_modified=False)
	ev.update(owner=p.user, changed=True)


# ---------- Google ----------


class _GoogleAccounts:
	"""One Google API client per user per run; failures are logged (at most every 6 hours per user)."""

	def __init__(self):
		self.cache = {}

	def account(self, user):
		if user in self.cache:
			return self.cache[user]
		self.cache[user] = None
		cal = connected_calendar(user)
		if cal:
			try:
				from frappe.integrations.doctype.google_calendar.google_calendar import get_google_calendar_object

				service, account = get_google_calendar_object(cal)
				if account.google_calendar_id:
					self.cache[user] = (service, account.google_calendar_id)
			except Exception:
				self.fail(user, "connect")
		return self.cache[user]

	def fail(self, user, what):
		key = f"sales_pipeline_calendar_err::{user}::{what}"
		if not frappe.cache.get_value(key):
			frappe.cache.set_value(key, 1, expires_in_sec=6 * 3600)
			frappe.log_error(title=f"Sales pipeline Google Calendar ({what}): {user}")

	def push(self, ev, p):
		acc = self.account(p.user)
		if not acc:
			return
		service, cal_id = acc
		from googleapiclient.errors import HttpError

		body = {
			"summary": p.subject,
			"description": p.text,
			"start": {"date": str(p.date)},
			"end": {"date": str(add_days(p.date, 1))},  # Google's end date is exclusive
			"transparency": "transparent",
			"colorId": p.gcolour,
			"source": {"title": "Sales Operation Board", "url": sales_ops.deal_link(p.deal)},
			"extendedProperties": {"private": {"salesPipelineKey": f"{p.deal}|{p.kind}|{p.user}"}},
		}
		same_cal = ev.google_calendar_id == cal_id and ev.google_calendar_event_id
		if same_cal and not ev.get("changed"):
			return
		try:
			if ev.google_calendar_event_id and not same_cal:
				self.delete(ev)  # was in another calendar (user re-connected)
				same_cal = False
			gid = None
			if same_cal:
				try:
					gid = service.events().update(calendarId=cal_id, eventId=ev.google_calendar_event_id, body=body).execute().get("id")
				except HttpError as e:
					if e.resp.status not in (404, 410):
						raise
			if not gid:
				gid = service.events().insert(calendarId=cal_id, body=body).execute().get("id")
			frappe.db.set_value(EVENT, ev.name, {"google_calendar_id": cal_id, "google_calendar_event_id": gid}, update_modified=False)
			ev.update(google_calendar_id=cal_id, google_calendar_event_id=gid)
		except Exception:
			self.fail(p.user, "push")

	def delete(self, ev):
		if not (ev.google_calendar_id and ev.google_calendar_event_id):
			return
		acc = self.account(ev.owner)
		if not acc:
			return
		service, _cal = acc
		from googleapiclient.errors import HttpError

		try:
			service.events().delete(calendarId=ev.google_calendar_id, eventId=ev.google_calendar_event_id).execute()
		except HttpError as e:
			if e.resp.status not in (404, 410):
				self.fail(ev.owner, "delete")
		except Exception:
			self.fail(ev.owner, "delete")


def connected_calendar(user):
	"""Name of the user's Google Calendar doc that can receive pipeline events (Push on + authorised)."""
	rows = frappe.get_all("Google Calendar", filters={"user": user, "enable": 1, "push_to_google_calendar": 1},
		fields=["name", "calendar_name"], order_by="creation asc")
	rows.sort(key=lambda r: r.calendar_name != CALENDAR_NAME)
	for r in rows:
		doc = frappe.get_doc("Google Calendar", r.name)
		if doc.get_password("refresh_token", raise_exception=False):
			return r.name
	return None


# ---------- board: connect Google ----------


@frappe.whitelist()
def google_status():
	user = frappe.session.user
	cal = connected_calendar(user)
	return {
		"connected": bool(cal),
		"calendar": cal,
		"settings_ready": bool(cint(frappe.db.get_single_value("Google Settings", "enable"))),
		"sync_on": cint(config().enabled),
		"events": frappe.db.count(EVENT, {KEY_FIELD: ("like", f"%|{user}"), "owner": user}),
	}


@frappe.whitelist()
def connect_google():
	"""Find or make the user's 'Motley Sales Pipeline' Google Calendar doc (push only, no pull) and
	return Google's sign-in URL for it."""
	user = frappe.session.user
	if user in SKIP_USERS:
		frappe.throw(_("Log in with your own user to connect Google Calendar."))
	name = frappe.db.get_value("Google Calendar", {"user": user, "calendar_name": CALENDAR_NAME}, "name")
	if not name:
		doc = frappe.get_doc({
			"doctype": "Google Calendar",
			"enable": 1,
			"user": user,
			"calendar_name": CALENDAR_NAME,
			"pull_from_google_calendar": 0,  # never copy personal Google events into the ERP
			"push_to_google_calendar": 1,
		})
		doc.insert()
		name = doc.name
	from frappe.integrations.doctype.google_calendar.google_calendar import authorize_access

	return {"calendar": name, **(authorize_access(name, reauthorize=True) or {})}


@frappe.whitelist()
def sync_mine():
	"""'Sync now' from the board: the user's own deals (a full run, cheap when nothing changed)."""
	queue_all()
	return True
