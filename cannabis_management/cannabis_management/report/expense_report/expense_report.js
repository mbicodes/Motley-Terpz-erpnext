// Copyright (c) 2015, Frappe Technologies Pvt. Ltd. and Contributors
// License: GNU General Public License v3. See license.txt
//
// Same filter bar and period handling as the TSBC Expense Report - this is
// erpnext's financial_statements client script, reused unchanged.

frappe.query_reports["Expense Report"] = $.extend({}, erpnext.financial_statements, {
	formatter: function (value, row, column, data, default_formatter, filter) {
		// Voucher rows: the voucher number opens the Purchase Invoice / Journal Entry.
		if (data && data.voucher_no && column.fieldname === "expense_category") {
			return `<a href="${frappe.utils.get_form_link(data.voucher_type, data.voucher_no)}">${frappe.utils.escape_html(data.voucher_no)}</a>`;
		}
		return erpnext.financial_statements.formatter.call(
			this, value, row, column, data, default_formatter, filter
		);
	},

	// Re-apply the Expand / Collapse filter whenever the report reloads.
	after_datatable_render: function () {
		apply_tree_view(frappe.query_report);
	},
});

function apply_tree_view(report) {
	if (!report || !report.datatable) return;
	if (report.get_filter_value("tree_view") === "Collapse All") {
		report.collapse_all_rows();
	} else {
		report.expand_all_rows();
	}
}

erpnext.utils.add_dimensions("Expense Report", 10);

frappe.query_reports["Expense Report"]["filters"].push(
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
	},
	{
		fieldname: "tree_view",
		label: __("Expand / Collapse"),
		fieldtype: "Select",
		options: [
			{ value: "Expand All", label: __("Expand All") },
			{ value: "Collapse All", label: __("Collapse All") },
		],
		default: "Expand All",
		// Only opens or folds the rows already on screen; the report does not reload.
		on_change: function (report) {
			apply_tree_view(report);
		},
	}
);
