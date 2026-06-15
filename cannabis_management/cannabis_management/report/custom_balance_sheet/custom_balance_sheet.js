// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt

frappe.query_reports["Custom Balance Sheet"] = $.extend({}, erpnext.financial_statements);

const base_formatter = frappe.query_reports["Custom Balance Sheet"].formatter;

frappe.query_reports["Custom Balance Sheet"].formatter = function(value, row, column, data, default_formatter, filter) {
	if (data && data.is_group == 1 && !String(data.account_name).includes("Total") && !String(data.account_name).includes("Profit / Loss")) {
		if (column.fieldtype === "Currency") {
			value = "";
			return value;
		}
	}
	if (base_formatter) {
		return base_formatter.call(this, value, row, column, data, default_formatter, filter);
	}
	return default_formatter(value, row, column, data);
};

erpnext.utils.add_dimensions("Custom Balance Sheet", 10);

frappe.query_reports["Custom Balance Sheet"]["filters"].push(
	{
		fieldname: "selected_view",
		label: __("Select View"),
		fieldtype: "Select",
		options: [
			{ value: "Report", label: __("Report View") },
			{ value: "Growth", label: __("Growth View") },
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
