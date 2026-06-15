import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class HashRecording(Document):
	def validate(self):
		self.calculate_totals()

	def calculate_totals(self):
		self.total_quantity = sum(flt(row.pound_sent) for row in self.table_smqw)
		
		# Sync expected yields from parent to child rows if empty
		for row in self.table_smqw:
			if not row.expected_yield_to_hash:
				row.expected_yield_to_hash = self.expected_hash_yield

		# Only calculate if fields exist (we'll add them to JSON in next step)
		if hasattr(self, 'rate_tolling_partner'):
			self.tolling_partner_charges = flt(self.total_quantity) * flt(self.rate_tolling_partner)


@frappe.whitelist()
def get_stock_balance_items(project, warehouse):
	"""
	Returns items with positive stock balance for a given project + warehouse.
	Runs the Stock Balance Report with project and warehouse filters.
	"""
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

	# Return only items with positive balance qty
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


@frappe.whitelist()
def create_rosin_recording(hash_recording_name):
	hash_rec = frappe.get_doc("Hash Recording", hash_recording_name)

	if hash_rec.docstatus != 1:
		frappe.throw(_("Hash Recording must be submitted before creating a Rosin Recording."))

	# Use correct field name: hash_reference
	existing = frappe.db.exists("Rosin Recording", {"hash_reference": hash_rec.name})
	if existing:
		frappe.throw(_("A Rosin Recording <b>{0}</b> already exists for this Hash Recording.").format(existing))

	rosin_rec = frappe.new_doc("Rosin Recording")
	rosin_rec.batch = hash_rec.batchproject
	rosin_rec.tolling_partner = hash_rec.tolling_partner
	rosin_rec.hash_reference = hash_rec.name
	rosin_rec.rate_tolling_partner = flt(hash_rec.get("rate_tolling_partner"))
	rosin_rec.tolling_partner_charges = flt(hash_rec.get("tolling_partner_charges"))
	rosin_rec.total_quantity = flt(hash_rec.total_quantity)

	for row in hash_rec.table_smqw:
		child = rosin_rec.append("lab_tolling_data")
		child.strain_name = row.strain_name
		child.batch_no = row.batchproject
		child.source_bloom = row.tooling_partner
		child.pounds_sent = row.pound_sent
		child.pounds_ran = row.pounds_ran
		child.run_for = row.run_for
		child.date_transferred = row.date_transferred
		child.amount_ran_grams = row.amount_ran_grams
		child.set("150u_hash", row.get("150u_hash"))
		child.set("120u_hash", row.get("120u_hash"))
		child.set("90u_hash", row.get("90u_hash"))
		child.set("73u_hash", row.get("73u_hash"))
		child.set("45u_hash", row.get("45u_hash"))
		child.set("25u_hash_copy", row.get("25u_hash_copy"))
		child.set("expected__yield__to_hash", flt(row.get("expected_yield_to_hash")))
		child.total_hash = row.total_hash

	rosin_rec.insert(ignore_permissions=True)
	frappe.db.commit()

	return rosin_rec.name


@frappe.whitelist()
def get_hash_recording_status(hash_recording_name):
	"""Return computed status of a Hash Recording (used by JS client)."""
	doc = frappe.get_doc("Hash Recording", hash_recording_name)

	if doc.docstatus == 2:
		return "Cancelled"
	if doc.docstatus == 0:
		return "Draft"

	# Check if Rosin Recording exists
	rosin_exists = frappe.db.exists("Rosin Recording", {"hash_reference": doc.name})
	if rosin_exists:
		return "Rosin Created"

	return "Submitted"
