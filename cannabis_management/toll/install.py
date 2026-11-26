"""Master data for toll processing (spec 'Master data setup'). Runs after every migrate; idempotent.

Creates only what is missing and never changes a record a user has edited, except the few flags the toll flow
depends on (customer provided, batch, zero valuation) which are re-asserted on the three toll stock items.
"""
import json

import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

from cannabis_management.toll.constants import (
	ABBR,
	COMPANY,
	CUSTOMER_GROUP,
	GENERIC_CUSTOMER,
	INCOME_ACCOUNT,
	ITEM_BH,
	ITEM_FF,
	ITEM_GROUP,
	ITEM_ROSIN,
	ITEM_SVC,
	RETURN_EXPENSE_ACCOUNT,
	UOM_FF,
	UOM_G,
	WH_GROUP,
	WH_INBOUND,
	WH_OUTPUT,
	WH_WIP,
)

COGS_REPORT = "Repack Conversion COGS (A to B)"


def custom_fields():
	toll_dep = "eval:doc.toll_job"
	return {
		"Stock Entry": [
			dict(fieldname="toll_job", label="Toll Job", fieldtype="Link", options="Toll Job", insert_after="stock_entry_type",
				search_index=1, no_copy=1, allow_on_submit=0, description="Customer-owned material: set by the Toll Processing Board."),
			dict(fieldname="toll_section", label="Toll Processing", fieldtype="Section Break", insert_after="remarks",
				collapsible=1, depends_on=toll_dep),
			dict(fieldname="wash_date", label="Wash Date", fieldtype="Date", insert_after="toll_section", no_copy=1),
			dict(fieldname="washer", label="Washer", fieldtype="Data", insert_after="wash_date", no_copy=1),
			dict(fieldname="wash_notes", label="Wash Notes", fieldtype="Small Text", insert_after="washer", no_copy=1),
			dict(fieldname="toll_column_break", fieldtype="Column Break", insert_after="wash_notes"),
			dict(fieldname="press_date", label="Press Date", fieldtype="Date", insert_after="toll_column_break", no_copy=1),
			dict(fieldname="press_notes", label="Press Notes", fieldtype="Small Text", insert_after="press_date", no_copy=1),
		],
		"Delivery Note": [
			dict(fieldname="toll_job", label="Toll Job", fieldtype="Link", options="Toll Job", insert_after="customer_name",
				search_index=1, no_copy=1, description="Return of customer-owned material: set by the Toll Processing Board."),
			dict(fieldname="toll_return_section", label="Toll Return", fieldtype="Section Break", insert_after="toll_job",
				collapsible=0, depends_on=toll_dep),
			dict(fieldname="outbound_manifest", label="Outbound METRC Manifest", fieldtype="Data", insert_after="toll_return_section", no_copy=1),
			dict(fieldname="driver_name", label="Driver", fieldtype="Data", insert_after="outbound_manifest", no_copy=1),
			dict(fieldname="toll_return_column_break", fieldtype="Column Break", insert_after="driver_name"),
			dict(fieldname="outbound_tags", label="Outbound METRC Tags", fieldtype="Small Text", insert_after="toll_return_column_break", no_copy=1),
		],
		"Sales Invoice": [
			dict(fieldname="toll_job", label="Toll Job", fieldtype="Link", options="Toll Job", insert_after="customer_name",
				search_index=1, no_copy=0, description="Toll processing service invoice."),
		],
		"Material Request": [
			dict(fieldname="toll_job", label="Toll Job", fieldtype="Link", options="Toll Job", insert_after="material_request_type",
				search_index=1, no_copy=1, depends_on="eval:doc.material_request_type=='Customer Provided'"),
		],
		"Batch": [
			dict(fieldname="toll_section", label="Toll Processing", fieldtype="Section Break", insert_after="description",
				collapsible=0, depends_on=toll_dep),
			dict(fieldname="toll_job", label="Toll Job", fieldtype="Link", options="Toll Job", insert_after="toll_section",
				search_index=1, read_only=1, no_copy=1),
			dict(fieldname="toll_customer", label="Toll Customer", fieldtype="Link", options="Customer", insert_after="toll_job",
				read_only=1, no_copy=1),
			dict(fieldname="strain", label="Strain", fieldtype="Data", insert_after="toll_customer", read_only=1, no_copy=1),
		],
	}


def install():
	if not frappe.db.exists("Company", COMPANY) or not frappe.db.exists("DocType", "Toll Job"):
		return
	frappe.local._toll_warehouses = None
	create_custom_fields(custom_fields(), ignore_validate=True, update=True)
	_customer_group()
	_item_group()
	_warehouses()
	_income_account()
	_items()
	_cogs_report_exclusion()
	_hub_block()
	_workspace_shortcut()
	frappe.local._toll_warehouses = None
	frappe.db.commit()


def _insert(doc, set_name=None):
	doc = frappe.get_doc(doc)
	doc.flags.ignore_permissions = True
	doc.insert(set_name=set_name)  # set_name: Items are named by naming series on this site; toll items need their codes
	return doc


def _customer_group():
	if not frappe.db.exists("Customer Group", CUSTOMER_GROUP):
		_insert({"doctype": "Customer Group", "customer_group_name": CUSTOMER_GROUP, "parent_customer_group": "All Customer Groups", "is_group": 0})
	if not frappe.db.exists("Customer", GENERIC_CUSTOMER):
		_insert({"doctype": "Customer", "customer_name": GENERIC_CUSTOMER, "customer_group": CUSTOMER_GROUP, "customer_type": "Company",
			"disabled": 0})


def _item_group():
	if not frappe.db.exists("Item Group", ITEM_GROUP):
		_insert({"doctype": "Item Group", "item_group_name": ITEM_GROUP, "parent_item_group": "All Item Groups", "is_group": 0})


def _warehouses():
	parent = frappe.db.get_value("Warehouse", {"company": COMPANY, "is_group": 1, "parent_warehouse": ["in", ["", None]]}, "name") \
		or "All Warehouses - " + ABBR
	if not frappe.db.exists("Warehouse", WH_GROUP):
		_insert({"doctype": "Warehouse", "warehouse_name": WH_GROUP.rsplit(" - ", 1)[0], "company": COMPANY, "is_group": 1,
			"parent_warehouse": parent})
	for wh in (WH_INBOUND, WH_WIP, WH_OUTPUT):
		if not frappe.db.exists("Warehouse", wh):
			_insert({"doctype": "Warehouse", "warehouse_name": wh.rsplit(" - ", 1)[0], "company": COMPANY, "is_group": 0,
				"parent_warehouse": WH_GROUP})


def _income_account():
	if not frappe.db.exists("Account", RETURN_EXPENSE_ACCOUNT):
		cogs = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 1, "account_name": "Cost of Goods Sold"}, "name") \
			or frappe.db.get_value("Account", {"company": COMPANY, "is_group": 1, "root_type": "Expense", "parent_account": ["in", ["", None]]}, "name")
		_insert({"doctype": "Account", "account_name": RETURN_EXPENSE_ACCOUNT.rsplit(" - ", 1)[0], "company": COMPANY, "parent_account": cogs,
			"is_group": 0, "root_type": "Expense", "report_type": "Profit and Loss"})
	if frappe.db.exists("Account", INCOME_ACCOUNT):
		return
	parent = frappe.db.get_value("Account", {"company": COMPANY, "is_group": 1, "account_name": "Direct Income"}, "name") \
		or frappe.db.get_value("Account", {"company": COMPANY, "is_group": 1, "root_type": "Income", "parent_account": ["in", ["", None]]}, "name")
	_insert({"doctype": "Account", "account_name": INCOME_ACCOUNT.rsplit(" - ", 1)[0], "company": COMPANY, "parent_account": parent,
		"is_group": 0, "root_type": "Income", "report_type": "Profit and Loss", "account_type": "Income Account"})


STOCK_ITEMS = (
	(ITEM_FF, "Toll Fresh Frozen", UOM_FF, WH_INBOUND, 0),
	(ITEM_BH, "Toll Bubble Hash", UOM_G, WH_OUTPUT, 1),
	(ITEM_ROSIN, "Toll Rosin", UOM_G, WH_OUTPUT, 1),
)
TOLL_FLAGS = {"is_stock_item": 1, "has_batch_no": 1, "create_new_batch": 0, "is_customer_provided_item": 1,
	"is_purchase_item": 0, "valuation_rate": 0, "customer": GENERIC_CUSTOMER, "item_group": ITEM_GROUP, "disabled": 0}


def _items():
	for code, name, uom, wh, sales in STOCK_ITEMS:
		if not frappe.db.exists("Item", code):
			_insert({"doctype": "Item", "item_code": code, "item_name": name, "description": name + " (customer-owned, zero value)",
				"stock_uom": uom, "is_sales_item": sales, "include_item_in_manufacturing": 0, **TOLL_FLAGS,
				"item_defaults": [{"company": COMPANY, "default_warehouse": wh}]}, set_name=code)
		else:
			cur = frappe.db.get_value("Item", code, list(TOLL_FLAGS), as_dict=True)
			diff = {k: v for k, v in TOLL_FLAGS.items() if str(cur.get(k) or "") != str(v or "") and not (k == "valuation_rate" and not cur.get(k))}
			if diff:
				frappe.db.set_value("Item", code, diff)
	# expense account on the toll stock items: MTM has no default COGS account, and a zero-value Delivery Note still
	# needs a P&L account per row. Toll Material Returns - MTM never receives an amount.
	if frappe.db.exists("Account", RETURN_EXPENSE_ACCOUNT):
		stock_adj = frappe.db.get_value("Company", COMPANY, "stock_adjustment_account")
		for code, *_rest in STOCK_ITEMS:
			for d in frappe.get_all("Item Default", filters={"parent": code, "parenttype": "Item", "company": COMPANY},
					fields=["name", "expense_account"]):
				if not d.expense_account or d.expense_account == stock_adj:
					frappe.db.set_value("Item Default", d.name, "expense_account", RETURN_EXPENSE_ACCOUNT)
	if not frappe.db.exists("Item", ITEM_SVC):
		_insert({"doctype": "Item", "item_code": ITEM_SVC, "item_name": "Toll Processing Service",
			"description": "Toll processing service (washing / pressing of customer-owned material)",
			"item_group": "Services" if frappe.db.exists("Item Group", "Services") else "All Item Groups",
			"stock_uom": "Nos", "is_stock_item": 0, "is_sales_item": 1, "is_purchase_item": 0, "include_item_in_manufacturing": 0,
			"uoms": [{"uom": "Nos", "conversion_factor": 1}, {"uom": UOM_FF, "conversion_factor": 1}, {"uom": UOM_G, "conversion_factor": 1}],
			# a valid MTM warehouse, or ERPNext fills the row from the session default (another company)
			"item_defaults": [{"company": COMPANY, "income_account": INCOME_ACCOUNT,
				"default_warehouse": frappe.db.get_value("Warehouse", {"company": COMPANY, "warehouse_name": "Stores", "is_group": 0}) or WH_OUTPUT}]},
			set_name=ITEM_SVC)


def _cogs_report_exclusion():
	"""Repack Conversion COGS (A to B) is a site query report: leave toll repacks (zero value) out of it."""
	q = frappe.db.get_value("Report", COGS_REPORT, "query")
	if not q or ITEM_GROUP in q:
		return
	anchor = "AND se.purpose = 'Repack'"
	if anchor not in q:
		return
	q = q.replace(anchor, anchor + "\n    AND d.item_code NOT IN (SELECT i.name FROM `tabItem` i WHERE i.item_group = '{0}')".format(ITEM_GROUP), 1)
	frappe.db.set_value("Report", COGS_REPORT, "query", q)


def _workspace_shortcut():
	"""Toll Processing Board shortcut on the Manufacturing workspace, after the Press Plan Board."""
	if not frappe.db.exists("Workspace", "Manufacturing") or not frappe.db.exists("Page", "toll-processing-board"):
		return
	ws = frappe.get_doc("Workspace", "Manufacturing")
	if any(s.link_to == "toll-processing-board" for s in ws.shortcuts):
		return
	ws.append("shortcuts", {"label": "Toll Processing Board", "type": "Page", "link_to": "toll-processing-board", "color": "Green"})
	content = json.loads(ws.content or "[]")
	at = next((i + 1 for i, b in enumerate(content) if b.get("id") in ("press-plan-board",)), None)
	if at is None:
		at = next((i + 1 for i, b in enumerate(content) if b.get("id") == "wash-plan-board"), 0)
	content.insert(at, {"id": "toll-processing-board", "type": "shortcut", "data": {"shortcut_name": "Toll Processing Board", "col": 3}})
	ws.content = json.dumps(content)
	ws.flags.ignore_permissions = True
	ws.save()


HUB_BLOCK = "Toll Processing Hub"


def _hub_block():
	"""The Toll Processing workspace hub (Custom HTML Block), kept equal to cannabis_management/toll/hub/."""
	import os
	base = os.path.join(os.path.dirname(__file__), "hub")
	read = lambda f: open(os.path.join(base, f), encoding="utf-8").read()
	want = {"html": read("hub.html"), "style": read("hub.css"), "script": read("hub.js"), "private": 0}
	if not frappe.db.exists("Custom HTML Block", HUB_BLOCK):
		doc = frappe.new_doc("Custom HTML Block")
		doc.name = HUB_BLOCK
		doc.update(want)
		doc.flags.ignore_permissions = True
		doc.insert(set_name=HUB_BLOCK)
		return
	cur = frappe.db.get_value("Custom HTML Block", HUB_BLOCK, list(want), as_dict=True)
	diff = {k: v for k, v in want.items() if (cur.get(k) or 0 if k == "private" else cur.get(k) or "") != v}
	if diff:
		frappe.db.set_value("Custom HTML Block", HUB_BLOCK, diff)
