// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

// Cash Basis Profit and Loss: set up exactly like the Profit and Loss Statement
// (profit_and_loss_statement.js); only the entries behind it differ.
(function () {
	const REPORT = "Cash Basis Profit and Loss";

	// Deep copy: erpnext.financial_statements.filters is one shared array that the
	// P&L and Balance Sheet push their own filters into, so take the base filters
	// without any of those and add this report's set below.
	const report = $.extend(true, {}, erpnext.financial_statements);
	const ours = ["selected_view", "accumulated_values", "include_default_book_entries", "show_zero_values"];
	report.filters = (erpnext.financial_statements.filters || [])
		.filter((f) => ours.indexOf(f.fieldname) === -1)
		.map((f) => $.extend(true, {}, f));
	frappe.query_reports[REPORT] = report;

	erpnext.utils.add_dimensions(REPORT, 10);

	report.filters.push(
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
})();
