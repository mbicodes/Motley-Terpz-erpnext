// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Onboarding Completion"] = {
	filters: [
		{
			fieldname: "business_entity",
			label: __("Business Entity"),
			fieldtype: "Link",
			options: "Business Entity",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nReceived\nUnder Review\nComplete\nIncomplete",
			description: __("Leave blank for everything not yet Complete"),
		},
		{
			fieldname: "min_days_open",
			label: __("Open At Least (Days)"),
			fieldtype: "Int",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_open" && data && cint(data.days_open) > 30) {
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
