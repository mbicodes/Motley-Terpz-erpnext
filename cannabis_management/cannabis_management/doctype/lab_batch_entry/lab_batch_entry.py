import frappe
from frappe import _
from frappe.model.document import Document
from frappe.utils import flt


class LabBatchEntry(Document):
	def on_update_after_submit(self):
		"""
		Sync any child row updates to the linked Hash Recording child rows.
		Only marks batch_run = 1 if a Hash Recording exists and rows were updated.
		"""
		hash_rec_name = frappe.db.get_value("Hash Recording", {"lab_batch_refrence": self.name}, "name")

		if not hash_rec_name:
			# No Hash Recording yet — do not set batch_run, status stays Batch Sent
			return

		hash_doc = frappe.get_doc("Hash Recording", hash_rec_name)
		doc_updated = False

		for lab_row in self.lab_batch_entry_child:
			for hash_row in hash_doc.table_smqw:
				if hash_row.strain_name == lab_row.strain_name and flt(hash_row.pound_sent) == flt(lab_row.pounds_sent):
					if (flt(hash_row.amount_ran_grams) != flt(lab_row.amount_ran_grams) or
						flt(hash_row.pounds_ran) != flt(lab_row.pounds_ran) or
						hash_row.date_transferred != lab_row.date_transferred or
						hash_row.run_for != lab_row.run_for):

						hash_row.amount_ran_grams = lab_row.amount_ran_grams
						hash_row.pounds_ran = lab_row.pounds_ran
						hash_row.date_transferred = lab_row.date_transferred
						hash_row.run_for = lab_row.run_for
						doc_updated = True
					break

		if doc_updated:
			hash_doc.flags.ignore_permissions = True
			hash_doc.save()

			# Only set batch_run here — after Hash Recording exists and rows updated
			frappe.db.set_value("Lab Batch Entry", self.name, "batch_run", 1, update_modified=False)

			frappe.msgprint(_("Linked Hash Recording row updated: {0}").format(
				f'<a href="/app/hash-recording/{hash_rec_name}">{hash_rec_name}</a>'
			), alert=True)


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


@frappe.whitelist()
def create_hash_recording(lab_batch_entry_name):
	lab_batch = frappe.get_doc("Lab Batch Entry", lab_batch_entry_name)

	if lab_batch.docstatus != 1:
		frappe.throw(_("Lab Batch Entry must be submitted before creating a Hash Recording."))

	existing = frappe.db.exists("Hash Recording", {"lab_batch_refrence": lab_batch.name})
	if existing:
		frappe.throw(_("A Hash Recording <b>{0}</b> already exists for this Lab Batch Entry.").format(existing))

	hash_rec = frappe.new_doc("Hash Recording")
	hash_rec.batchproject = lab_batch.batchproject
	hash_rec.tolling_partner = lab_batch.tolling_partner
	hash_rec.lab_batch_refrence = lab_batch.name

	for row in lab_batch.lab_batch_entry_child:
		child = hash_rec.append("table_smqw")
		child.strain_name = row.strain_name
		child.batchproject = row.batch_number
		child.tooling_partner = row.tolling_partner
		child.pound_sent = row.pounds_sent
		child.pounds_ran = row.pounds_ran
		child.run_for = row.run_for
		child.date_transferred = row.date_transferred
		child.amount_ran_grams = row.amount_ran_grams

	hash_rec.insert(ignore_permissions=True)
	frappe.db.commit()

	return hash_rec.name


@frappe.whitelist()
def create_rosin_recording(lab_batch_entry_name):
	lab_batch = frappe.get_doc("Lab Batch Entry", lab_batch_entry_name)

	hash_rec = frappe.db.get_value(
		"Hash Recording",
		{"lab_batch_refrence": lab_batch.name, "docstatus": 1},
		["name", "batchproject", "tolling_partner"],
		as_dict=True
	)

	if not hash_rec:
		frappe.throw(_("A submitted Hash Recording is required before creating a Rosin Recording."))

	existing = frappe.db.exists("Rosin Recording", {"hash_reference": hash_rec.name})
	if existing:
		frappe.throw(_("A Rosin Recording <b>{0}</b> already exists for this Hash Recording.").format(existing))

	hash_doc = frappe.get_doc("Hash Recording", hash_rec.name)

	rosin_rec = frappe.new_doc("Rosin Recording")
	rosin_rec.batch = hash_rec.batchproject
	rosin_rec.tolling_partner = hash_rec.tolling_partner
	rosin_rec.hash_reference = hash_rec.name

	for row in hash_doc.table_smqw:
		child = rosin_rec.append("lab_tolling_data")
		child.strain_name = row.strain_name
		child.batch_no = row.batchproject
		child.source_bloom = row.tooling_partner
		child.pounds_sent = row.pound_sent
		child.pounds_ran = row.pounds_ran
		child.run_for = row.run_for
		child.date_transferred = row.date_transferred
		child.amount_ran_grams = row.amount_ran_grams

	rosin_rec.insert(ignore_permissions=True)
	frappe.db.commit()

	return rosin_rec.name


@frappe.whitelist()
def get_batch_status(lab_batch_entry_name):
	docstatus = frappe.db.get_value("Lab Batch Entry", lab_batch_entry_name, "docstatus")

	if docstatus == 0:
		return "Draft"
	if docstatus == 2:
		return "Cancelled"

	# Check Hash Recording
	hash_rec = frappe.db.get_value(
		"Hash Recording",
		{"lab_batch_refrence": lab_batch_entry_name},
		["name", "docstatus"],
		as_dict=True
	)

	if hash_rec:
		rosin_rec = frappe.db.get_value(
			"Rosin Recording",
			{"hash_reference": hash_rec.name},
			["name", "docstatus"],
			as_dict=True
		)
		if rosin_rec and rosin_rec.docstatus == 1:
			return "Rosin Produced"

		if hash_rec.docstatus == 1:
			return "Hash Produced"

	# No submitted Hash Recording — check if any child row has amount_ran_grams filled
	has_amount_ran = frappe.db.sql("""
		SELECT 1 FROM `tabLab Batch Entry Child`
		WHERE parent = %s
		AND CAST(amount_ran_grams AS DECIMAL(10,4)) > 0
		LIMIT 1
	""", lab_batch_entry_name)

	if has_amount_ran:
		return "Batch Run"

	return "Batch Sent"