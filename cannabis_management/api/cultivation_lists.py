import frappe
from frappe import _
from frappe.utils import cint, flt, nowdate


@frappe.whitelist()
def teardown_stats(names):
	"""Per-teardown plant count, recorded weight and reviewed/total harvests,
	read from the existing Teardown child tables."""
	names = frappe.parse_json(names) if isinstance(names, str) else names
	out = {}
	for n in names or []:
		frappe.has_permission("Teardown", "read", n, throw=True)
		hb = frappe.get_all("Teardown Harvest Batch", filters={"parent": n, "parenttype": "Teardown"},
			fields=["wet_weight", "plant_count", "sync_status"])
		tags = frappe.db.count("Teardown Tag", {"parent": n})
		out[n] = {
			"plants": tags or sum(cint(h.plant_count) for h in hb),
			"weight": sum(flt(h.wet_weight) for h in hb),
			"harvests": len(hb),
			"reviewed": sum(1 for h in hb if h.sync_status == "Synced"),
		}
	return out


@frappe.whitelist()
def create_packages_from_harvest(harvest_batch, packages, owner=None, destination=None, description=None):
	"""Create one Metrc Package per row ({tag, item_code, quantity, uom}) from a
	Harvest Batch and roll the quantity into its packaged_weight (status is derived by Harvest Batch.validate)."""
	packages = frappe.parse_json(packages) if isinstance(packages, str) else packages
	if not packages:
		frappe.throw(_("Add at least one package."))
	hb = frappe.get_doc("Harvest Batch", harvest_batch)
	hb.check_permission("write")

	total = 0
	created = []
	for row in packages:
		qty = flt(row.get("quantity"))
		if qty <= 0 or not row.get("tag"):
			frappe.throw(_("Each package needs a tag and a quantity above zero."))
		total += qty
		doc = frappe.get_doc({
			"doctype": "Metrc Package",
			"tag": row["tag"],
			"status": "Active",
			"item_code": row.get("item_code"),
			"uom": row.get("uom") or hb.weight_uom,
			"quantity": qty,
			"original_quantity": qty,
			"license": hb.licence,
			"warehouse": destination or hb.dry_room,
		}).insert()
		created.append(doc.name)

	remaining = flt(hb.dry_weight or hb.wet_weight) - flt(hb.packaged_weight) - flt(hb.waste_weight)
	if total > remaining + 1e-6:
		frappe.throw(_("Packages total {0}; only {1} left in this harvest.").format(total, remaining))

	hb.packaged_weight = flt(hb.packaged_weight) + total
	hb.save()
	if description:
		hb.add_comment("Comment", _("Packaged by {0}: {1}").format(owner or frappe.session.user, description))
	return created
