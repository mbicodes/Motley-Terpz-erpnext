// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Active Holds by Age"] = {
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
			options: "Active Hold\nFulfilled\nExpired\nCancelled",
			default: "Active Hold",
		},
		{
			fieldname: "min_days_held",
			label: __("Held At Least (Days)"),
			fieldtype: "Int",
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_held" && data && cint(data.days_held) > 90) {
			value = `<span style="color:var(--red-600);font-weight:600">${value} ⚠</span>`;
		}
		return value;
	},
};
