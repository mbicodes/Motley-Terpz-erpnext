import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class RosinRecording(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		self.total_quantity = sum(flt(row.pounds_sent) for row in self.lab_tolling_data)
		self.tolling_partner_charges = flt(self.total_quantity) * flt(self.rate_tolling_partner)
		
		for row in self.lab_tolling_data:
			if not row.expected_rosin_yield:
				row.expected_rosin_yield = self.expected_rosin_yield

			# Prefer row-level yield, fallback to parent-level
			exp_hash_yield = flt(row.expected_hash_yield or row.expected__yield__to_hash)
			exp_rosin_yield = flt(row.expected_rosin_yield or self.expected_rosin_yield)
			
			total_hash = flt(row.total_hash)
			total_rosin = flt(row.total_rosin)
			amount_ran_grams = flt(row.amount_ran_grams)

			# 1. Calculate Actual Yields
			actual_yield_to_hash = 0
			if amount_ran_grams > 0:
				actual_yield_to_hash = (total_hash / amount_ran_grams) * 100
			row.actual_yield_to_hash = flt(actual_yield_to_hash, 2)

			actual_rosin_yield = 0
			if total_hash > 0:
				actual_rosin_yield = (total_rosin / total_hash) * 100
			row.actual_rosin_yield = flt(actual_rosin_yield, 2)

			# 2. Formula for Raw Qty using Actuals
			# Fallback to pounds_ran as a safe starting point
			raw_qty = flt(row.pounds_ran)
			if actual_yield_to_hash > 0 and actual_rosin_yield > 0 and total_hash > 0:
				raw_qty = total_hash / (actual_yield_to_hash / 100) / 453.592 / (actual_rosin_yield / 100)
			
			# Ensure it's never zero if we have inputs/outputs participation
			if raw_qty <= 0 and (total_hash > 0 or flt(row.pounds_ran) > 0):
				raw_qty = flt(row.pounds_ran) or 0
			
			# Cap at pounds_sent if calculation exceeds it
			pounds_sent = flt(row.pounds_sent)
			if raw_qty > pounds_sent and pounds_sent > 0:
				raw_qty = pounds_sent
				
			row.raw_material_quantity = flt(raw_qty, 4)

	def on_submit(self):
		# Existing lab batch status update logic
		self._update_lab_batch_status()

		# Create draft Stock Entry (Repack)
		try:
			self._create_repack_stock_entry()
		except Exception as e:
			frappe.log_error(message=frappe.get_traceback(), title="Rosin Recording Stock Entry Creation Failed")
			frappe.msgprint(_("Failed to create Stock Entry. Please check Error Log for details."), indicator="red")

	def _update_lab_batch_status(self):
		"""Update linked Lab Batch Entry status to Rosin Produced."""
		hash_rec_name = self.hash_reference

		if not hash_rec_name:
			return

		lab_batch_name = frappe.db.get_value(
			"Hash Recording",
			hash_rec_name,
			"lab_batch_refrence"
		)

		if lab_batch_name:
			frappe.publish_realtime(
				"lab_batch_status_update",
				{"lab_batch": lab_batch_name, "status": "Rosin Produced"},
				user=frappe.session.user
			)
			frappe.msgprint(
				_("Lab Batch Entry {0} status updated to Rosin Produced.").format(
					f'<a href="/app/lab-batch-entry/{lab_batch_name}">{lab_batch_name}</a>'
				),
				alert=True
			)

	def _create_repack_stock_entry(self):
		"""Create a draft Repack Stock Entry from Rosin Recording child rows."""
		frappe.logger().info(f"Starting Stock Entry creation for {self.name}")
		
		se = frappe.new_doc("Stock Entry")
		se.stock_entry_type = "Repack"
		se.company = "Motley Terpz"
		se.custom_rosin_recording_reference = self.name

		has_items = False

		for row in self.lab_tolling_data:
			# ── Row 1: Raw Material (strain_name) ──
			raw_qty = flt(row.raw_material_quantity)

			if row.strain_name and raw_qty > 0:
				se.append("items", {
					"item_code": row.strain_name,
					"qty": raw_qty,
					"s_warehouse": self.tolling_partner,
					"is_finished_item": 0,
					"allow_zero_valuation_rate": 1,
				})
				has_items = True

			# ── Row 2: Prime Strain (finished good) ──
			prime_qty = flt(row.prime_inventory_total_tolled)
			if prime_qty > 0 and row.prime_strain:
				se.append("items", {
					"item_code": row.prime_strain,
					"qty": prime_qty,
					"t_warehouse": self.target_warehouse,
					"is_finished_item": 1,
				})
				has_items = True

			# ── Row 3: Subprime Strain (finished good) ──
			subprime_qty = flt(row.subprime_total_tolled)
			if subprime_qty > 0 and row.subprime_strain:
				se.append("items", {
					"item_code": row.subprime_strain,
					"qty": subprime_qty,
					"t_warehouse": self.target_warehouse,
					"is_finished_item": 1,
				})
				has_items = True

		if not has_items:
			frappe.msgprint(
				_("No items to create Stock Entry. Please ensure strain names and quantities are filled."),
				alert=True
			)
			return

		# ── Additional Cost: Tolling Partner Charges ──
		if flt(self.tolling_partner_charges) > 0 and self.expense_account:
			se.append("additional_costs", {
				"expense_account": self.expense_account,
				"description": "Tolling Partner Charges",
				"amount": flt(self.tolling_partner_charges),
			})

		se.insert(ignore_permissions=True)
		frappe.msgprint(
			_("Draft Stock Entry {0} created.").format(
				f'<a href="/app/stock-entry/{se.name}">{se.name}</a>'
			),
			alert=True,
		)


@frappe.whitelist()
def get_stock_balance_items(project, warehouse):
	if not project or not warehouse:
		return []

	from erpnext.stock.report.stock_balance.stock_balance import execute

	filters = frappe._dict({
		"from_date": "2000-01-01",
		"to_date": frappe.utils.today(),
		"warehouse": [warehouse],
		"project": [project],
		"company": "Motley Terpz",
	})

	_columns, data = execute(filters)

	return [
		{
			"item_code": row.get("item_code"),
			"item_name": row.get("item_name") or frappe.db.get_value("Item", row.get("item_code"), "item_name") or row.get("item_code"),
			"bal_qty": flt(row.get("bal_qty")),
			"posting_date": frappe.db.get_value("Stock Ledger Entry", {
				"item_code": row.get("item_code"),
				"warehouse": warehouse,
				"project": project,
				"is_cancelled": 0
			}, "posting_date", order_by="posting_date desc")
		}
		for row in (data or [])
		if flt(row.get("bal_qty")) > 0
	]