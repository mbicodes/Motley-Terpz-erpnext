// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Stock Valuation Lineage"] = {
	filters: [
		{
			fieldname: "from_date",
			label: __("From Date (Sale)"),
			fieldtype: "Date",
			default: frappe.datetime.add_months(frappe.datetime.get_today(), -1),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date (Sale)"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "sales_document_type",
			label: __("Sold Through"),
			fieldtype: "Select",
			options: ["Both", "Sales Invoice", "Delivery Note"].join("\n"),
			default: "Both",
		},
		cannabis.reports.company_filter(),
		{
			fieldname: "item_code",
			label: __("Item"),
			fieldtype: "Link",
			options: "Item",
		},
		{
			fieldname: "warehouse",
			label: __("Warehouse (Sold From)"),
			fieldtype: "Link",
			options: "Warehouse",
		},
		{
			fieldname: "customer",
			label: __("Customer"),
			fieldtype: "Link",
			options: "Customer",
		},
		{
			fieldname: "voucher_no",
			label: __("Specific Sales Document"),
			fieldtype: "Data",
		},
		{
			fieldname: "max_depth",
			label: __("Max Trace Depth"),
			fieldtype: "Int",
			default: 15,
		},
		{
			fieldname: "row_limit",
			label: __("Row Limit"),
			fieldtype: "Int",
			default: 5000,
		},
	],

	// Colour-code each phase and indent visually so the back-trace reads as a tree.
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "phase" && data) {
			let colour = "#6c7680";
			if ((data.phase || "").startsWith(__("Sold"))) colour = "#c0392b";
			else if ((data.phase || "").indexOf("Produced") !== -1) colour = "#8e44ad";
			else if ((data.phase || "").indexOf("Consumed") !== -1) colour = "#d35400";
			else if ((data.phase || "").indexOf("Purchased") !== -1) colour = "#27ae60";
			else if ((data.phase || "").indexOf("Transferred") !== -1) colour = "#2980b9";
			else if ((data.phase || "").indexOf("Origin") !== -1) colour = "#27ae60";
			value = `<span style="color:${colour};font-weight:600">${value}</span>`;
		}
		return value;
	},

	onload: function (report) {
		report.page.add_inner_message(
			__("Each top row is a sold stock line. Expand it to walk backward through every phase the stock passed through, with the valuation rate and source document at each phase. A branch stops when no earlier producing/receiving event exists. Note: this site has no batch tracking, so lineage is reconstructed by item + warehouse via the most recent producing event on the ledger.")
		);
	},
};
