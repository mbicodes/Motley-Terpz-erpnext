// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Contract and Agreement Expiry"] = {
	filters: [
		{
			fieldname: "expiring_within",
			label: __("Expiring Within (Days)"),
			fieldtype: "Select",
			options: "30\n60\n90\n180\n365",
			default: "90",
		},
		{
			fieldname: "business_entity",
			label: __("Business Entity"),
			fieldtype: "Link",
			options: "Business Entity",
		},
		{
			fieldname: "contract_type",
			label: __("Contract Type"),
			fieldtype: "Select",
			options: "\nClient\nVendor\nStaffing\nOther",
			description: __("Setting this hides Tolling Agreements"),
		},
		{
			fieldname: "include_tolling",
			label: __("Include Tolling Agreements"),
			fieldtype: "Check",
			default: 1,
		},
		{
			fieldname: "include_expired",
			label: __("Include Already Expired"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "days_to_expiry" && data) {
			const days = cint(data.days_to_expiry);
			if (days < 0) {
				value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
			} else if (days <= 30) {
				value = `<span style="color:var(--orange-600);font-weight:600">${value}</span>`;
			}
		}
		return value;
	},
};
