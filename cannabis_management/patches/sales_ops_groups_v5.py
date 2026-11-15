# Sales Operation Board v5 (16 Nov 2026): product lines get a Group so the board totals Extracts, Fresh Frozen and
# Tolling separately. Fresh Frozen and Tolling keep their own name; every other line is an extract. Only empty groups
# are filled, so a group set by hand stays. Safe to run twice.

import frappe

OWN = ("fresh frozen", "tolling")


def execute():
	frappe.reload_doc("cannabis_management", "doctype", "sales_pipeline_product_line")
	doc = frappe.get_single("Sales Pipeline Settings")
	changed = False
	for row in doc.product_lines:
		if (row.get("product_group") or "").strip():
			continue
		name = (row.product_line or "").strip()
		row.product_group = name if name.lower() in OWN else "Extracts"
		changed = True
	if changed:
		doc.flags.ignore_permissions = True
		doc.save()
