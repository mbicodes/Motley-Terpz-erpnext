"""Add the 'Presale' section to the TSBC Logistics workspace.

Idempotent: creates the 'Presale TSBC' Custom HTML Block (cloned from the
existing 'Pending Sales Orders TSBC' block, retitled and pointed at the
get_presale_sales_orders API), appends it to the TSBC Logistics workspace
content, and drops any orphaned workspace roles so the save goes through and
the cached workspace is refreshed.
"""

import json

import frappe

WORKSPACE = "TSBC Logistics"
BLOCK = "Presale TSBC"
TEMPLATE = "Pending Sales Orders TSBC"


def execute():
	if not frappe.db.exists("Workspace", WORKSPACE):
		return

	_ensure_block()
	_ensure_in_workspace()


def _ensure_block():
	if frappe.db.exists("Custom HTML Block", BLOCK):
		return
	if not frappe.db.exists("Custom HTML Block", TEMPLATE):
		# No template to clone from on this site — skip silently.
		return

	src = frappe.get_doc("Custom HTML Block", TEMPLATE)
	html = (src.html or "").replace(
		"Pending Orders In Sales Pipeline", "Presale Orders — TSBC"
	).replace(
		"These are sales that we have inventory on hold so we want to monitor, "
		"but it is NOT ready for any logistics.",
		"Sales Orders flagged as Presale (sold ahead of fulfilment) for TSBC Ranch.",
	)
	script = (src.script or "").replace("get_pending_sales_orders", "get_presale_sales_orders")

	block = frappe.new_doc("Custom HTML Block")
	block.name = BLOCK
	block.flags.name_set = True
	block.html = html
	block.script = script
	block.style = src.style
	block.insert(ignore_permissions=True)


def _ensure_in_workspace():
	ws = frappe.get_doc("Workspace", WORKSPACE)

	content = json.loads(ws.content or "[]")
	present = any((b.get("data") or {}).get("custom_block_name") == BLOCK for b in content)
	if not present:
		content.append(
			{
				"id": frappe.generate_hash(length=10),
				"type": "custom_block",
				"data": {"custom_block_name": BLOCK, "col": 12},
			}
		)
		ws.content = json.dumps(content)

	# Drop orphaned roles (referencing deleted Role records) so save() validates.
	ws.roles = [r for r in ws.roles if frappe.db.exists("Role", r.role)]

	# A real save() fires on_update, which clears the cached workspace so the
	# new block actually renders (a raw db_set does not).
	ws.save(ignore_permissions=True)
	frappe.clear_cache()
