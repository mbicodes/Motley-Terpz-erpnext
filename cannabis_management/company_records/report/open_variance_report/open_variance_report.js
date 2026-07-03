// Copyright (c) 2026, alltechvirtual.com and contributors
// For license information, please see license.txt

frappe.query_reports["Open Variance Report"] = {
	filters: [
		{
			fieldname: "business_entity",
			label: __("Business Entity"),
			fieldtype: "Link",
			options: "Business Entity",
		},
		{
			fieldname: "reconciliation_type",
			label: __("Reconciliation Type"),
			fieldtype: "Select",
			options: "\nAR Trailing\nAP Trailing\nInventory vs Metrc\nClient Reconciliation\nBank Recon\nIntercompany",
		},
		{
			fieldname: "status",
			label: __("Status"),
			fieldtype: "Select",
			options: "\nDraft\nUnder Review\nApproved",
			description: __("Locked reconciliations are always excluded"),
		},
		{
			fieldname: "from_date",
			label: __("Period End From"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("Period End To"),
			fieldtype: "Date",
		},
		{
			fieldname: "only_with_variance",
			label: __("Only Non-Zero Variance"),
			fieldtype: "Check",
			default: 0,
		},
	],
	formatter: function (value, row, column, data, default_formatter) {
		value = default_formatter(value, row, column, data);
		if (column.fieldname === "variance" && data && flt(data.variance) !== 0) {
			value = `<span style="color:var(--red-600);font-weight:600">${value}</span>`;
		}
		if (column.fieldname === "days_open" && data && cint(data.days_open) > 30) {
			value = `<span style="color:var(--orange-600);font-weight:600">${value}</span>`;
		}
		return value;
	},
};
