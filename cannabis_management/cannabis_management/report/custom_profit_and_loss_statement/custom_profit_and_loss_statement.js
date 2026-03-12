// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Custom Profit and Loss Statement"] = $.extend({}, erpnext.financial_statements);

const pnl_base_formatter = frappe.query_reports["Custom Profit and Loss Statement"].formatter;

frappe.query_reports["Custom Profit and Loss Statement"].formatter = function(value, row, column, data, default_formatter, filter) {
	if (data && data.is_group == 1 && !String(data.account_name).includes("Total") && !String(data.account_name).includes("Profit / Loss") && !String(data.account_name).includes("Profit for the year")) {
		if (column.fieldtype === "Currency") {
			value = "";
			return value;
		}
	}
	if (pnl_base_formatter) {
		return pnl_base_formatter.call(this, value, row, column, data, default_formatter, filter);
	}
	return default_formatter(value, row, column, data);
};

erpnext.utils.add_dimensions("Custom Profit and Loss Statement", 10);

frappe.query_reports["Custom Profit and Loss Statement"]["filters"].push(
	{
		fieldname: "selected_view",
		label: __("Select View"),
		fieldtype: "Select",
		options: [
			{ value: "Report", label: __("Report View") },
			{ value: "Growth", label: __("Growth View") },
			{ value: "Margin", label: __("Margin View") },
		],
		default: "Report",
		reqd: 1,
	},
	{
		fieldname: "accumulated_values",
		label: __("Accumulated Values"),
		fieldtype: "Check",
		default: 1,
	},
	{
		fieldname: "include_default_book_entries",
		label: __("Include Default FB Entries"),
		fieldtype: "Check",
		default: 1,
	},
	{
		fieldname: "show_zero_values",
		label: __("Show zero values"),
		fieldtype: "Check",
	}
);
