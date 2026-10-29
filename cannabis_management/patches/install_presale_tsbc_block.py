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
	if not any((b.get("data") or {}).get("custom_block_name") == BLOCK for b in content):
		content.append(
			{
				"id": frappe.generate_hash(length=10),
				"type": "custom_block",
				"data": {"custom_block_name": BLOCK, "col": 12},
			}
		)
		ws.content = json.dumps(content)

	if BLOCK not in [cb.custom_block_name for cb in ws.custom_blocks]:
		ws.append("custom_blocks", {"custom_block_name": BLOCK, "label": BLOCK})

	ws.roles = [r for r in ws.roles if frappe.db.exists("Role", r.role)]

	ws.save(ignore_permissions=True)
	frappe.clear_cache()
