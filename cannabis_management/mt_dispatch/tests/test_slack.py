"""Slack layer tests: request verification, button rules, modal validation,
the reminder clock, and how a click reaches transition().

None of these talk to Slack. The Web API client is patched wherever a code
path would reach it, and notify.slack_enabled() is off in test mode, so a test
run never posts to the real channels.

Test IDs map to the acceptance table in the developer spec.
"""

import json
from datetime import datetime
from unittest import mock
from zoneinfo import ZoneInfo

import frappe
from frappe.tests.utils import FrappeTestCase
from frappe.utils import get_system_timezone

from cannabis_management.mt_dispatch import reminders, stages
from cannabis_management.mt_dispatch.gates import GateError
from cannabis_management.mt_dispatch.slack import blocks, handlers, verify

LA = ZoneInfo("America/Los_Angeles")


class FakeDoc:
	"""Stands in for a Sales Order. frappe._dict won't do: its .items is the
	dict method, where a Document's is the child rows."""

	def __init__(self, **values):
		self.__dict__.update(values)

	def __getattr__(self, name):
		return None

	def get(self, key, default=None):
		return self.__dict__.get(key, default)


def cfg(**overrides):
	values = {
		"company": "Master Touch Manufacturing",
		"enabled": 1,
		"conversions_enabled": 1,
		"payment_gate_enabled": 1,
		"gate_internal_customers": 0,
		"require_muid_on_dn": 0,
		"payment_tolerance": 0.01,
		"timezone": "America/Los_Angeles",
		"work_start": "08:00:00",
		"work_end": "17:00:00",
		"work_days": "Mon,Tue,Wed,Thu,Fri,Sat",
		"digest_time": "08:40:00",
		"orders_channel": "C1",
		"dispatch_channel": "C2",
		"exceptions_channel": "C3",
		"fulfillment_group_id": None,
		"drivers_group_id": None,
		"reminders": [],
		"team": [],
	}
	values.update(overrides)
	return frappe._dict(values)


def order(stage, mode=stages.COD, total=14860, advance=0, **overrides):
	values = {
		"name": "SAL-ORD-TEST-99999",
		"company": "Master Touch Manufacturing",
		"customer": "Test Customer",
		"customer_name": "Test Customer",
		"custom_logistic_status": stage,
		"custom_mode_of_payment": mode,
		"grand_total": total,
		"rounded_total": total,
		"disable_rounded_total": 0,
		"advance_paid": advance,
		"is_internal_customer": 0,
		"currency": "USD",
		"items": [],
		"sales_team": [],
		"owner": "Administrator",
		"total_qty": 0,
		"delivery_date": None,
	}
	values.update(overrides)
	return FakeDoc(**values)


def system_naive(y, m, d, hh, mm=0):
	"""A wall-clock time in Los Angeles, as the naive system-time datetime
	the stage log stores."""
	aware = datetime(y, m, d, hh, mm, tzinfo=LA)
	return aware.astimezone(ZoneInfo(get_system_timezone())).replace(tzinfo=None)


class TestVerify(FrappeTestCase):
	SECRET = "8f742231b10e8888abcd99yyyzzz85a5"
	BODY = b"token=x&team_id=T1&command=%2Forder&text=00563"

	def signed(self, ts, body=None):
		return verify.expected_signature(self.SECRET, ts, body or self.BODY)

	def test_valid_request_passes(self):
		ts = 1_800_000_000
		verify.check_signature(self.SECRET, str(ts), self.BODY, self.signed(ts), now=ts + 10)

	def test_t17_replay_after_six_minutes_is_rejected(self):
		ts = 1_800_000_000
		with self.assertRaises(verify.SlackAuthError):
			verify.check_signature(self.SECRET, str(ts), self.BODY, self.signed(ts), now=ts + 360)

	def test_t17_changed_body_is_rejected(self):
		ts = 1_800_000_000
		with self.assertRaises(verify.SlackAuthError):
			verify.check_signature(self.SECRET, str(ts), self.BODY + b"x", self.signed(ts), now=ts)

	def test_missing_secret_rejects_everything(self):
		ts = 1_800_000_000
		with self.assertRaises(verify.SlackAuthError):
			verify.check_signature("", str(ts), self.BODY, self.signed(ts), now=ts)

	def test_other_workspace_is_rejected(self):
		with mock.patch.object(verify, "_globals", return_value=frappe._dict(slack_team_id="T_OURS")):
			verify.check_team("T_OURS")
			with self.assertRaises(verify.SlackAuthError):
				verify.check_team("T_THEIRS")


class TestButtons(FrappeTestCase):
	def ids(self, so, c=None):
		return blocks.stage_action_ids(so, c or cfg())

	def test_received_offers_conversion_only_when_enabled(self):
		self.assertEqual(self.ids(order(stages.RECEIVED)), ["mt:flag_conversion", "mt:start_preparing", "mt:record_payment", "mt:hold"])
		self.assertNotIn("mt:flag_conversion", self.ids(order(stages.RECEIVED), cfg(conversions_enabled=0)))

	def test_t14_buttons_match_after_resume_to_dn_ready(self):
		so = order(stages.DN_READY, mode=stages.TERMS)
		self.assertEqual(self.ids(so), ["mt:upload_manifest", "mt:hold"])
		self.assertEqual(self.ids(order(stages.ON_HOLD)), ["mt:resume"])

	def test_t08_unpaid_cod_gets_no_release_button(self):
		ids = self.ids(order(stages.AWAITING_RELEASE, advance=10000))
		self.assertNotIn("mt:release", ids)
		self.assertIn("mt:override", ids)
		self.assertIn("mt:record_payment", ids)

	def test_t09_paid_cod_gets_release(self):
		ids = self.ids(order(stages.AWAITING_RELEASE, advance=14860))
		self.assertIn("mt:release", ids)
		self.assertNotIn("mt:override", ids)

	def test_t08_approval_dm_without_release_when_short(self):
		_text, blks = blocks.approval_dm(order(stages.AWAITING_RELEASE, advance=10000), cfg())
		action_ids = [e.get("action_id") for b in blks if b["type"] == "actions" for e in b["elements"]]
		self.assertNotIn("mt:release", action_ids)
		self.assertIn("mt:override", action_ids)
		self.assertIn("mt:open_erp", action_ids)

	def test_approval_dm_after_release_has_no_buttons(self):
		_text, blks = blocks.approval_dm(order(stages.RELEASED, advance=14860), cfg(), released_by="MBi")
		self.assertFalse([b for b in blks if b["type"] == "actions"])

	def test_button_value_carries_order_and_stage(self):
		b = blocks.button("mt:release", order(stages.AWAITING_RELEASE))
		self.assertEqual(json.loads(b["value"]), {"so": "SAL-ORD-TEST-99999", "stage": stages.AWAITING_RELEASE})

	def test_terminal_order_has_only_erp_link(self):
		_text, blks = blocks.thread_parent(order(stages.CLOSED_OUT, mode=stages.TERMS), cfg())
		actions = [b for b in blks if b["type"] == "actions"][0]
		self.assertEqual([e["action_id"] for e in actions["elements"]], ["mt:open_erp"])

	def test_conversion_modal_fits_slack_limits(self):
		so = order(stages.AWAITING_CONVERSION)
		view = blocks.conversion_modal(so, cfg(), rows=3, microns=True)
		self.assertLessEqual(len(view["blocks"]), 100)
		self.assertLessEqual(len(view["private_metadata"]), 3000)


class TestModalValidation(FrappeTestCase):
	def values(self, **blocks_):
		out = {}
		for block_id, element in blocks_.items():
			out[block_id] = {"value": element}
		return out

	def test_t07_nine_digit_manifest_is_an_error(self):
		values = {
			"manifest_number": {"value": {"type": "plain_text_input", "value": "123456789"}},
			"manifest_file": {"value": {"type": "file_input", "files": [{"id": "F1", "mimetype": "application/pdf", "size": 10}]}},
		}
		errors, _payload, _files = handlers._parse_manifest(values, {})
		self.assertIn("manifest_number", errors)
		self.assertNotIn("manifest_file", errors)

	def test_t07_missing_file_is_an_error(self):
		values = {
			"manifest_number": {"value": {"type": "plain_text_input", "value": "1234567890"}},
			"manifest_file": {"value": {"type": "file_input", "files": []}},
		}
		errors, _payload, _files = handlers._parse_manifest(values, {})
		self.assertEqual(list(errors), ["manifest_file"])

	def test_wrong_file_type_is_an_error(self):
		values = {
			"manifest_number": {"value": {"type": "plain_text_input", "value": "1234567890"}},
			"manifest_file": {"value": {"type": "file_input", "files": [{"id": "F1", "mimetype": "application/zip", "filetype": "zip", "size": 10}]}},
		}
		errors, _payload, _files = handlers._parse_manifest(values, {})
		self.assertIn("manifest_file", errors)

	def test_override_needs_fifteen_characters(self):
		short = {"reason": {"value": {"type": "plain_text_input", "value": "cash tomorrow"}}}
		self.assertIn("reason", handlers._parse_override(short, {})[0])
		long = {"reason": {"value": {"type": "plain_text_input", "value": "Customer pays on delivery, MBi agreed"}}}
		self.assertFalse(handlers._parse_override(long, {})[0])

	def test_hold_needs_a_reason(self):
		empty = {"reason": {"value": {"type": "plain_text_input", "value": "  "}}}
		self.assertIn("reason", handlers._parse_hold(empty, {})[0])

	def test_payment_needs_an_amount(self):
		values = {
			"amount": {"value": {"type": "number_input", "value": "0"}},
			"mode_of_payment": {"value": {"type": "static_select", "selected_option": {"value": "Cash"}}},
		}
		self.assertIn("amount", handlers._parse_payment(values, {})[0])

	def test_conversion_row_needs_raw_and_finished(self):
		values = {
			"r1_rm1": {"v": {"type": "external_select", "selected_option": {"value": "item:ANY"}}},
			"r1_rmq1": {"v": {"type": "number_input", "value": "5"}},
		}
		errors, _payload, _files = handlers._parse_conversion(values, {"rows": 1})
		self.assertIn("r1_fg1", errors)

	def test_conversion_counts_become_the_type(self):
		values = {
			"r1_rm1": {"v": {"type": "external_select", "selected_option": {"value": "item:A"}}},
			"r1_rmq1": {"v": {"type": "number_input", "value": "5"}},
			"r1_rm2": {"v": {"type": "external_select", "selected_option": {"value": "item:B"}}},
			"r1_rmq2": {"v": {"type": "number_input", "value": "2"}},
			"r1_fg1": {"v": {"type": "external_select", "selected_option": {"value": "item:C"}}},
			"r1_fgq1": {"v": {"type": "number_input", "value": "6"}},
			"submit_mode": {"v": {"type": "radio_buttons", "selected_option": {"value": "draft"}}},
		}
		errors, payload, _files = handlers._parse_conversion(values, {"rows": 1})
		self.assertFalse(errors)
		self.assertEqual(len(payload["rows"][0]["raw_materials"]), 2)
		self.assertFalse(payload["submit"])

	def test_t06_tag_short_of_line_quantity_errors_on_that_line(self):
		so = FakeDoc(name="SO-X", company="Master Touch Manufacturing",
		             items=[frappe._dict(name="row1", qty=10, item_code="I1")])
		values = {"line_row1": {"value": {"type": "static_select", "selected_option": {"value": "TAG-1"}}}}
		with mock.patch("frappe.get_doc", return_value=so), \
			mock.patch.object(handlers, "get_company_settings", return_value=cfg()), \
			mock.patch.object(handlers.gates, "tag_qty", return_value=4):
			errors, payload, _files = handlers._parse_delivery_note(values, {"so": "SO-X"})
		self.assertIn("line_row1", errors)
		self.assertEqual(payload["muid"], {"row1": "TAG-1"})


class TestWorkingClock(FrappeTestCase):
	def test_counts_only_inside_work_hours(self):
		c = cfg()
		# Tue 16:00 -> Wed 09:00 LA: one hour Tuesday, one hour Wednesday.
		self.assertEqual(reminders.working_minutes(system_naive(2026, 9, 29, 16), system_naive(2026, 9, 30, 9), c), 120)

	def test_t16_nothing_counts_overnight_or_on_sunday(self):
		c = cfg()
		# Sat 17:00 -> Mon 08:00: Saturday closed, Sunday off, Monday not open yet.
		self.assertEqual(reminders.working_minutes(system_naive(2026, 10, 3, 17), system_naive(2026, 10, 5, 8), c), 0)

	def test_outside_hours_the_job_does_nothing(self):
		c = cfg()
		self.assertFalse(reminders.in_work_hours(datetime(2026, 10, 4, 10, tzinfo=LA), c))  # Sunday
		self.assertFalse(reminders.in_work_hours(datetime(2026, 9, 29, 20, tzinfo=LA), c))  # evening
		self.assertTrue(reminders.in_work_hours(datetime(2026, 9, 29, 10, tzinfo=LA), c))

	def test_zero_minute_rules_are_ignored(self):
		c = cfg(reminders=[frappe._dict(stage=stages.PREPARED, after_minutes=0, notify="compliance")])
		self.assertEqual(reminders.rules(c), [])

	def test_defaults_apply_when_no_rules(self):
		self.assertEqual(reminders.rules(cfg()), reminders.DEFAULT_RULES)

	def test_t16_one_reminder_only(self):
		c = cfg()
		so = order(stages.PREPARED, mode=stages.TERMS)
		reached = system_naive(2026, 9, 29, 9)
		log = frappe._dict(at=reached, last_reminded_on=None)

		_age, due = reminders.due_rules(so, c, stages.PREPARED, log, system_naive(2026, 9, 29, 10, 45))
		self.assertEqual(due, [])  # 105 working minutes

		now = system_naive(2026, 9, 29, 11, 15)
		_age, due = reminders.due_rules(so, c, stages.PREPARED, log, now)
		self.assertEqual(due, [(120, "compliance")])

		log.last_reminded_on = now
		_age, due = reminders.due_rules(so, c, stages.PREPARED, log, system_naive(2026, 9, 29, 11, 30))
		self.assertEqual(due, [])

	def test_awaiting_release_rule_depends_on_payment(self):
		c = cfg()
		unpaid = reminders.applicable_rules(order(stages.AWAITING_RELEASE, advance=0), c, stages.AWAITING_RELEASE)
		paid = reminders.applicable_rules(order(stages.AWAITING_RELEASE, advance=14860), c, stages.AWAITING_RELEASE)
		self.assertEqual(sorted(n for _m, n in unpaid), ["exceptions", "finance"])
		self.assertEqual([n for _m, n in paid], ["approver"])


class TestClickToTransition(FrappeTestCase):
	def test_unlinked_slack_user_is_told(self):
		with mock.patch.object(handlers.identity, "erp_user_for", return_value=None), \
			mock.patch.object(handlers, "tell") as tell, \
			mock.patch.object(handlers.flow, "transition") as transition:
			handlers.run_action("U1", "release", "SO-1", response_url="https://hooks.slack.test/x")
		transition.assert_not_called()
		self.assertEqual(tell.call_args[0][1], "Your Slack account isn't linked to an ERP user.")

	def test_gate_failure_is_ephemeral_to_the_clicker(self):
		with mock.patch.object(handlers.identity, "erp_user_for", return_value="Administrator"), \
			mock.patch.object(handlers, "tell") as tell, \
			mock.patch.object(handlers.flow, "transition", side_effect=GateError("This COD order is short $4,860.00.")), \
			mock.patch.object(handlers.client, "post") as post:
			handlers.run_action("U1", "release", "SO-1", "Awaiting Release", response_url="https://hooks.slack.test/x")
		post.assert_not_called()
		self.assertIn("short", tell.call_args[0][1])
		self.assertEqual(tell.call_args[0][2], "https://hooks.slack.test/x")

	def test_transition_runs_as_the_erp_user(self):
		seen = {}

		def fake_transition(*args, **kwargs):
			seen["user"] = frappe.session.user
			seen["source"] = kwargs.get("source")

		with mock.patch.object(handlers.identity, "erp_user_for", return_value="Administrator"), \
			mock.patch.object(handlers.flow, "transition", side_effect=fake_transition), \
			mock.patch.object(handlers.frappe.db, "commit"):
			handlers.run_action("U1", "start_preparing", "SO-1", "Order Received")
		self.assertEqual(seen, {"user": "Administrator", "source": "Slack"})


class TestConversionCheck(FrappeTestCase):
	def so(self):
		return FakeDoc(
			name="SAL-ORD-TEST-1", customer="C1", customer_name="BIG TERPS", set_warehouse="WH-1",
			custom_logistic_status=stages.RECEIVED, custom_mode_of_payment=stages.TERMS,
			items=[
				frappe._dict(item_code="I-SHORT", item_name="Grape Belts", stock_uom="Gram", stock_qty=28, qty=28, warehouse="WH-1"),
				frappe._dict(item_code="I-OK", item_name="Food Grade", stock_uom="Gram", stock_qty=600, qty=600, warehouse="WH-1"),
				frappe._dict(item_code="I-OK", item_name="Food Grade", stock_uom="Gram", stock_qty=6, qty=6, warehouse=None),
			],
		)

	def test_shortage_lines_match_the_existing_format(self):
		bins = {"I-SHORT": 0, "I-OK": 606}
		with mock.patch.object(blocks.frappe.db, "get_value", side_effect=lambda dt, f, fld: bins[f["item_code"]]):
			check = blocks.stock_check(self.so())
		self.assertEqual(check.need, ["• *Grape Belts* (`I-SHORT`) — need *28.00 Gram* (required 28.00, available 0.00)"])
		self.assertEqual(check.ok, ["• *Food Grade* (`I-OK`) — ok (606.00 Gram)"])  # both lines summed

	def test_header_and_fulfillment_tag(self):
		with mock.patch.object(blocks.frappe.db, "get_value", return_value=0):
			_text, blks = blocks.conversion_check(self.so(), cfg(), ["<!subteam^S1>"])
		self.assertEqual(blks[0]["text"]["text"], ":red_circle: Conversion required")
		self.assertTrue(any("<!subteam^S1> :warning: *Needs conversion*" in (b.get("text") or {}).get("text", "") for b in blks))

	def test_nothing_short_says_no_conversion(self):
		with mock.patch.object(blocks.frappe.db, "get_value", return_value=10_000):
			_text, blks = blocks.conversion_check(self.so(), cfg())
		self.assertEqual(blks[0]["text"]["text"], ":large_green_circle: No conversion required")


class TestConversionMessageOnlyWhenShort(FrappeTestCase):
	def run_enter_flow(self, need, action="enter_flow"):
		from cannabis_management.mt_dispatch.slack import post

		so = FakeDoc(name="SO-1", company="C", customer="X", customer_name="X", custom_logistic_status=stages.RECEIVED,
		             custom_mode_of_payment=stages.TERMS, items=[], owner="Administrator", sales_team=[])
		sent = []
		with mock.patch.object(post.frappe, "get_doc", return_value=so), \
			mock.patch.object(post.frappe.db, "get_value"), \
			mock.patch.object(post.frappe.db, "commit"), \
			mock.patch.object(post, "get_company_settings", return_value=cfg()), \
			mock.patch.object(post, "ensure_thread", return_value=frappe._dict(channel="C1", ts="1")), \
			mock.patch.object(post, "refresh_parent"), mock.patch.object(post, "_refresh_homes"), \
			mock.patch.object(post, "mentions_for", return_value=[]), \
			mock.patch.object(post, "fulfillment_mentions", return_value=[]), \
			mock.patch.object(post, "mention_users", return_value=[]), \
			mock.patch.object(post.blocks, "stock_check", return_value=frappe._dict(need=need, ok=[], warehouses=["W"])), \
			mock.patch.object(post.blocks, "sales_rep_user", return_value="Administrator"), \
			mock.patch.object(post.client, "post", side_effect=lambda *a, **k: sent.append(a[1])):
			post.on_transition("SO-1", action, actor="Administrator")
		return sent

	def test_new_order_does_not_repeat_the_conversion_message(self):
		# On a new order the thread parent itself is the conversion message.
		self.assertFalse(any("onversion" in t for t in self.run_enter_flow(["\u2022 short"])))

	def test_flagged_conversion_gets_the_message_when_short(self):
		self.assertTrue(any("Conversion required" in t for t in self.run_enter_flow(["\u2022 short"], "flag_conversion")))

	def test_nothing_short_gets_no_conversion_message(self):
		sent = self.run_enter_flow([])
		self.assertTrue(sent)
		self.assertFalse(any("onversion" in t for t in sent))


class TestStatusDropdown(FrappeTestCase):
	def test_dropdown_shows_current_stage_and_reachable_ones(self):
		select = blocks.status_section(order(stages.RECEIVED, mode=stages.TERMS), cfg())["accessory"]
		self.assertEqual(select["action_id"], "mt:set_status")
		labels = [o["text"]["text"] for o in select["options"]]
		self.assertEqual(labels, [stages.RECEIVED, stages.AWAITING_CONVERSION, stages.PREPARING, stages.ON_HOLD])
		self.assertEqual(select["initial_option"]["text"]["text"], stages.RECEIVED)

	def test_repicking_current_stage_does_nothing(self):
		from cannabis_management.mt_dispatch.slack import endpoints

		value = json.dumps({"so": "SO-1", "stage": stages.RECEIVED, "a": ""})
		payload = {"type": "block_actions", "user": {"id": "U1"},
		           "actions": [{"action_id": "mt:set_status", "selected_option": {"value": value}}]}
		with mock.patch.object(endpoints, "_enqueue") as enqueue:
			endpoints._block_actions(payload)
		enqueue.assert_not_called()

	def test_closed_order_has_no_dropdown(self):
		self.assertNotIn("accessory", blocks.status_section(order(stages.CLOSED_OUT, mode=stages.TERMS), cfg()))

	def test_failed_step_resets_the_dropdown(self):
		with mock.patch.object(handlers.identity, "erp_user_for", return_value="Administrator"), \
			mock.patch.object(handlers, "tell"), \
			mock.patch.object(handlers.flow, "transition", side_effect=GateError("no")), \
			mock.patch.object(handlers, "reset_status") as reset:
			handlers.run_action("U1", "release", "SO-1", "Awaiting Release")
		reset.assert_called_once_with("SO-1")

	def test_message_has_no_total(self):
		so = order(stages.RECEIVED, mode=stages.TERMS, total=3096, advance=3096, set_warehouse="W")
		with mock.patch.object(blocks.frappe.db, "get_value", return_value=0):
			dump = json.dumps(blocks.thread_parent(so, cfg())[1])
		self.assertNotIn("3,096", dump)
		self.assertNotIn("Paid", dump)

	def test_dropdown_value_names_the_button(self):
		select = blocks.status_select(order(stages.DN_READY), ["mt:upload_manifest"])
		self.assertEqual(json.loads(select["options"][0]["value"])["a"], "mt:upload_manifest")

	def test_picking_a_status_runs_that_step(self):
		from cannabis_management.mt_dispatch.slack import endpoints

		value = json.dumps({"so": "SO-1", "stage": stages.RECEIVED, "a": "mt:start_preparing"})
		payload = {"type": "block_actions", "user": {"id": "U1"}, "response_url": "https://hooks.slack.test/x",
		           "actions": [{"action_id": "mt:set_status", "selected_option": {"value": value}}]}
		with mock.patch.object(endpoints, "_enqueue") as enqueue:
			endpoints._block_actions(payload)
		kwargs = enqueue.call_args.kwargs
		self.assertEqual((enqueue.call_args.args[0], kwargs["action"], kwargs["sales_order"], kwargs["expected_stage"]),
		                 ("run_action", "start_preparing", "SO-1", stages.RECEIVED))


class TestItemNames(FrappeTestCase):
	def so(self):
		return order(stages.RECEIVED, mode=stages.TERMS, set_warehouse="WH-1", items=[
			frappe._dict(item_code="PR-0011", item_name="GOVERNMENT OASIS - Primes", qty=100, uom="Gram", stock_uom="Gram"),
			frappe._dict(item_code="PR-0040", item_name="TRIANGLE GMO - Primes", qty=250, uom="Gram", stock_uom="Gram"),
		])

	def test_thread_parent_lists_every_item_by_name(self):
		with mock.patch.object(blocks.frappe.db, "get_value", return_value=10_000):
			dump = json.dumps(blocks.thread_parent(self.so(), cfg())[1])
		self.assertIn("GOVERNMENT OASIS - Primes", dump)
		self.assertIn("(`PR-0040`) \\u2014 250 Gram", dump)

	def test_thread_parent_is_the_conversion_message_when_short(self):
		c = cfg(conversion_mention="U0AJ7HW183G")
		with mock.patch.object(blocks.frappe.db, "get_value", return_value=0):
			text, blks = blocks.thread_parent(self.so(), c)
		self.assertEqual(blks[0]["text"]["text"], ":red_circle: Conversion required")
		self.assertTrue(blks[1]["text"]["text"].startswith("*Sales Order:*"))
		self.assertIn("*Customer:*", blks[1]["text"]["text"])
		self.assertIn("*Warehouse:*", blks[1]["text"]["text"])
		self.assertTrue(blks[3]["text"]["text"].startswith("<@U0AJ7HW183G> :warning: *Needs conversion*"))
		self.assertIn("need *100.00 Gram* (required 100.00, available 0.00)", blks[3]["text"]["text"])
		self.assertTrue(text.startswith("Conversion required"))

	def test_no_python_reprs_leak_into_messages(self):
		so = self.so()
		for _text, blks in (blocks.thread_parent(so, cfg()), blocks.dispatch_post(so, cfg()), blocks.approval_dm(so, cfg())):
			dump = json.dumps(blks)
			for sign in ("built-in method", "bound method", "object at 0x"):
				self.assertNotIn(sign, dump)
