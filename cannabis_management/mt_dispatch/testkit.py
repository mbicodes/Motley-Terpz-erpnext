"""A throwaway test setup for trying the whole flow by hand, on staging only.

TSBC Ranch becomes the test company: its real settings are saved to a JSON
file first, then pointed at three test channels with a two-person test team.
Two people, because separation of duties forbids one team row being both
fulfillment and approver.

	bench --site <site> execute cannabis_management.mt_dispatch.testkit.setup
	bench --site <site> execute cannabis_management.mt_dispatch.testkit.make_orders
	bench --site <site> execute cannabis_management.mt_dispatch.testkit.teardown

teardown() puts TSBC back exactly as it was, cancels every test order and
what hangs off it, archives the test channels and disables the test login.
Test orders carry PO numbers MT-DISPATCH-TEST-<n>. ERPNext refuses two
orders with the same PO number, so each gets its own.
"""

import json
import os
import secrets

import frappe
from frappe.utils import add_days, nowdate

COMPANY = "TSBC Ranch"
TESTER = "ali.zafar@alltechvirtual.com"
FULFILLER = "dispatch.test.fulfillment@alltechvirtual.com"
MARKER = "MT-DISPATCH-TEST"
CHANNELS = {
	"orders_channel": "mt-dispatch-test-orders",
	"dispatch_channel": "mt-dispatch-test-dispatch",
	"exceptions_channel": "mt-dispatch-test-exceptions",
}
CUSTOMER = "Greenmount, LLC (Cold Fire)"
ITEM = "FF-0255"
WAREHOUSE = "Hemet TSBC - TSBC"

# Short thresholds so a reminder can be watched arriving (T16).
TEST_RULES = [
	("Order Received", 30, "fulfillment", None),
	("Awaiting Conversion", 30, "fulfillment", None),
	("Order Prepared", 15, "compliance", None),
	("Delivery Note Ready", 30, "compliance", None),
	("Awaiting Release", 15, "approver", "paid"),
	("Awaiting Release", 30, "finance", "unpaid"),
	("Awaiting Release", 30, "exceptions", "unpaid"),
	("Released", 30, "dispatch", None),
]


def _backup_path():
	return frappe.get_site_path("private", "mt_dispatch_testkit_backup.json")


def _ensure_channel(name):
	from cannabis_management.mt_dispatch.slack import client

	try:
		return client.api("conversations.create", name=name, is_private=False)["channel"]["id"]
	except client.SlackError as e:
		if e.error != "name_taken":
			raise
	cursor = None
	while True:
		d = client.api_get("conversations.list", types="public_channel", exclude_archived="false", limit=1000, cursor=cursor)
		for ch in d["channels"]:
			if ch["name"] == name:
				if ch.get("is_archived"):
					client.api("conversations.unarchive", channel=ch["id"])
				if not ch.get("is_member"):
					client.api("conversations.join", channel=ch["id"])
				return ch["id"]
		cursor = (d.get("response_metadata") or {}).get("next_cursor")
		if not cursor:
			raise RuntimeError(f"Channel {name} is taken but could not be found.")


def _ensure_fulfiller():
	"""A second login for the fulfillment steps. Returns its password when
	the account is created or re-enabled, else None."""
	password = secrets.token_urlsafe(9)
	if frappe.db.exists("User", FULFILLER):
		user = frappe.get_doc("User", FULFILLER)
		user.enabled = 1
	else:
		user = frappe.get_doc(
			{
				"doctype": "User",
				"email": FULFILLER,
				"first_name": "Dispatch Test",
				"last_name": "Fulfillment",
				"send_welcome_email": 0,
				"user_type": "System User",
			}
		)
	user.new_password = password
	user.flags.ignore_password_policy = True
	for role in ("Fulfilment - Consolidated", "Sales User", "Stock User"):
		if role not in [r.role for r in user.roles]:
			user.append("roles", {"role": role})
	user.save(ignore_permissions=True)
	return password


def _grant_tester_roles():
	user = frappe.get_doc("User", TESTER)
	have = {r.role for r in user.roles}
	added = []
	for role in ("Compliance - Consolidated", "Dispatch Approver", "Dispatch Driver", "Sales User"):
		if role not in have:
			user.append("roles", {"role": role})
			added.append(role)
	if added:
		user.save(ignore_permissions=True)
	return added


def setup():
	frappe.only_for("System Manager") if frappe.session.user != "Administrator" else None
	cfg = frappe.get_doc("Dispatch Company Settings", COMPANY)

	path = _backup_path()
	if not os.path.exists(path):
		with open(path, "w") as f:
			json.dump({"settings": cfg.as_dict(), "tester_roles_added": []}, f, default=str)
	with open(path) as f:
		backup = json.load(f)

	channel_ids = {field: _ensure_channel(name) for field, name in CHANNELS.items()}
	password = _ensure_fulfiller()
	backup["tester_roles_added"] = sorted(set(backup.get("tester_roles_added", [])) | set(_grant_tester_roles()))
	backup["channel_ids"] = channel_ids
	with open(path, "w") as f:
		json.dump(backup, f, default=str)

	cfg.update(channel_ids)
	cfg.update(
		{
			"enabled": 1,
			"conversions_enabled": 1,
			"payment_gate_enabled": 1,
			"require_muid_on_dn": 0,
			"fulfillment_group_id": None,
			"drivers_group_id": None,
			"default_source_warehouse": WAREHOUSE,
			"default_target_warehouse": WAREHOUSE,
			"default_mode_of_payment": "Cash",
		}
	)
	cfg.set("team", [])
	cfg.append("team", {"user": FULFILLER, "fulfillment": 1})
	cfg.append("team", {"user": TESTER, "compliance": 1, "approver": 1, "finance": 1, "dispatch": 1, "can_override": 1})
	cfg.set("reminders", [])
	for stage, minutes, notify, only_when in TEST_RULES:
		cfg.append("reminders", {"stage": stage, "after_minutes": minutes, "notify": notify, "only_when": only_when})
	cfg.save(ignore_permissions=True)
	frappe.db.commit()

	print("Test setup ready for", COMPANY)
	print("Channels:", ", ".join(f"#{n} ({channel_ids[k]})" for k, n in CHANNELS.items()))
	print("Tester:", TESTER, "-> compliance, approver, finance, dispatch, can_override")
	print("Fulfillment login:", FULFILLER, "password:", password)
	return channel_ids


def _next_po():
	used = frappe.get_all("Sales Order", filters={"po_no": ["like", f"{MARKER}-%"]}, pluck="po_no")
	numbers = [int(p.rsplit("-", 1)[-1]) for p in used if p.rsplit("-", 1)[-1].isdigit()]
	return f"{MARKER}-{max(numbers, default=0) + 1}"


def _new_order(mode, rate, qty, note):
	so = frappe.new_doc("Sales Order")
	so.update(
		{
			"company": COMPANY,
			"customer": CUSTOMER,
			"transaction_date": nowdate(),
			"delivery_date": add_days(nowdate(), 2),
			"po_no": _next_po(),
			"set_warehouse": WAREHOUSE,
			"custom_mode_of_payment": mode,
			"custom_pickup_or_dropoff": "Dropoff",
			"custom_sales_order_type": "Presale",
			"custom_notes_for_logistics": note,
		}
	)
	so.append("items", {"item_code": ITEM, "qty": qty, "rate": rate, "warehouse": WAREHOUSE, "delivery_date": so.delivery_date})
	so.insert(ignore_permissions=True)
	return so.name


def make_orders():
	"""Three draft orders. Submitting one from the ERP starts its thread."""
	made = {
		"cod_full": _new_order("Cash On Delivery", 100, 10, "Test: COD, walk it end to end (T01, T07, T09, T11, T14)"),
		"cod_partial": _new_order("Cash On Delivery", 1486, 10, "Test: COD 14,860, pay 10,000 then 4,860 (T08, T09, T12)"),
		"terms": _new_order("Payment Terms", 100, 5, "Test: Payment Terms, no thread until credit approves (T02)"),
	}
	frappe.db.commit()
	for k, v in made.items():
		print(k, v)
	return made


def _cancel(doctype, name):
	doc = frappe.get_doc(doctype, name)
	if doc.docstatus == 1:
		doc.flags.ignore_links = True
		doc.cancel()
	elif doc.docstatus == 0:
		frappe.delete_doc(doctype, name, force=1, ignore_permissions=True)


def teardown():
	from cannabis_management.mt_dispatch.slack import client

	orders = frappe.get_all("Sales Order", filters={"po_no": ["like", f"{MARKER}-%"], "company": COMPANY}, pluck="name")
	for so in orders:
		for dn in frappe.get_all("Delivery Note Item", filters={"against_sales_order": so, "docstatus": ["<", 2]}, pluck="parent", distinct=True):
			_cancel("Delivery Note", dn)
		for pe in frappe.get_all("Payment Entry Reference", filters={"reference_name": so, "docstatus": 1}, pluck="parent", distinct=True):
			_cancel("Payment Entry", pe)
		for ce in frappe.get_all("Conversion Entry", filters={"sales_order": so, "docstatus": ["<", 2]}, pluck="name"):
			_cancel("Conversion Entry", ce)
		_cancel("Sales Order", so)
	frappe.db.commit()

	path = _backup_path()
	if os.path.exists(path):
		with open(path) as f:
			backup = json.load(f)
		saved = backup["settings"]
		cfg = frappe.get_doc("Dispatch Company Settings", COMPANY)
		for field in ("enabled", "orders_channel", "dispatch_channel", "exceptions_channel", "fulfillment_group_id",
					  "drivers_group_id", "conversions_enabled", "payment_gate_enabled", "require_muid_on_dn",
					  "default_source_warehouse", "default_target_warehouse", "default_mode_of_payment"):
			cfg.set(field, saved.get(field))
		cfg.set("team", [])
		for row in saved.get("team", []):
			cfg.append("team", {k: row.get(k) for k in ("user", "fulfillment", "compliance", "approver", "finance", "dispatch", "can_override", "backup_approver")})
		cfg.set("reminders", [])
		for row in saved.get("reminders", []):
			cfg.append("reminders", {k: row.get(k) for k in ("stage", "after_minutes", "notify", "only_when")})
		cfg.save(ignore_permissions=True)

		if backup.get("tester_roles_added"):
			user = frappe.get_doc("User", TESTER)
			user.set("roles", [r for r in user.roles if r.role not in backup["tester_roles_added"]])
			user.save(ignore_permissions=True)

		for channel in (backup.get("channel_ids") or {}).values():
			try:
				client.api("conversations.archive", channel=channel)
			except client.SlackError:
				pass
		os.remove(path)

	if frappe.db.exists("User", FULFILLER):
		frappe.db.set_value("User", FULFILLER, "enabled", 0)
	frappe.db.commit()
	print(f"Teardown done: {len(orders)} test order(s) cancelled, {COMPANY} settings restored.")
