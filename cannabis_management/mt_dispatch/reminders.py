"""The 15-minute reminder job and the morning digest.

Age is counted in working minutes only, in the company's own timezone and
work week. So an order that reaches Order Prepared at 16:50 on a Saturday,
with a Mon–Sat 08:00–17:00 week, has 10 working minutes by Monday 08:00 --
not a weekend's worth -- and nobody is reminded overnight or on a day off.

Each reminder stamps last_reminded_on on the order's latest stage log row,
and the same stage is only reminded again once another full threshold of
working time has passed.
"""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import frappe
from frappe.utils import get_datetime, get_system_timezone, get_time, now_datetime

from cannabis_management.mt_dispatch import stages
from cannabis_management.mt_dispatch.payments import payment_status
from cannabis_management.mt_dispatch.settings import get_company_settings, users_with_flag

DAY_NAMES = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]

# Section 9.2. Used for any company whose settings carry no reminder rows.
DEFAULT_RULES = [
	(stages.RECEIVED, 240, "fulfillment", None),
	(stages.AWAITING_CONVERSION, 480, "fulfillment", None),
	(stages.PREPARED, 120, "compliance", None),
	(stages.DN_READY, 240, "compliance", None),
	(stages.AWAITING_RELEASE, 120, "approver", "paid"),
	(stages.AWAITING_RELEASE, 480, "finance", "unpaid"),
	(stages.AWAITING_RELEASE, 480, "exceptions", "unpaid"),
	(stages.RELEASED, 480, "dispatch", None),
]

DIGEST_WINDOW_MINUTES = 15


# ── working time ─────────────────────────────────────────────────────────────


def company_tz(cfg):
	try:
		return ZoneInfo(cfg.get("timezone") or "America/Los_Angeles")
	except Exception:
		return ZoneInfo("America/Los_Angeles")


def to_local(dt, cfg):
	"""A naive system-time datetime as an aware datetime in the company's zone."""
	dt = get_datetime(dt)
	if dt.tzinfo is None:
		dt = dt.replace(tzinfo=ZoneInfo(get_system_timezone()))
	return dt.astimezone(company_tz(cfg))


def work_days(cfg):
	names = [d.strip()[:3].title() for d in (cfg.get("work_days") or "Mon,Tue,Wed,Thu,Fri,Sat").split(",")]
	return {DAY_NAMES.index(d) for d in names if d in DAY_NAMES}


def work_hours(cfg):
	return get_time(cfg.get("work_start") or "08:00:00"), get_time(cfg.get("work_end") or "17:00:00")


def in_work_hours(local_dt, cfg):
	start, end = work_hours(cfg)
	return local_dt.weekday() in work_days(cfg) and start <= local_dt.time() < end


def working_minutes(start, end, cfg):
	"""Working minutes between two system-time datetimes."""
	if not start or not end:
		return 0
	a, b = to_local(start, cfg), to_local(end, cfg)
	if b <= a:
		return 0
	tz = company_tz(cfg)
	days = work_days(cfg)
	ws, we = work_hours(cfg)
	total = 0.0
	day = a.date()
	while day <= b.date():
		if day.weekday() in days:
			open_at = datetime.combine(day, ws, tzinfo=tz)
			close_at = datetime.combine(day, we, tzinfo=tz)
			lo, hi = max(a, open_at), min(b, close_at)
			if hi > lo:
				total += (hi - lo).total_seconds() / 60
		day += timedelta(days=1)
	return int(total)


# ── rules ────────────────────────────────────────────────────────────────────


def rules(cfg):
	rows = [
		(r.stage, int(r.after_minutes or 0), r.notify, r.get("only_when") or None)
		for r in cfg.get("reminders") or []
	]
	rows = rows or DEFAULT_RULES
	# A zero or negative threshold would fire every fifteen minutes. Treat it as off.
	return [r for r in rows if r[1] > 0 and r[0] and r[2]]


def is_paid(so, cfg):
	applies, _paid, _required, short = payment_status(so, cfg)
	return not (applies and short)


def applicable_rules(so, cfg, stage):
	out = []
	for rule_stage, minutes, notify, only_when in rules(cfg):
		if rule_stage != stage:
			continue
		if only_when:
			paid = is_paid(so, cfg)
			if (only_when == "paid") != paid:
				continue
		out.append((minutes, notify))
	return out


def last_log(so_name):
	rows = frappe.get_all(
		"Dispatch Stage Log",
		filters={"parent": so_name, "parenttype": "Sales Order"},
		fields=["name", "at", "to_stage", "last_reminded_on"],
		order_by="idx desc",
		limit=1,
	)
	return rows[0] if rows else None


def open_orders(cfg):
	open_stages = [s for s in stages.ALL_STAGES if s not in stages.TERMINAL_STAGES and s != stages.ON_HOLD]
	return frappe.get_all(
		"Sales Order",
		filters={"company": cfg.company, "docstatus": 1, "custom_logistic_status": ["in", open_stages]},
		fields=["name", "custom_logistic_status as stage"],
	)


def due_rules(so, cfg, stage, log, now):
	"""The rules whose threshold has passed and that were not already sent."""
	age = working_minutes(log.at, now, cfg)
	since_reminder = working_minutes(log.last_reminded_on, now, cfg) if log.last_reminded_on else None
	due = []
	for minutes, notify in applicable_rules(so, cfg, stage):
		if age < minutes:
			continue
		if since_reminder is not None and since_reminder < minutes:
			continue
		due.append((minutes, notify))
	return age, due


def overdue_orders(cfg, now=None):
	"""(order, stage, working minutes) for everything past its first threshold."""
	now = now or now_datetime()
	out = []
	for row in open_orders(cfg):
		log = last_log(row.name)
		if not log or not log.at:
			continue
		so = frappe.get_doc("Sales Order", row.name)
		thresholds = [m for m, _n in applicable_rules(so, cfg, row.stage)]
		if not thresholds:
			continue
		age = working_minutes(log.at, now, cfg)
		if age >= min(thresholds):
			out.append((row.name, row.stage, age))
	return sorted(out, key=lambda r: -r[2])


# ── the job ──────────────────────────────────────────────────────────────────


def run():
	from cannabis_management.mt_dispatch.notify import slack_enabled

	if not slack_enabled():
		return
	for name in frappe.get_all("Dispatch Company Settings", filters={"enabled": 1}, pluck="name"):
		cfg = get_company_settings(name)
		if not cfg:
			continue
		try:
			run_company(cfg)
			frappe.db.commit()
		except Exception:
			frappe.db.rollback()
			frappe.log_error(f"MT Dispatch reminders failed for {name}", "MT Dispatch Reminders")


def run_company(cfg, now=None, sender=None):
	"""One company's reminders. `sender` is injectable for tests."""
	now = now or now_datetime()
	local = to_local(now, cfg)
	if not in_work_hours(local, cfg):
		return []

	send = sender or send_reminder
	sent = []
	maybe_digest(cfg, local, now)
	for row in open_orders(cfg):
		log = last_log(row.name)
		if not log or not log.at or log.to_stage != row.stage:
			continue
		so = frappe.get_doc("Sales Order", row.name)
		age, due = due_rules(so, cfg, row.stage, log, now)
		if not due:
			continue
		for _minutes, notify in due:
			send(so, cfg, row.stage, notify, age)
		frappe.db.set_value("Dispatch Stage Log", log.name, "last_reminded_on", now, update_modified=False)
		sent.append((row.name, [n for _m, n in due]))
	return sent


def _age_text(minutes):
	return f"{minutes // 60}h {minutes % 60}m" if minutes >= 60 else f"{minutes}m"


def send_reminder(so, cfg, stage, notify, age):
	from cannabis_management.mt_dispatch.slack import blocks, client, post

	line = f":alarm_clock: *{so.name}* has been at *{stage}* for {_age_text(age)} of working time."

	if notify == "exceptions":
		_, paid, required, short = payment_status(so, cfg)
		post.post_exception(
			so, cfg, "Stuck COD",
			f"At {stage} for {_age_text(age)} of working time. Paid {blocks.money(paid, so)} of "
			f"{blocks.money(required, so)}, {blocks.money(short, so)} outstanding.",
		)
		return

	if notify == "dispatch":
		rows = post.message_rows(so.name, post.DISPATCH_POST)
		if rows:
			client.post(rows[-1].channel, line, thread_ts=rows[-1].ts)
		elif cfg.dispatch_channel:
			client.post(cfg.dispatch_channel, line)
		return

	if notify == "fulfillment":
		mentions = post.fulfillment_mentions(cfg)
	else:
		mentions = post.mention_users(users_with_flag(cfg, notify))
	text, blks = blocks.stage_update(so, cfg, line, mentions)
	post.reply(so, cfg, text, blks)

	if notify == "approver":
		backups = [row.user for row in cfg.team or [] if row.backup_approver]
		if backups:
			post.send_approval_dms(so, cfg, users=backups)


# ── digest ───────────────────────────────────────────────────────────────────


def maybe_digest(cfg, local, now):
	digest_at = get_time(cfg.get("digest_time") or "08:40:00")
	start = datetime.combine(local.date(), digest_at, tzinfo=local.tzinfo)
	if not (start <= local < start + timedelta(minutes=DIGEST_WINDOW_MINUTES)):
		return False
	key = f"mt_dispatch:digest:{cfg.company}:{local.date().isoformat()}"
	if frappe.cache.get_value(key):
		return False
	frappe.cache.set_value(key, 1, expires_in_sec=26 * 3600)
	post_digest(cfg, now)
	return True


def post_digest(cfg, now=None):
	from cannabis_management.mt_dispatch.slack import blocks, client

	if not cfg.orders_channel:
		return
	rows = frappe.get_all(
		"Sales Order",
		filters={"company": cfg.company, "docstatus": 1, "custom_logistic_status": ["in", stages.ALL_STAGES]},
		fields=["custom_logistic_status as stage", "count(name) as n"],
		group_by="custom_logistic_status",
	)
	counts = {r.stage: r.n for r in rows}
	overdue = overdue_orders(cfg, now)
	lines = [
		f"{blocks.STAGE_EMOJI.get(s, '')} {s}: *{counts.get(s, 0)}*"
		for s in stages.ALL_STAGES
		if s not in stages.TERMINAL_STAGES
	]
	text = f"Good morning. {cfg.company} dispatch board"
	blks = [blocks.section(f"*{text}*\n" + "\n".join(lines))]
	if overdue:
		blks.append(
			blocks.section(
				f":alarm_clock: *{len(overdue)} overdue*\n"
				+ "\n".join(f"{n} · {s} · {_age_text(m)}" for n, s, m in overdue[:20])
			)
		)
	client.post(cfg.orders_channel, text, blks)
