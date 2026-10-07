"""Who hears about a transition, and where.

The audience rules live here and are complete. The transport does not: until
Dispatch Global Settings holds a bot token, every call resolves its audience
and returns quietly. That keeps the flow fully usable from the ERP while the
Slack app is still being set up, and means the Slack layer only has to supply
posting -- not decide who to post to.
"""

import frappe

from cannabis_management.mt_dispatch import stages
from cannabis_management.mt_dispatch.settings import get_company_settings, users_with_flag

# action -> (team flags to tag, channel key or None)
AUDIENCE = {
	"enter_flow": ((stages.FULFILLMENT, stages.COMPLIANCE), "orders_channel"),
	"flag_conversion": ((stages.FULFILLMENT,), "orders_channel"),
	"conversions_done": ((), "orders_channel"),
	"conversion_progress": ((), "orders_channel"),
	"start_preparing": ((), "orders_channel"),
	"mark_prepared": ((stages.COMPLIANCE,), "orders_channel"),
	"create_conversion": ((), "orders_channel"),
	"create_delivery_note": ((), "orders_channel"),
	"upload_manifest": ((stages.APPROVER,), "orders_channel"),
	"record_payment": ((), "orders_channel"),
	"release": ((), "dispatch_channel"),
	"release_override": ((stages.FINANCE,), "exceptions_channel"),
	"mark_delivered": ((), "orders_channel"),
	"hold": ((stages.APPROVER,), "exceptions_channel"),
	"resume": ((stages.APPROVER,), "exceptions_channel"),
	"cancel": ((), "exceptions_channel"),
	"dn_cancelled": ((stages.APPROVER, stages.COMPLIANCE), "exceptions_channel"),
	"admin_set": ((), "orders_channel"),
}


def enqueue(method, **kwargs):
	"""Queue a notify job -- except under test.

	The guard has to sit here, where the job is queued. The job itself runs on
	a worker that knows nothing of the test run, so a check inside the job
	would let a test post to the real channels.
	"""
	if frappe.flags.in_test and not frappe.flags.mt_dispatch_allow_slack:
		return
	frappe.enqueue(method, **kwargs)


def slack_enabled():
	"""A bot token AND a transport to spend it through.

	Both halves matter. The token can be configured long before the Slack
	package is written -- it is needed to look up channel and user IDs during
	setup -- and without the second check every transition would then enqueue
	a job that dies on ImportError.
	"""
	if not transport_available():
		return False
	# Tests run against a copy of production with the real bot token. They
	# must never post to the real channels.
	if frappe.flags.in_test and not frappe.flags.mt_dispatch_allow_slack:
		return False
	try:
		settings = frappe.get_cached_doc("Dispatch Global Settings")
		return bool(settings.get_password("bot_token", raise_exception=False))
	except Exception:
		return False


def transport_available():
	"""True once the Slack posting layer exists on disk."""
	try:
		import cannabis_management.mt_dispatch.slack.post  # noqa: F401

		return True
	except ImportError:
		return False


def bot_token():
	"""The raw token, for setup lookups that run before the transport exists."""
	try:
		return frappe.get_cached_doc("Dispatch Global Settings").get_password(
			"bot_token", raise_exception=False
		)
	except Exception:
		return None


def audience_for(action, cfg):
	"""(users to tag, channel id) for one action at one company."""
	flags, channel_key = AUDIENCE.get(action, ((), "orders_channel"))
	users = []
	for flag in flags:
		for user in users_with_flag(cfg, flag):
			if user not in users:
				users.append(user)
	return users, (cfg.get(channel_key) if channel_key else None)


def on_transition(sales_order=None, action=None, **kwargs):
	if not sales_order or not frappe.db.exists("Sales Order", sales_order):
		return

	company = frappe.db.get_value("Sales Order", sales_order, "company")
	cfg = get_company_settings(company)
	if not cfg:
		return

	users, channel = audience_for(action, cfg)
	if not slack_enabled():
		return {"pending": True, "users": users, "channel": channel}

	from cannabis_management.mt_dispatch.slack import post

	return post.on_transition(sales_order, action, users, channel, **kwargs)


def on_event(sales_order=None, what=None, **kwargs):
	"""A thread note that moves no stage (see mt_dispatch/events.py)."""
	if not sales_order or not what or not frappe.db.exists("Sales Order", sales_order):
		return
	company = frappe.db.get_value("Sales Order", sales_order, "company")
	if not get_company_settings(company) or not slack_enabled():
		return

	from cannabis_management.mt_dispatch.slack import post

	return post.on_event(sales_order, what, **kwargs)


def on_payment_cleared(sales_order=None, **kwargs):
	"""A COD order that just became payable in full -- the approval DMs need
	to grow a Release button."""
	if not slack_enabled():
		return
	from cannabis_management.mt_dispatch.slack import post

	return post.on_payment_cleared(sales_order)
