// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

// Same filter set as the standard "Profit and Loss Statement" (company,
// Fiscal Year/Date Range toggle, periodicity, presentation currency, cost
// center, project, ...) plus the same extra filters the other financial
// statements in this app add on top - works for any company, no
// company-specific default.
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

// Same tree-view/bold-totals/Growth-Margin formatting as every other
// financial statement in this app - plus one addition: the final Net
// Income row gets the same dark "total bar" treatment a printed income
// statement gives its bottom line, so it reads as the answer to the whole
// report rather than just another bold row.
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
