// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Reconciled Cash Basis Profit and Loss"] = {
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
			fieldname: "periodicity",
			label: __("Columns"),
			fieldtype: "Select",
			options: [
				{ value: "Total", label: __("Total (per company when consolidated)") },
				{ value: "Monthly", label: __("Monthly") },
				{ value: "Quarterly", label: __("Quarterly") },
			],
			default: "Total",
			reqd: 1,
		},
	],

	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;
		const colours = {
			section: "#1f4e79",
			total: "#1f4e79",
			profit: "#2e7d32",
			net: "#2e7d32",
			unclassified: "#c62828",
			check: "#6a1b9a",
		};
		if (column.fieldname === "account") {
			const pad = (data.indent || 0) * 18;
			value = `<span style="padding-left:${pad}px">${value}</span>`;
		}
		if (data.bold) value = `<b>${value}</b>`;
		if (colours[data.kind]) value = `<span style="color:${colours[data.kind]}">${value}</span>`;
		return value;
	},
};
