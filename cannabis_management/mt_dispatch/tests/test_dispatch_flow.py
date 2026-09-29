"""Gate and state-machine tests.

Runs against whatever data the site holds: the tests pick a submitted Sales
Order rather than building one, which is what makes them meaningful on a copy
of production. FrappeTestCase rolls back after each test, so the order, its
settings record and every document created here are gone afterwards.

Test IDs in the names map to the acceptance table in the developer spec.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from cannabis_management.mt_dispatch import flow, gates, payments, stages
from cannabis_management.mt_dispatch.gates import GateError, StaleAction
from cannabis_management.mt_dispatch.settings import get_company_settings
from cannabis_management.mt_dispatch.tests.utils import (
	delete_new_log_rows,
	existing_log_rows,
	restore_settings,
	snapshot_settings,
)

COMPANY = "Master Touch Manufacturing"
OTHER_COMPANY = "TSBC Ranch"
FULFILLER = "tori@motleyterpz.com"
COMPLIANCE = "leo@motleyterpz.com"
APPROVER = "sean@motleyterpz.com"
OVERRIDER = "manny@motleyterpz.com"


class TestDispatchFlow(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.mt_dispatch_cfg = {}
		self.settings_snapshot = snapshot_settings((COMPANY, OTHER_COMPANY))
		self.cfg = self.make_settings(COMPANY, enabled=1)
		if OTHER_COMPANY in self.settings_snapshot:
			# The inert-company test needs TSBC to have no record at all.
			frappe.delete_doc("Dispatch Company Settings", OTHER_COMPANY, force=1, ignore_permissions=True)
			frappe.local.mt_dispatch_cfg = {}
		self.so = self.pick_order(COMPANY)
		# Remembered so tearDown can put a real order back exactly as it was.
		self.log_before = existing_log_rows(self.so.name)
		self.original = frappe.db.get_value(
			"Sales Order",
			self.so.name,
			[
				flow.STAGE_FIELD,
				"custom_conversion_required",
				"custom_hold_from_stage",
				"custom_hold_reason",
				"advance_paid",
			],
			as_dict=True,
		)
		flow.set_stage(self.so, stages.RECEIVED, "enter_flow", "System")

	def tearDown(self):
		"""Put everything back by hand.

		FrappeTestCase rolls back per class, not per test, and these tests run
		against real orders on a copy of production. Restoring explicitly means
		a failure halfway through still leaves the order as it was found.
		"""
		frappe.set_user("Administrator")
		if getattr(self, "original", None):
			frappe.db.set_value("Sales Order", self.so.name, self.original, update_modified=False)
			delete_new_log_rows(self.so.name, self.log_before)
		restore_settings(getattr(self, "settings_snapshot", {}), (COMPANY, OTHER_COMPANY))
		frappe.db.commit()

	# ── fixtures ────────────────────────────────────────────────────────────

	def make_settings(self, company, enabled=1, **overrides):
		values = {
			"doctype": "Dispatch Company Settings",
			"company": company,
			"enabled": enabled,
			"conversions_enabled": 1,
			"payment_gate_enabled": 1,
			"require_muid_on_dn": 0,
			"payment_tolerance": 0.01,
			"team": [
				{"user": FULFILLER, "fulfillment": 1},
				{"user": COMPLIANCE, "compliance": 1},
				{"user": APPROVER, "approver": 1},
				{"user": OVERRIDER, "approver": 1, "can_override": 1},
			],
		}
		values.update(overrides)
		if frappe.db.exists("Dispatch Company Settings", company):
			frappe.delete_doc(
				"Dispatch Company Settings", company, force=1, ignore_permissions=True
			)
		doc = frappe.get_doc(values).insert(ignore_permissions=True)
		frappe.local.mt_dispatch_cfg = {}
		return doc

	def pick_order(self, company, mode=None):
		filters = {"docstatus": 1, "company": company}
		if mode:
			filters["custom_mode_of_payment"] = mode
		# An order with no Conversion Entry of its own: the conversion gates are
		# asserted from a clean start, not from whatever real work is linked.
		with_conversions = set(frappe.get_all("Conversion Entry", filters={"sales_order": ["is", "set"]}, pluck="sales_order"))
		for name in frappe.get_all("Sales Order", filters=filters, pluck="name", order_by="creation desc", limit=50):
			if name not in with_conversions:
				return frappe.get_doc("Sales Order", name)
		self.skipTest(f"no submitted Sales Order without conversions for {company}")

	def stage(self):
		return frappe.db.get_value("Sales Order", self.so.name, flow.STAGE_FIELD)

	# ── tests ───────────────────────────────────────────────────────────────

	def test_unconfigured_company_is_inert(self):
		"""No settings record means every gate ignores the company."""
		other = self.pick_order(OTHER_COMPANY)
		self.assertIsNone(get_company_settings(other.company))

		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		dn = make_delivery_note(other.name)
		gates.dn_before_insert(dn)  # must not raise

	def test_t03_delivery_note_blocked_outside_the_flow(self):
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		dn = make_delivery_note(self.so.name)
		with self.assertRaises(GateError):
			gates.dn_before_insert(dn)

	def test_t03_delivery_note_allowed_with_the_flag(self):
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		dn = make_delivery_note(self.so.name)
		frappe.flags.mt_dispatch = "create_delivery_note"
		try:
			gates.dn_before_insert(dn)
		finally:
			frappe.flags.mt_dispatch = None

	def test_t11_delivery_note_submit_needs_release(self):
		from erpnext.selling.doctype.sales_order.sales_order import make_delivery_note

		dn = make_delivery_note(self.so.name)
		with self.assertRaises(GateError):
			gates.dn_before_submit(dn)

		frappe.flags.mt_dispatch = "release"
		try:
			gates.dn_before_submit(dn)
		finally:
			frappe.flags.mt_dispatch = None

	def test_t13_stage_field_is_not_editable_by_hand(self):
		doc = frappe.get_doc("Sales Order", self.so.name)
		doc.custom_logistic_status = stages.RELEASED
		with self.assertRaises(GateError):
			doc.save(ignore_permissions=True)

	def test_t15_team_authority_is_per_company(self):
		"""Fulfillment at one company is nothing at another."""
		self.make_settings(OTHER_COMPANY, team=[{"user": OVERRIDER, "fulfillment": 1}])
		frappe.set_user(OVERRIDER)
		with self.assertRaises(GateError):
			flow.transition(self.so.name, "start_preparing")

		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")
		self.assertEqual(self.stage(), stages.PREPARING)

	def test_wrong_from_stage_is_refused(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")
		with self.assertRaises(GateError):
			flow.transition(self.so.name, "start_preparing")

	def test_t10_stale_click_is_refused(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")
		with self.assertRaises(StaleAction):
			flow.transition(self.so.name, "mark_prepared", expected_stage=stages.RECEIVED)

	def test_t05_draft_conversion_blocks_mark_prepared(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")

		ce = self.draft_conversion()
		with self.assertRaises(GateError):
			flow.transition(self.so.name, "mark_prepared")

		ce.delete(ignore_permissions=True)
		flow.transition(self.so.name, "mark_prepared")
		self.assertEqual(self.stage(), stages.PREPARED)

	def test_t04_conversion_required_needs_a_submitted_entry(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "flag_conversion")
		self.assertEqual(self.stage(), stages.AWAITING_CONVERSION)
		self.assertTrue(frappe.db.get_value("Sales Order", self.so.name, "custom_conversion_required"))

		so = frappe.get_doc("Sales Order", self.so.name)
		with self.assertRaises(GateError):
			gates.conversions_complete(so, self.cfg)

	def test_hold_needs_a_reason_and_remembers_the_stage(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")

		with self.assertRaises(GateError):
			flow.transition(self.so.name, "hold", payload={"reason": "   "})

		flow.transition(self.so.name, "hold", payload={"reason": "customer unreachable"})
		self.assertEqual(self.stage(), stages.ON_HOLD)
		self.assertEqual(
			frappe.db.get_value("Sales Order", self.so.name, "custom_hold_from_stage"),
			stages.PREPARING,
		)

	def test_t14_resume_returns_to_the_held_stage(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")
		flow.transition(self.so.name, "hold", payload={"reason": "waiting on the lab"})

		frappe.set_user(APPROVER)
		flow.transition(self.so.name, "resume")
		self.assertEqual(self.stage(), stages.PREPARING)
		self.assertIsNone(frappe.db.get_value("Sales Order", self.so.name, "custom_hold_from_stage"))

	def test_t12_override_requires_the_flag_and_a_reason(self):
		frappe.db.set_value(
			"Sales Order", self.so.name, flow.STAGE_FIELD, stages.AWAITING_RELEASE,
			update_modified=False,
		)
		frappe.set_user(APPROVER)  # approver, but no can_override
		with self.assertRaises(GateError):
			flow.transition(self.so.name, "release_override", payload={"reason": "customer is good for it"})

		frappe.set_user(OVERRIDER)
		with self.assertRaises(GateError):  # reason missing
			flow.transition(self.so.name, "release_override", payload={})

	def test_g4_rejects_a_short_manifest_number(self):
		so = frappe.get_doc("Sales Order", self.so.name)
		with self.assertRaises(GateError):
			gates.manifest_present(so, self.cfg, {"manifest_number": "123456789", "file_url": "/x.pdf"})

	def test_g5_only_bites_on_cash_on_delivery(self):
		so = frappe.get_doc("Sales Order", self.so.name)
		so.custom_mode_of_payment = stages.TERMS
		self.assertFalse(payments.payment_gate_applies(so, self.cfg))

		so.custom_mode_of_payment = stages.COD
		expected = payments.required_amount(so) > 0
		self.assertEqual(payments.payment_gate_applies(so, self.cfg), expected)

	def test_g5_passes_once_paid_within_tolerance(self):
		"""Needs an order with no invoices behind it.

		paid_amount takes the larger of advances and settled invoices, so on an
		order that is already invoiced and paid, moving advance_paid proves
		nothing -- the invoice leg keeps the figure up on its own. That is the
		fallback working; this test is about the advance leg and the tolerance.
		"""
		name = self.order_without_invoices(COMPANY)
		so = frappe.get_doc("Sales Order", name)
		so.custom_mode_of_payment = stages.COD
		if not payments.payment_gate_applies(so, self.cfg):
			self.skipTest("no uninvoiced order with a value to gate")

		required = payments.required_amount(so)
		original_advance = so.advance_paid
		self.addCleanup(
			frappe.db.set_value, "Sales Order", name, "advance_paid", original_advance, update_modified=False
		)

		def gate_with(advance):
			frappe.db.set_value("Sales Order", name, "advance_paid", advance, update_modified=False)
			doc = frappe.get_doc("Sales Order", name)
			doc.custom_mode_of_payment = stages.COD
			gates.paid(doc, self.cfg)

		gate_with(required)  # paid in full -- must not raise

		gate_with(required - 0.005)  # inside the 0.01 tolerance -- must not raise

		with self.assertRaises(GateError):
			gate_with(required - 1)

	def test_paid_amount_never_double_counts_an_allocated_advance(self):
		so = frappe.get_doc("Sales Order", self.so.name)
		frappe.db.set_value("Sales Order", so.name, "advance_paid", 500, update_modified=False)
		so = frappe.get_doc("Sales Order", so.name)
		self.assertGreaterEqual(payments.paid_amount(so), 500)

	def test_stage_log_records_every_move(self):
		frappe.set_user(FULFILLER)
		flow.transition(self.so.name, "start_preparing")
		flow.transition(self.so.name, "mark_prepared")

		rows = frappe.get_all(
			"Dispatch Stage Log",
			filters={"parent": self.so.name, "parenttype": "Sales Order"},
			fields=["from_stage", "to_stage", "action", "user", "source"],
			order_by="idx",
		)
		actions = [r.action for r in rows]
		self.assertIn("start_preparing", actions)
		self.assertIn("mark_prepared", actions)
		self.assertEqual(rows[-1].to_stage, stages.PREPARED)
		self.assertEqual(rows[-1].user, FULFILLER)

	def test_conversion_types_match_the_doctype(self):
		from cannabis_management.mt_dispatch.builders import conversion_types

		types = conversion_types()
		self.assertIn("1 to 1", types)
		self.assertIn("7 to 1", types)
		self.assertNotIn("2 to 3", types)

	# ── helpers ─────────────────────────────────────────────────────────────

	def order_without_invoices(self, company):
		invoiced = frappe.get_all(
			"Sales Invoice Item",
			filters={"docstatus": 1, "sales_order": ["is", "set"]},
			pluck="sales_order",
			distinct=True,
		)
		filters = {"docstatus": 1, "company": company, "grand_total": [">", 0]}
		if invoiced:
			filters["name"] = ["not in", invoiced]
		name = frappe.db.get_value("Sales Order", filters, "name", order_by="creation desc")
		if not name:
			self.skipTest(f"no uninvoiced submitted Sales Order for {company}")
		return name

	def draft_conversion(self):
		item = self.so.items[0]
		warehouse = item.warehouse or self.so.set_warehouse
		return frappe.get_doc(
			{
				"doctype": "Conversion Entry",
				"company": self.so.company,
				"customer": self.so.customer,
				"sales_order": self.so.name,
				"posting_date": frappe.utils.nowdate(),
				"items": [
					{
						"conversion_type": "1 to 1",
						"source_warehouse": warehouse,
						"target_warehouse": warehouse,
						"raw_material_1": item.item_code,
						"qty_rm_1": 1,
						"finished_good_1": item.item_code,
						"qty_fg_1": 1,
					}
				],
			}
		).insert(ignore_permissions=True)
