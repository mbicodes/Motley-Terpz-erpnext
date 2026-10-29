import frappe

from cannabis_management.mt_dispatch import stages
from cannabis_management.mt_dispatch.settings import get_company_settings, users_with_flag

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
	"board_move": ((), "orders_channel"),
	"invoice_close": ((), "orders_channel"),
}


def enqueue(method, **kwargs):
	if frappe.flags.in_test and not frappe.flags.mt_dispatch_allow_slack:
		return
	frappe.enqueue(method, **kwargs)


def slack_enabled():
	if not transport_available():
		return False
	if frappe.flags.in_test and not frappe.flags.mt_dispatch_allow_slack:
		return False
	try:
		settings = frappe.get_cached_doc("Dispatch Global Settings")
		return bool(settings.get_password("bot_token", raise_exception=False))
	except Exception:
		return False


def transport_available():
	try:
		import cannabis_management.mt_dispatch.slack.post  # noqa: F401

		return True
	except ImportError:
		return False


def bot_token():
	try:
		return frappe.get_cached_doc("Dispatch Global Settings").get_password(
			"bot_token", raise_exception=False
		)
	except Exception:
		return None


def audience_for(action, cfg):
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
	if not sales_order or not what or not frappe.db.exists("Sales Order", sales_order):
		return
	company = frappe.db.get_value("Sales Order", sales_order, "company")
	if not get_company_settings(company) or not slack_enabled():
		return

	from cannabis_management.mt_dispatch.slack import post

	return post.on_event(sales_order, what, **kwargs)


def on_payment_cleared(sales_order=None, **kwargs):
	if not slack_enabled():
		return
	from cannabis_management.mt_dispatch.slack import post

	return post.on_payment_cleared(sales_order)
