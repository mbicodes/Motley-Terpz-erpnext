frappe.query_reports["Expense Report"] = $.extend({}, erpnext.financial_statements, {
	formatter: function (value, row, column, data, default_formatter, filter) {
		if (data && data.voucher_no && column.fieldname === "expense_category") {
			return `<a href="${frappe.utils.get_form_link(data.voucher_type, data.voucher_no)}">${frappe.utils.escape_html(data.voucher_no)}</a>`;
		}
		return erpnext.financial_statements.formatter.call(
			this, value, row, column, data, default_formatter, filter
		);
	},

	after_datatable_render: function () {
		apply_tree_view(frappe.query_report);
	},
});

frappe.query_reports["Expense Report"].filters = expense_report_base_filters();

function expense_report_base_filters() {
	const own = [
		"cost_center", "project", "selected_view", "accumulated_values",
		"include_default_book_entries", "show_zero_values", "tree_view",
	];
	const seen = {};
	const base = (erpnext.financial_statements.filters || [])
		.filter((f) => {
			if (!f || own.includes(f.fieldname) || seen[f.fieldname]) return false;
			seen[f.fieldname] = true;
			return true;
		})
		.map((f) => $.extend(true, {}, f));

	const link_filter = (fieldname, label, doctype) => ({
		fieldname: fieldname,
		label: label,
		placeholder: label,
		fieldtype: "MultiSelectList",
		options: doctype,
		get_data: function (txt) {
			return frappe.db.get_link_options(doctype, txt, {
				company: frappe.query_report.get_filter_value("company"),
			});
		},
	});

	let at = base.findIndex((f) => f.fieldname === "periodicity") + 1;
	if (!at) at = base.length;
	base.splice(
		at,
		0,
		link_filter("cost_center", "Cost Center", "Cost Center"),
		link_filter("project", "Project", "Project")
	);
	return base;
}

function apply_tree_view(report) {
	if (!report || !report.datatable) return;
	if (report.get_filter_value("tree_view") === "Collapse All") {
		report.collapse_all_rows();
	} else {
		report.expand_all_rows();
	}
}

frappe.call({
	method: "erpnext.accounts.doctype.accounting_dimension.accounting_dimension.get_dimensions",
	callback: function (r) {
		const filters = frappe.query_reports["Expense Report"].filters;
		((r.message && r.message[0]) || []).forEach((dimension) => {
			const existing = filters.findIndex((f) => f.fieldname === dimension.fieldname);
			const df =
				existing === -1
					? {
							fieldname: dimension.fieldname,
							label: __(dimension.label),
							fieldtype: "MultiSelectList",
							get_data: function (txt) {
								return frappe.db.get_link_options(dimension.document_type, txt);
							},
					  }
					: filters.splice(existing, 1)[0];
			const at = filters.findIndex((f) => f.fieldname === "cost_center");
			filters.splice(at === -1 ? filters.length : at, 0, df);
		});
	},
});

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
		on_change: function (report) {
			apply_tree_view(report);
		},
	}
);
