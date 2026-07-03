// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["COA Exceptions"] = {
	filters: [
		{
			fieldname: "business_entity",
			label: __("Business Entity"),
			fieldtype: "Link",
			options: "Business Entity",
		},
		{
			fieldname: "product_category",
			label: __("Product Category"),
			fieldtype: "Select",
			options: "\nVape\nFlower\nConcentrate\nEdible\nOther",
		},
		{
			fieldname: "result_status",
			label: __("Result Status"),
			fieldtype: "Select",
			options: "\nFail\nPending\nRetest",
			description: __("Leave blank for Fail + Pending"),
		},
		{
			fieldname: "from_date",
			label: __("Sample Date From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Sample Date To"),
			fieldtype: "Date",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "result_status" && data) {
			const color = data.result_status === "Fail" ? "var(--red-600)" : "var(--orange-600)";
			value = `<span style="color:${color};font-weight:600">${value}</span>`;
		}
		return value;
	},
};
