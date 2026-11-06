// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

(function () {
	const REPORT = "Cash Basis Profit and Loss Statement";
	const this_month = frappe.datetime.month_start();

	frappe.query_reports[REPORT] = {
		filters: [
			{
				fieldname: "company",
				label: __("Company"),
				fieldtype: "Select",
				options: ["Consolidated", "TSBC Ranch", "Motley Terpz", "Master Touch Manufacturing"].join("\n"),
				default: "Consolidated",
				reqd: 1,
			},
			{
				fieldname: "from_date",
				label: __("From Date"),
				fieldtype: "Date",
				default: frappe.datetime.add_months(this_month, -1),
				reqd: 1,
			},
			{
				fieldname: "to_date",
				label: __("To Date"),
				fieldtype: "Date",
				default: frappe.datetime.add_days(this_month, -1),
				reqd: 1,
			},
			{
				fieldname: "periodicity",
				label: __("Columns"),
				fieldtype: "Select",
				options: [
					{ value: "Total", label: __("Total (one per company when consolidated)") },
					{ value: "Monthly", label: __("Monthly") },
					{ value: "Quarterly", label: __("Quarterly") },
				],
				default: "Total",
				reqd: 1,
			},
			{
				fieldname: "show_reconciliation",
				label: __("Show reconciliation to Bank / Cash"),
				fieldtype: "Check",
				default: 0,
			},
		],

		tree: true,
		name_field: "account",
		parent_field: "parent_account",
		initial_depth: 2,

		formatter(value, row, column, data, default_formatter) {
			if (!data) return default_formatter(value, row, column, data);
			const colours = {
				section: "#1f4e79",
				total: "#1f4e79",
				profit: "#2e7d32",
				net: "#2e7d32",
				unclassified: "#c62828",
				check: "#6a1b9a",
			};
			if (column.fieldname === "account") {
				column.is_tree = true;
				const label = frappe.utils.escape_html(data.account_name || value || "");
				if (data.head) {
					const arg = encodeURIComponent(data.head).replace(/'/g, "%27");
					value = `<a onclick="frappe.query_reports['${REPORT}'].open_transactions(decodeURIComponent('${arg}'))">${label}</a>`;
				} else {
					value = label;
				}
			} else {
				value = default_formatter(value, row, column, data);
				if (data.kind === "net" || data.kind === "profit") {
					if (data[column.fieldname] < 0) value = `<span class="text-danger">${value}</span>`;
				}
			}
			if (data.bold) value = `<b>${value}</b>`;
			if (colours[data.kind]) value = `<span style="color:${colours[data.kind]}">${value}</span>`;
			return value;
		},

		// The movements behind a head, in the Cash Basis Transaction Review.
		open_transactions(head) {
			const q = frappe.query_report;
			frappe.route_options = {
				view: "Transactions",
				classification: "P&L",
				head: head,
				from_date: q.get_filter_value("from_date"),
				to_date: q.get_filter_value("to_date"),
			};
			frappe.set_route("query-report", "Cash Basis Transaction Review");
		},
	};
})();
