// Copyright (c) 2026, alltechvirtual.com and contributors
frappe.query_reports["Metrc Variance"] = {
	filters: [
		{
			fieldname: "license_number",
			label: __("METRC License #"),
			fieldtype: "Data",
		},
		{
			fieldname: "min_difference",
			label: __("Min Absolute Difference"),
			fieldtype: "Float",
			default: 0.01,
		},
	],
	formatter(value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "difference" && data && data.difference) {
			const color = data.difference > 0 ? "var(--orange-600)" : "var(--red-600)";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
