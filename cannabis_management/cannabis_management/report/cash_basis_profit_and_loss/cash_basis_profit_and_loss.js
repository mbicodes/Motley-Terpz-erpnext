// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

// Cash Basis Profit and Loss: the Profit and Loss Statement's filters and
// layout, over Bank and Cash GL entries grouped by their Against value
// (see cash_basis_profit_and_loss.py).
(function () {
	const REPORT = "Cash Basis Profit and Loss";

	// Deep copy: erpnext.financial_statements.filters is one shared array, and
	// the P&L / Balance Sheet push their own filters into it.
	const report = $.extend(true, {}, erpnext.financial_statements);
	const ours = ["selected_view", "accumulated_values", "include_default_book_entries", "show_zero_values"];
	report.filters = (erpnext.financial_statements.filters || [])
		.filter((f) => ours.indexOf(f.fieldname) === -1)
		.map((f) => $.extend(true, {}, f));

	// A row's ledger: an account's General Ledger, or the General Ledger for a
	// customer / supplier / employee. Rows for several accounts at once have none.
	report.open_general_ledger = function (data) {
		if (!data || !(data.is_ledger_account || data.party)) return;
		const qr = frappe.query_report;
		frappe.route_options = {
			company: qr.get_filter_value("company"),
			from_date: data.year_start_date,
			to_date: data.year_end_date,
		};
		if (data.is_ledger_account) {
			frappe.route_options.account = [data.account];
		} else {
			frappe.route_options.party_type = data.party_type;
			frappe.route_options.party = [data.party];
		}
		const project = qr.get_filter_value("project");
		const cost_center = qr.get_filter_value("cost_center");
		if (project && project.length) frappe.route_options.project = project;
		if (cost_center && cost_center.length) frappe.route_options.cost_center = cost_center;
		frappe.set_route("query-report", "General Ledger");
	};

	// The money columns use the shared formatter (Growth / Margin views, bold
	// totals). The Account column is drawn here: its values are Against values,
	// often a party or several accounts, so it must not link to an Account
	// record, and a click opens this report's own open_general_ledger.
	const base_formatter = report.formatter;
	report.formatter = function (value, row, column, data, default_formatter, filter) {
		if (!data || column.fieldname !== "account") {
			return base_formatter.call(this, value, row, column, data, default_formatter, filter);
		}
		column.is_tree = true;
		const label = data.account_name || value;
		const has_ledger = data.is_ledger_account || data.party;
		const col = $.extend({}, column, {
			fieldtype: has_ledger ? "Link" : "Data",
			link_onclick: has_ledger
				? `frappe.query_reports['${REPORT}'].open_general_ledger(${JSON.stringify({
					account: data.account, is_ledger_account: data.is_ledger_account,
					party_type: data.party_type, party: data.party,
					year_start_date: data.year_start_date, year_end_date: data.year_end_date,
				})})`
				: null,
		});
		let out = default_formatter(label, row, col, data);
		if (!data.parent_account) {
			const $v = $(`<span>${out}</span>`).css("font-weight", "bold");
			out = $v.wrap("<p></p>").parent().html();
		}
		return out;
	};

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
