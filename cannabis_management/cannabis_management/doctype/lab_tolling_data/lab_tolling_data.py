# Copyright (c) 2026, Your Company and contributors
# For license information, please see license.txt

import frappe
from frappe.model.document import Document


class LabTollingData(Document):
	"""
	Child table controller for Lab Tolling Data.
	Calculations run server-side on every save of the parent (All Lab Tolling Data).
	"""

	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		"""Calculate all derived/formula fields."""

		# ── Helper: safe float conversion ─────────────────────────────────
		def f(val):
			try:
				return float(val or 0)
			except (ValueError, TypeError):
				return 0.0

		# ── 1. Total Hash ──────────────────────────────────────────────────
		# Total Hash = 150u + 120u + 90u + 73u + 45u + 25u Hash
		total_hash = (
			f(self.get("150u_hash"))
			+ f(self.get("120u_hash"))
			+ f(self.get("90u_hash"))
			+ f(self.get("73u_hash"))
			+ f(self.get("45u_hash"))
			+ f(self.get("25u_hash_copy"))
		)
		self.total_hash = total_hash

		# ── 2. Total Rosin ─────────────────────────────────────────────────
		# Total Rosin = 150u + 120u + 90u + 73u + 45u + 25u Rosin
		total_rosin = (
			f(self.get("150u_rosin"))
			+ f(self.get("120u_rosin"))
			+ f(self.get("90u_rosin"))
			+ f(self.get("73u_rosin"))
			+ f(self.get("45u_rosin"))
			+ f(self.get("25u_rosin"))
		)
		self.total_rosin = total_rosin

		# ── 3. Pounds Ran ──────────────────────────────────────────────────
		# Pounds Ran = Amount Ran Grams / 453.592
		amount_ran_grams = f(self.amount_ran_grams)
		if amount_ran_grams:
			self.pounds_ran = round(amount_ran_grams / 453.592, 4)
		else:
			self.pounds_ran = 0

		# ── 4. Yield % to Hash ────────────────────────────────────────────
		# Yield to Hash = (Total Hash / Amount Ran Grams) * 100
		if amount_ran_grams:
			self.yield_to_hash = str(round((total_hash / amount_ran_grams) * 100, 2)) + "%"
		else:
			self.yield_to_hash = "0%"

		# ── 5. Hash to Rosin % ────────────────────────────────────────────
		# Hash to Rosin % = (Total Rosin / Total Hash) * 100
		if total_hash:
			self.hash_to_rosin_ = round((total_rosin / total_hash) * 100, 2)
		else:
			self.hash_to_rosin_ = 0

		# NOTE: rosin_yield_ is manually entered — no calculation applied

		# ── 6. Subprime Total Tolled ──────────────────────────────────────
		# Subprime = 45u Rosin + 150u Rosin
		self.subprime_total_tolled = str(
			f(self.get("45u_rosin")) + f(self.get("150u_rosin"))
		)

		# ── 7. Prime Inventory Total Tolled ───────────────────────────────
		# Prime = 73u Rosin + 90u Rosin
		self.prime_inventory_total_tolled = str(
			f(self.get("73u_rosin")) + f(self.get("90u_rosin"))
		)

		# ── 8. Yield % (overall) ──────────────────────────────────────────
		# Yield % = (Total Rosin / Total Hash) * 100
		if total_hash:
			self.yield_ = round((total_rosin / total_hash) * 100, 2)
		else:
			self.yield_ = 0