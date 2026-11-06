// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Cash Basis Transaction Review"] = {
	filters: [
		{
			fieldname: "view",
			label: __("View"),
			fieldtype: "Select",
			options: ["Transactions", "Reconciliation by Cash Account"].join("\n"),
			default: "Transactions",
			reqd: 1,
		},
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Select",
			options: ["", "TSBC Ranch", "Motley Terpz", "Master Touch Manufacturing"].join("\n"),
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
			default: frappe.datetime.year_start(),
			reqd: 1,
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
			default: frappe.datetime.get_today(),
			reqd: 1,
		},
		{
			fieldname: "cash_account",
			label: __("Bank / Cash Account"),
			fieldtype: "Link",
			options: "Account",
			get_query: () => ({
				filters: { account_type: ["in", ["Bank", "Cash"]], is_group: 0 },
			}),
		},
		{
			fieldname: "classification",
			label: __("Classification"),
			fieldtype: "Select",
			options: ["", "P&L", "Balance Sheet", "Intercompany", "Bank / Cash transfer", "Unclassified - review"].join(
				"\n"
			),
		},
		{
			fieldname: "review_only",
			label: __("Only items needing review"),
			fieldtype: "Check",
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const colours = {
			"P&L": "#2e7d32",
			"Balance Sheet": "#1f4e79",
			Intercompany: "#8e24aa",
			"Bank / Cash transfer": "#616161",
			"Unclassified - review": "#c62828",
		};
		if (column.fieldname === "classification" && colours[data.classification]) {
			value = `<span style="color:${colours[data.classification]};font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "difference" && Math.abs(data.difference || 0) >= 0.01) {
			value = `<span style="color:#c62828;font-weight:600">${value}</span>`;
		}
		if (data.bold) value = `<b>${value}</b>`;
		return value;
	},
};
