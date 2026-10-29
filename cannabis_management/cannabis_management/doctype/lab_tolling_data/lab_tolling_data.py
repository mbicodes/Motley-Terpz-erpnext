import frappe
from frappe.model.document import Document


class LabTollingData(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		def f(val):
			try:
				return float(val or 0)
			except (ValueError, TypeError):
				return 0.0

		total_hash = (
			f(self.get("150u_hash"))
			+ f(self.get("120u_hash"))
			+ f(self.get("90u_hash"))
			+ f(self.get("73u_hash"))
			+ f(self.get("45u_hash"))
			+ f(self.get("25u_hash_copy"))
		)
		self.total_hash = total_hash

		total_rosin = (
			f(self.get("150u_rosin"))
			+ f(self.get("120u_rosin"))
			+ f(self.get("90u_rosin"))
			+ f(self.get("73u_rosin"))
			+ f(self.get("45u_rosin"))
			+ f(self.get("25u_rosin"))
		)
		self.total_rosin = total_rosin

		amount_ran_grams = f(self.amount_ran_grams)
		if amount_ran_grams:
			self.pounds_ran = round(amount_ran_grams / 453.592, 4)
		else:
			self.pounds_ran = 0

		if amount_ran_grams:
			self.yield_to_hash = str(round((total_hash / amount_ran_grams) * 100, 2)) + "%"
		else:
			self.yield_to_hash = "0%"

		if total_hash:
			self.hash_to_rosin_ = round((total_rosin / total_hash) * 100, 2)
		else:
			self.hash_to_rosin_ = 0

		self.subprime_total_tolled = str(
			f(self.get("45u_rosin")) + f(self.get("150u_rosin"))
		)

		self.prime_inventory_total_tolled = str(
			f(self.get("73u_rosin")) + f(self.get("90u_rosin"))
		)

		if total_hash:
			self.yield_ = round((total_rosin / total_hash) * 100, 2)
		else:
			self.yield_ = 0
