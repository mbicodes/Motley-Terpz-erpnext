frappe.query_reports["Income Statement"] = $.extend({}, erpnext.financial_statements);

erpnext.utils.add_dimensions("Income Statement", 10);

frappe.query_reports["Income Statement"]["filters"].push(
	{
		fieldname: "selected_view",
		label: __("Select View"),
		fieldtype: "Select",
		options: [
			{ value: "Report", label: __("Report View") },
			{ value: "Growth", label: __("Growth View") },
			{ value: "Margin", label: __("Percentage View (% of Income)") },
		],
		default: "Report",
		reqd: 1,
	},
	{
		fieldname: "accumulated_values",
		label: __("Accumulated Values"),
		fieldtype: "Check",
		default: 0,
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

frappe.query_reports["Income Statement"].formatter = function (
	value,
	row,
	column,
	data,
	default_formatter,
	filter
) {
	value = erpnext.financial_statements.formatter.call(
		this,
		value,
		row,
		column,
		data,
		default_formatter,
		filter
	);

	if (data && data.is_net_income_row) {
		value = $(
			`<div style="background-color:#1a2b4c; color:#fff; font-weight:bold; padding:4px 6px; margin:-4px -6px;">${value}</div>`
		).prop("outerHTML");
	}

	return value;
};
