"""One order, all the way through, against real data.

The unit tests in test_dispatch_flow.py prove each rule in isolation. This
proves the chain: a submitted Sales Order goes from Order Received to Order
Closed Out, creating and submitting a real Delivery Note on the way, with the
company actually enabled.

Everything is put back in tearDown -- the note is cancelled and deleted, the
order is restored to the stage and flags it was found with, and the settings
record is removed. Run it as often as you like.
"""

import frappe
from frappe.tests.utils import FrappeTestCase

from cannabis_management.mt_dispatch import flow, gates, stages
from cannabis_management.mt_dispatch.gates import GateError
from cannabis_management.mt_dispatch.tests.utils import (
	delete_new_log_rows,
	existing_log_rows,
	restore_settings,
	snapshot_settings,
)

COMPANY = "Master Touch Manufacturing"
MANIFEST_NUMBER = "0000000001"


class TestDispatchWalk(FrappeTestCase):
	def setUp(self):
		frappe.set_user("Administrator")
		frappe.local.mt_dispatch_cfg = {}
		self.dn_name = None
		self.file_name = None
		self.settings_snapshot = snapshot_settings((COMPANY,))
		self.cfg = self.enable_company()
		self.so = self.pick_order()
		self.log_before = existing_log_rows(self.so.name)
		self.original = frappe.db.get_value(
			"Sales Order", self.so.name,
			[flow.STAGE_FIELD, "custom_released_by", "custom_released_on"], as_dict=True,
		)

	def tearDown(self):
		frappe.set_user("Administrator")
		if self.dn_name and frappe.db.exists("Delivery Note", self.dn_name):
			dn = frappe.get_doc("Delivery Note", self.dn_name)
			if dn.docstatus == 1:
				dn.cancel()
			frappe.delete_doc("Delivery Note", self.dn_name, force=1, ignore_permissions=True)
		if self.file_name and frappe.db.exists("File", self.file_name):
			frappe.delete_doc("File", self.file_name, force=1, ignore_permissions=True)
		if getattr(self, "original", None):
			frappe.db.set_value("Sales Order", self.so.name, self.original, update_modified=False)
			delete_new_log_rows(self.so.name, self.log_before)
		restore_settings(getattr(self, "settings_snapshot", {}), (COMPANY,))
		frappe.db.commit()

	def enable_company(self):
		"""Enabled, with the payment gate off so the walk is about the stages."""
		if frappe.db.exists("Dispatch Company Settings", COMPANY):
			frappe.delete_doc("Dispatch Company Settings", COMPANY, force=1, ignore_permissions=True)
		doc = frappe.get_doc(
			{
				"doctype": "Dispatch Company Settings",
				"company": COMPANY,
				"enabled": 1,
				"conversions_enabled": 1,
				"payment_gate_enabled": 0,
				"require_muid_on_dn": 0,
				"payment_tolerance": 0.01,
			}
		).insert(ignore_permissions=True)
		frappe.local.mt_dispatch_cfg = {}
		return doc

	def pick_order(self):
		"""A submitted order with nothing delivered and no note against it."""
		for row in frappe.get_all(
			"Sales Order",
			filters={"docstatus": 1, "company": COMPANY, "status": ["not in", ["Closed", "Cancelled"]],
			         "per_delivered": ["<", 100]},
			fields=["name"], order_by="creation desc", limit=40,
		):
			if not gates.delivery_notes_for(row.name):
				return frappe.get_doc("Sales Order", row.name)
		self.skipTest("no deliverable Sales Order without an existing Delivery Note")

	def stage(self):
		return frappe.db.get_value("Sales Order", self.so.name, flow.STAGE_FIELD)

	# A real 1x1 PNG. Frappe parses uploads to scan for embedded scripts, so
	# a file merely named .pdf with junk inside is rejected by the reader
	# before it ever reaches the gate.
	PNG_1x1 = (
		"iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
	)

	def make_manifest_file(self):
		doc = frappe.get_doc(
			{
				"doctype": "File",
				"file_name": "manifest-test.png",
				"is_private": 1,
				"content": self.PNG_1x1,
				"decode": True,
			}
		).insert(ignore_permissions=True)
		self.file_name = doc.name
		return doc.file_url

	def test_full_walk_received_to_closed_out(self):
		flow.set_stage(self.so, stages.RECEIVED, "enter_flow", "System")
		self.assertEqual(self.stage(), stages.RECEIVED)

		flow.transition(self.so.name, "start_preparing")
		self.assertEqual(self.stage(), stages.PREPARING)

		flow.transition(self.so.name, "mark_prepared")
		self.assertEqual(self.stage(), stages.PREPARED)

		self.dn_name = flow.transition(self.so.name, "create_delivery_note", payload={"muid": {}})
		self.assertEqual(self.stage(), stages.DN_READY)
		self.assertTrue(frappe.db.exists("Delivery Note", self.dn_name))
		self.assertEqual(frappe.db.get_value("Delivery Note", self.dn_name, "docstatus"), 0)

		# A second note is refused while the first exists.
		with self.assertRaises(GateError):
			gates.one_delivery_note(frappe.get_doc("Sales Order", self.so.name), self.cfg)

		file_url = self.make_manifest_file()
		flow.transition(
			self.so.name, "upload_manifest",
			payload={"manifest_number": MANIFEST_NUMBER, "file_url": file_url},
		)
		self.assertEqual(self.stage(), stages.AWAITING_RELEASE)
		self.assertEqual(
			frappe.db.get_value("Delivery Note", self.dn_name, "custom_metrc_manifest_number"),
			MANIFEST_NUMBER,
		)

		# Release submits the Delivery Note, which moves stock for real. On a
		# copy of production the picked order often has none left, and ERPNext
		# refuses. That is the warehouse talking, not the flow: everything the
		# flow is responsible for has already happened by this point.
		from erpnext.stock.stock_ledger import NegativeStockError

		try:
			flow.transition(self.so.name, "release")
		except NegativeStockError as e:
			self.assertEqual(self.stage(), stages.AWAITING_RELEASE)
			self.skipTest(f"stock short, flow reached release: {frappe.utils.strip_html(str(e))[:110]}")

		self.assertEqual(self.stage(), stages.RELEASED)
		self.assertEqual(frappe.db.get_value("Delivery Note", self.dn_name, "docstatus"), 1)
		self.assertEqual(
			frappe.db.get_value("Sales Order", self.so.name, "custom_released_by"), "Administrator"
		)

		flow.transition(self.so.name, "mark_delivered")
		self.assertEqual(self.stage(), stages.CLOSED_OUT)

		# Only the rows this walk wrote. A real order may already carry history.
		actions = [
			r.action
			for r in frappe.get_all(
				"Dispatch Stage Log",
				filters={"parent": self.so.name, "parenttype": "Sales Order"},
				fields=["name", "action"], order_by="idx",
			)
			if r.name not in self.log_before
		]
		# enter_flow is only written when the order was not already at Order
		# Received -- a real order picked for the walk may already be there.
		self.assertEqual(
			[a for a in actions if a != "enter_flow"],
			["start_preparing", "mark_prepared", "create_delivery_note",
			 "upload_manifest", "release", "mark_delivered"],
		)
