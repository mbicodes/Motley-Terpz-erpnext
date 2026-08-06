// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["TSBC Ranch Income Statement"] = {
	filters: [
		{
			fieldname: "company",
			label: __("Company"),
			fieldtype: "Link",
			options: "Company",
			default: "TSBC Ranch",
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
	],

	// Mirrors the draft statement's own look: section headings and the
	// Gross Profit / Operating Income rows get a light banded background,
	// totals are bold, margin-% rows are italic and greyed, and the final
	// Net Income row gets the same dark "bar" treatment as the source
	// document - all driven off flags the .py sets per row (section/banner/
	// bold/italic/highlight), not by column position.
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (!data) return value;

		if (column.fieldname === "amount") {
			value = `<div style="text-align:right">${value ?? ""}</div>`;
		}

		if (data.section || data.banner) {
			value = `<div style="background-color:var(--bg-light-gray, #f0f2f5); padding:2px 4px;">${value}</div>`;
		}

		if (data.highlight) {
			value = `<div style="background-color:#1a2b4c; color:#fff; padding:4px; font-weight:bold;">${value}</div>`;
		} else if (data.bold) {
			value = `<span style="font-weight:bold;">${value}</span>`;
		} else if (data.italic) {
			value = `<span style="font-style:italic; color:var(--text-muted, #888);">${value}</span>`;
		}

		return value;
	},
};
