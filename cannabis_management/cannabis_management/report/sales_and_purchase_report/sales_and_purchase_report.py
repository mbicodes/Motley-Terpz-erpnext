import frappe
from frappe import _
from frappe.utils import flt


def execute(filters=None):
	filters = frappe._dict(filters or {})

	if filters.get("type") == "Cost Reconciliation":
		columns = get_cost_reconciliation_columns()
		data = get_cost_reconciliation_data(filters)
		report_summary = get_cost_reconciliation_summary(data)
		return columns, data, None, None, report_summary

	columns = get_columns(filters)
	data = get_data(filters)
	report_summary = get_report_summary(data)
	return columns, data, None, None, report_summary


def get_columns(filters):
	is_purchase = filters.get("type") == "Purchase"
	party_label = _("Supplier") if is_purchase else _("Customer")
	party_doctype = "Supplier" if is_purchase else "Customer"

	return [
		{"label": _("Date"), "fieldname": "date", "fieldtype": "Date", "width": 100},
		{"label": party_label, "fieldname": "party", "fieldtype": "Link", "options": party_doctype, "width": 160},
		{
			"label": _("Invoice No"),
			"fieldname": "invoice_no",
			"fieldtype": "Dynamic Link",
			"options": "invoice_doctype",
			"width": 160,
		},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 220},
		{"label": _("Qty"), "fieldname": "qty", "fieldtype": "Float", "width": 100},
		{"label": _("Amount"), "fieldname": "amount", "fieldtype": "Currency", "width": 130},
	]


def get_data(filters):
	is_purchase = filters.get("type") == "Purchase"
	doctype = "Purchase Invoice" if is_purchase else "Sales Invoice"
	child_doctype = f"{doctype} Item"
	party_field = "supplier" if is_purchase else "customer"

	conditions = ["parent_tab.docstatus = 1"]
	params = {}

	if filters.get("from_date"):
		conditions.append("parent_tab.posting_date >= %(from_date)s")
		params["from_date"] = filters.from_date
	if filters.get("to_date"):
		conditions.append("parent_tab.posting_date <= %(to_date)s")
		params["to_date"] = filters.to_date
	if filters.get("party"):
		conditions.append(f"parent_tab.{party_field} = %(party)s")
		params["party"] = filters.party
	if filters.get("company"):
		conditions.append("parent_tab.company = %(company)s")
		params["company"] = filters.company

	return frappe.db.sql(
		f"""
		SELECT
			parent_tab.posting_date AS date,
			parent_tab.name AS invoice_no,
			'{doctype}' AS invoice_doctype,
			parent_tab.{party_field} AS party,
			child_tab.item_name AS item_name,
			child_tab.qty AS qty,
			child_tab.amount AS amount
		FROM `tab{doctype}` parent_tab
		INNER JOIN `tab{child_doctype}` child_tab ON child_tab.parent = parent_tab.name
		WHERE {" AND ".join(conditions)}
		ORDER BY parent_tab.posting_date DESC, parent_tab.name DESC
	""",
		params,
		as_dict=True,
	)


def get_report_summary(data):
	if not data:
		return None

	total_qty = sum(flt(d.get("qty")) for d in data)
	total_amount = sum(flt(d.get("amount")) for d in data)
	total_invoices = len({d.get("invoice_no") for d in data})

	return [
		{"label": _("Total Invoices"), "value": total_invoices, "indicator": "Blue", "datatype": "Int"},
		{"label": _("Total Qty"), "value": total_qty, "indicator": "Blue", "datatype": "Float"},
		{"label": _("Total Amount"), "value": total_amount, "indicator": "Green", "datatype": "Currency"},
	]


# ── Cost Reconciliation (Opening / Purchase / Consumption / Closing / Sales / COGS) ──


def get_cost_reconciliation_columns():
	return [
		{"label": _("Item Code"), "fieldname": "item_code", "fieldtype": "Link", "options": "Item", "width": 150},
		{"label": _("Item Name"), "fieldname": "item_name", "fieldtype": "Data", "width": 180},
		{"label": _("Opening Qty"), "fieldname": "opening_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Opening Value"), "fieldname": "opening_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Purchase Qty"), "fieldname": "purchase_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Purchase Value"), "fieldname": "purchase_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Consumption Qty"), "fieldname": "consumption_qty", "fieldtype": "Float", "width": 110},
		{"label": _("Consumption Value"), "fieldname": "consumption_value", "fieldtype": "Currency", "width": 130},
		{"label": _("Closing Qty"), "fieldname": "closing_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Closing Value"), "fieldname": "closing_value", "fieldtype": "Currency", "width": 120},
		{"label": _("Sales Qty"), "fieldname": "sales_qty", "fieldtype": "Float", "width": 100},
		{"label": _("Revenue"), "fieldname": "revenue", "fieldtype": "Currency", "width": 120},
		{"label": _("COGS"), "fieldname": "cogs", "fieldtype": "Currency", "width": 120},
		{"label": _("Gross Profit"), "fieldname": "gross_profit", "fieldtype": "Currency", "width": 120},
		{"label": _("Gross Profit %"), "fieldname": "gross_profit_percent", "fieldtype": "Percent", "width": 110},
		{"label": _("Revenue Share %"), "fieldname": "revenue_share_percent", "fieldtype": "Percent", "width": 120},
		{
			"label": _("Reconciliation Variance"),
			"fieldname": "reconciliation_variance",
			"fieldtype": "Currency",
			"width": 160,
		},
	]


def get_cost_reconciliation_data(filters):
	from erpnext.stock.report.stock_balance.stock_balance import StockBalanceReport

	items = {}

	def bucket(item_code, item_name=None):
		return items.setdefault(
			item_code,
			frappe._dict(
				{
					"item_code": item_code,
					"item_name": item_name or item_code,
					"opening_qty": 0,
					"opening_value": 0,
					"purchase_qty": 0,
					"purchase_value": 0,
					"consumption_qty": 0,
					"consumption_value": 0,
					"closing_qty": 0,
					"closing_value": 0,
					"sales_qty": 0,
					"revenue": 0,
					"cogs": 0,
				}
			),
		)

	# Opening / Closing — reuse ERPNext's own stock balance engine (same approach as
	# this app's existing Custom Stock Balance report), aggregated across warehouses.
	sb_filters = frappe._dict(
		{"company": filters.get("company"), "from_date": filters.from_date, "to_date": filters.to_date}
	)
	_, stock_rows = StockBalanceReport(sb_filters).run()
	for r in stock_rows:
		if not r.get("item_code"):
			continue
		b = bucket(r.get("item_code"), r.get("item_name"))
		b.opening_qty += flt(r.get("opening_qty"))
		b.opening_value += flt(r.get("opening_val"))
		b.closing_qty += flt(r.get("bal_qty"))
		b.closing_value += flt(r.get("bal_val"))

	params = {"from_date": filters.from_date, "to_date": filters.to_date}
	if filters.get("company"):
		params["company"] = filters.company

	def company_condition(parent_alias):
		return f"AND {parent_alias}.company = %(company)s" if filters.get("company") else ""

	# Purchases
	purchase_rows = frappe.db.sql(
		f"""
		SELECT
			child_tab.item_code, child_tab.item_name,
			SUM(child_tab.stock_qty) AS qty,
			SUM(child_tab.base_net_amount) AS value
		FROM `tabPurchase Invoice Item` child_tab
		INNER JOIN `tabPurchase Invoice` parent_tab ON parent_tab.name = child_tab.parent
		WHERE parent_tab.docstatus = 1
			AND parent_tab.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{company_condition("parent_tab")}
		GROUP BY child_tab.item_code
	""",
		params,
		as_dict=True,
	)
	for r in purchase_rows:
		b = bucket(r.item_code, r.item_name)
		b.purchase_qty += flt(r.qty)
		b.purchase_value += flt(r.value)

	# Consumption — raw material issued for production. In this business that flow
	# runs through Repack / Manufacture / Material Issue stock entries; only the pure
	# outgoing leg (s_warehouse set, t_warehouse empty) counts as consumption — a leg
	# with both set is an internal transfer, not material leaving the tracked stock.
	consumption_rows = frappe.db.sql(
		f"""
		SELECT
			child_tab.item_code, child_tab.item_name,
			SUM(child_tab.qty) AS qty,
			SUM(child_tab.basic_amount) AS value
		FROM `tabStock Entry Detail` child_tab
		INNER JOIN `tabStock Entry` se_parent ON se_parent.name = child_tab.parent
		WHERE se_parent.docstatus = 1
			AND se_parent.posting_date BETWEEN %(from_date)s AND %(to_date)s
			AND se_parent.purpose IN ('Repack', 'Manufacture', 'Material Issue', 'Material Consumption for Manufacture')
			AND child_tab.s_warehouse IS NOT NULL
			AND child_tab.t_warehouse IS NULL
			{company_condition("se_parent")}
		GROUP BY child_tab.item_code
	""",
		params,
		as_dict=True,
	)
	for r in consumption_rows:
		b = bucket(r.item_code, r.item_name)
		b.consumption_qty += flt(r.qty)
		b.consumption_value += flt(r.value)

	# Sales + COGS — COGS uses Sales Invoice Item's own incoming_rate, the same
	# valuation ERPNext itself books to the Cost of Goods Sold account on submit.
	sales_rows = frappe.db.sql(
		f"""
		SELECT
			sii.item_code, sii.item_name,
			SUM(sii.stock_qty) AS qty,
			SUM(sii.base_net_amount) AS revenue,
			SUM(sii.incoming_rate * sii.stock_qty) AS cogs
		FROM `tabSales Invoice Item` sii
		INNER JOIN `tabSales Invoice` si ON si.name = sii.parent
		WHERE si.docstatus = 1
			AND si.posting_date BETWEEN %(from_date)s AND %(to_date)s
			{company_condition("si")}
		GROUP BY sii.item_code
	""",
		params,
		as_dict=True,
	)
	for r in sales_rows:
		b = bucket(r.item_code, r.item_name)
		b.sales_qty += flt(r.qty)
		b.revenue += flt(r.revenue)
		b.cogs += flt(r.cogs)

	total_revenue = sum(flt(b.revenue) for b in items.values()) or 0

	data = []
	for b in items.values():
		b.gross_profit = b.revenue - b.cogs
		b.gross_profit_percent = (b.gross_profit / b.revenue * 100) if b.revenue else 0
		b.revenue_share_percent = (b.revenue / total_revenue * 100) if total_revenue else 0
		b.reconciliation_variance = (
			b.opening_value + b.purchase_value - b.consumption_value - b.cogs
		) - b.closing_value
		data.append(b)

	data.sort(key=lambda b: b.revenue, reverse=True)
	return data


def get_cost_reconciliation_summary(data):
	if not data:
		return None

	total_revenue = sum(flt(d.get("revenue")) for d in data)
	total_cogs = sum(flt(d.get("cogs")) for d in data)
	total_gross_profit = total_revenue - total_cogs
	total_variance = sum(flt(d.get("reconciliation_variance")) for d in data)

	return [
		{"label": _("Total Revenue"), "value": total_revenue, "indicator": "Blue", "datatype": "Currency"},
		{"label": _("Total COGS"), "value": total_cogs, "indicator": "Red", "datatype": "Currency"},
		{
			"label": _("Total Gross Profit"),
			"value": total_gross_profit,
			"indicator": "Green" if total_gross_profit >= 0 else "Red",
			"datatype": "Currency",
		},
		{
			"label": _("Reconciliation Variance"),
			"value": total_variance,
			"indicator": "Green" if abs(total_variance) < 1 else "Orange",
			"datatype": "Currency",
		},
	]
